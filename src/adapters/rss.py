"""RSS 어댑터 — 핫딜 커뮤니티 등 RSS 피드 제공 소스용 (기획서 §3.1 D8, §3.4 등).

Phase 0에서는 LLM 호출 없이 정규식 기반 규칙 추출만 수행한다. 추출된 딜은
항상 confidence를 낮게 잡고 status=needs_review로 남겨, 사람 검토 큐로
보내는 것을 원칙으로 한다 (기획서 §5.3 LLM 추출 신뢰도 0.7 미만은 사람이 검토).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

import requests

from ..models import Deal, RawDocument, raw_hash
from .base import AdapterHealth, BaseAdapter

USER_AGENT = "DiscountRadarBot/0.1 (+https://github.com/mungbws1031/discount-radar; personal use, contact via GitHub)"

PERCENT_RE = re.compile(r"(\d{1,3})\s*%")
AMOUNT_RE = re.compile(r"([\d,]{3,})\s*원")


def _guess_benefit(title: str) -> tuple[str, Optional[float]]:
    m = PERCENT_RE.search(title)
    if m:
        return "percent", float(m.group(1))
    m = AMOUNT_RE.search(title)
    if m:
        return "amount", float(m.group(1).replace(",", ""))
    if "1+1" in title or "원플원" in title:
        return "one_plus_one", None
    if "무료" in title:
        return "free", None
    return "unknown", None


class RssAdapter(BaseAdapter):
    def fetch(self) -> list[RawDocument]:
        resp = requests.get(
            self.source.url,
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        return [
            RawDocument(
                source_id=self.source.id,
                url=self.source.url,
                text=resp.text,
                meta={"content_type": resp.headers.get("Content-Type", "")},
            )
        ]

    def extract(self, doc: RawDocument) -> list[Deal]:
        deals: list[Deal] = []
        try:
            root = ET.fromstring(doc.text)
        except ET.ParseError:
            return deals

        items = root.findall(".//item")
        h = raw_hash(doc.text)
        for item in items:
            title_el = item.find("title")
            link_el = item.find("link")
            if title_el is None or not (title_el.text or "").strip():
                continue
            title = title_el.text.strip()
            link = (link_el.text or self.source.url).strip() if link_el is not None else self.source.url
            benefit_type, value = _guess_benefit(title)
            deals.append(
                Deal(
                    source_id=self.source.id,
                    source_url=link,
                    title=title,
                    domain=self.source.domain[0] if self.source.domain else "etc",
                    benefit_type=benefit_type,
                    benefit_value=value,
                    confidence=0.3,  # 규칙 기반 추출 — 사람 검토 전제
                    raw_hash=h,
                    status="needs_review",
                )
            )
        return deals

    def healthcheck(self, doc_count: int) -> AdapterHealth:
        return super().healthcheck(doc_count)
