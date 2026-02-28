import os
import sys
import grpc
import pandas as pd
import time

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "gen"))

import scheduler_pb2
import scheduler_pb2_grpc

def orchestrate():
    """
    Simulates the Global Cloud Orchestrator.
    Runs slowly (e.g., every 10 seconds), reads PySpark analytics output,
    and pushes new slice policies down to the Edge Scheduler.
    """
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "output", "slice_stats.csv")
    
    # Default policy
    policy = {"eMBB": 1.0, "URLLC": 1.0, "mMTC": 1.0}

    print("--- Global Cloud Orchestrator Started ---")

    if not os.path.exists(OUTPUT_DIR):
        print(f"Waiting for PySpark analytics output at {OUTPUT_DIR}...")
        
    while True:
        try:
            if os.path.exists(OUTPUT_DIR):
                # Read the CSV output from the PySpark job
                # Spark writes directory with .csv parts, get the actual csv file
                csv_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.csv')]
                if csv_files:
                    latest_csv = os.path.join(OUTPUT_DIR, csv_files[0])
                    df = pd.read_csv(latest_csv)
                    
                    # Logic: If URLLC has high demand but low PRB allocation relative to eMBB, boost its weight.
                    urllc_row = df[df['slice_id'] == 'URLLC']
                    embb_row = df[df['slice_id'] == 'eMBB']
                    
                    if not urllc_row.empty and not embb_row.empty:
                        urllc_demand = urllc_row.iloc[0]['total_dl_demand_bytes']
                        embb_demand = embb_row.iloc[0]['total_dl_demand_bytes']
                        
                        # Example heuristic
                        if urllc_demand > embb_demand * 0.5:
                            policy["URLLC"] = 5.0 # Boost URLLC priority 5x
                        else:
                            policy["URLLC"] = 2.0
                            
                        print(f"[CLOUD] Re-calculated slice policy: {policy}")
            
            # Send the global policy to the Edge Scheduler Leader
            # (Assuming scheduler-1 is leader or routing is handled)
            edge_target = os.getenv("EDGE_SCHEDULER_URL", "localhost:50051")
            
            try:
                with grpc.insecure_channel(edge_target) as channel:
                    stub = scheduler_pb2_grpc.SchedulerServiceStub(channel)
                    req = scheduler_pb2.SlicePolicyRequest(slice_weights=policy)
                    resp = stub.UpdateSlicePolicy(req, timeout=2.0)
                    print(f"[CLOUD] Successfully pushed policy to Edge ({edge_target}): {resp.message}")
            except grpc.RpcError as e:
                print(f"[CLOUD] Warning: Could not reach Edge Scheduler: {e.details()}")

        except Exception as e:
            print(f"[CLOUD] Orchestration loop error: {e}")

        # Slow loop
        time.sleep(10)

if __name__ == "__main__":
    orchestrate()
