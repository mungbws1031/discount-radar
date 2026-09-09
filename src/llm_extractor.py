"""LLM 기반 딜 추출기 — 기획서 §5.1 'LLM Extractor', §5.3 '비정형 -> Deal JSON'.

HTML 어댑터가 저장한 원문(RawDocument)에서 Claude에게 구조화된 Deal 후보를
뽑아달라고 요청한다. 신뢰도(confidence) 0.7 미만은 항상 사람 검토
(status=needs_review)로 남기고, 그 이상만 active로 승격한다 (기획서 §5.3).

이 모듈은 anthropic 패키지와 API 자격증명이 있어야 동작한다. 둘 중 하나라도
없으면 LlmExtractionError를 던지며, 호출측(pipeline)이 소스별로 격리해
전체 수집이 죽지 않게 한다.
"""
from __future__ import annotations

import json
import os
import re
from html.parser import HTMLParser

from .models import Deal, RawDocument, raw_hash
from .registry import Source

MAX_CHARS = 12000  # 원문 텍스트를 이 길이로 잘라 토큰 비용을 제한한다.
CONFIDENCE_AUTO_ACTIVE = 0.7  # 기획서 §5.3: 이 값 미만은 항상 needs_review.
DEFAULT_MODEL = os.environ.get("DISCOUNT_RADAR_LLM_MODEL", "claude-opus-5")
DEFAULT_EFFORT = os.environ.get("DISCOUNT_RADAR_LLM_EFFORT", "medium")

DEAL_SCHEMA = {
    "type": "object",
    "properties": {
        "deals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "딜 제목 (원문 그대로 또는 축약)"},
                    "domain": {
                        "type": "string",
                        "enum": ["dining", "kids", "card", "travel", "etc"],
                    },
                    "brand": {"type": "array", "items": {"type": "string"}},
                    "benefit_type": {
                        "type": "string",
                        "enum": ["percent", "amount", "coupon", "one_plus_one", "free", "point", "unknown"],
                    },
                    "benefit_value": {
                        "type": "number",
                        "description": "percent면 %, amount면 원 단위 숫자. 모르면 0",
                    },
                    "benefit_cap": {"type": "number", "description": "1회/월 한도(원). 없으면 0"},
                    "conditions_summary": {
                        "type": "string",
                        "description": "카드사·통신사·지역·요일·응모 필요 여부 등 조건을 한 줄 요약",
                    },
                    "period_start": {"type": "string", "description": "ISO 날짜(YYYY-MM-DD) 또는 빈 문자열"},
                    "period_end": {"type": "string", "description": "ISO 날짜(YYYY-MM-DD) 또는 빈 문자열"},
                    "confidence": {
                        "type": "number",
                        "description": "이 추출이 정확하다는 확신도 0.0~1.0",
                    },
                },
                "required": [
                    "title",
                    "domain",
                    "brand",
                    "benefit_type",
                    "benefit_value",
                    "benefit_cap",
                    "conditions_summary",
                    "period_start",
                    "period_end",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["deals"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "너는 한국 할인 정보 페이지에서 할인/쿠폰/이벤트 딜만 뽑아내는 추출기다. "
    "메뉴, 배너, 로그인, 저작권 등 딜이 아닌 텍스트는 무시해라. "
    "같은 딜이 여러 번 반복되면 한 번만 추출해라. "
    "숫자·날짜는 원문에 명시된 값만 사용하고, 불확실하면 확신도(confidence)를 낮춰라. "
    "할인 관련 내용이 전혀 없으면 deals를 빈 배열로 반환해라."
)


class LlmExtractionError(RuntimeError):
    pass


class _HTMLTextExtractor(HTMLParser):
    """<script>/<style>를 제외한 가시 텍스트만 모으는 최소 HTML -> 텍스트 변환기."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self.chunks.append(data.strip())


def html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    text = "\n".join(parser.chunks)
    return re.sub(r"\n{3,}", "\n\n", text)


def _to_optional(value):
    if value in (0, "", None):
        return None
    return value


def parse_llm_deals(source: Source, doc: RawDocument, payload: dict) -> list[Deal]:
    h = raw_hash(doc.text)
    deals: list[Deal] = []
    for item in payload.get("deals", []):
        confidence = float(item.get("confidence", 0) or 0)
        status = "active" if confidence >= CONFIDENCE_AUTO_ACTIVE else "needs_review"
        deals.append(
            Deal(
                source_id=source.id,
                source_url=doc.url,
                title=item.get("title", "").strip(),
                domain=item.get("domain") or (source.domain[0] if source.domain else "etc"),
                brand=item.get("brand") or [],
                benefit_type=item.get("benefit_type", "unknown"),
                benefit_value=_to_optional(item.get("benefit_value")),
                benefit_cap=_to_optional(item.get("benefit_cap")),
                conditions={"summary": item["conditions_summary"]} if item.get("conditions_summary") else {},
                period_start=_to_optional(item.get("period_start")),
                period_end=_to_optional(item.get("period_end")),
                confidence=confidence,
                raw_hash=h,
                status=status,
            )
        )
    return deals


def extract_deals(source: Source, doc: RawDocument) -> list[Deal]:
    """RawDocument에서 Claude로 Deal 후보를 추출한다.

    anthropic 미설치·API 키 미설정·API 오류는 모두 LlmExtractionError로
    통일해 던진다 — 호출측(pipeline.run_source)이 소스 단위로 격리한다.
    """
    try:
        import anthropic
    except ImportError as exc:
        raise LlmExtractionError(
            "anthropic 패키지가 설치되어 있지 않습니다 (`pip install -r requirements.txt`)."
        ) from exc

    text = html_to_text(doc.text)[:MAX_CHARS]
    if not text.strip():
        return []

    client = anthropic.Anthropic()
    user_content = (
        f"소스: {source.name} ({source.id})\n원문 URL: {doc.url}\n\n"
        f"--- 페이지 텍스트 (최대 {MAX_CHARS}자) ---\n{text}"
    )

    try:
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            output_config={
                "effort": DEFAULT_EFFORT,
                "format": {"type": "json_schema", "schema": DEAL_SCHEMA},
            },
        )
    except anthropic.AuthenticationError as exc:
        raise LlmExtractionError("Claude API 인증 실패 — ANTHROPIC_API_KEY를 확인하세요.") from exc
    except anthropic.PermissionDeniedError as exc:
        raise LlmExtractionError("Claude API 권한 없음.") from exc
    except anthropic.NotFoundError as exc:
        raise LlmExtractionError(f"모델을 찾을 수 없음: {DEFAULT_MODEL}") from exc
    except anthropic.RateLimitError as exc:
        raise LlmExtractionError("Claude API 레이트 리밋 — 다음 수집 주기에 재시도됩니다.") from exc
    except anthropic.APIStatusError as exc:
        raise LlmExtractionError(f"Claude API 오류 ({exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise LlmExtractionError("Claude API 연결 실패 — 네트워크를 확인하세요.") from exc

    if response.stop_reason == "refusal":
        raise LlmExtractionError("Claude가 추출 요청을 거부했습니다 (정책).")

    try:
        text_block = next(b.text for b in response.content if b.type == "text")
        payload = json.loads(text_block)
    except (StopIteration, json.JSONDecodeError) as exc:
        raise LlmExtractionError(f"LLM 응답을 JSON으로 파싱하지 못했습니다: {exc}") from exc

    return parse_llm_deals(source, doc, payload)
