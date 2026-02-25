from __future__ import annotations

from dataclasses import dataclass

from .state_store import ReplicatedStateStore


@dataclass
class RecoveryManager:
    store: ReplicatedStateStore

    def recover_latest_version(self, cell_id: str) -> int:
        latest = self.store.get_latest(cell_id)
        if not latest:
            return 0
        return int(latest.get("decision_version", 0))
