"""수집 파이프라인 오케스트레이션 — 기획서 §5.1 파이프라인 다이어그램의 실행부.

Scheduler -> Adapter.fetch -> Adapter.extract -> Validator -> Dedup/Merge(Store) -> DB
"""
from __future__ import annotations

from datetime import datetime, timezone

from .adapters import ADAPTERS_BY_METHOD, AdapterHealth
from .models import Deal
from .registry import Source
from .storage import DealStore


def validate(deal: Deal) -> bool:
    """필수 필드 검증 (기획서 §5.1 Validator, §7.1 FR-002)."""
    if not deal.title or not deal.source_url or not deal.domain:
        return False
    if deal.confidence < 0 or deal.confidence > 1:
        return False
    return True


def run_source(source: Source, store: DealStore) -> AdapterHealth:
    adapter_cls = ADAPTERS_BY_METHOD.get(source.method)
    run_at = datetime.now(timezone.utc).isoformat()

    if adapter_cls is None:
        health = AdapterHealth(source.id, ok=False, doc_count=0, message=f"지원하지 않는 method: {source.method}")
        store.record_health(source.id, run_at, 0, False, health.message)
        return health

    adapter = adapter_cls(source)
    try:
        docs = adapter.fetch()
    except Exception as exc:  # noqa: BLE001 — 소스별 실패는 격리하고 계속 진행
        health = AdapterHealth(source.id, ok=False, doc_count=0, message=f"fetch 실패: {exc}")
        store.record_health(source.id, run_at, 0, False, health.message)
        return health

    total_deals = 0
    for doc in docs:
        candidates = adapter.extract(doc)
        for deal in candidates:
            if not validate(deal):
                continue
            store.upsert_deal(deal)
            total_deals += 1

    health = adapter.healthcheck(total_deals)
    store.record_health(source.id, run_at, total_deals, health.ok, health.message)
    return health


def run_all(sources: list[Source], store: DealStore) -> list[AdapterHealth]:
    return [run_source(s, store) for s in sources]


def expire_stale_deals(store: DealStore) -> int:
    return store.mark_expired(datetime.now(timezone.utc).isoformat())
