from __future__ import annotations


from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from .metrics import MetricsCollector, Stopwatch
from .monitoring import PrometheusExporter
from .radio import RadioModel
from .scheduler_base import Scheduler
from .types import Allocation, AllocationStatus, BaseStation, SimulationSummary




@dataclass(frozen=True)
class SimulatorConfig:
    verbose: bool = False

    #log allocations and KPIs
    log_dir: str = "logs"
    export_csv: bool = True
    export_jsonl: bool = True


    #capacity replenishment per tick
    reset_bs_each_tick: bool = True


    #expose prometheus metrics
    enable_prometheus: bool = False
    prometheus_port: int = 8000





class Simulator:
    def __init__(
        self,
        base_stations: List[BaseStation],
        scheduler: Scheduler,
        radio: Optional[RadioModel] = None,
        cfg: SimulatorConfig = SimulatorConfig(),
        prometheus: Optional[PrometheusExporter] = None,
    ) -> None:
        self.base_stations = base_stations
        self.scheduler = scheduler
        self.cfg = cfg
        self.radio = radio
        self.metrics = MetricsCollector()
        self.prom = prometheus

        if self.cfg.enable_prometheus and self.prom is None:
            self.prom = PrometheusExporter(port=self.cfg.prometheus_port)


    def run(self, requests: Iterable) -> SimulationSummary:
        log_dir = Path(self.cfg.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        allocations: List[Allocation] = []
        granted_per_bs: Dict[str, int] = {bs.id: 0 for bs in self.base_stations}

        total = granted = blocked = 0

        current_tick: Optional[int] = None

        def tick_start(tick: int) -> None:
            if self.cfg.reset_bs_each_tick:
                for bs in self.base_stations:
                    bs.reset()
            self.scheduler.on_tick_start(tick, self.base_stations)
            if self.cfg.verbose:
                print(f"\n--- tick={tick} ---")



        def tick_end(tick: int) -> None:
            self.metrics.finalize_tick(tick)

        for req in requests:
            #thisll detect tick boundaries
            if current_tick is None:
                current_tick = req.tick
                tick_start(current_tick)
            elif req.tick != current_tick:
                tick_end(current_tick)
                current_tick = req.tick
                tick_start(current_tick)

            with Stopwatch() as sw:
                alloc = self.scheduler.schedule(req, self.base_stations)

            allocations.append(alloc)
            total += 1
            if alloc.status == AllocationStatus.GRANTED:
                granted += 1
                if alloc.bs_id:
                    granted_per_bs[alloc.bs_id] = granted_per_bs.get(alloc.bs_id, 0) + 1
            else:
                blocked += 1

            self.metrics.record_request(alloc, scheduler_latency_ms=sw.ms, radio=self.radio)

            #prometheus stuff
            if self.prom is not None:
                self.prom.observe_allocation(alloc, scheduler_latency_ms=sw.ms)

            if self.cfg.verbose:
                bs_txt = alloc.bs_id if alloc.bs_id else "-"
                print(f"{alloc.request_id} user={alloc.user_id} qos={alloc.qos_class} -> {bs_txt} [{alloc.status.value}]")

        if current_tick is not None:
            tick_end(current_tick)

        #export stuff!
        if self.cfg.export_csv:
            self.metrics.export_requests_csv(log_dir / "requests_kpi.csv")
            self.metrics.export_ticks_csv(log_dir / "ticks_kpi.csv")
        if self.cfg.export_jsonl:
            self.metrics.export_jsonl(log_dir / "requests_kpi.jsonl")

        return SimulationSummary(
            total_requests=total,
            granted=granted,
            blocked=blocked,
            granted_per_bs=granted_per_bs,
        )
