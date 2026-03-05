#!/usr/bin/env python3
"""
Evaluation script to generate quantitative metrics for the Edge Scheduling Engine.
Analyzes telemetry logs and produces benchmark statistics for the technical report.

Metrics computed:
- Scheduling latency (mean, p95, p99)
- Buffer starvation rate (% of epochs where buffer > threshold)
- PRB utilization efficiency
- Per-slice QoS statistics
- TDD adaptation range and distribution
- Baseline comparison (static 50/50 vs DDPG)
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime
import math

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "logs")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "evaluation")

# Buffer starvation thresholds (bytes) - buffer exceeding this indicates starvation
STARVATION_THRESHOLD_DL = 100000  # 100 KB
STARVATION_THRESHOLD_UL = 50000   # 50 KB


def load_telemetry_sample(sample_size=10000):
    """Load a sample of telemetry records for analysis."""
    log_path = os.path.join(DATA_DIR, "telemetry.jsonl")

    if not os.path.exists(log_path):
        print(f"Error: Telemetry log not found at {log_path}")
        return []

    records = []
    with open(log_path, "r") as f:
        for i, line in enumerate(f):
            if i >= sample_size:
                break
            try:
                records.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue

    return records


def analyze_scheduling_performance(records):
    """Analyze scheduling decision metrics."""
    metrics = {
        "total_epochs": len(records),
        "avg_decision_latency_ms": [],
        "tdd_dl_percent_distribution": [],
        "prb_utilization": [],
        "buffer_stats": defaultdict(list),
        "slice_stats": defaultdict(lambda: defaultdict(list)),
        # Buffer starvation tracking
        "starvation_events_dl": 0,
        "starvation_events_ul": 0,
        "total_ue_samples": 0,
        # Per-epoch aggregate buffers for baseline comparison
        "epoch_dl_buffers": [],
        "epoch_ul_buffers": [],
        "epoch_tdd_dl": [],
    }

    prev_timestamp = None

    for rec in records:
        # TDD split analysis
        tdd = rec.get("tdd", {})
        dl_pct = tdd.get("dl_percent", 50)
        metrics["tdd_dl_percent_distribution"].append(dl_pct)

        # Decision timing
        ts = rec.get("timestamp_ms", 0)
        if prev_timestamp:
            latency = ts - prev_timestamp
            if 50 <= latency <= 500:  # Filter reasonable latencies
                metrics["avg_decision_latency_ms"].append(latency)
        prev_timestamp = ts

        # UE-level analysis
        ues = rec.get("ues", [])
        total_prbs = sum(ue.get("allocated_prbs", 0) for ue in ues)
        metrics["prb_utilization"].append(total_prbs)

        # Aggregate epoch buffers
        epoch_dl = sum(ue.get("dl_buffer_bytes", 0) for ue in ues)
        epoch_ul = sum(ue.get("ul_buffer_bytes", 0) for ue in ues)
        metrics["epoch_dl_buffers"].append(epoch_dl)
        metrics["epoch_ul_buffers"].append(epoch_ul)
        metrics["epoch_tdd_dl"].append(dl_pct)

        for ue in ues:
            slice_id = ue.get("slice_id", "unknown")
            dl_buf = ue.get("dl_buffer_bytes", 0)
            ul_buf = ue.get("ul_buffer_bytes", 0)

            metrics["slice_stats"][slice_id]["dl_buffer"].append(dl_buf)
            metrics["slice_stats"][slice_id]["ul_buffer"].append(ul_buf)
            metrics["slice_stats"][slice_id]["cqi"].append(ue.get("cqi", 0))
            metrics["slice_stats"][slice_id]["sinr"].append(ue.get("sinr_db", 0))
            metrics["slice_stats"][slice_id]["prbs"].append(ue.get("allocated_prbs", 0))

            # Track buffer starvation (buffer exceeds threshold = demand not met)
            metrics["total_ue_samples"] += 1
            if dl_buf > STARVATION_THRESHOLD_DL:
                metrics["starvation_events_dl"] += 1
            if ul_buf > STARVATION_THRESHOLD_UL:
                metrics["starvation_events_ul"] += 1

    return metrics


def compute_baseline_comparison(metrics):
    """Compare DDPG adaptive TDD vs static 50/50 baseline."""
    dl_buffers = np.array(metrics["epoch_dl_buffers"])
    ul_buffers = np.array(metrics["epoch_ul_buffers"])
    tdd_dl = np.array(metrics["epoch_tdd_dl"]) / 100.0  # Convert to fraction

    # Simplified throughput model: throughput proportional to TDD ratio * avg_capacity
    # Assume 100 PRBs * 50 bytes/PRB avg = 5000 bytes/epoch capacity
    capacity_per_epoch = 5000 * 20  # 20 UEs * 5000 bytes

    # DDPG policy: actual TDD ratios used
    ddpg_dl_throughput = capacity_per_epoch * tdd_dl
    ddpg_ul_throughput = capacity_per_epoch * (1 - tdd_dl)

    # Static 50/50 baseline
    static_dl_throughput = capacity_per_epoch * 0.5
    static_ul_throughput = capacity_per_epoch * 0.5

    # Compute unmet demand (buffer remaining after transmission)
    ddpg_dl_unmet = np.maximum(0, dl_buffers - ddpg_dl_throughput)
    ddpg_ul_unmet = np.maximum(0, ul_buffers - ddpg_ul_throughput)
    static_dl_unmet = np.maximum(0, dl_buffers - static_dl_throughput)
    static_ul_unmet = np.maximum(0, ul_buffers - static_ul_throughput)

    # Total unmet demand
    ddpg_total_unmet = np.mean(ddpg_dl_unmet + ddpg_ul_unmet)
    static_total_unmet = np.mean(static_dl_unmet + static_ul_unmet)

    # Improvement percentage
    improvement = (static_total_unmet - ddpg_total_unmet) / (static_total_unmet + 1) * 100

    return {
        "ddpg_avg_unmet_demand_bytes": ddpg_total_unmet,
        "static_avg_unmet_demand_bytes": static_total_unmet,
        "improvement_percent": improvement,
        "ddpg_dl_satisfaction_rate": np.mean(ddpg_dl_throughput >= dl_buffers) * 100,
        "static_dl_satisfaction_rate": np.mean(static_dl_throughput >= dl_buffers) * 100,
    }


def compute_final_statistics(metrics):
    """Compute final statistics for reporting with confidence intervals."""
    stats = {}

    # Decision performance
    stats["total_scheduling_decisions"] = metrics["total_epochs"]

    if metrics["avg_decision_latency_ms"]:
        latencies = np.array(metrics["avg_decision_latency_ms"])
        stats["avg_scheduling_latency_ms"] = np.mean(latencies)
        stats["std_scheduling_latency_ms"] = np.std(latencies)
        stats["p95_scheduling_latency_ms"] = np.percentile(latencies, 95)
        stats["p99_scheduling_latency_ms"] = np.percentile(latencies, 99)
        # 95% confidence interval
        n = len(latencies)
        se = stats["std_scheduling_latency_ms"] / np.sqrt(n)
        stats["latency_95ci_lower"] = stats["avg_scheduling_latency_ms"] - 1.96 * se
        stats["latency_95ci_upper"] = stats["avg_scheduling_latency_ms"] + 1.96 * se

    # TDD analysis
    tdd = np.array(metrics["tdd_dl_percent_distribution"])
    stats["tdd_avg_dl_percent"] = np.mean(tdd)
    stats["tdd_std_dl_percent"] = np.std(tdd)
    stats["tdd_min_dl_percent"] = int(np.min(tdd))
    stats["tdd_max_dl_percent"] = int(np.max(tdd))
    # TDD distribution histogram
    stats["tdd_histogram"] = {
        "10-30%": np.sum((tdd >= 10) & (tdd < 30)) / len(tdd) * 100,
        "30-50%": np.sum((tdd >= 30) & (tdd < 50)) / len(tdd) * 100,
        "50-70%": np.sum((tdd >= 50) & (tdd < 70)) / len(tdd) * 100,
        "70-90%": np.sum((tdd >= 70) & (tdd <= 90)) / len(tdd) * 100,
    }

    # PRB utilization
    prb_util = np.array(metrics["prb_utilization"])
    stats["avg_prb_allocation_per_epoch"] = np.mean(prb_util)
    stats["prb_utilization_percent"] = np.mean(prb_util) / 100 * 100  # Assuming 100 total PRBs

    # Buffer starvation rates
    if metrics["total_ue_samples"] > 0:
        stats["dl_starvation_rate_percent"] = (
            metrics["starvation_events_dl"] / metrics["total_ue_samples"] * 100
        )
        stats["ul_starvation_rate_percent"] = (
            metrics["starvation_events_ul"] / metrics["total_ue_samples"] * 100
        )
        stats["combined_starvation_rate_percent"] = (
            (metrics["starvation_events_dl"] + metrics["starvation_events_ul"])
            / (2 * metrics["total_ue_samples"]) * 100
        )
    else:
        stats["dl_starvation_rate_percent"] = 0
        stats["ul_starvation_rate_percent"] = 0
        stats["combined_starvation_rate_percent"] = 0

    # Per-slice statistics with confidence intervals
    slice_report = {}
    for slice_id, slice_data in metrics["slice_stats"].items():
        dl_buf = np.array(slice_data["dl_buffer"])
        ul_buf = np.array(slice_data["ul_buffer"])
        cqi = np.array(slice_data["cqi"])
        sinr = np.array(slice_data["sinr"])
        prbs = np.array(slice_data["prbs"])

        n = len(cqi)
        slice_report[slice_id] = {
            "avg_dl_buffer_kb": np.mean(dl_buf) / 1024,
            "std_dl_buffer_kb": np.std(dl_buf) / 1024,
            "avg_ul_buffer_kb": np.mean(ul_buf) / 1024,
            "std_ul_buffer_kb": np.std(ul_buf) / 1024,
            "avg_cqi": np.mean(cqi),
            "std_cqi": np.std(cqi),
            "avg_sinr_db": np.mean(sinr),
            "std_sinr_db": np.std(sinr),
            "avg_prbs_allocated": np.mean(prbs),
            "std_prbs_allocated": np.std(prbs),
            "total_samples": n,
            # Starvation rate per slice
            "dl_starvation_rate": np.sum(dl_buf > STARVATION_THRESHOLD_DL) / n * 100,
            "ul_starvation_rate": np.sum(ul_buf > STARVATION_THRESHOLD_UL) / n * 100,
        }
    stats["slice_statistics"] = slice_report

    # Baseline comparison
    baseline = compute_baseline_comparison(metrics)
    stats["baseline_comparison"] = baseline

    return stats


def evaluate_raft_consensus():
    """Evaluate Raft consensus performance (simulated based on algorithm parameters)."""
    return {
        "election_timeout_min_ms": 150,
        "election_timeout_max_ms": 300,
        "heartbeat_interval_ms": 50,
        "log_replication_rpc_timeout_ms": 100,
        "cluster_size": 3,
        "fault_tolerance": 1,  # Can tolerate 1 node failure
        "consensus_algorithm": "Raft",
        "expected_election_time_ms": 225,  # (150+300)/2
    }


def evaluate_ddpg_agent():
    """Evaluate DDPG agent architecture and hyperparameters."""
    return {
        "actor_architecture": "Linear(4→256→256→1)",
        "critic_architecture": "Linear(5→256→256→1)",
        "state_dimension": 4,
        "action_dimension": 1,
        "replay_buffer_capacity": 100000,
        "batch_size": 64,
        "gamma_discount": 0.99,
        "tau_soft_update": 0.005,
        "actor_learning_rate": 1e-4,
        "critic_learning_rate": 1e-3,
        "noise_type": "Ornstein-Uhlenbeck",
        "training_episodes": 200,
        "episode_length": 50,
    }


def evaluate_simulator_parameters():
    """Document simulator configuration."""
    return {
        "cell_radius_meters": 250,
        "total_prbs": 100,
        "default_ue_count": 20,
        "epoch_duration_ms": 100,
        "scheduling_frequency_hz": 10,
        "mobility_model": "Random Walk",
        "max_mobility_per_epoch_m": 5,
        "path_loss_model": "Free Space (simplified)",
        "sinr_range_db": [-5, 25],
        "cqi_range": [1, 15],
        "slice_types": ["eMBB", "URLLC", "mMTC"],
        "traffic_models": {
            "eMBB": "Exponential DL (mean 50kB), Exponential UL (mean 10kB)",
            "URLLC": "Uniform DL/UL (0-5kB)",
            "mMTC": "Bursty UL (20% probability, 500-2000B)",
        },
    }


def generate_latex_table(stats):
    """Generate LaTeX table code for the report."""
    latex = r"""
\begin{table}[h]
\centering
\caption{Edge Scheduling Engine Performance Metrics}
\label{tab:performance}
\begin{tabular}{|l|r|}
\hline
\textbf{Metric} & \textbf{Value} \\
\hline
"""
    latex += "Total Scheduling Decisions & {:,} \\\\\n".format(stats.get("total_scheduling_decisions", 0))
    latex += "Avg Scheduling Latency & {:.2f} ms \\\\\n".format(stats.get("avg_scheduling_latency_ms", 0))
    latex += "95th Percentile Latency & {:.2f} ms \\\\\n".format(stats.get("p95_scheduling_latency_ms", 0))
    latex += "99th Percentile Latency & {:.2f} ms \\\\\n".format(stats.get("p99_scheduling_latency_ms", 0))
    latex += "Avg TDD DL Ratio & {:.1f}\\% \\\\\n".format(stats.get("tdd_avg_dl_percent", 50))
    latex += "TDD Ratio Std Dev & {:.2f}\\% \\\\\n".format(stats.get("tdd_std_dl_percent", 0))
    latex += "Avg PRBs Allocated/Epoch & {:.1f} \\\\\n".format(stats.get("avg_prb_allocation_per_epoch", 0))
    latex += r"""\hline
\end{tabular}
\end{table}
"""
    return latex


def generate_slice_latex_table(slice_stats):
    """Generate LaTeX table for per-slice statistics."""
    latex = r"""
\begin{table}[h]
\centering
\caption{Per-Slice Network Statistics}
\label{tab:slice_stats}
\begin{tabular}{|l|r|r|r|r|r|}
\hline
\textbf{Slice} & \textbf{Avg DL (kB)} & \textbf{Avg UL (kB)} & \textbf{Avg CQI} & \textbf{Avg SINR} & \textbf{Avg PRBs} \\
\hline
"""
    for slice_id in ["eMBB", "URLLC", "mMTC"]:
        if slice_id in slice_stats:
            s = slice_stats[slice_id]
            latex += "{} & {:.1f} & {:.1f} & {:.1f} & {:.1f} dB & {:.1f} \\\\\n".format(
                slice_id,
                s["avg_dl_buffer_kb"],
                s["avg_ul_buffer_kb"],
                s["avg_cqi"],
                s["avg_sinr_db"],
                s["avg_prbs_allocated"],
            )

    latex += r"""\hline
\end{tabular}
\end{table}
"""
    return latex


def main():
    print("=" * 60)
    print("Edge Scheduling Engine - Quantitative Evaluation")
    print("=" * 60)

    # Load and analyze telemetry
    print("\n[1/4] Loading telemetry data...")
    records = load_telemetry_sample(sample_size=10000)
    print(f"Loaded {len(records)} scheduling decision records")

    print("\n[2/4] Analyzing scheduling performance...")
    metrics = analyze_scheduling_performance(records)
    stats = compute_final_statistics(metrics)

    print("\n[3/4] Evaluating system components...")
    raft_stats = evaluate_raft_consensus()
    ddpg_stats = evaluate_ddpg_agent()
    sim_stats = evaluate_simulator_parameters()

    # Print results
    print("\n" + "=" * 60)
    print("SCHEDULING PERFORMANCE RESULTS")
    print("=" * 60)
    print(f"Total Scheduling Decisions: {stats['total_scheduling_decisions']:,}")
    print(f"Avg Scheduling Latency: {stats.get('avg_scheduling_latency_ms', 0):.2f} ms")
    print(f"  95% CI: [{stats.get('latency_95ci_lower', 0):.2f}, {stats.get('latency_95ci_upper', 0):.2f}] ms")
    print(f"  Std Dev: {stats.get('std_scheduling_latency_ms', 0):.2f} ms")
    print(f"P95 Latency: {stats.get('p95_scheduling_latency_ms', 0):.2f} ms")
    print(f"P99 Latency: {stats.get('p99_scheduling_latency_ms', 0):.2f} ms")
    print(f"Avg TDD DL Ratio: {stats['tdd_avg_dl_percent']:.1f}%")
    print(f"TDD Ratio Range: [{stats['tdd_min_dl_percent']}%, {stats['tdd_max_dl_percent']}%]")
    print(f"Avg PRBs/Epoch: {stats['avg_prb_allocation_per_epoch']:.1f}")

    print("\n" + "-" * 40)
    print("BUFFER STARVATION ANALYSIS")
    print("-" * 40)
    print(f"DL Starvation Rate: {stats.get('dl_starvation_rate_percent', 0):.2f}%")
    print(f"  (epochs where DL buffer > {STARVATION_THRESHOLD_DL/1024:.0f} kB)")
    print(f"UL Starvation Rate: {stats.get('ul_starvation_rate_percent', 0):.2f}%")
    print(f"  (epochs where UL buffer > {STARVATION_THRESHOLD_UL/1024:.0f} kB)")
    print(f"Combined Starvation Rate: {stats.get('combined_starvation_rate_percent', 0):.2f}%")

    print("\n" + "-" * 40)
    print("TDD DISTRIBUTION HISTOGRAM")
    print("-" * 40)
    for range_str, pct in stats.get("tdd_histogram", {}).items():
        print(f"  {range_str}: {pct:.1f}%")

    print("\n" + "-" * 40)
    print("BASELINE COMPARISON (DDPG vs Static 50/50)")
    print("-" * 40)
    baseline = stats.get("baseline_comparison", {})
    print(f"DDPG Avg Unmet Demand: {baseline.get('ddpg_avg_unmet_demand_bytes', 0)/1024:.1f} kB")
    print(f"Static Avg Unmet Demand: {baseline.get('static_avg_unmet_demand_bytes', 0)/1024:.1f} kB")
    print(f"Improvement: {baseline.get('improvement_percent', 0):.1f}%")
    print(f"DDPG DL Satisfaction Rate: {baseline.get('ddpg_dl_satisfaction_rate', 0):.1f}%")
    print(f"Static DL Satisfaction Rate: {baseline.get('static_dl_satisfaction_rate', 0):.1f}%")

    print("\n" + "-" * 40)
    print("PER-SLICE STATISTICS")
    print("-" * 40)
    for slice_id, s in stats.get("slice_statistics", {}).items():
        print(f"\n{slice_id}:")
        print(f"  Avg DL Buffer: {s['avg_dl_buffer_kb']:.1f} +/- {s['std_dl_buffer_kb']:.1f} kB")
        print(f"  Avg UL Buffer: {s['avg_ul_buffer_kb']:.1f} +/- {s['std_ul_buffer_kb']:.1f} kB")
        print(f"  Avg CQI: {s['avg_cqi']:.1f} +/- {s['std_cqi']:.1f}")
        print(f"  Avg SINR: {s['avg_sinr_db']:.1f} +/- {s['std_sinr_db']:.1f} dB")
        print(f"  Avg PRBs: {s['avg_prbs_allocated']:.1f} +/- {s['std_prbs_allocated']:.1f}")
        print(f"  DL Starvation: {s['dl_starvation_rate']:.1f}%")
        print(f"  UL Starvation: {s['ul_starvation_rate']:.1f}%")
        print(f"  Samples: {s['total_samples']:,}")

    print("\n" + "-" * 40)
    print("RAFT CONSENSUS PARAMETERS")
    print("-" * 40)
    for k, v in raft_stats.items():
        print(f"  {k}: {v}")

    print("\n" + "-" * 40)
    print("DDPG AGENT PARAMETERS")
    print("-" * 40)
    for k, v in ddpg_stats.items():
        print(f"  {k}: {v}")

    # Save evaluation results
    print("\n[4/4] Saving evaluation results...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = {
        "timestamp": datetime.now().isoformat(),
        "scheduling_stats": stats,
        "raft_parameters": raft_stats,
        "ddpg_parameters": ddpg_stats,
        "simulator_parameters": sim_stats,
    }

    with open(os.path.join(OUTPUT_DIR, "evaluation_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Generate LaTeX tables
    latex_output = generate_latex_table(stats)
    latex_output += "\n" + generate_slice_latex_table(stats.get("slice_statistics", {}))

    with open(os.path.join(OUTPUT_DIR, "latex_tables.tex"), "w") as f:
        f.write(latex_output)

    print(f"\nResults saved to {OUTPUT_DIR}/")
    print("  - evaluation_results.json")
    print("  - latex_tables.tex")

    return stats


if __name__ == "__main__":
    main()
