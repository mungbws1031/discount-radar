"""LLM Extractor 테스트 — 실제 Claude API를 호출하지 않는다.

이 샌드박스는 외부 네트워크가 막혀 있어 api.anthropic.com에 붙는 통합
테스트는 실행할 수 없다. 대신 `anthropic` 모듈을 가짜로 주입해 성공/거부/
인증 실패 경로의 분기 로직(신뢰도 임계값, 에러 매핑)만 검증한다.
"""
from __future__ import annotations

import json
import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock

from src.llm_extractor import (
    LlmExtractionError,
    extract_deals,
    html_to_text,
    parse_llm_deals,
)
from src.models import RawDocument
from src.registry import Source


def make_source(**overrides) -> Source:
    base = dict(
        id="test.html",
        name="테스트 HTML 소스",
        domain=["dining"],
        method="html",
        extract="llm",
        policy="gray",
        schedule="0 * * * *",
        url="https://example.com/page",
        priority=3,
    )
    base.update(overrides)
    return Source.from_dict(base)


def make_fake_anthropic_module(create_side_effect=None, create_return=None):
    """anthropic 패키지를 흉내내는 최소 가짜 모듈.

    실제 SDK의 예외 클래스 이름(AuthenticationError 등)만 맞춰서
    llm_extractor의 except 체인이 그대로 동작하는지 확인한다.
    """
    fake = types.ModuleType("anthropic")

    class AuthenticationError(Exception):
        pass

    class PermissionDeniedError(Exception):
        pass

    class NotFoundError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    class APIStatusError(Exception):
        def __init__(self, message="err", status_code=500):
            super().__init__(message)
            self.message = message
            self.status_code = status_code

    class APIConnectionError(Exception):
        pass

    fake.AuthenticationError = AuthenticationError
    fake.PermissionDeniedError = PermissionDeniedError
    fake.NotFoundError = NotFoundError
    fake.RateLimitError = RateLimitError
    fake.APIStatusError = APIStatusError
    fake.APIConnectionError = APIConnectionError

    messages = mock.Mock()
    if create_side_effect is not None:
        messages.create.side_effect = create_side_effect
    else:
        messages.create.return_value = create_return

    client = mock.Mock()
    client.messages = messages
    fake.Anthropic = mock.Mock(return_value=client)
    return fake


class HtmlToTextTest(unittest.TestCase):
    def test_strips_script_and_style_keeps_visible_text(self):
        html = """
        <html><head><style>.x{color:red}</style></head>
        <body>
          <script>console.log('noise')</script>
          <h1>스타벅스 20% 할인</h1>
          <p>9/1~9/30 신한카드 결제 시</p>
        </body></html>
        """
        text = html_to_text(html)
        self.assertIn("스타벅스 20% 할인", text)
        self.assertIn("신한카드", text)
        self.assertNotIn("console.log", text)
        self.assertNotIn("color:red", text)


class ParseLlmDealsTest(unittest.TestCase):
    def test_confidence_threshold_sets_status(self):
        source = make_source()
        doc = RawDocument(source_id=source.id, url=source.url, text="<html></html>")
        payload = {
            "deals": [
                {
                    "title": "높은 확신 딜",
                    "domain": "dining",
                    "brand": ["스타벅스"],
                    "benefit_type": "percent",
                    "benefit_value": 20,
                    "benefit_cap": 0,
                    "conditions_summary": "신한카드 결제 시",
                    "period_start": "2026-09-01",
                    "period_end": "2026-09-30",
                    "confidence": 0.9,
                },
                {
                    "title": "낮은 확신 딜",
                    "domain": "dining",
                    "brand": [],
                    "benefit_type": "unknown",
                    "benefit_value": 0,
                    "benefit_cap": 0,
                    "conditions_summary": "",
                    "period_start": "",
                    "period_end": "",
                    "confidence": 0.3,
                },
            ]
        }

        deals = parse_llm_deals(source, doc, payload)

        self.assertEqual(len(deals), 2)
        self.assertEqual(deals[0].status, "active")
        self.assertEqual(deals[0].benefit_value, 20)
        self.assertEqual(deals[1].status, "needs_review")
        self.assertIsNone(deals[1].benefit_value)  # 0 -> None
        self.assertIsNone(deals[1].period_start)   # "" -> None
        self.assertEqual(deals[1].conditions, {})  # 빈 요약은 저장하지 않음


class ExtractDealsTest(unittest.TestCase):
    def test_success_path_returns_parsed_deals(self):
        source = make_source()
        doc = RawDocument(source_id=source.id, url=source.url, text="<p>교촌치킨 5000원 할인 9/1~9/10</p>")
        payload = {
            "deals": [
                {
                    "title": "교촌치킨 5000원 할인",
                    "domain": "dining",
                    "brand": ["교촌치킨"],
                    "benefit_type": "amount",
                    "benefit_value": 5000,
                    "benefit_cap": 0,
                    "conditions_summary": "",
                    "period_start": "2026-09-01",
                    "period_end": "2026-09-10",
                    "confidence": 0.85,
                }
            ]
        }
        response = SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        )
        fake_anthropic = make_fake_anthropic_module(create_return=response)

        with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
            deals = extract_deals(source, doc)

        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].title, "교촌치킨 5000원 할인")
        self.assertEqual(deals[0].status, "active")

    def test_refusal_raises_llm_extraction_error(self):
        source = make_source()
        doc = RawDocument(source_id=source.id, url=source.url, text="<p>내용</p>")
        response = SimpleNamespace(stop_reason="refusal", content=[])
        fake_anthropic = make_fake_anthropic_module(create_return=response)

        with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
            with self.assertRaises(LlmExtractionError):
                extract_deals(source, doc)

    def test_authentication_error_is_wrapped(self):
        source = make_source()
        doc = RawDocument(source_id=source.id, url=source.url, text="<p>내용</p>")
        fake_anthropic = make_fake_anthropic_module()
        fake_anthropic.Anthropic.return_value.messages.create.side_effect = fake_anthropic.AuthenticationError(
            "bad key"
        )

        with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
            with self.assertRaises(LlmExtractionError) as ctx:
                extract_deals(source, doc)
        self.assertIn("인증", str(ctx.exception))

    def test_empty_text_short_circuits_without_calling_api(self):
        source = make_source()
        doc = RawDocument(source_id=source.id, url=source.url, text="<script>only script</script>")
        fake_anthropic = make_fake_anthropic_module()

        with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic}):
            deals = extract_deals(source, doc)

        self.assertEqual(deals, [])
        fake_anthropic.Anthropic.return_value.messages.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
