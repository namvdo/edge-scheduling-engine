from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


@dataclass(frozen=True)
class ResourceVector:
    #Generic resource vector.
    spectrum_mhz: float = 0.0
    compute_units: float = 0.0
    storage_gb: float = 0.0

    def fits_in(self, other: "ResourceVector") -> bool:
        return (
            self.spectrum_mhz <= other.spectrum_mhz
            and self.compute_units <= other.compute_units
            and self.storage_gb <= other.storage_gb
        )

    def add(self, other: "ResourceVector") -> "ResourceVector":
        return ResourceVector(
            spectrum_mhz=self.spectrum_mhz + other.spectrum_mhz,
            compute_units=self.compute_units + other.compute_units,
            storage_gb=self.storage_gb + other.storage_gb,
        )

    def sub(self, other: "ResourceVector") -> "ResourceVector":
        return ResourceVector(
            spectrum_mhz=self.spectrum_mhz - other.spectrum_mhz,
            compute_units=self.compute_units - other.compute_units,
            storage_gb=self.storage_gb - other.storage_gb,
        )


@dataclass
class BaseStation:
    id: str
    capacity: ResourceVector
    available: ResourceVector = field(init=False)

    def __post_init__(self) -> None:
        self.available = self.capacity

    def can_allocate(self, demand: ResourceVector) -> bool:
        return demand.fits_in(self.available)

    def allocate(self, demand: ResourceVector) -> None:
        if not self.can_allocate(demand):
            raise ValueError(f"Insufficient capacity on {self.id}. demand={demand}, available={self.available}")
        self.available = self.available.sub(demand)

    def reset(self) -> None:
        self.available = self.capacity


@dataclass(frozen=True)
class UserRequest:
    #a single request at a discrete time tick.
    request_id: str
    user_id: str
    tick: int
    demand: ResourceVector
    #Extension points:
    qos_class: str = "best-effort"
    signal_quality: Optional[float] = None  #for example SINR
    cell_preference: Optional[str] = None   #for example user wants nearest BS


class AllocationStatus(str, Enum):
    GRANTED = "granted"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class Allocation:
    request_id: str
    user_id: str
    tick: int
    bs_id: Optional[str]
    granted: ResourceVector
    status: AllocationStatus
    reason: Optional[str] = None


@dataclass
class SimulationSummary:
    total_requests: int
    granted: int
    blocked: int
    granted_per_bs: Dict[str, int]
