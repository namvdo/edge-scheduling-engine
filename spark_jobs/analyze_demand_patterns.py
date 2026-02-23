from __future__ import annotations



import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean





def analyze_with_stdlib(input_csv: Path) -> dict:
    by_tick = defaultdict(list)
    by_bs = Counter()
    by_qos = Counter()
    latencies = []
    thr = []

    with input_csv.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            tick = int(row["tick"])
            by_tick[tick].append(row)
            if row.get("bs_id"):
                by_bs[row["bs_id"]] += 1
            by_qos[row["qos_class"]] += 1
            latencies.append(float(row["scheduler_latency_ms"]))
            thr.append(float(row["estimated_throughput_mbps"]))

    tick_counts = {t: len(rows) for t, rows in by_tick.items()}
    top_ticks = sorted(tick_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "input": str(input_csv),
        "total_rows": sum(tick_counts.values()),
        "top_ticks_by_request_volume": top_ticks,
        "base_station_hotspots": by_bs.most_common(),
        "qos_distribution": by_qos.most_common(),
        "avg_scheduler_latency_ms": mean(latencies) if latencies else 0.0,
        "avg_estimated_throughput_mbps": mean(thr) if thr else 0.0,
    }




def analyze_with_spark(input_csv: Path) -> dict:
    from pyspark.sql import SparkSession
    from pyspark.sql.functions import col, count, avg

    spark = SparkSession.builder.appName("RAN-Demand-Patterns").getOrCreate()
    df = spark.read.option("header", "true").csv(str(input_csv))
    df = (
        df.withColumn("tick", col("tick").cast("int"))
        .withColumn("scheduler_latency_ms", col("scheduler_latency_ms").cast("double"))
        .withColumn("estimated_throughput_mbps", col("estimated_throughput_mbps").cast("double"))
    )

    top_ticks = (
        df.groupBy("tick")
        .agg(count("*").alias("requests"))
        .orderBy(col("requests").desc())
        .limit(5)
        .collect()
    )

    hotspots = (
        df.where(col("bs_id").isNotNull())
        .groupBy("bs_id")
        .agg(count("*").alias("allocations"))
        .orderBy(col("allocations").desc())
        .collect()
    )

    qos = (
        df.groupBy("qos_class")
        .agg(count("*").alias("requests"))
        .orderBy(col("requests").desc())
        .collect()
    )

    avgs = df.agg(avg("scheduler_latency_ms").alias("avg_lat"), avg("estimated_throughput_mbps").alias("avg_thr")).collect()[0]

    out = {
        "input": str(input_csv),
        "total_rows": df.count(),
        "top_ticks_by_request_volume": [(int(r["tick"]), int(r["requests"])) for r in top_ticks],
        "base_station_hotspots": [(r["bs_id"], int(r["allocations"])) for r in hotspots],
        "qos_distribution": [(r["qos_class"], int(r["requests"])) for r in qos],
        "avg_scheduler_latency_ms": float(avgs["avg_lat"]) if avgs["avg_lat"] is not None else 0.0,
        "avg_estimated_throughput_mbps": float(avgs["avg_thr"]) if avgs["avg_thr"] is not None else 0.0,
    }

    spark.stop()
    return out





def main() -> None:
    ap = argparse.ArgumentParser(description="Week 4 (Miika): batch analytics over KPI exports.")
    ap.add_argument("--input", default="logs/requests_kpi.csv", help="CSV from simulator (requests_kpi.csv)")
    ap.add_argument("--output", default="reports/demand_patterns.json")
    ap.add_argument("--use-spark", action="store_true", help="Use PySpark if available")
    args = ap.parse_args()

    input_csv = Path(args.input)
    if not input_csv.exists():
        raise SystemExit(f"Input not found: {input_csv}")

    if args.use_spark:
        try:
            report = analyze_with_spark(input_csv)
        except Exception:
            report = analyze_with_stdlib(input_csv)
    else:
        report = analyze_with_stdlib(input_csv)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote report to {out_path.resolve()}")



if __name__ == "__main__":
    main()
