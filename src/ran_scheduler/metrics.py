from __future__ import annotations

import csv
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from .radio import RadioModel
from .types import Allocation, AllocationStatus





def jains_fairness(values: List[float]) -> float:
    """jain's fairness index in [0,1]."""
    if not values:
        return 1.0
    s = sum(values)
    ss = sum(v * v for v in values)
    if ss <= 1e-12:
        return 1.0
    return float((s * s) / (len(values) * ss))


QOS_LATENCY_TARGET_MS: Dict[str, float] = {
    "urllc": 10.0,
    "embb": 50.0,
    "mmtc": 200.0,
    "best-effort": 100.0,
}




@dataclass(frozen=True)
class RequestKpi:
    request_id: str
    user_id: str
    tick: int
    qos_class: str
    status: str
    bs_id: Optional[str]
    scheduler_latency_ms: float
    estimated_throughput_mbps: float
    signal_quality_db: Optional[float]
    distance_m: Optional[float]
    qos_target_ms: float
    meets_qos: bool




@dataclass(frozen=True)
class TickKpi:
    tick: int
    requests: int
    granted: int
    blocked: int
    total_throughput_mbps: float
    fairness_jain: float
    avg_scheduler_latency_ms: float
    qos_meet_rate: float





class MetricsCollector:
    """KPI collection AND exports for ml/analytics."""

    def __init__(self) -> None:
        self._req_rows: List[RequestKpi] = []
        self._tick_rows: List[TickKpi] = []
        self._tick_user_thr: Dict[int, Dict[str, float]] = {}


    def record_request(
        self,
        alloc: Allocation,
        scheduler_latency_ms: float,
        radio: Optional[RadioModel] = None,
    ) -> None:
        if alloc.status == AllocationStatus.GRANTED:
            thr = RadioModel.throughput_mbps(alloc.granted.spectrum_mhz, alloc.signal_quality_db)
        else:
            thr = 0.0

        qos_target = float(QOS_LATENCY_TARGET_MS.get(alloc.qos_class, QOS_LATENCY_TARGET_MS["best-effort"]))
        meets = scheduler_latency_ms <= qos_target and alloc.status == AllocationStatus.GRANTED

        self._req_rows.append(
            RequestKpi(
                request_id=alloc.request_id,
                user_id=alloc.user_id,
                tick=alloc.tick,
                qos_class=alloc.qos_class,
                status=str(alloc.status.value),
                bs_id=alloc.bs_id,
                scheduler_latency_ms=float(scheduler_latency_ms),
                estimated_throughput_mbps=float(thr),
                signal_quality_db=alloc.signal_quality_db,
                distance_m=alloc.distance_m,
                qos_target_ms=qos_target,
                meets_qos=bool(meets),
            )
        )

        if alloc.tick not in self._tick_user_thr:
            self._tick_user_thr[alloc.tick] = {}
        self._tick_user_thr[alloc.tick][alloc.user_id] = self._tick_user_thr[alloc.tick].get(alloc.user_id, 0.0) + thr


    def finalize_tick(self, tick: int) -> None:
        rows = [r for r in self._req_rows if r.tick == tick]
        if not rows:
            self._tick_rows.append(
                TickKpi(
                    tick=tick,
                    requests=0,
                    granted=0,
                    blocked=0,
                    total_throughput_mbps=0.0,
                    fairness_jain=1.0,
                    avg_scheduler_latency_ms=0.0,
                    qos_meet_rate=0.0,
                )
            )
            return

        granted = sum(1 for r in rows if r.status == "granted")
        blocked = len(rows) - granted
        total_thr = sum(r.estimated_throughput_mbps for r in rows)
        avg_lat = sum(r.scheduler_latency_ms for r in rows) / len(rows)

        user_thr = list(self._tick_user_thr.get(tick, {}).values())
        fairness = jains_fairness(user_thr)

        qos_meet = sum(1 for r in rows if r.meets_qos) / len(rows)

        self._tick_rows.append(
            TickKpi(
                tick=tick,
                requests=len(rows),
                granted=granted,
                blocked=blocked,
                total_throughput_mbps=float(total_thr),
                fairness_jain=float(fairness),
                avg_scheduler_latency_ms=float(avg_lat),
                qos_meet_rate=float(qos_meet),
            )
        )

    @property
    def request_rows(self) -> List[RequestKpi]:
        return list(self._req_rows)

    @property
    def tick_rows(self) -> List[TickKpi]:
        return list(self._tick_rows)

    def export_jsonl(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for row in self._req_rows:
                f.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")

    def export_requests_csv(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not self._req_rows:
            return
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(self._req_rows[0]).keys()))
            w.writeheader()
            for row in self._req_rows:
                w.writerow(asdict(row))

    def export_ticks_csv(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not self._tick_rows:
            return
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(self._tick_rows[0]).keys()))
            w.writeheader()
            for row in self._tick_rows:
                w.writerow(asdict(row))





class Stopwatch:
    """THIS is helper for scheduler-latency measurement."""

    def __enter__(self) -> "Stopwatch":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._t1 = time.perf_counter()

    @property
    def ms(self) -> float:
        return float((self._t1 - self._t0) * 1000.0)
