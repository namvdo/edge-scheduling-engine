from __future__ import annotations

import os
import sys
import time
import logging
from concurrent import futures

logging.basicConfig(level=logging.INFO)

import grpc

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv() -> None:
        return None


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GEN_DIR = os.path.join(PROJECT_ROOT, "gen")
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
if GEN_DIR not in sys.path:
    sys.path.append(GEN_DIR)

import scheduler_pb2
import scheduler_pb2_grpc
import telemetry_pb2

import json
import torch
import numpy as np
from services.scheduler.ml.ddpg_agent import DDPGAgent
from services.scheduler.cluster import (
    ClusterConfig,
    RaftNode,
    RaftState,
    RaftGrpcServer,
)


def simple_pf_allocate(cell: telemetry_pb2.CellTelemetry):
    """Simple PF-style allocator for demo traffic."""
    total_prbs = max(1, int(cell.total_prbs))
    scores = []
    for ue in cell.ues:
        demand = float(ue.dl_buffer_bytes + ue.ul_buffer_bytes)
        avg_tp = float(ue.avg_throughput_kbps)
        score = demand / (avg_tp + 1.0)
        scores.append((ue.ue_id, score))

    score_sum = sum(s for _, s in scores) or 1.0

    allocations = []
    prb_assigned = 0
    for ue_id, score in scores:
        prbs = int(round(total_prbs * (score / score_sum)))
        allocations.append((ue_id, prbs))
        prb_assigned += prbs

    if allocations:
        drift = total_prbs - prb_assigned
        last_ue, last_prbs = allocations[-1]
        allocations[-1] = (last_ue, max(0, last_prbs + drift))

    return allocations


def dynamic_tdd(cell: telemetry_pb2.CellTelemetry):
    """Rule-based dynamic TDD for demo traffic."""
    dl = sum(u.dl_buffer_bytes for u in cell.ues)
    ul = sum(u.ul_buffer_bytes for u in cell.ues)

    if dl > 2 * ul:
        return 70, 30
    if ul > 2 * dl:
        return 40, 60
    return 50, 50


class SchedulerService(scheduler_pb2_grpc.SchedulerServiceServicer):
    def __init__(self):
        self._decision_versions: dict[str, int] = {}

        load_dotenv()
        self.cluster_cfg = ClusterConfig.from_env()

        self.consensus_enabled = False
        self.raft_node: RaftNode | None = None
        self.raft_server: RaftGrpcServer | None = None

        self.ddpg_agent = DDPGAgent(state_dim=4, action_dim=1, max_action=1.0, device="cpu")
        model_path = os.path.join(PROJECT_ROOT, "models", "ddpg_actor.pth")
        if os.path.exists(model_path):
            self.ddpg_agent.actor.load_state_dict(torch.load(model_path, map_location="cpu"))
            print(f"[ML] Loaded DDPG Actor from {model_path}")
        else:
            print("[ML] No trained DDPG model found, using random weights")

        if self.cluster_cfg.consensus_enabled:
            try:
                peers = [p for p in self.cluster_cfg.raft_peers if p != self.cluster_cfg.raft_address]
                self.raft_node = RaftNode(
                    node_id=self.cluster_cfg.node_id,
                    peers=peers,
                    state_prefix=self.cluster_cfg.state_prefix
                )
                self.raft_server = RaftGrpcServer(
                    node=self.raft_node,
                    port=self.cluster_cfg.raft_port
                )
                
                self.raft_node.start()
                self.raft_server.start()
                self.consensus_enabled = True
                print(
                    f"[CLUSTER] consensus enabled node={self.cluster_cfg.node_id} "
                    f"raft_peers={','.join(self.cluster_cfg.raft_peers)}"
                )
            except Exception as exc:
                print(f"[CLUSTER] consensus disabled due to startup error: {exc}")

    def _load_recovered_version(self, cell_id: str) -> None:
        if cell_id in self._decision_versions:
            return
        recovered = 0
        if self.consensus_enabled and self.raft_node:
            latest_str = self.raft_node.get_latest_committed()
            if latest_str:
                try:
                    payload = json.loads(latest_str)
                    if payload.get("cell_id") == cell_id:
                        recovered = payload.get("decision_version", 0)
                except Exception:
                    pass
        self._decision_versions[cell_id] = recovered
        if recovered > 0:
            print(f"[RECOVERY] cell={cell_id} recovered_version={recovered}")

    def _try_lead_cell(self, cell_id: str) -> bool:
        if not self.consensus_enabled or not self.raft_node:
            return True
        if self.raft_node.state == RaftState.LEADER:
            return True
        print(f"[FOLLOWER] cell={cell_id} local={self.cluster_cfg.node_id} is follower")
        return False

    def Ping(self, request, context):
        return scheduler_pb2.Ack(ok=True, message="pong")

    def Schedule(self, request_iterator, context):
        """Bidirectional stream with optional consensus guardrails."""
        for cell in request_iterator:
            self._load_recovered_version(cell.cell_id)

            if not self._try_lead_cell(cell.cell_id):
                latest_str = self.raft_node.get_latest_committed() if self.raft_node else None
                latest = json.loads(latest_str) if latest_str else None
                if latest and latest.get("cell_id") == cell.cell_id:
                    # Return last committed decision to avoid diverging output on followers.
                    yield scheduler_pb2.ScheduleDecision(
                        cell_id=cell.cell_id,
                        epoch=cell.epoch,
                        decision_version=int(latest.get("decision_version", 0)),
                        tdd=scheduler_pb2.TddConfig(
                            dl_percent=int(latest.get("dl_percent", 50)),
                            ul_percent=int(latest.get("ul_percent", 50)),
                        ),
                        allocations=[
                            scheduler_pb2.UeAllocation(
                                ue_id=a["ue_id"],
                                prbs=int(a["prbs"]),
                                weight=float(a.get("weight", 0.0)),
                            )
                            for a in latest.get("allocations", [])
                        ],
                    )
                continue

            self._decision_versions[cell.cell_id] += 1
            decision_version = self._decision_versions[cell.cell_id]

            if len(cell.ues) > 0:
                dl_buf = sum(u.dl_buffer_bytes for u in cell.ues) / len(cell.ues)
                ul_buf = sum(u.ul_buffer_bytes for u in cell.ues) / len(cell.ues)
                cqi = sum(u.cqi for u in cell.ues) / len(cell.ues)
                sinr = sum(u.sinr_db for u in cell.ues) / len(cell.ues)
                state = np.array([dl_buf/50000.0, ul_buf/30000.0, cqi/15.0, sinr/25.0], dtype=np.float32)
                action = self.ddpg_agent.select_action(state, add_noise=False)
                dl_pct = int(action[0] * 100)
                dl_pct = max(10, min(90, dl_pct))
                ul_pct = 100 - dl_pct
            else:
                dl_pct, ul_pct = 50, 50

            allocs = simple_pf_allocate(cell)

            decision = scheduler_pb2.ScheduleDecision(
                cell_id=cell.cell_id,
                epoch=cell.epoch,
                decision_version=decision_version,
                tdd=scheduler_pb2.TddConfig(dl_percent=dl_pct, ul_percent=ul_pct),
                allocations=[
                    scheduler_pb2.UeAllocation(ue_id=ue_id, prbs=prbs, weight=0.0)
                    for ue_id, prbs in allocs
                ],
            )

            if self.consensus_enabled and self.raft_node:
                decision_dict = {
                    "cell_id": cell.cell_id,
                    "epoch": int(cell.epoch),
                    "decision_version": decision_version,
                    "dl_percent": dl_pct,
                    "ul_percent": ul_pct,
                    "allocations": [
                        {"ue_id": ue_id, "prbs": prbs, "weight": 0.0}
                        for ue_id, prbs in allocs
                    ],
                }
                self.raft_node.propose(json.dumps(decision_dict))

            print(
                f"[SCHED] cell={cell.cell_id} epoch={cell.epoch} "
                f"ver={decision.decision_version} tdd={dl_pct}/{ul_pct} "
                f"ues={len(cell.ues)}"
            )

            yield decision


def serve():
    load_dotenv()
    host = os.getenv("SCHEDULER_HOST", "0.0.0.0")
    port = int(os.getenv("SCHEDULER_PORT", "50051"))

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
