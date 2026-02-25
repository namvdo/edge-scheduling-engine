from __future__ import annotations

from typing import Any


class EtcdClient:
    """Thin wrapper around etcd3 client.

    This keeps server code decoupled from the library and allows local fallback.
    """

    def __init__(self, endpoints: list[str], dial_timeout_sec: float):
        self._client: Any | None = None
        self._endpoint = endpoints[0] if endpoints else "localhost:2379"
        self._dial_timeout_sec = dial_timeout_sec

    def connect(self) -> None:
        try:
            import etcd3  # type: ignore

            host, port = self._endpoint.split(":", 1)
            self._client = etcd3.client(
                host=host,
                port=int(port),
                timeout=self._dial_timeout_sec,
            )
            self._client.status()
        except Exception as exc:  # pragma: no cover - runtime fallback path
            raise RuntimeError(f"Failed to connect etcd at {self._endpoint}: {exc}") from exc

    @property
    def raw(self) -> Any:
        if self._client is None:
            raise RuntimeError("etcd client not connected")
        return self._client

    def get(self, key: str) -> str | None:
        value, _ = self.raw.get(key)
        if value is None:
            return None
        return value.decode("utf-8")

    def put(self, key: str, value: str, lease: Any | None = None) -> None:
        self.raw.put(key, value, lease=lease)

    def put_if_not_exists(self, key: str, value: str, lease: Any | None = None) -> bool:
        ok, _ = self.raw.transaction(
            compare=[self.raw.transactions.version(key) == 0],
            success=[self.raw.transactions.put(key, value, lease=lease)],
            failure=[],
        )
        return bool(ok)

    def lease(self, ttl: int) -> Any:
        return self.raw.lease(ttl)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
