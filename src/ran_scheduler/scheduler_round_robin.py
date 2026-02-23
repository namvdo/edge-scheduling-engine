from __future__ import annotations



import math
from typing import List, Optional, Tuple
from .scheduler_base import Scheduler
from .types import Allocation, AllocationStatus, BaseStation, ResourceVector, UserRequest





def _distance_m(user_xy: Optional[Tuple[float, float]], bs_xy: Tuple[float, float]) -> Optional[float]:
    if user_xy is None:
        return None
    dx = user_xy[0] - bs_xy[0]
    dy = user_xy[1] - bs_xy[1]
    return float(math.hypot(dx, dy))





class RoundRobinScheduler(Scheduler):
    """round-robin across base stations with feasibility check.

    Policy:
      -try base stations in rotating order until one can allocate the full demand.
      -if none can ---> block.
    """


    def __init__(self) -> None:
        self._idx = 0
        self._last_tick: Optional[int] = None


    def on_tick_start(self, tick: int, base_stations: List[BaseStation]) -> None:
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
                signal_quality_db=request.signal_quality_db,
                distance_m=None,
                qos_class=request.qos_class,
            )

        n = len(base_stations)
        start = self._idx

        for offset in range(n):
            i = (start + offset) % n
            bs = base_stations[i]
            if bs.can_allocate(request.demand):
                bs.allocate(request.demand)
                self._idx = (i + 1) % n
                return Allocation(
                    request_id=request.request_id,
                    user_id=request.user_id,
                    tick=request.tick,
                    bs_id=bs.id,
                    granted=request.demand,
                    status=AllocationStatus.GRANTED,
                    signal_quality_db=request.signal_quality_db,
                    distance_m=_distance_m(request.user_location_xy, bs.location_xy),
                    qos_class=request.qos_class,
                )

        #rotate even if blocked ---> to avoid sticking
        self._idx = (start + 1) % n
        return Allocation(
            request_id=request.request_id,
            user_id=request.user_id,
            tick=request.tick,
            bs_id=None,
            granted=ResourceVector(),
            status=AllocationStatus.BLOCKED,
            reason="insufficient_capacity_all_bs",
            signal_quality_db=request.signal_quality_db,
            distance_m=None,
            qos_class=request.qos_class,
        )


    def name(self) -> str:
        return "round_robin"
