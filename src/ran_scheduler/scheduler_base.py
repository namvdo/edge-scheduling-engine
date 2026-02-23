from __future__ import annotations



from abc import ABC, abstractmethod
from typing import List
from .types import Allocation, BaseStation, UserRequest





class Scheduler(ABC):
    """scheduler interface!"""


    @abstractmethod
    def on_tick_start(self, tick: int, base_stations: List[BaseStation]) -> None:
        """hook for tick-based logic"""


    @abstractmethod
    def schedule(self, request: UserRequest, base_stations: List[BaseStation]) -> Allocation:
        """return allocation decision for request"""


    @abstractmethod
    def name(self) -> str:
        """readable name for logs"""
