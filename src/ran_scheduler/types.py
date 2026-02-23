from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple






@dataclass(frozen=True)
class ResourceVector:
    """THIS is generic resource vector, so spectrum, compute, storage."""

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
    location_xy: Tuple[float, float] = (0.0, 0.0)
    region: str = "local"

    available: ResourceVector = field(init=False)

    def __post_init__(self) -> None:
        self.available = self.capacity


    def can_allocate(self, demand: ResourceVector) -> bool:
        return demand.fits_in(self.available)

    def allocate(self, demand: ResourceVector) -> None:
        if not self.can_allocate(demand):
            raise ValueError(
                f"Insufficient capacity on {self.id}. demand={demand}, available={self.available}"
            )
        self.available = self.available.sub(demand)

    def reset(self) -> None:
        self.available = self.capacity






@dataclass(frozen=True)
class UserRequest:
    """this thing is a single user request at discrete time tick."""

    request_id: str
    user_id: str
    tick: int
    demand: ResourceVector

    #extension points here
    qos_class: str = "best-effort"  #for exxample best-effort, embb, urllc, mmtc
    signal_quality_db: Optional[float] = None  #e.g., SINR in dB
    cell_preference: Optional[str] = None  #preferred base station id!!!
    user_location_xy: Optional[Tuple[float, float]] = None  #(x,y) in meters!!!



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

    #tie allocation back to radio conditions
    signal_quality_db: Optional[float] = None
    distance_m: Optional[float] = None
    qos_class: str = "best-effort"





@dataclass
class SimulationSummary:
    total_requests: int
    granted: int
    blocked: int
    granted_per_bs: Dict[str, int]
