import random
import time
import grpc

import os, sys
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "gen"))

import scheduler_pb2
import scheduler_pb2_grpc
import telemetry_pb2

def telemetry_stream(cell_id="cell-1", total_prbs=50, ue_count=8, epochs=50):
    """
    Generates simulated telemetry every 100ms.
    """
    avg_tp = {f"ue-{i+1}": 100 for i in range(ue_count)}  # simple moving throughput
    for epoch in range(epochs):
        ues = []
        for i in range(ue_count):
            ue_id = f"ue-{i+1}"
            slice_id = random.choice(["eMBB", "URLLC", "mMTC"])
            cqi = random.randint(1, 15)
            sinr = random.uniform(-5.0, 25.0)

            # Simulated buffers (bytes)
            dl_buf = random.randint(0, 50000)
            ul_buf = random.randint(0, 30000)

            ues.append(
                telemetry_pb2.UeReport(
                    ue_id=ue_id,
                    slice_id=slice_id,
                    cqi=cqi,
                    sinr_db=sinr,
                    dl_buffer_bytes=dl_buf,
                    ul_buffer_bytes=ul_buf,
                    avg_throughput_kbps=avg_tp[ue_id],
                )
            )

        msg = telemetry_pb2.CellTelemetry(
            cell_id=cell_id,
            epoch=epoch,
            timestamp_ms=int(time.time() * 1000),
            total_prbs=total_prbs,
            prb_utilization=0.0,
            ues=ues,
        )

        yield msg
        time.sleep(0.1)  # 100ms epoch


def run(target="localhost:50051", cell_id="cell-1"):
    with grpc.insecure_channel(target) as channel:
        stub = scheduler_pb2_grpc.SchedulerServiceStub(channel)

        decisions = stub.Schedule(telemetry_stream(cell_id=cell_id))
        for d in decisions:
            top3 = sorted(d.allocations, key=lambda x: x.prbs, reverse=True)[:3]
            top3_str = ", ".join([f"{a.ue_id}:{a.prbs}" for a in top3])
            print(
                f"[BS] cell={d.cell_id} epoch={d.epoch} ver={d.decision_version} "
                f"TDD DL/UL={d.tdd.dl_percent}/{d.tdd.ul_percent} top={top3_str}"
            )


if __name__ == "__main__":
    run()