from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class OHTStatus(Enum):
    IDLE = "Idle"
    BUSY = "Busy"
    ERROR = "Error"


class LotStatus(Enum):
    WAITING = "Waiting"
    IN_TRANSIT = "InTransit"
    PROCESSING = "Processing"
    DONE = "Done"


PROCESS_SEQUENCE = ["ETCH", "PHOTO", "CMP"]

EQUIPMENT_PROCESS = {
    "ETCH-01": "ETCH",
    "ETCH-02": "ETCH",
    "PHOTO-01": "PHOTO",
    "PHOTO-02": "PHOTO",
    "CMP-01": "CMP",
    "CMP-02": "CMP",
}

PROCESS_DURATION = {
    "ETCH": 5,
    "PHOTO": 4,
    "CMP": 6,
}


@dataclass
class Equipment:
    equip_id: str
    process: str
    position: str  # node name in graph

    def __repr__(self):
        return f"Equipment({self.equip_id}, {self.process}, pos={self.position})"


@dataclass
class OHT:
    oht_id: str
    position: str
    status: OHTStatus = OHTStatus.IDLE
    total_distance: float = 0.0
    task_count: int = 0
    current_lot: Optional[str] = None
    current_task: Optional[dict] = None  # {lot_id, from_node, to_node, ticks_remaining}

    def __repr__(self):
        return (f"OHT({self.oht_id}, pos={self.position}, "
                f"status={self.status.value}, dist={self.total_distance:.1f})")


@dataclass
class Lot:
    lot_id: str
    process_index: int = 0          # index into PROCESS_SEQUENCE
    status: LotStatus = LotStatus.WAITING
    current_position: str = "LOAD_PORT"
    start_tick: int = 0
    end_tick: Optional[int] = None
    wait_ticks: int = 0
    assigned_oht: Optional[str] = None
    processing_ticks_remaining: int = 0

    @property
    def current_process(self) -> Optional[str]:
        if self.process_index < len(PROCESS_SEQUENCE):
            return PROCESS_SEQUENCE[self.process_index]
        return None

    @property
    def is_complete(self) -> bool:
        return self.process_index >= len(PROCESS_SEQUENCE)

    def total_time(self, current_tick: int) -> int:
        if self.end_tick is not None:
            return self.end_tick - self.start_tick
        return current_tick - self.start_tick

    def __repr__(self):
        proc = self.current_process or "DONE"
        return (f"Lot({self.lot_id}, proc={proc}, "
                f"pos={self.current_position}, status={self.status.value})")


@dataclass
class FailoverEvent:
    tick: int
    oht_id: str
    lot_id: str
    from_node: str
    to_node: str
    reassigned_oht: Optional[str] = None

    def __repr__(self):
        return (f"[tick={self.tick}] FAILOVER: {self.oht_id} failed while moving "
                f"{self.lot_id} ({self.from_node}->{self.to_node}), "
                f"reassigned to {self.reassigned_oht or 'PENDING'}")
