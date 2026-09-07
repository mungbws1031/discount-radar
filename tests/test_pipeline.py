"""네트워크 없이 돌아가는 단위 테스트.

이 개발 샌드박스는 아웃바운드 네트워크가 조직 정책으로 제한되어 있어
실제 RSS/HTML 소스에 붙는 통합 테스트는 여기서 실행할 수 없다. 대신
로컬 픽스처로 추출·검증·중복 제거·만료·스케줄 로직을 검증한다.
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.adapters.rss import RssAdapter
from src.models import Deal, RawDocument
from src.pipeline import validate
from src.registry import Source
from src.scheduler import is_due
from src.storage import DealStore

FIXTURES = Path(__file__).parent / "fixtures"


def make_source(**overrides) -> Source:
    base = dict(
        id="test.hotdeal",
        name="테스트 핫딜",
        domain=["dining"],
        method="rss",
        extract="rules",
        policy="allowed",
        schedule="*/30 * * * *",
        url="https://example.com/hotdeal.rss",
        priority=2,
    )
    base.update(overrides)
    return Source.from_dict(base)


class RssExtractionTest(unittest.TestCase):
    def test_extract_parses_items_and_guesses_benefit(self):
        source = make_source()
        adapter = RssAdapter(source)
        text = (FIXTURES / "sample_hotdeal.rss").read_text(encoding="utf-8")
        doc = RawDocument(source_id=source.id, url=source.url, text=text)

        deals = adapter.extract(doc)

        self.assertEqual(len(deals), 3)
        self.assertEqual(deals[0].benefit_type, "percent")
        self.assertEqual(deals[0].benefit_value, 20.0)
        self.assertEqual(deals[1].benefit_type, "amount")
        self.assertEqual(deals[1].benefit_value, 5000.0)
        self.assertEqual(deals[2].benefit_type, "one_plus_one")
        for d in deals:
            self.assertEqual(d.status, "needs_review")
            self.assertLess(d.confidence, 0.5)  # 규칙 기반 추출은 항상 사람 검토 대상

    def test_extract_ignores_malformed_xml(self):
        source = make_source()
        adapter = RssAdapter(source)
        doc = RawDocument(source_id=source.id, url=source.url, text="not xml at all")
        self.assertEqual(adapter.extract(doc), [])


class ValidateTest(unittest.TestCase):
    def test_rejects_deal_missing_required_fields(self):
        bad = Deal(source_id="s", source_url="", title="", domain="dining")
        self.assertFalse(validate(bad))

    def test_accepts_well_formed_deal(self):
        good = Deal(source_id="s", source_url="https://x", title="할인", domain="dining")
        self.assertTrue(validate(good))


class DealExpiryTest(unittest.TestCase):
    def test_is_expired_past_period_end(self):
        d = Deal(source_id="s", source_url="https://x", title="t", domain="dining",
                  period_end="2020-01-01T00:00:00+00:00")
        self.assertTrue(d.is_expired(at=datetime(2026, 1, 1, tzinfo=timezone.utc)))

    def test_not_expired_when_no_period_end(self):
        d = Deal(source_id="s", source_url="https://x", title="t", domain="dining")
        self.assertFalse(d.is_expired())


class StorageDedupTest(unittest.TestCase):
    def test_upsert_deduplicates_by_title_domain_period(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DealStore(db_path=Path(tmp) / "test.db")
            d1 = Deal(source_id="a", source_url="https://a", title="스타벅스 20% 할인",
                      domain="dining", raw_hash="hash1")
            d2 = Deal(source_id="b", source_url="https://b", title="스타벅스 20% 할인",
                      domain="dining", raw_hash="hash2")  # 다른 소스, 같은 딜

            r1 = store.upsert_deal(d1)
            r2 = store.upsert_deal(d2)

            self.assertEqual(r1, "inserted")
            self.assertEqual(r2, "updated")  # 새로 삽입되지 않고 병합됨
            active = store.list_active(domain="dining")
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["source_id"], "b")  # 최신 소스로 갱신

    def test_mark_expired_hides_from_active_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DealStore(db_path=Path(tmp) / "test.db")
            expired = Deal(source_id="a", source_url="https://a", title="지난 딜",
                          domain="dining", period_end="2020-01-01T00:00:00+00:00")
            store.upsert_deal(expired)

            count = store.mark_expired(datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat())

            self.assertEqual(count, 1)
            self.assertEqual(store.list_active(domain="dining"), [])


class SchedulerTest(unittest.TestCase):
    def test_star_slash_minute_pattern(self):
        self.assertTrue(is_due("*/30 * * * *", at=datetime(2026, 1, 1, 10, 30)))
        self.assertFalse(is_due("*/30 * * * *", at=datetime(2026, 1, 1, 10, 15)))

    def test_fixed_hour_minute_pattern(self):
        self.assertTrue(is_due("0 9 * * *", at=datetime(2026, 1, 1, 9, 0)))
        self.assertFalse(is_due("0 9 * * *", at=datetime(2026, 1, 1, 9, 30)))

    def test_hour_step_pattern(self):
        self.assertTrue(is_due("0 */2 * * *", at=datetime(2026, 1, 1, 4, 0)))
        self.assertFalse(is_due("0 */2 * * *", at=datetime(2026, 1, 1, 3, 0)))


if __name__ == "__main__":
    unittest.main()
