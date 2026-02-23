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

    bs_list: List[BaseStation] = []
    for item in data.get("base_stations", []):
        cap = item["capacity"]
        loc = item.get("location_xy") or item.get("location") or {}
        if isinstance(loc, dict):
            x = float(loc.get("x", 0.0))
            y = float(loc.get("y", 0.0))
            location_xy = (x, y)
        elif isinstance(loc, (list, tuple)) and len(loc) >= 2:
            location_xy = (float(loc[0]), float(loc[1]))
        else:
            location_xy = (0.0, 0.0)

        bs = BaseStation(
            id=str(item["id"]),
            capacity=ResourceVector(
                spectrum_mhz=float(cap["spectrum_mhz"]),
                compute_units=float(cap["compute_units"]),
                storage_gb=float(cap["storage_gb"]),
            ),
            location_xy=location_xy,
            region=str(item.get("region", "local")),
        )
        bs_list.append(bs)

    if not bs_list:
        raise ValueError("No base stations found in config.")

    return SimConfig(base_stations=bs_list)
