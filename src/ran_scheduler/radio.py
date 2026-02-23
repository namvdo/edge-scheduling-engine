from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple
from .types import BaseStation

XY = Tuple[float, float]





def distance_m(a: XY, b: XY) -> float:
    return float(math.hypot(a[0] - b[0], a[1] - b[1]))







@dataclass(frozen=True)
class RadioConfig:
    pathloss_exp: float = 3.3
    noise_floor: float = 1e-9  #arbitrary power units
    fading_std_db: float = 2.0
    seed: int = 42





class RadioModel:
    """radio model producing SINR (dB) and throughput approximations.
    this isnt meant to be superaccurate. It exists to drive metrics and ml features.
    """

    def __init__(self, cfg: RadioConfig) -> None:
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)

    def _rx_power(self, d_m: float) -> float:
        #this avoid singularity at d=0 with 1m reference.
        d = max(1.0, d_m)
        return 1.0 / (d ** self.cfg.pathloss_exp)

    def sinr_db(self, user_xy: XY, serving_bs: BaseStation, all_bs: Iterable[BaseStation]) -> float:
        s = self._rx_power(distance_m(user_xy, serving_bs.location_xy))
        i = 0.0
        for bs in all_bs:
            if bs.id == serving_bs.id:
                continue
            i += 0.6 * self._rx_power(distance_m(user_xy, bs.location_xy))
        n = self.cfg.noise_floor
        sinr = s / (i + n)

        #log-normal fading in dB.
        fading_db = self.rng.gauss(0.0, self.cfg.fading_std_db)
        sinr_db = 10.0 * math.log10(max(1e-12, sinr)) + fading_db
        return float(sinr_db)



    @staticmethod
    def spectral_efficiency_bps_per_hz(sinr_db: float) -> float:
        sinr_lin = 10 ** (sinr_db / 10.0)
        eff = math.log2(1.0 + sinr_lin)
        return float(min(6.0, max(0.0, eff)))



    @classmethod
    def throughput_mbps(cls, spectrum_mhz: float, sinr_db: Optional[float]) -> float:
        if sinr_db is None:
            return 0.0
        eff = cls.spectral_efficiency_bps_per_hz(sinr_db)
        #MHz * (bps/Hz) ---> Mbps
        return float(max(0.0, spectrum_mhz) * eff)
