from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from .mobility import CommuterConfig, CommuterMobility, MobilityConfig, RandomWaypointMobility
from .radio import RadioConfig, RadioModel, distance_m
from .types import BaseStation, ResourceVector, UserRequest




@dataclass(frozen=True)
class TrafficConfig:
    """THIS IS traffic shaping."""

    base_requests_per_tick: int = 30
    pattern: str = "constant"  #constant | rush_hour | sine
    peak_multiplier: float = 2.5
    #this is for rush_hour. So peak around the middle of simulation.
    peak_width_ticks: int = 4




@dataclass(frozen=True)
class QosDemandProfile:
    spectrum_mhz_range: Tuple[float, float]
    compute_units_range: Tuple[float, float]
    storage_gb_range: Tuple[float, float]


DEFAULT_QOS_PROFILES: Dict[str, QosDemandProfile] = {
    "best-effort": QosDemandProfile((1.0, 8.0), (0.2, 2.0), (0.0, 1.0)),
    "embb": QosDemandProfile((5.0, 20.0), (0.5, 4.0), (0.0, 2.0)),
    "urllc": QosDemandProfile((1.0, 6.0), (0.5, 3.0), (0.0, 1.0)),
    "mmtc": QosDemandProfile((0.2, 2.0), (0.1, 0.5), (0.0, 0.2)),
}





@dataclass(frozen=True)
class RequestGenConfig:
    seed: int = 42
    users: int = 50
    ticks: int = 10

    traffic: TrafficConfig = TrafficConfig()

    #QoS distribution. If None then we use only best-effort.
    qos_weights: Optional[Dict[str, float]] = None

    #mobility
    mobility_mode: str = "random_waypoint"  #random_waypoint | commuter | static
    mobility: MobilityConfig = MobilityConfig()
    commuter: CommuterConfig = CommuterConfig()

    radio: RadioConfig = RadioConfig()

    dt_s: float = 1.0  #this is seconds per tick

    #custom QoS profiles
    qos_profiles: Optional[Dict[str, QosDemandProfile]] = None





class RequestGenerator:
    """okay so this generates requests with mobility and also signal quality."""

    def __init__(self, cfg: RequestGenConfig) -> None:
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.radio = RadioModel(cfg.radio)
        self._rw_mob = RandomWaypointMobility(cfg.mobility)
        self._commuter_mob = CommuterMobility(cfg.commuter, total_ticks=cfg.ticks)
        #weighted QoS sampler
        self._qos_weights = cfg.qos_weights or {"best-effort": 1.0}
        self._qos_keys = list(self._qos_weights.keys())
        self._qos_cum: List[float] = []
        s = 0.0
        for k in self._qos_keys:
            s += float(self._qos_weights[k])
            self._qos_cum.append(s)
        self._qos_sum = s
        self._profiles = dict(DEFAULT_QOS_PROFILES)
        if cfg.qos_profiles:
            self._profiles.update(cfg.qos_profiles)

        #this is cache positions per tick per user
        self._pos_cache: Dict[Tuple[int, str], Tuple[float, float]] = {}

    def _requests_this_tick(self, tick: int) -> int:
        tcfg = self.cfg.traffic
        base = int(tcfg.base_requests_per_tick)

        if tcfg.pattern == "constant":
            return base

        if tcfg.pattern == "sine":
            import math
            x = (tick / max(1, self.cfg.ticks - 1)) * math.pi
            mult = 1.0 + (tcfg.peak_multiplier - 1.0) * math.sin(x)
            return max(0, int(base * mult))

        if tcfg.pattern == "rush_hour":
            center = (self.cfg.ticks - 1) / 2.0
            w = max(1, int(tcfg.peak_width_ticks))
            dist = abs(tick - center)
            if dist >= w:
                return base
            mult = 1.0 + (tcfg.peak_multiplier - 1.0) * (1.0 - dist / w)
            return max(0, int(base * mult))

        raise ValueError(f"Unknown traffic pattern: {tcfg.pattern}")

    def _sample_qos(self) -> str:
        if self._qos_sum <= 0:
            return "best-effort"
        r = self.rng.uniform(0, self._qos_sum)
        for k, c in zip(self._qos_keys, self._qos_cum):
            if r <= c:
                return k
        return self._qos_keys[-1]

    def _user_location(self, tick: int, user_id: str) -> Tuple[float, float]:
        key = (tick, user_id)
        if key in self._pos_cache:
            return self._pos_cache[key]

        if self.cfg.mobility_mode == "static":
            rr = random.Random(hash((self.cfg.seed, user_id)) & 0xFFFFFFFF)
            xy = (rr.uniform(0, self.cfg.mobility.area_width_m), rr.uniform(0, self.cfg.mobility.area_height_m))
        elif self.cfg.mobility_mode == "commuter":
            xy = self._commuter_mob.step(user_id, tick=tick, dt_s=self.cfg.dt_s)
        else:
            xy = self._rw_mob.step(user_id, dt_s=self.cfg.dt_s)

        self._pos_cache[key] = xy
        return xy

    def _choose_bs_and_sinr(self, user_xy: Tuple[float, float], base_stations: List[BaseStation]) -> Tuple[Optional[str], Optional[float]]:
        if not base_stations:
            return None, None
        best_bs = None
        best_sinr = None
        for bs in base_stations:
            sinr_db = self.radio.sinr_db(user_xy, bs, base_stations)
            if best_sinr is None or sinr_db > best_sinr:
                best_sinr = sinr_db
                best_bs = bs
        return (best_bs.id if best_bs else None), best_sinr

    def generate(self, base_stations: List[BaseStation]) -> Iterable[UserRequest]:
        req_counter = 0
        for tick in range(self.cfg.ticks):
            nreq = self._requests_this_tick(tick)
            for _ in range(nreq):
                user_id = f"u-{self.rng.randint(1, self.cfg.users)}"
                user_xy = self._user_location(tick, user_id)

                qos = self._sample_qos()
                prof = self._profiles.get(qos, self._profiles["best-effort"])

                demand = ResourceVector(
                    spectrum_mhz=self.rng.uniform(*prof.spectrum_mhz_range),
                    compute_units=self.rng.uniform(*prof.compute_units_range),
                    storage_gb=self.rng.uniform(*prof.storage_gb_range),
                )

                cell_pref, sinr_db = self._choose_bs_and_sinr(user_xy, base_stations)

                req = UserRequest(
                    request_id=f"r-{req_counter}",
                    user_id=user_id,
                    tick=tick,
                    demand=demand,
                    qos_class=qos,
                    signal_quality_db=sinr_db,
                    cell_preference=cell_pref,
                    user_location_xy=user_xy,
                )
                req_counter += 1
                yield req
