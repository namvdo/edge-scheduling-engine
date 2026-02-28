import os
import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, explode, avg, sum as spark_sum, from_unixtime, to_timestamp, window

def run_analytics():
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    LOG_DIR = os.path.join(PROJECT_ROOT, "data", "logs")
    OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "output")
    
    if not os.path.exists(LOG_DIR) or not os.listdir(LOG_DIR):
        print(f"No logs found in {LOG_DIR}. Run the simulation first.")
        sys.exit(1)

    print("Initializing Spark Session...")
    spark = SparkSession.builder \
        .appName("EdgeSchedulerAnalytics") \
        .master("local[*]") \
        .getOrCreate()
        
    spark.sparkContext.setLogLevel("ERROR")

    print(f"Loading telemetry JSON logs from {LOG_DIR}...")
    # Read JSONL file
    df = spark.read.json(os.path.join(LOG_DIR, "telemetry.jsonl"))
    
    # df schema: timestamp_ms, cell_id, epoch, decision_version, tdd(dl_percent,ul_percent), ues[array]
    
    # 1. Explode UEs array to get one row per UE per epoch
    ues_df = df.select(
        col("timestamp_ms"),
        col("cell_id"),
        col("epoch"),
        explode(col("ues")).alias("ue")
    )

    # Flatten the struct
    flat_ues_df = ues_df.select(
        (col("timestamp_ms") / 1000).alias("timestamp_sec").cast("timestamp"),
        col("cell_id"),
        col("epoch"),
        col("ue.ue_id"),
        col("ue.slice_id"),
        col("ue.cqi"),
        col("ue.sinr_db"),
        col("ue.dl_buffer_bytes"),
        col("ue.ul_buffer_bytes"),
        col("ue.allocated_prbs")
    )

    print("\n--- Network Slice Demand Analysis ---")
    # Aggregate demand by slice_id to find which slice requires most resources
    slice_stats = flat_ues_df.groupBy("slice_id").agg(
        avg("cqi").alias("avg_cqi"),
        avg("sinr_db").alias("avg_sinr"),
        spark_sum("dl_buffer_bytes").alias("total_dl_demand_bytes"),
        spark_sum("ul_buffer_bytes").alias("total_ul_demand_bytes"),
        spark_sum("allocated_prbs").alias("total_prbs_allocated")
    ).orderBy(col("total_dl_demand_bytes").desc())

    slice_stats.show()

    print("\n--- Cell Load Analysis (Moving Window) ---")
    # Simulate a time window aggregation (e.g., 10 seconds tumbling window)
    cell_load = flat_ues_df.groupBy(
        window(col("timestamp_sec"), "10 seconds"),
        col("cell_id")
    ).agg(
        avg("dl_buffer_bytes").alias("avg_dl_buffer_per_ue"),
        spark_sum("allocated_prbs").alias("total_prb_utilization")
    ).orderBy("window")

    cell_load.show(truncate=False)

    # Save outputs to disk for the "Global Cloud Scheduler"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "slice_stats.csv")
    
    # Coalesce to 1 partition for a single CSV file output in this demo
    slice_stats.coalesce(1).write.mode("overwrite").csv(out_path, header=True)
    print(f"\nAnalytics complete. Output saved to {OUTPUT_DIR}")
    
    spark.stop()

if __name__ == "__main__":
    run_analytics()
