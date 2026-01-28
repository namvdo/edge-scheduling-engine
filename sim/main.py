from __future__ import annotations

from pathlib import Path

from .config import load_config
from .generator import RequestGenConfig, RequestGenerator
from .scheduler_round_robin import RoundRobinScheduler
from .simulator import Simulator, SimulatorConfig


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg_path = root / "configs" / "base_stations.yaml"

    sim_cfg = load_config(cfg_path)

    scheduler = RoundRobinScheduler()

    gen_cfg = RequestGenConfig(
        seed=7,
        users=50,
        ticks=10,
        requests_per_tick=30,
        #qos_classes=["best-effort", "embb", "urllc"]  #I made this ready for later
    )
    generator = RequestGenerator(gen_cfg)

    simulator = Simulator(
        base_stations=sim_cfg.base_stations,
        scheduler=scheduler,
        cfg=SimulatorConfig(verbose=True, log_allocations=True),
    )

    summary = simulator.run(generator.generate())

    print("\n=== SUMMARY ===")
    print(f"total_requests={summary.total_requests}")
    print(f"granted={summary.granted}")
    print(f"blocked={summary.blocked}")
    print(f"granted_per_bs={summary.granted_per_bs}")


if __name__ == "__main__":
    main()
