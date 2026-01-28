from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .types import Allocation, BaseStation, UserRequest


class Scheduler(ABC):
    #Scheduler interface.
    #More implementations in the future.
    
    @abstractmethod
    def on_tick_start(self, tick: int, base_stations: List[BaseStation]) -> None:
        """Hook for tick-based logic."""

    @abstractmethod
    def schedule(self, request: UserRequest, base_stations: List[BaseStation]) -> Allocation:
        """Return allocation decision for request."""

    @abstractmethod
    def name(self) -> str:
        """Readable name for logs..."""
