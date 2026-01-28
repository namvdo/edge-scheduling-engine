from __future__ import annotations

from typing import List

from .scheduler_base import Scheduler
from .types import Allocation, AllocationStatus, BaseStation, ResourceVector, UserRequest


class RoundRobinScheduler(Scheduler):
    """Week1 scheduler: round-robin across base stations with feasibility check.
    Policy:
      - Try BS in rotating order until a BS can allocate full demand.
      - If none can, block.
    """

    def __init__(self) -> None:
        self._idx = 0
        self._last_tick = None

    def on_tick_start(self, tick: int, base_stations: List[BaseStation]) -> None:
        #For week1 this don't reset capacities each tick.
        #In the future will be more impelentations...
        self._last_tick = tick
        if base_stations:
            self._idx %= len(base_stations)

    def schedule(self, request: UserRequest, base_stations: List[BaseStation]) -> Allocation:
        if not base_stations:
            return Allocation(
                request_id=request.request_id,
                user_id=request.user_id,
                tick=request.tick,
                bs_id=None,
                granted=ResourceVector(),
                status=AllocationStatus.BLOCKED,
                reason="no_base_stations",
            )

        n = len(base_stations)
        start = self._idx

        for offset in range(n):
            i = (start + offset) % n
            bs = base_stations[i]
            if bs.can_allocate(request.demand):
                bs.allocate(request.demand)
                #next start index after a successful placement
                self._idx = (i + 1) % n
                return Allocation(
                    request_id=request.request_id,
                    user_id=request.user_id,
                    tick=request.tick,
                    bs_id=bs.id,
                    granted=request.demand,
                    status=AllocationStatus.GRANTED,
                )

        self._idx = (start + 1) % n
        return Allocation(
            request_id=request.request_id,
            user_id=request.user_id,
            tick=request.tick,
            bs_id=None,
            granted=ResourceVector(),
            status=AllocationStatus.BLOCKED,
            reason="insufficient_capacity_all_bs",
        )

    def name(self) -> str:
        return "round_robin"
