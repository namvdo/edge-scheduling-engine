from __future__ import annotations

import argparse
from pathlib import Path
from .config import load_config
from .generator import RequestGenConfig, TrafficConfig, RequestGenerator
from .mobility import MobilityConfig
from .radio import RadioConfig, RadioModel
from .scheduler_round_robin import RoundRobinScheduler
from .simulator import Simulator, SimulatorConfig





def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="RAN scheduler simulator")
    p.add_argument("--config", default="configs/base_stations.yaml", help="Base station config YAML")
    p.add_argument("--ticks", type=int, default=20)
    p.add_argument("--users", type=int, default=200)
    p.add_argument("--base-requests-per-tick", type=int, default=200)
    p.add_argument("--scenario", choices=["normal", "rush", "dense"], default="normal")
    p.add_argument("--log-dir", default="logs")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--no-reset", action="store_true", help="Do not reset BS capacity each tick")
    p.add_argument("--prometheus", action="store_true", help="Expose Prometheus metrics endpoint")
    p.add_argument("--prometheus-port", type=int, default=8000)
    return p




def main() -> None:
    args = build_argparser().parse_args()
    sim_cfg = load_config(args.config)

    #scenario presets
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

    gen_cfg = RequestGenConfig(
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

    generator = RequestGenerator(gen_cfg)
    scheduler = RoundRobinScheduler()
    radio = RadioModel(gen_cfg.radio)

    sim = Simulator(
        base_stations=sim_cfg.base_stations,
        scheduler=scheduler,
        radio=radio,
        cfg=SimulatorConfig(
            verbose=args.verbose,
            log_dir=args.log_dir,
            reset_bs_each_tick=(not args.no_reset),
            enable_prometheus=args.prometheus,
            prometheus_port=args.prometheus_port,
        ),
    )

    summary = sim.run(generator.generate(sim_cfg.base_stations))

    print("\n=== SUMMARY ===")
    print(f"scheduler={scheduler.name()}")
    print(f"total_requests={summary.total_requests}")
    print(f"granted={summary.granted}")
    print(f"blocked={summary.blocked}")
    print(f"granted_per_bs={summary.granted_per_bs}")
    print(f"logs_written_to={Path(args.log_dir).resolve()}")


if __name__ == "__main__":
    main()
