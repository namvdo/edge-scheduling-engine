from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from .metrics import RequestKpi, TickKpi





class MetricsStore:
    def write_request_rows(self, rows: Iterable[RequestKpi]) -> None:
        raise NotImplementedError

    def write_tick_rows(self, rows: Iterable[TickKpi]) -> None:
        raise NotImplementedError

    def get_tick_row(self, tick: int) -> Optional[TickKpi]:
        raise NotImplementedError





class SQLiteMetricsStore(MetricsStore):
    """DB with indices for fast KPI queries."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn



    def _init_db(self) -> None:
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS request_kpi (
                    request_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    tick INTEGER,
                    qos_class TEXT,
                    status TEXT,
                    bs_id TEXT,
                    scheduler_latency_ms REAL,
                    estimated_throughput_mbps REAL,
                    signal_quality_db REAL,
                    distance_m REAL,
                    qos_target_ms REAL,
                    meets_qos INTEGER
                );
                """
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_request_tick ON request_kpi(tick);")
            c.execute("CREATE INDEX IF NOT EXISTS idx_request_user ON request_kpi(user_id);")

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS tick_kpi (
                    tick INTEGER PRIMARY KEY,
                    requests INTEGER,
                    granted INTEGER,
                    blocked INTEGER,
                    total_throughput_mbps REAL,
                    fairness_jain REAL,
                    avg_scheduler_latency_ms REAL,
                    qos_meet_rate REAL
                );
                """
            )

    def write_request_rows(self, rows: Iterable[RequestKpi]) -> None:
        rows = list(rows)
        if not rows:
            return
        with self._conn() as c:
            c.executemany(
                """
                INSERT OR REPLACE INTO request_kpi (
                    request_id, user_id, tick, qos_class, status, bs_id,
                    scheduler_latency_ms, estimated_throughput_mbps,
                    signal_quality_db, distance_m, qos_target_ms, meets_qos
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r.request_id,
                        r.user_id,
                        r.tick,
                        r.qos_class,
                        r.status,
                        r.bs_id,
                        r.scheduler_latency_ms,
                        r.estimated_throughput_mbps,
                        r.signal_quality_db,
                        r.distance_m,
                        r.qos_target_ms,
                        1 if r.meets_qos else 0,
                    )
                    for r in rows
                ],
            )

    def write_tick_rows(self, rows: Iterable[TickKpi]) -> None:
        rows = list(rows)
        if not rows:
            return
        with self._conn() as c:
            c.executemany(
                """
                INSERT OR REPLACE INTO tick_kpi (
                    tick, requests, granted, blocked,
                    total_throughput_mbps, fairness_jain,
                    avg_scheduler_latency_ms, qos_meet_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r.tick,
                        r.requests,
                        r.granted,
                        r.blocked,
                        r.total_throughput_mbps,
                        r.fairness_jain,
                        r.avg_scheduler_latency_ms,
                        r.qos_meet_rate,
                    )
                    for r in rows
                ],
            )

    def get_tick_row(self, tick: int) -> Optional[TickKpi]:
        with self._conn() as c:
            row = c.execute(
                """SELECT tick, requests, granted, blocked, total_throughput_mbps,
                          fairness_jain, avg_scheduler_latency_ms, qos_meet_rate
                   FROM tick_kpi WHERE tick=?""",
                (tick,),
            ).fetchone()
        if not row:
            return None
        return TickKpi(
            tick=int(row[0]),
            requests=int(row[1]),
            granted=int(row[2]),
            blocked=int(row[3]),
            total_throughput_mbps=float(row[4]),
            fairness_jain=float(row[5]),
            avg_scheduler_latency_ms=float(row[6]),
            qos_meet_rate=float(row[7]),
        )






class TTLCache:
    def __init__(self, ttl_s: float = 5.0, max_items: int = 1024) -> None:
        self.ttl_s = float(ttl_s)
        self.max_items = int(max_items)
        self._data: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Any:
        now = time.time()
        item = self._data.get(key)
        if not item:
            return None
        t0, v = item
        if now - t0 > self.ttl_s:
            self._data.pop(key, None)
            return None
        return v

    def set(self, key: str, value: Any) -> None:
        if len(self._data) >= self.max_items:
            self._data.pop(next(iter(self._data.keys())), None)
        self._data[key] = (time.time(), value)






class CachedMetricsStore(MetricsStore):
    """THIS IS caching layer"""

    def __init__(self, inner: MetricsStore, redis_url: Optional[str] = None, ttl_s: float = 5.0) -> None:
        self.inner = inner
        self.redis_url = redis_url
        self.ttl_s = float(ttl_s)
        self._mem = TTLCache(ttl_s=ttl_s)

        self._redis = None
        if redis_url:
            try:
                import redis

                self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None

    def write_request_rows(self, rows: Iterable[RequestKpi]) -> None:
        self.inner.write_request_rows(rows)
        #THIS writes invalidate cache.
        self._mem = TTLCache(ttl_s=self.ttl_s)


    def write_tick_rows(self, rows: Iterable[TickKpi]) -> None:
        self.inner.write_tick_rows(rows)
        self._mem = TTLCache(ttl_s=self.ttl_s)

    def _cache_get(self, key: str) -> Any:
        if self._redis is not None:
            v = self._redis.get(key)
            if v is None:
                return None
            return json.loads(v)
        return self._mem.get(key)

    def _cache_set(self, key: str, value: Any) -> None:
        if self._redis is not None:
            self._redis.setex(key, int(self.ttl_s), json.dumps(value))
        else:
            self._mem.set(key, value)

    def get_tick_row(self, tick: int) -> Optional[TickKpi]:
        key = f"tick:{tick}"
        cached = self._cache_get(key)
        if cached is not None:
            return TickKpi(**cached)

        row = self.inner.get_tick_row(tick)
        if row is None:
            return None
        self._cache_set(key, asdict(row))
        return row
