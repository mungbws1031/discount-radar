"""정적 HTML 어댑터 — 기획서 §3 방식 'HTML' 소스용.

fetch()로 원문을 가져오고, extract()는 Claude API 기반 LLM Extractor
(src/llm_extractor.py, 기획서 §5.1/§5.3)로 넘겨 Deal 후보를 뽑는다.
LLM 호출 실패(자격증명 미설정, 레이트리밋 등)는 LlmExtractionError로
올라가고, pipeline.run_source가 소스 단위로 격리해 전체 수집을 죽이지
않는다. 사이트별 셀렉터가 있는 편이 더 저렴하고 정확하면 이 클래스를
상속해 extract()를 오버라이드한다.
"""
from __future__ import annotations

import requests

from ..llm_extractor import extract_deals
from ..models import Deal, RawDocument
from .base import AdapterHealth, BaseAdapter

USER_AGENT = "DiscountRadarBot/0.1 (+https://github.com/mungbws1031/discount-radar; personal use, contact via GitHub)"


class HtmlAdapter(BaseAdapter):
    def fetch(self) -> list[RawDocument]:
        resp = requests.get(self.source.url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        return [RawDocument(source_id=self.source.id, url=self.source.url, text=resp.text)]

    def extract(self, doc: RawDocument) -> list[Deal]:
        return extract_deals(self.source, doc)

    def healthcheck(self, doc_count: int) -> AdapterHealth:
        return super().healthcheck(doc_count)
