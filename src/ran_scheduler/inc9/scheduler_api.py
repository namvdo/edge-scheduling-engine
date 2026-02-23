from __future__ import annotations

"""Inc 9: Scheduler API service (HTTPS + mTLS).


"""

import argparse
import json
import ssl
import threading
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
from ..config import load_config
from ..monitoring import PrometheusExporter
from ..scheduler_round_robin import RoundRobinScheduler
from ..types import Allocation, AllocationStatus, ResourceVector, UserRequest
from .tls import ServerTLSConfig, build_server_ssl_context





def _json_read(handler: BaseHTTPRequestHandler, max_bytes: int = 256_000) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    if length > max_bytes:
        raise ValueError("payload_too_large")
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))




def _json_write(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)




def _resource_from_json(d: Dict[str, Any]) -> ResourceVector:
    return ResourceVector(
        spectrum_mhz=float(d.get("spectrum_mhz", 0.0)),
        compute_units=float(d.get("compute_units", 0.0)),
        storage_gb=float(d.get("storage_gb", 0.0)),
    )




def _request_from_json(d: Dict[str, Any]) -> UserRequest:
    user_xy = d.get("user_location_xy")
    user_location_xy: Optional[Tuple[float, float]]
    if isinstance(user_xy, (list, tuple)) and len(user_xy) >= 2:
        user_location_xy = (float(user_xy[0]), float(user_xy[1]))
    else:
        user_location_xy = None

    return UserRequest(
        request_id=str(d["request_id"]),
        user_id=str(d["user_id"]),
        tick=int(d["tick"]),
        demand=_resource_from_json(d.get("demand") or {}),
        qos_class=str(d.get("qos_class", "best-effort")),
        signal_quality_db=(float(d["signal_quality_db"]) if d.get("signal_quality_db") is not None else None),
        cell_preference=(str(d["cell_preference"]) if d.get("cell_preference") is not None else None),
        user_location_xy=user_location_xy,
    )




def _alloc_to_json(a: Allocation) -> Dict[str, Any]:
    out = asdict(a)
    # Enum -> value
    out["status"] = a.status.value
    out["granted"] = asdict(a.granted)
    return out




class _SchedulerState:
    def __init__(
        self,
        *,
        config_path: str,
        region: str,
        reset_bs_each_tick: bool,
        enable_prometheus: bool,
        prometheus_port: int,
    ) -> None:
        sim_cfg = load_config(config_path)
        self.region = region
        self.base_stations = [bs for bs in sim_cfg.base_stations if bs.region == region]
        if not self.base_stations:
            raise ValueError(f"No base stations for region='{region}'. Check config: {config_path}")
        self.scheduler = RoundRobinScheduler()
        self.reset_bs_each_tick = bool(reset_bs_each_tick)
        self.current_tick: Optional[int] = None
        self.lock = threading.Lock()
        self.prom: Optional[PrometheusExporter] = None
        if enable_prometheus:
            self.prom = PrometheusExporter(port=int(prometheus_port), namespace=f"ran_{region}")



    def _tick_start(self, tick: int) -> None:
        if self.reset_bs_each_tick:
            for bs in self.base_stations:
                bs.reset()
        self.scheduler.on_tick_start(tick, self.base_stations)



    def schedule(self, req: UserRequest) -> Allocation:
        with self.lock:
            if self.current_tick is None:
                self.current_tick = req.tick
                self._tick_start(self.current_tick)
            elif req.tick != self.current_tick:
                self.current_tick = req.tick
                self._tick_start(self.current_tick)

            alloc = self.scheduler.schedule(req, self.base_stations)
        return alloc




class SchedulerAPIHandler(BaseHTTPRequestHandler):
    #Set by server factory
    state: _SchedulerState

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: N802
        #keep logs minimal; enable via docker logs if needed
        return

    def do_GET(self) -> None:  #noqa: N802
        if self.path == "/health":
            _json_write(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "region": self.state.region,
                    "scheduler": self.state.scheduler.name(),
                },
            )
            return
        _json_write(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})



    def do_POST(self) -> None:  #noqa: N802
        if self.path != "/allocate":
            _json_write(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return

        try:
            body = _json_read(self)
            req = _request_from_json(body)
        except Exception as e:
            _json_write(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "bad_request", "detail": str(e)})
            return

        try:
            alloc = self.state.schedule(req)
            #prometheus
            if self.state.prom is not None:
                self.state.prom.observe_allocation(alloc, scheduler_latency_ms=0.0)

            _json_write(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "region": self.state.region,
                    "allocation": _alloc_to_json(alloc),
                },
            )
        except Exception as e:
            _json_write(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "internal", "detail": str(e)})




def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Inc9: Scheduler API (HTTPS + mTLS)")
    p.add_argument("--config", default="configs/base_stations_multiregion.yaml")
    p.add_argument("--region", default="eu", help="Region label (e.g. eu/us)")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8443)
    p.add_argument("--no-reset", action="store_true", help="Do not reset BS capacity each tick")
    p.add_argument("--prometheus", action="store_true", help="Expose Prometheus metrics endpoint")
    p.add_argument("--prometheus-port", type=int, default=8000)
    # TLS
    p.add_argument("--tls-ca", default="cloud/inc9/certs/out/ca.crt")
    p.add_argument("--tls-cert", default=None)
    p.add_argument("--tls-key", default=None)
    p.add_argument("--no-client-cert", action="store_true", help="Allow clients without cert (NOT recommended)")
    return p




def serve_forever(args: argparse.Namespace) -> None:
    cert = args.tls_cert or f"cloud/inc9/certs/out/scheduler-{args.region}.crt"
    key = args.tls_key or f"cloud/inc9/certs/out/scheduler-{args.region}.key"
    tls_cfg = ServerTLSConfig(
        ca_file=args.tls_ca,
        cert_file=cert,
        key_file=key,
        require_client_cert=(not args.no_client_cert),
    )
    ssl_ctx = build_server_ssl_context(tls_cfg)

    state = _SchedulerState(
        config_path=args.config,
        region=args.region,
        reset_bs_each_tick=(not args.no_reset),
        enable_prometheus=bool(args.prometheus),
        prometheus_port=int(args.prometheus_port),
    )

    handler_cls = SchedulerAPIHandler
    handler_cls.state = state  #type: ignore[attr-defined]

    httpd = ThreadingHTTPServer((args.host, int(args.port)), handler_cls)
    httpd.socket = ssl_ctx.wrap_socket(httpd.socket, server_side=True)

    print(f"[inc9] scheduler_api region={args.region} listening on https://{args.host}:{args.port}")
    httpd.serve_forever()




def main() -> None:
    args = build_argparser().parse_args()
    serve_forever(args)


if __name__ == "__main__":
    main()
