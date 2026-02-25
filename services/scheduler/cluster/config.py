from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ClusterConfig:
    node_id: str
    consensus_enabled: bool
    etcd_endpoints: list[str]
    etcd_dial_timeout_sec: float
    lease_ttl_sec: int
    state_prefix: str


    @classmethod
    def from_env(cls) -> "ClusterConfig":
        endpoints = [e.strip() for e in os.getenv("ETCD_ENDPOINTS", "localhost:2379").split(",") if e.strip()]
        return cls(
            node_id=os.getenv("NODE_ID", "scheduler-1"),
            consensus_enabled=os.getenv("CONSENSUS_ENABLED", "false").lower() == "true",
            etcd_endpoints=endpoints,
            etcd_dial_timeout_sec=float(os.getenv("ETCD_DIAL_TIMEOUT_SEC", "2.0")),
            lease_ttl_sec=int(os.getenv("LEASE_TTL_SEC", "5")),
            state_prefix=os.getenv("STATE_PREFIX", "/edge-scheduler"),
        )
