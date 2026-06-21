import logging
from typing import Dict, List, Optional

from .models import OHT, OHTStatus, Lot, LotStatus, FailoverEvent
from .graph import FabGraph

logger = logging.getLogger("amhs.scheduler")

TRANSIT_TICKS_PER_UNIT = 1   # 거리 1 단위 = 1 tick


def _transit_ticks(distance: float) -> int:
    """거리 → 이동 tick 수 (최소 1)."""
    return max(1, int(round(distance * TRANSIT_TICKS_PER_UNIT)))


class Scheduler:
    """
    Nearest OHT Scheduling + Failover 담당.

    Transport 완료 시 lot.status = PROCESSING, lot.processing_ticks_remaining = -1 로 설정.
    Simulator가 -1 를 감지해 공정 처리 시간을 세팅한다.
    """

    def __init__(self, graph: FabGraph, ohts: Dict[str, OHT], failover_prob: float = 0.12):
        self.graph = graph
        self.ohts = ohts
        self.failover_prob = failover_prob
        self.failover_events: List[FailoverEvent] = []
        self._pending_queue: List[dict] = []

    # ------------------------------------------------------------------ #
    #  OHT 선택 (Nearest Idle)                                            #
    # ------------------------------------------------------------------ #

    def nearest_idle_oht(self, from_node: str) -> Optional[OHT]:
        best: Optional[OHT] = None
        best_dist = float("inf")

        for oht in self.ohts.values():
            if oht.status != OHTStatus.IDLE:
                continue
            d = self.graph.distance(oht.position, from_node)
            if d < best_dist or (d == best_dist and (best is None or oht.oht_id < best.oht_id)):
                best_dist = d
                best = oht

        return best

    # ------------------------------------------------------------------ #
    #  작업 할당                                                           #
    # ------------------------------------------------------------------ #

    def assign_transport(self, lot: Lot, from_node: str, to_node: str, tick: int) -> bool:
        """
        Nearest Idle OHT에 LOT 운송 할당.
        Idle OHT 없으면 pending 큐에 추가 후 False 반환.
        """
        oht = self.nearest_idle_oht(from_node)
        if oht is None:
            already = any(t["lot_id"] == lot.lot_id for t in self._pending_queue)
            if not already:
                self._pending_queue.append(
                    {"lot_id": lot.lot_id, "from_node": from_node, "to_node": to_node}
                )
                logger.info(
                    "[tick=%d] No idle OHT for %s (%s->%s). Queued.",
                    tick, lot.lot_id, from_node, to_node,
                )
            return False

        self._do_assign(oht, lot, from_node, to_node, tick)
        return True

    def _do_assign(self, oht: OHT, lot: Lot, from_node: str, to_node: str, tick: int):
        dist_to_lot = self.graph.distance(oht.position, from_node)
        dist_transit = self.graph.distance(from_node, to_node)
        total_dist = dist_to_lot + dist_transit
        ticks_needed = _transit_ticks(total_dist)

        oht.status = OHTStatus.BUSY
        oht.current_lot = lot.lot_id
        oht.current_task = {
            "lot_id":          lot.lot_id,
            "from_node":       from_node,
            "to_node":         to_node,
            "ticks_remaining": ticks_needed,
            "distance":        total_dist,
        }

        lot.status = LotStatus.IN_TRANSIT
        lot.assigned_oht = oht.oht_id

        logger.info(
            "[tick=%d] ASSIGN %s -> %s | %s->%s | dist=%.1f | ticks=%d",
            tick, oht.oht_id, lot.lot_id, from_node, to_node, total_dist, ticks_needed,
        )

    # ------------------------------------------------------------------ #
    #  Tick 업데이트                                                       #
    # ------------------------------------------------------------------ #

    def tick(self, lots: Dict[str, Lot], current_tick: int, rng) -> List[FailoverEvent]:
        """1 tick 전진. Failover 이벤트 목록 반환."""
        new_events: List[FailoverEvent] = []

        for oht in list(self.ohts.values()):
            if oht.status != OHTStatus.BUSY or oht.current_task is None:
                continue

            task = oht.current_task

            # Failover 판정
            if rng.random() < self.failover_prob:
                ev = self._handle_failover(oht, lots, current_tick)
                new_events.append(ev)
                self.failover_events.append(ev)
                continue

            # 정상 진행
            task["ticks_remaining"] -= 1

            if task["ticks_remaining"] <= 0:
                self._complete_transport(oht, lots[task["lot_id"]], task, current_tick)

        # Pending 재시도
        self._retry_pending(lots, current_tick)
        return new_events

    def _complete_transport(self, oht: OHT, lot: Lot, task: dict, tick: int):
        oht.total_distance += task["distance"]
        oht.task_count += 1
        oht.position = task["to_node"]
        oht.status = OHTStatus.IDLE
        oht.current_lot = None
        oht.current_task = None

        lot.current_position = task["to_node"]
        lot.assigned_oht = None
        # sentinel -1: simulator가 감지해 공정 시간을 세팅
        lot.status = LotStatus.PROCESSING
        lot.processing_ticks_remaining = -1

        logger.info(
            "[tick=%d] DELIVERED %s -> %s (arrived %s)",
            tick, oht.oht_id, lot.lot_id, task["to_node"],
        )

    # ------------------------------------------------------------------ #
    #  Failover                                                            #
    # ------------------------------------------------------------------ #

    def _handle_failover(self, oht: OHT, lots: Dict[str, Lot], tick: int) -> FailoverEvent:
        task = oht.current_task
        lot = lots[task["lot_id"]]

        logger.warning(
            "[tick=%d] !! FAILOVER !! %s error while moving %s (%s->%s)",
            tick, oht.oht_id, lot.lot_id, task["from_node"], task["to_node"],
        )

        ev = FailoverEvent(
            tick=tick,
            oht_id=oht.oht_id,
            lot_id=lot.lot_id,
            from_node=task["from_node"],
            to_node=task["to_node"],
        )

        # OHT: Error → 즉시 Idle 복구 (단순화)
        oht.status = OHTStatus.IDLE
        oht.current_lot = None
        oht.current_task = None

        # LOT: 출발지에서 재대기
        lot.status = LotStatus.WAITING
        lot.assigned_oht = None

        # 재할당 시도
        alt = self.nearest_idle_oht(task["from_node"])
        if alt:
            self._do_assign(alt, lot, task["from_node"], task["to_node"], tick)
            ev.reassigned_oht = alt.oht_id
            logger.info("[tick=%d] REASSIGN %s -> %s", tick, alt.oht_id, lot.lot_id)
        else:
            self._pending_queue.append(
                {"lot_id": lot.lot_id, "from_node": task["from_node"], "to_node": task["to_node"]}
            )
            logger.warning("[tick=%d] No idle OHT for reassignment. Queued.", tick)

        return ev

    def _retry_pending(self, lots: Dict[str, Lot], tick: int):
        remaining = []
        for task in self._pending_queue:
            lot = lots.get(task["lot_id"])
            if lot is None or lot.status != LotStatus.WAITING:
                continue
            oht = self.nearest_idle_oht(task["from_node"])
            if oht:
                self._do_assign(oht, lot, task["from_node"], task["to_node"], tick)
            else:
                remaining.append(task)
        self._pending_queue = remaining
