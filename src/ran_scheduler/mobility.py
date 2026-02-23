from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, Tuple

XY = Tuple[float, float]





@dataclass(frozen=True)
class MobilityConfig:
    area_width_m: float = 2000.0
    area_height_m: float = 2000.0
    min_speed_mps: float = 0.5
    max_speed_mps: float = 2.0
    seed: int = 42






class RandomWaypointMobility:
    """deterministic (seeded) random-waypoint mobility model. Quite small..."""

    def __init__(self, cfg: MobilityConfig) -> None:
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self._pos: Dict[str, XY] = {}
        self._target: Dict[str, XY] = {}
        self._speed: Dict[str, float] = {}

    def _rand_xy(self) -> XY:
        return (self.rng.uniform(0, self.cfg.area_width_m), self.rng.uniform(0, self.cfg.area_height_m))

    def _ensure_user(self, user_id: str) -> None:
        if user_id in self._pos:
            return
        self._pos[user_id] = self._rand_xy()
        self._target[user_id] = self._rand_xy()
        self._speed[user_id] = self.rng.uniform(self.cfg.min_speed_mps, self.cfg.max_speed_mps)

    def step(self, user_id: str, dt_s: float = 1.0) -> XY:
        self._ensure_user(user_id)
        x, y = self._pos[user_id]
        tx, ty = self._target[user_id]
        v = self._speed[user_id]

        dx = tx - x
        dy = ty - y
        dist = math.hypot(dx, dy)

        if dist < 1e-6 or dist <= v * dt_s:
            #arrived ---> new waypoint
            self._pos[user_id] = (tx, ty)
            self._target[user_id] = self._rand_xy()
            self._speed[user_id] = self.rng.uniform(self.cfg.min_speed_mps, self.cfg.max_speed_mps)
            return self._pos[user_id]

        ux = dx / dist
        uy = dy / dist
        self._pos[user_id] = (x + ux * v * dt_s, y + uy * v * dt_s)
        return self._pos[user_id]







@dataclass(frozen=True)
class CommuterConfig:
    """Two-cluster commuting: 'home' cluster ---> 'work' cluster ---> home."""

    area_width_m: float = 2000.0
    area_height_m: float = 2000.0
    cluster_radius_m: float = 250.0
    speed_mps: float = 3.0
    seed: int = 42




class CommuterMobility:
    def __init__(self, cfg: CommuterConfig, total_ticks: int) -> None:
        self.cfg = cfg
        self.total_ticks = max(1, total_ticks)
        self.rng = random.Random(cfg.seed)
        self.home_center: XY = (cfg.area_width_m * 0.25, cfg.area_height_m * 0.25)
        self.work_center: XY = (cfg.area_width_m * 0.75, cfg.area_height_m * 0.75)
        self._pos: Dict[str, XY] = {}
        self._phase: Dict[str, int] = {}

    def _jitter(self, center: XY) -> XY:
        cx, cy = center
        r = self.cfg.cluster_radius_m
        return (cx + self.rng.uniform(-r, r), cy + self.rng.uniform(-r, r))



    def _ensure_user(self, user_id: str) -> None:
        if user_id in self._pos:
            return
        self._pos[user_id] = self._jitter(self.home_center)
        self._phase[user_id] = 0

    def step(self, user_id: str, tick: int, dt_s: float = 1.0) -> XY:
        self._ensure_user(user_id)

        #this switch phase roughly at mid-point (rush-hour commute back).
        if tick >= self.total_ticks // 2:
            self._phase[user_id] = 1

        x, y = self._pos[user_id]
        target = self.work_center if self._phase[user_id] == 0 else self.home_center
        tx, ty = target

        dx = tx - x
        dy = ty - y
        dist = math.hypot(dx, dy)

        if dist < 1e-6 or dist <= self.cfg.speed_mps * dt_s:
            # Arrive and then jitter around the cluster.
            self._pos[user_id] = self._jitter(target)
            return self._pos[user_id]

        ux = dx / dist
        uy = dy / dist
        self._pos[user_id] = (x + ux * self.cfg.speed_mps * dt_s, y + uy * self.cfg.speed_mps * dt_s)
        return self._pos[user_id]
