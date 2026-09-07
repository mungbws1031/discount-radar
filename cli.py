#!/usr/bin/env python3
"""할인 레이더 Phase 0 CLI.

사용 예:
  python cli.py collect              # due 여부와 무관하게 모든 fetchable 소스 즉시 수집
  python cli.py collect --due-only   # scheduler.is_due()로 지금 시각에 해당하는 소스만 수집
  python cli.py list --domain dining # 활성 딜 목록
  python cli.py briefing             # 주말 브리핑 텍스트 생성
  python cli.py health               # 소스별 헬스 상태 / 커버리지 KPI
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from src.briefing import build_briefing
from src.pipeline import expire_stale_deals, run_source
from src.registry import fetchable, load_registry
from src.scheduler import RunState, is_due
from src.storage import DealStore


def cmd_collect(args: argparse.Namespace) -> None:
    store = DealStore()
    sources = fetchable(load_registry())
    if args.source:
        sources = [s for s in sources if s.id == args.source]
        if not sources:
            print(f"소스를 찾을 수 없음(또는 url 미등록): {args.source}", file=sys.stderr)
            sys.exit(1)

    state = RunState()
    now = datetime.now(timezone.utc)
    ran, skipped = 0, 0
    for source in sources:
        if args.due_only:
            if not is_due(source.schedule, at=now) or state.already_ran_this_minute(source.id, now):
                skipped += 1
                continue
        health = run_source(source, store)
        state.mark_run(source.id, now)
        ran += 1
        status = "OK" if health.ok else "FAIL"
        print(f"[{status}] {source.id}: {health.doc_count}건 — {health.message}")

    expired = expire_stale_deals(store)
    print(f"\n실행 {ran}건 / 스킵 {skipped}건, 만료 처리 {expired}건")


def cmd_list(args: argparse.Namespace) -> None:
    store = DealStore()
    deals = store.list_active(domain=args.domain, limit=args.limit)
    if not deals:
        print("활성 딜이 없습니다. 먼저 `python cli.py collect`를 실행하세요.")
        return
    for d in deals:
        print(f"[{d['domain']}] {d['title']} (신뢰도 {d['confidence']:.1f}, {d['status']}) -> {d['source_url']}")


def cmd_briefing(_: argparse.Namespace) -> None:
    store = DealStore()
    print(build_briefing(store))


def cmd_health(_: argparse.Namespace) -> None:
    store = DealStore()
    cov = store.coverage()
    print(f"소스 커버리지: {cov['healthy_sources']}/{cov['total_sources_run']} "
          f"({cov['coverage_ratio']:.0%}) — 목표 90% (기획서 §2.3)")
    for s in cov["sources"]:
        mark = "✅" if s["last_ok"] else "⚠️"
        print(f"  {mark} {s['source_id']}: {s['last_doc_count']}건 @ {s['last_run_at']} — {s['last_message']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_collect = sub.add_parser("collect", help="소스 수집 실행")
    p_collect.add_argument("--source", help="특정 소스 ID만 실행")
    p_collect.add_argument("--due-only", action="store_true", help="스케줄상 지금 due인 소스만 실행")
    p_collect.set_defaults(func=cmd_collect)

    p_list = sub.add_parser("list", help="활성 딜 목록")
    p_list.add_argument("--domain", choices=["dining", "kids", "card", "travel", "etc"])
    p_list.add_argument("--limit", type=int, default=50)
    p_list.set_defaults(func=cmd_list)

    p_brief = sub.add_parser("briefing", help="주말 브리핑 텍스트 생성")
    p_brief.set_defaults(func=cmd_briefing)

    p_health = sub.add_parser("health", help="소스 헬스 / 커버리지")
    p_health.set_defaults(func=cmd_health)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
