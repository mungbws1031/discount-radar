"""주말 브리핑 생성 — 기획서 §4.1 F-08, §6.2 Flow 2.

Phase 0에서는 매칭 엔진(F-06) 이전 단계이므로 프로필 조건 대조는 하지
않고, 최근 수집된 needs_review 이상 신뢰도(>=0.3)의 딜을 도메인별 상위
N개로 뽑아 텍스트 브리핑을 만든다. 텔레그램/카카오 발송은 Phase 0
스캐폴드 밖으로 남겨두고, 여기서는 브리핑 텍스트만 생성한다.
"""
from __future__ import annotations

from .storage import DealStore

DOMAIN_LABEL = {"dining": "외식", "kids": "키즈카페", "card": "카드", "travel": "여행", "etc": "기타"}


def build_briefing(store: DealStore, top_n_per_domain: int = 5) -> str:
    lines = ["📋 이번 주말 할인 브리핑\n"]
    for domain in ["dining", "kids", "card", "travel"]:
        deals = store.list_active(domain=domain, limit=top_n_per_domain)
        if not deals:
            continue
        lines.append(f"## {DOMAIN_LABEL.get(domain, domain)}")
        for d in deals:
            benefit = _format_benefit(d)
            lines.append(f"- {d['title']} {benefit}\n  {d['source_url']}")
        lines.append("")
    if len(lines) == 1:
        return "이번 주말은 아직 수집된 딜이 없습니다. `python cli.py collect`를 먼저 실행하세요."
    return "\n".join(lines)


def _format_benefit(d: dict) -> str:
    if d["benefit_type"] == "percent" and d["benefit_value"]:
        return f"({int(d['benefit_value'])}% 할인)"
    if d["benefit_type"] == "amount" and d["benefit_value"]:
        return f"({int(d['benefit_value']):,}원 할인)"
    if d["benefit_type"] == "one_plus_one":
        return "(1+1)"
    if d["benefit_type"] == "free":
        return "(무료)"
    return "(조건 확인 필요)"
