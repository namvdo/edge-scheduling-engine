from __future__ import annotations

import json
from dataclasses import dataclass

from .etcd_client import EtcdClient


@dataclass
class ReplicatedStateStore:
    """Replicated state facade.

    Stores per-cell latest decision metadata in etcd for recovery and consistency checks.
    """

    state_prefix: str
    etcd: EtcdClient

    def _latest_key(self, cell_id: str) -> str:
        return f"{self.state_prefix}/cells/{cell_id}/decision/latest"

    def get_latest(self, cell_id: str) -> dict | None:
        payload = self.etcd.get(self._latest_key(cell_id))
        if not payload:
            return None
        return json.loads(payload)

    def put_latest(self, cell_id: str, decision: dict) -> None:
        self.etcd.put(self._latest_key(cell_id), json.dumps(decision))
