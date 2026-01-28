from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, List, Optional

from .types import ResourceVector, UserRequest


@dataclass(frozen=True)
class RequestGenConfig:
    seed: int = 42
    users: int = 50
    ticks: int = 10
    requests_per_tick: int = 30

    #Demand ranges. I will tune later.
    spectrum_mhz_range: tuple[float, float] = (1.0, 10.0)
    compute_units_range: tuple[float, float] = (0.5, 4.0)
    storage_gb_range: tuple[float, float] = (0.0, 2.0)

    #Future hooks:
    qos_classes: Optional[List[str]] = None  #it can be for exxample ["urllc", "embb", "mmtc"]


class RequestGenerator:
    #Generates user requests per tick. (gRPC input to this)
    def __init__(self, cfg: RequestGenConfig) -> None:
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)

    def generate(self) -> Iterable[UserRequest]:
        req_counter = 0
        for tick in range(self.cfg.ticks):
            for _ in range(self.cfg.requests_per_tick):
                user_id = f"u-{self.rng.randint(1, self.cfg.users)}"
                demand = ResourceVector(
                    spectrum_mhz=self.rng.uniform(*self.cfg.spectrum_mhz_range),
                    compute_units=self.rng.uniform(*self.cfg.compute_units_range),
                    storage_gb=self.rng.uniform(*self.cfg.storage_gb_range),
                )
                qos_class = "best-effort"
                if self.cfg.qos_classes:
                    qos_class = self.rng.choice(self.cfg.qos_classes)

                req = UserRequest(
                    request_id=f"r-{req_counter}",
                    user_id=user_id,
                    tick=tick,
                    demand=demand,
                    qos_class=qos_class,
                    signal_quality=None,
                    cell_preference=None,
                )
                req_counter += 1
                yield req
