from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import yaml

from .types import BaseStation, ResourceVector


@dataclass(frozen=True)
class SimConfig:
    base_stations: List[BaseStation]


def load_config(path: str | Path) -> SimConfig:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))

    bs_list = []
    for item in data.get("base_stations", []):
        cap = item["capacity"]
        bs = BaseStation(
            id=item["id"],
            capacity=ResourceVector(
                spectrum_mhz=float(cap["spectrum_mhz"]),
                compute_units=float(cap["compute_units"]),
                storage_gb=float(cap["storage_gb"]),
            ),
        )
        bs_list.append(bs)

    if not bs_list:
        raise ValueError("No base stations found in config.")

    return SimConfig(base_stations=bs_list)
