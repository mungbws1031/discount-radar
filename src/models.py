"""공통 딜 스키마 — 기획서 §5.2 Deal 스키마의 파이썬 구현."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def raw_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class RawDocument:
    """어댑터가 소스에서 가져온 원문 스냅샷."""

    source_id: str
    url: str
    text: str
    fetched_at: str = field(default_factory=now_iso)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def hash(self) -> str:
        return raw_hash(self.text)


@dataclass
class Deal:
    """기획서 §5.2의 공통 Deal 스키마."""

    source_id: str
    source_url: str
    title: str
    domain: str = "etc"  # dining | kids | card | travel | etc
    brand: list[str] = field(default_factory=list)
    benefit_type: str = "unknown"  # percent | amount | coupon | one_plus_one | free | point | unknown
    benefit_value: Optional[float] = None
    benefit_cap: Optional[float] = None
    conditions: dict[str, Any] = field(default_factory=dict)
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    confidence: float = 0.5
    raw_hash: str = ""
    deal_id: str = field(default_factory=new_id)
    extracted_at: str = field(default_factory=now_iso)
    status: str = "needs_review"  # active | expired | needs_review

    def dedup_key(self) -> str:
        """같은 딜을 소스 간 병합하기 위한 근사 키 (기획서 §5.1 Dedup/Merge)."""
        norm_title = "".join(self.title.split()).lower()
        return f"{self.domain}:{norm_title}:{self.period_end or ''}"

    def is_expired(self, at: Optional[datetime] = None) -> bool:
        if not self.period_end:
            return False
        at = at or datetime.now(timezone.utc)
        try:
            end = datetime.fromisoformat(self.period_end)
        except ValueError:
            return False
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return at > end

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Deal":
        return cls(**d)
