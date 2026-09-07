"""어댑터 인터페이스 — 기획서 §5.3 SourceAdapter Protocol."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import Deal, RawDocument
from ..registry import Source


@dataclass
class AdapterHealth:
    source_id: str
    ok: bool
    doc_count: int
    message: str = ""


class SourceAdapter(Protocol):
    """모든 어댑터(API/RSS/HTML/Browser/Mail)가 구현하는 공통 인터페이스.

    fetch(): 원문 스냅샷 목록을 가져온다.
    extract(): 원문에서 Deal 후보를 뽑는다 (규칙 기반 또는 LLM — Phase 0은 규칙만).
    healthcheck(): 최근 결과가 정상 범위인지 판단해 needs_review 전환 신호를 낸다.
    """

    source: Source

    def fetch(self) -> list[RawDocument]: ...

    def extract(self, doc: RawDocument) -> list[Deal]: ...

    def healthcheck(self, doc_count: int) -> AdapterHealth: ...


class BaseAdapter:
    """공통 healthcheck 구현을 제공하는 베이스 클래스."""

    def __init__(self, source: Source):
        self.source = source

    def healthcheck(self, doc_count: int) -> AdapterHealth:
        # 기획서 §5.3: 추출 건수가 0이면 셀렉터 깨짐/차단 의심 -> needs_review
        ok = doc_count > 0
        msg = "정상" if ok else "수집 결과 0건 — 셀렉터·접근 차단 의심, needs_review 전환 권장"
        return AdapterHealth(source_id=self.source.id, ok=ok, doc_count=doc_count, message=msg)
