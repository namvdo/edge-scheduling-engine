from __future__ import annotations

"""Inc 9: RAN agent (traffic generator) that calls scheduler over mTLS.

Here demonstrate:
  - multi-region (run one agent per region)
  - secure channel between RAN and cloud scheduler (mTLS)

"""

import argparse
import json
import time
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional
from ..config import load_config
from ..generator import RequestGenConfig, RequestGenerator, TrafficConfig
from ..metrics import MetricsCollector, Stopwatch
from ..mobility import MobilityConfig
from ..radio import RadioConfig, RadioModel
from ..types import Allocation, AllocationStatus, ResourceVector
from .tls import ClientTLSConfig, build_client_ssl_context





def _scenario_to_gen_cfg(args: argparse.Namespace) -> RequestGenConfig:
    #mirror ran_scheduler.main presets to keep results comparable.
    if args.scenario == "normal":
        traffic = TrafficConfig(base_requests_per_tick=args.base_requests_per_tick, pattern="constant")
        mobility_mode = "random_waypoint"
        qos_weights = {"best-effort": 0.7, "embb": 0.2, "urllc": 0.08, "mmtc": 0.02}
        area = MobilityConfig(area_width_m=2500, area_height_m=2500, min_speed_mps=0.5, max_speed_mps=2.0, seed=7)
    elif args.scenario == "rush":
        traffic = TrafficConfig(
            base_requests_per_tick=args.base_requests_per_tick,
            pattern="rush_hour",
            peak_multiplier=3.0,
            peak_width_ticks=max(2, args.ticks // 6),
        )
        mobility_mode = "commuter"
        qos_weights = {"best-effort": 0.6, "embb": 0.3, "urllc": 0.09, "mmtc": 0.01}
        area = MobilityConfig(area_width_m=4000, area_height_m=4000, min_speed_mps=0.5, max_speed_mps=2.0, seed=7)
    else:
        traffic = TrafficConfig(base_requests_per_tick=args.base_requests_per_tick, pattern="sine", peak_multiplier=2.0)
        mobility_mode = "random_waypoint"
        qos_weights = {"best-effort": 0.5, "embb": 0.35, "urllc": 0.12, "mmtc": 0.03}
        area = MobilityConfig(area_width_m=1200, area_height_m=1200, min_speed_mps=0.2, max_speed_mps=1.2, seed=7)

    return RequestGenConfig(
        seed=7,
        users=args.users,
        ticks=args.ticks,
        traffic=traffic,
        qos_weights=qos_weights,
        mobility_mode=mobility_mode,
        mobility=area,
        radio=RadioConfig(seed=7),
        dt_s=1.0,
    )



def _alloc_from_json(d: Dict[str, Any]) -> Allocation:
    g = d.get("granted") or {}
    granted = ResourceVector(
        spectrum_mhz=float(g.get("spectrum_mhz", 0.0)),
        compute_units=float(g.get("compute_units", 0.0)),
        storage_gb=float(g.get("storage_gb", 0.0)),
    )
    status = AllocationStatus(str(d.get("status", "blocked")))
    return Allocation(
        request_id=str(d.get("request_id")),
        user_id=str(d.get("user_id")),
        tick=int(d.get("tick")),
        bs_id=(str(d["bs_id"]) if d.get("bs_id") is not None else None),
        granted=granted,
        status=status,
        reason=(str(d["reason"]) if d.get("reason") is not None else None),
        signal_quality_db=(float(d["signal_quality_db"]) if d.get("signal_quality_db") is not None else None),
        distance_m=(float(d["distance_m"]) if d.get("distance_m") is not None else None),
        qos_class=str(d.get("qos_class", "best-effort")),
    )




def _post_json(url: str, payload: Dict[str, Any], *, ssl_ctx) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)





def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Inc9: RAN agent -> Scheduler API (mTLS)")
    p.add_argument("--config", default="configs/base_stations_multiregion.yaml")
    p.add_argument("--region", default="eu")

    p.add_argument("--scheduler-url", default="https://127.0.0.1:8443", help="Base URL, e.g. https://scheduler-eu:8443")
    p.add_argument("--server-hostname", default=None, help="If set, enables hostname verification for TLS")

    p.add_argument("--tls-ca", default="cloud/inc9/certs/out/ca.crt")
    p.add_argument("--tls-cert", default=None)
    p.add_argument("--tls-key", default=None)

    p.add_argument("--ticks", type=int, default=50)
    p.add_argument("--users", type=int, default=200)
    p.add_argument("--base-requests-per-tick", type=int, default=200)
    p.add_argument("--scenario", choices=["normal", "rush", "dense"], default="rush")
    p.add_argument("--log-dir", default="logs_inc9")
    return p





def main() -> None:
    args = build_argparser().parse_args()

    cert = args.tls_cert or f"cloud/inc9/certs/out/ran-{args.region}.crt"
    key = args.tls_key or f"cloud/inc9/certs/out/ran-{args.region}.key"
    tls_cfg = ClientTLSConfig(
        ca_file=args.tls_ca,
        cert_file=cert,
        key_file=key,
        server_hostname=args.server_hostname,
    )
    ssl_ctx = build_client_ssl_context(tls_cfg)

    sim_cfg = load_config(args.config)
    #Agent "knows" its regional topology for SINR + cell preference
    base_stations = [bs for bs in sim_cfg.base_stations if bs.region == args.region]
    if not base_stations:
        raise SystemExit(f"No base stations for region='{args.region}'. Check config: {args.config}")

    gen_cfg = _scenario_to_gen_cfg(args)
    generator = RequestGenerator(gen_cfg)
    radio = RadioModel(gen_cfg.radio)

    metrics = MetricsCollector()
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    total = granted = blocked = 0
    t0 = time.time()

    for req in generator.generate(base_stations):
        payload = {
            "request_id": req.request_id,
            "user_id": req.user_id,
            "tick": req.tick,
            "qos_class": req.qos_class,
            "signal_quality_db": req.signal_quality_db,
            "cell_preference": req.cell_preference,
            "user_location_xy": list(req.user_location_xy) if req.user_location_xy else None,
            "demand": asdict(req.demand),
        }

        with Stopwatch() as sw:
            resp = _post_json(args.scheduler_url.rstrip("/") + "/allocate", payload, ssl_ctx=ssl_ctx)

        if not resp.get("ok"):
            # Treat as blocked on server errors
            alloc = Allocation(
                request_id=req.request_id,
                user_id=req.user_id,
                tick=req.tick,
                bs_id=None,
                granted=ResourceVector(),
                status=AllocationStatus.BLOCKED,
                reason="scheduler_api_error",
                signal_quality_db=req.signal_quality_db,
                distance_m=None,
                qos_class=req.qos_class,
            )
        else:
            alloc = _alloc_from_json(resp.get("allocation") or {})

        total += 1
        if alloc.status == AllocationStatus.GRANTED:
            granted += 1
        else:
            blocked += 1

        metrics.record_request(alloc, scheduler_latency_ms=sw.ms, radio=radio)

    #finalizes ticks and export
    for tick in range(gen_cfg.ticks):
        metrics.finalize_tick(tick)
    metrics.export_requests_csv(log_dir / "requests_kpi.csv")
    metrics.export_ticks_csv(log_dir / "ticks_kpi.csv")
    metrics.export_jsonl(log_dir / "requests_kpi.jsonl")

    dt = time.time() - t0
    print("\n=== INC9 RAN AGENT SUMMARY ===")
    print(f"region={args.region}")
    print(f"scheduler_url={args.scheduler_url}")
    print(f"total_requests={total}")
    print(f"granted={granted}")
    print(f"blocked={blocked}")
    print(f"elapsed_s={dt:.2f}")
    print(f"logs_written_to={log_dir.resolve()}")


if __name__ == "__main__":
    main()
