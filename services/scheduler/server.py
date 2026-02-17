import time
from concurrent import futures

import grpc


# Add generated code folder to path (simple approach for student projects)
import os, sys
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "gen"))

from gen import scheduler_pb2
from gen import scheduler_pb2_grpc
from gen import telemetry_pb2

def simple_pf_allocate(cell: telemetry_pb2.CellTelemetry):
    """
    Very simple proportional-fair-ish allocator:
    score = demand / (avg_throughput+1)
    allocate PRBs proportional to score.
    """
    total_prbs = max(1, int(cell.total_prbs))
    scores = []
    for ue in cell.ues:
        demand = float(ue.dl_buffer_bytes + ue.ul_buffer_bytes)
        avg_tp = float(ue.avg_throughput_kbps)
        score = demand / (avg_tp + 1.0)
        scores.append((ue.ue_id, score))

    score_sum = sum(s for _, s in scores) or 1.0

    # Allocate PRBs
    allocations = []
    prb_assigned = 0
    for ue_id, score in scores:
        prbs = int(round(total_prbs * (score / score_sum)))
        allocations.append((ue_id, prbs))
        prb_assigned += prbs

    # Fix rounding drift: adjust last UE to match total_prbs
    if allocations:
        drift = total_prbs - prb_assigned
        last_ue, last_prbs = allocations[-1]
        allocations[-1] = (last_ue, max(0, last_prbs + drift))

    return allocations


def dynamic_tdd(cell: telemetry_pb2.CellTelemetry):
    """
    Rule-based dynamic TDD:
    If DL buffer dominates -> more DL percent; if UL dominates -> more UL.
    Add a simple clamp and balanced fallback.
    """
    dl = sum(u.dl_buffer_bytes for u in cell.ues)
    ul = sum(u.ul_buffer_bytes for u in cell.ues)

    if dl > 2 * ul:
        return 70, 30
    if ul > 2 * dl:
        return 40, 60
    return 50, 50


class SchedulerService(scheduler_pb2_grpc.SchedulerServiceServicer):
    def __init__(self):
        self._decision_version = 0

    def Ping(self, request, context):
        return scheduler_pb2.Ack(ok=True, message="pong")

    def Schedule(self, request_iterator, context):
        """
        Bidirectional stream:
        Base station sends CellTelemetry; Scheduler yields ScheduleDecision.
        """
        for cell in request_iterator:
            self._decision_version += 1

            dl_pct, ul_pct = dynamic_tdd(cell)
            allocs = simple_pf_allocate(cell)

            decision = scheduler_pb2.ScheduleDecision(
                cell_id=cell.cell_id,
                epoch=cell.epoch,
                decision_version=self._decision_version,
                tdd=scheduler_pb2.TddConfig(dl_percent=dl_pct, ul_percent=ul_pct),
                allocations=[
                    scheduler_pb2.UeAllocation(ue_id=ue_id, prbs=prbs, weight=0.0)
                    for ue_id, prbs in allocs
                ],
            )

            print(
                f"[SCHED] cell={cell.cell_id} epoch={cell.epoch} "
                f"ver={decision.decision_version} tdd={dl_pct}/{ul_pct} "
                f"ues={len(cell.ues)}"
            )

            yield decision


def serve(host="0.0.0.0", port=50051):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    scheduler_pb2_grpc.add_SchedulerServiceServicer_to_server(SchedulerService(), server)

    listen_addr = f"{host}:{port}"
    server.add_insecure_port(listen_addr)
    server.start()
    print(f"Scheduler gRPC server running on {listen_addr}")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("Shutting down server...")
        server.stop(0)


if __name__ == "__main__":
    serve()