from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from .types import Allocation, AllocationStatus






class PrometheusExporter:
    """this is prometheus metrics exporter.

    If prometheus_client is not installed, this becomes a no-op exporter!!!
    """

    def __init__(self, port: int = 8000, namespace: str = "ran") -> None:
        self.port = int(port)
        self.namespace = namespace
        self._enabled = False

        try:
            from prometheus_client import Counter, Gauge, Histogram, start_http_server
        except Exception:
            return

        self._Counter = Counter
        self._Gauge = Gauge
        self._Histogram = Histogram
        self._start_http_server = start_http_server

        #metrics
        self.req_total = Counter(f"{namespace}_requests_total", "Total requests", ["status", "qos"])
        self.throughput = Gauge(f"{namespace}_throughput_mbps", "Estimated throughput per allocation", ["qos"])
        self.latency = Histogram(
            f"{namespace}_scheduler_latency_ms",
            "Scheduler decision latency (ms)",
            buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 25, 50, 100, 250),
        )

        self._start_http_server(self.port)
        self._enabled = True




    def observe_allocation(self, alloc: Allocation, scheduler_latency_ms: float) -> None:
        if not self._enabled:
            return
        status = alloc.status.value
        qos = alloc.qos_class
        self.req_total.labels(status=status, qos=qos).inc()
        self.latency.observe(float(scheduler_latency_ms))
        if alloc.status == AllocationStatus.GRANTED:
            self.throughput.labels(qos=qos).set(float(alloc.granted.spectrum_mhz))
