"""Deal DB — 기획서 §5.1 Raw Store/Deal DB의 Phase 0 구현 (SQLite).

Phase 1부터는 Postgres로 교체 예정(기획서 §5.4). 스키마는 최대한 그대로
이식 가능하게 단순 컬럼 위주로 구성한다.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .models import Deal

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "deals.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    deal_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    domain TEXT NOT NULL,
    brand TEXT NOT NULL DEFAULT '[]',
    benefit_type TEXT NOT NULL DEFAULT 'unknown',
    benefit_value REAL,
    benefit_cap REAL,
    conditions TEXT NOT NULL DEFAULT '{}',
    period_start TEXT,
    period_end TEXT,
    confidence REAL NOT NULL DEFAULT 0.5,
    raw_hash TEXT NOT NULL DEFAULT '',
    extracted_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'needs_review',
    dedup_key TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deals_dedup_key ON deals(dedup_key);
CREATE INDEX IF NOT EXISTS idx_deals_status ON deals(status);
CREATE INDEX IF NOT EXISTS idx_deals_domain ON deals(domain);

CREATE TABLE IF NOT EXISTS source_health (
    source_id TEXT PRIMARY KEY,
    last_run_at TEXT,
    last_doc_count INTEGER,
    last_ok INTEGER,
    last_message TEXT
);
"""


class DealStore:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_deal(self, deal: Deal) -> str:
        """dedup_key로 기존 딜을 찾아 병합(merge), 없으면 새로 삽입.

        기획서 §5.1 Dedup/Merge: 같은 딜이 여러 소스에서 발견되면 하나로
        합치되 원문 링크는 보존한다 (Phase 0은 최신 소스의 링크로 갱신).
        반환값: 'inserted' | 'updated'
        """
        dedup_key = deal.dedup_key()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT deal_id, raw_hash FROM deals WHERE dedup_key = ?", (dedup_key,)
            ).fetchone()
            if row is None:
                conn.execute(
                    """INSERT INTO deals
                    (deal_id, source_id, source_url, title, domain, brand, benefit_type,
                     benefit_value, benefit_cap, conditions, period_start, period_end,
                     confidence, raw_hash, extracted_at, status, dedup_key)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        deal.deal_id,
                        deal.source_id,
                        deal.source_url,
                        deal.title,
                        deal.domain,
                        json.dumps(deal.brand, ensure_ascii=False),
                        deal.benefit_type,
                        deal.benefit_value,
                        deal.benefit_cap,
                        json.dumps(deal.conditions, ensure_ascii=False),
                        deal.period_start,
                        deal.period_end,
                        deal.confidence,
                        deal.raw_hash,
                        deal.extracted_at,
                        deal.status,
                        dedup_key,
                    ),
                )
                return "inserted"
            existing_id, existing_hash = row
            if existing_hash == deal.raw_hash:
                return "unchanged"
            conn.execute(
                """UPDATE deals SET source_id=?, source_url=?, benefit_type=?, benefit_value=?,
                   benefit_cap=?, conditions=?, period_start=?, period_end=?, confidence=?,
                   raw_hash=?, extracted_at=?, status=? WHERE deal_id=?""",
                (
                    deal.source_id,
                    deal.source_url,
                    deal.benefit_type,
                    deal.benefit_value,
                    deal.benefit_cap,
                    json.dumps(deal.conditions, ensure_ascii=False),
                    deal.period_start,
                    deal.period_end,
                    deal.confidence,
                    deal.raw_hash,
                    deal.extracted_at,
                    deal.status,
                    existing_id,
                ),
            )
            return "updated"

    def mark_expired(self, before_iso: str) -> int:
        """기획서 §5.1: 만료된 딜은 피드·알림·검색에서 제외 (status=expired)."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE deals SET status='expired' WHERE period_end IS NOT NULL "
                "AND period_end < ? AND status != 'expired'",
                (before_iso,),
            )
            return cur.rowcount

    def list_active(self, domain: Optional[str] = None, limit: int = 100) -> list[dict]:
        q = "SELECT * FROM deals WHERE status != 'expired'"
        params: list = []
        if domain:
            q += " AND domain = ?"
            params.append(domain)
        q += " ORDER BY extracted_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(q, params).fetchall()
            return [dict(r) for r in rows]

    def record_health(self, source_id: str, run_at: str, doc_count: int, ok: bool, message: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO source_health (source_id, last_run_at, last_doc_count, last_ok, last_message)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(source_id) DO UPDATE SET
                     last_run_at=excluded.last_run_at,
                     last_doc_count=excluded.last_doc_count,
                     last_ok=excluded.last_ok,
                     last_message=excluded.last_message""",
                (source_id, run_at, doc_count, int(ok), message),
            )

    def coverage(self) -> dict:
        """기획서 §2.3 Coverage KPI 계산용 원시 데이터."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM source_health").fetchall()
            total = len(rows)
            healthy = sum(1 for r in rows if r["last_ok"])
            return {
                "total_sources_run": total,
                "healthy_sources": healthy,
                "coverage_ratio": (healthy / total) if total else 0.0,
                "sources": [dict(r) for r in rows],
            }
