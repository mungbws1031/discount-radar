"""정적 HTML 어댑터 — 기획서 §3 방식 'HTML' 소스용.

Phase 0은 원문 저장까지만 구현한다. HTML 구조는 사이트마다 달라 범용
셀렉터가 없으므로, extract()는 LLM Extractor(§5.1)로 넘길 원문을 그대로
Raw Store에 남기는 통과(pass-through) 동작을 하고 실제 Deal 후보는
만들지 않는다 (needs_review 큐를 늘리지 않기 위함). 소스별 커스텀 파서를
붙이려면 이 클래스를 상속해 extract()를 오버라이드한다.
"""
from __future__ import annotations

import requests

from ..models import Deal, RawDocument, raw_hash
from .base import AdapterHealth, BaseAdapter

USER_AGENT = "DiscountRadarBot/0.1 (+https://github.com/mungbws1031/discount-radar; personal use, contact via GitHub)"


class HtmlAdapter(BaseAdapter):
    def fetch(self) -> list[RawDocument]:
        resp = requests.get(self.source.url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        return [RawDocument(source_id=self.source.id, url=self.source.url, text=resp.text)]

    def extract(self, doc: RawDocument) -> list[Deal]:
        # LLM Extractor 연동 전까지는 원문만 보존한다 (기획서 §5.1 RAW -> LLM Extractor).
        return []

    def healthcheck(self, doc_count: int) -> AdapterHealth:
        return super().healthcheck(doc_count)
