from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ClusterConfig:
    node_id: str
    consensus_enabled: bool
    raft_peers: list[str]
    raft_port: int
    raft_address: str
    state_prefix: str

    @classmethod
    def from_env(cls) -> "ClusterConfig":
        peers = [e.strip() for e in os.getenv("RAFT_PEERS", "").split(",") if e.strip()]
        return cls(
            node_id=os.getenv("NODE_ID", "scheduler-1"),
            consensus_enabled=os.getenv("CONSENSUS_ENABLED", "false").lower() == "true",
            raft_peers=peers,
            raft_port=int(os.getenv("RAFT_PORT", "50052")),
            raft_address=os.getenv("RAFT_ADDRESS", "localhost:50052"),
            state_prefix=os.getenv("STATE_PREFIX", "/edge-scheduler"),
        )
