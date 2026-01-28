from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .scheduler_base import Scheduler
from .types import Allocation, AllocationStatus, BaseStation, SimulationSummary, UserRequest


@dataclass
class SimulatorConfig:
    #Simulation settings.
    verbose: bool = True
    log_allocations: bool = True  #store allocations for later analytics


class Simulator:
    def __init__(
        self,
        base_stations: List[BaseStation],
        scheduler: Scheduler,
        cfg: Optional[SimulatorConfig] = None,
    ) -> None:
        self.base_stations = base_stations
        self.scheduler = scheduler
        self.cfg = cfg or SimulatorConfig()
        self.allocations: List[Allocation] = []

    def run(self, requests: Iterable[UserRequest]) -> SimulationSummary:
        granted_per_bs: Dict[str, int] = {bs.id: 0 for bs in self.base_stations}
        granted = 0
        blocked = 0
        total = 0

        current_tick = None

        for req in requests:
            total += 1
            if current_tick != req.tick:
                current_tick = req.tick
                self.scheduler.on_tick_start(current_tick, self.base_stations)
                if self.cfg.verbose:
                    print(f"\n=== TICK {current_tick} | scheduler={self.scheduler.name()} ===")

            alloc = self.scheduler.schedule(req, self.base_stations)

            if self.cfg.log_allocations:
                self.allocations.append(alloc)

            if alloc.status == AllocationStatus.GRANTED and alloc.bs_id is not None:
                granted += 1
                granted_per_bs[alloc.bs_id] = granted_per_bs.get(alloc.bs_id, 0) + 1
                if self.cfg.verbose:
                    print(f"[GRANTED] {req.request_id} user={req.user_id} demand={req.demand} -> {alloc.bs_id}")
            else:
                blocked += 1
                if self.cfg.verbose:
                    print(f"[BLOCKED] {req.request_id} user={req.user_id} demand={req.demand} reason={alloc.reason}")

        if self.cfg.verbose:
            print("\n=== FINAL BASE STATION AVAILABILITY ===")
            for bs in self.base_stations:
                print(f"{bs.id}: available={bs.available} / capacity={bs.capacity}")

        return SimulationSummary(
            total_requests=total,
            granted=granted,
            blocked=blocked,
            granted_per_bs=granted_per_bs,
        )
