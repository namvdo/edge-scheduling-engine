from __future__ import annotations

from dataclasses import dataclass

from .config import ClusterConfig
from .etcd_client import EtcdClient


@dataclass
class LeaderElector:
    config: ClusterConfig
    etcd: EtcdClient

    def _cell_lock_key(self, cell_id: str) -> str:
        return f"{self.config.state_prefix}/cells/{cell_id}/leader"

    def try_acquire(self, cell_id: str):
        lease = self.etcd.lease(self.config.lease_ttl_sec)
        acquired = self.etcd.put_if_not_exists(
            self._cell_lock_key(cell_id),
            self.config.node_id,
            lease=lease,
        )
        return acquired, lease

    def current_leader(self, cell_id: str) -> str | None:
        return self.etcd.get(self._cell_lock_key(cell_id))
