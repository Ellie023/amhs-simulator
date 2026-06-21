import logging
import random
from typing import Dict, List

from .models import (
    Equipment, OHT, Lot, LotStatus,
    EQUIPMENT_PROCESS, PROCESS_SEQUENCE, PROCESS_DURATION,
)
from .graph import FabGraph
from .scheduler import Scheduler

logger = logging.getLogger("amhs.simulator")


class AMHSSimulator:
    def __init__(self, seed: int = 42, failover_prob: float = 0.12, max_ticks: int = 300):
        self.seed = seed
        self.max_ticks = max_ticks
        self.rng = random.Random(seed)
        self.tick_count = 0

        self.graph = FabGraph()

        self.equipments: Dict[str, Equipment] = {
            eid: Equipment(equip_id=eid, process=proc, position=eid)
            for eid, proc in EQUIPMENT_PROCESS.items()
        }

        self.ohts: Dict[str, OHT] = {
            "OHT-01": OHT("OHT-01", position="LOAD_PORT"),
            "OHT-02": OHT("OHT-02", position="BUFFER_A"),
            "OHT-03": OHT("OHT-03", position="BUFFER_B"),
        }

        self.lots: Dict[str, Lot] = {
            "LOT-1001": Lot("LOT-1001", start_tick=0),
            "LOT-1002": Lot("LOT-1002", start_tick=0),
            "LOT-1003": Lot("LOT-1003", start_tick=0),
        }

        self.scheduler = Scheduler(self.graph, self.ohts, failover_prob=failover_prob)

        # LOT별 공정 → 설비 배정 (분산 처리)
        equip_by_proc: Dict[str, List[str]] = {}
        for eid, proc in EQUIPMENT_PROCESS.items():
            equip_by_proc.setdefault(proc, []).append(eid)

        lot_ids = list(self.lots.keys())
        self._equip_assignment: Dict[str, Dict[str, str]] = {}
        for proc in PROCESS_SEQUENCE:
            pool = sorted(equip_by_proc[proc])
            for i, lot_id in enumerate(lot_ids):
                self._equip_assignment.setdefault(lot_id, {})[proc] = pool[i % len(pool)]

    # ------------------------------------------------------------------ #
    #  메인 루프                                                           #
    # ------------------------------------------------------------------ #

    def run(self):
        logger.info("=" * 60)
        logger.info("AMHS Simulator START  seed=%d  failover_prob=%.0f%%",
                    self.seed, self.scheduler.failover_prob * 100)
        logger.info("=" * 60)
        self.graph.print_graph()
        self._print_equip_assignment()

        # 초기 운송 요청
        for lot in self.lots.values():
            self._request_transport(lot)

        while self.tick_count < self.max_ticks:
            self.tick_count += 1
            logger.debug("--- Tick %d ---", self.tick_count)

            # 1) OHT 이동 및 Failover 처리
            self.scheduler.tick(self.lots, self.tick_count, self.rng)

            # 2) 방금 도착한 LOT 공정 시작 (sentinel -1 감지)
            self._start_processing_arrived_lots()

            # 3) 공정 진행
            self._tick_processing_lots()

            # 4) 종료 조건
            if all(lot.is_complete for lot in self.lots.values()):
                logger.info("[tick=%d] All LOTs completed!", self.tick_count)
                break
        else:
            logger.warning("Simulation reached max_ticks=%d without full completion.", self.max_ticks)

        self._print_results()

    # ------------------------------------------------------------------ #
    #  LOT 상태 처리                                                       #
    # ------------------------------------------------------------------ #

    def _start_processing_arrived_lots(self):
        """scheduler가 sentinel -1로 표시한 도착 LOT의 공정 처리 시간 세팅."""
        for lot in self.lots.values():
            if lot.status == LotStatus.PROCESSING and lot.processing_ticks_remaining == -1:
                proc = PROCESS_SEQUENCE[lot.process_index]
                lot.processing_ticks_remaining = PROCESS_DURATION[proc]
                logger.info(
                    "[tick=%d] START processing %s at %s (%s, %d ticks)",
                    self.tick_count, lot.lot_id, lot.current_position,
                    proc, lot.processing_ticks_remaining,
                )

    def _tick_processing_lots(self):
        """공정 중인 LOT 1 tick 진행."""
        for lot in self.lots.values():
            if lot.status == LotStatus.WAITING:
                lot.wait_ticks += 1

            elif lot.status == LotStatus.PROCESSING and lot.processing_ticks_remaining > 0:
                lot.processing_ticks_remaining -= 1
                if lot.processing_ticks_remaining == 0:
                    self._finish_processing(lot)

    def _finish_processing(self, lot: Lot):
        completed_proc = PROCESS_SEQUENCE[lot.process_index]
        logger.info(
            "[tick=%d] FINISH %s at %s (process=%s)",
            self.tick_count, lot.lot_id, lot.current_position, completed_proc,
        )
        lot.process_index += 1

        if lot.is_complete:
            lot.status = LotStatus.DONE
            lot.end_tick = self.tick_count
            logger.info("[tick=%d] *** LOT %s COMPLETE ***", self.tick_count, lot.lot_id)
        else:
            lot.status = LotStatus.WAITING
            self._request_transport(lot)

    def _request_transport(self, lot: Lot):
        if lot.is_complete:
            return
        proc = lot.current_process
        equip_id = self._equip_assignment[lot.lot_id][proc]
        to_node = self.equipments[equip_id].position
        from_node = lot.current_position

        logger.info(
            "[tick=%d] REQUEST %s: %s -> %s (%s)",
            self.tick_count, lot.lot_id, from_node, to_node, proc,
        )
        self.scheduler.assign_transport(lot, from_node, to_node, self.tick_count)

    # ------------------------------------------------------------------ #
    #  결과 출력                                                           #
    # ------------------------------------------------------------------ #

    def _print_equip_assignment(self):
        print("\n[Equipment Assignment per LOT]")
        for lot_id, mapping in self._equip_assignment.items():
            route = " -> ".join(f"{p}:{e}" for p, e in mapping.items())
            print(f"  {lot_id}: {route}")
        print()

    def _print_results(self):
        sep = "=" * 62
        print(f"\n{sep}")
        print("  AMHS SIMULATION RESULTS")
        print(sep)

        # ── LOT Summary ──────────────────────────────────────────────
        print("\n[LOT Summary]")
        print(f"  {'LOT ID':<12} {'Total Time':>10} {'Wait Ticks':>10} {'Status':<12}")
        print("  " + "-" * 48)
        total_wait = 0
        for lot in self.lots.values():
            tt = lot.total_time(self.tick_count)
            total_wait += lot.wait_ticks
            status = "COMPLETE" if lot.is_complete else lot.status.value
            print(f"  {lot.lot_id:<12} {tt:>10} {lot.wait_ticks:>10} {status:<12}")
        avg_wait = total_wait / max(len(self.lots), 1)
        print(f"\n  Average wait ticks per LOT : {avg_wait:.2f}")

        # ── OHT Summary ──────────────────────────────────────────────
        print("\n[OHT Summary]")
        print(f"  {'OHT ID':<10} {'Tasks':>6} {'Total Dist':>12} {'Final Pos':<18} {'Status':<8}")
        print("  " + "-" * 58)
        for oht in self.ohts.values():
            print(
                f"  {oht.oht_id:<10} {oht.task_count:>6} "
                f"{oht.total_distance:>12.1f} {oht.position:<18} {oht.status.value:<8}"
            )

        # ── Failover Events ───────────────────────────────────────────
        events = self.scheduler.failover_events
        print(f"\n[Failover Events]  (total={len(events)})")
        if events:
            for ev in events:
                reassign = ev.reassigned_oht or "PENDING"
                print(f"  tick={ev.tick:>3d} | {ev.oht_id} ERROR | {ev.lot_id} "
                      f"({ev.from_node}->{ev.to_node}) | reassigned->{reassign}")
        else:
            print("  (none)")

        # ── Summary ───────────────────────────────────────────────────
        completed = sum(1 for lot in self.lots.values() if lot.is_complete)
        print(f"\n  LOTs completed      : {completed} / {len(self.lots)}")
        print(f"  Total sim ticks     : {self.tick_count}")
        print(f"  Failover events     : {len(events)}")
        print(sep + "\n")
