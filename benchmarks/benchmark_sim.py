from __future__ import annotations




import argparse
import time
from pathlib import Path
from ran_scheduler.config import load_config
from ran_scheduler.generator import RequestGenConfig, TrafficConfig, RequestGenerator
from ran_scheduler.metrics_store import CachedMetricsStore, SQLiteMetricsStore
from ran_scheduler.radio import RadioConfig, RadioModel
from ran_scheduler.scheduler_round_robin import RoundRobinScheduler
from ran_scheduler.simulator import Simulator, SimulatorConfig





def main() -> None:
    ap = argparse.ArgumentParser(description="performance benchmark + caching.")
    ap.add_argument("--config", default="configs/base_stations.yaml")
    ap.add_argument("--ticks", type=int, default=50)
    ap.add_argument("--users", type=int, default=1000)
    ap.add_argument("--req-per-tick", type=int, default=1000)
    ap.add_argument("--log-dir", default="logs-bench")
    ap.add_argument("--redis-url", default="", help="THIS IS OPTIONAL, MIGHT NEED IF WANT: redis://localhost:6379/0")
    args = ap.parse_args()

    sim_cfg = load_config(args.config)

    gen_cfg = RequestGenConfig(
        seed=7,
        users=args.users,
        ticks=args.ticks,
        traffic=TrafficConfig(base_requests_per_tick=args.req_per_tick, pattern="sine", peak_multiplier=2.0),
        qos_weights={"best-effort": 0.7, "embb": 0.2, "urllc": 0.1},
        mobility_mode="random_waypoint",
        radio=RadioConfig(seed=7),
    )

    generator = RequestGenerator(gen_cfg)
    scheduler = RoundRobinScheduler()
    radio = RadioModel(gen_cfg.radio)

    sim = Simulator(
        base_stations=sim_cfg.base_stations,
        scheduler=scheduler,
        radio=radio,
        cfg=SimulatorConfig(verbose=False, log_dir=args.log_dir, reset_bs_each_tick=True),
    )

    t0 = time.perf_counter()
    summary = sim.run(generator.generate(sim_cfg.base_stations))
    t1 = time.perf_counter()

    print("=== BENCHMARK ===")
    print(f"requests={summary.total_requests} granted={summary.granted} blocked={summary.blocked}")
    print(f"sim_wall_time_s={(t1 - t0):.3f}")

    #thisll store KPI rows to sqlite for query benchmarks
    db_path = Path(args.log_dir) / "kpi.sqlite"
    store = SQLiteMetricsStore(db_path)
    store.write_request_rows(sim.metrics.request_rows)
    store.write_tick_rows(sim.metrics.tick_rows)

    cached = CachedMetricsStore(store, redis_url=(args.redis_url or None), ttl_s=50.0) #the s can be changed, was 10



    #query benchmark
    q0 = time.perf_counter()
    for _ in range(2000):
        for tick in range(args.ticks):
            _ = cached.get_tick_row(tick)
    q1 = time.perf_counter()
    print(f"cached_tick_queries_s={(q1 - q0):.3f} (2000 x {args.ticks} reads)")



if __name__ == "__main__":
    main()
