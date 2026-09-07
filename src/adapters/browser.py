"""브라우저 렌더링 어댑터 — 기획서 §3 방식 'BRW' (카드사·통신사·예약 플랫폼 등).

Phase 0 스캐폴드에는 Playwright를 설치하지 않았다 (개인 실행 환경 의존성
최소화). 실제 구현 시 이 클래스에서 Playwright의 sync/async API로
로그인 없는 공개 이벤트 페이지만 렌더링하고, 사용자 계정으로 로그인하는
개인화 영역은 다루지 않는다 (기획서 §3.5 소스 접근 정책).

동시 요청 1, 요청 간격 최소 30분 — 소스별 스케줄러 설정(schedule)로 보장.
"""
from __future__ import annotations

from ..models import Deal, RawDocument
from .base import AdapterHealth, BaseAdapter


class BrowserNotConfiguredError(RuntimeError):
    pass


class BrowserAdapter(BaseAdapter):
    def fetch(self) -> list[RawDocument]:
        raise BrowserNotConfiguredError(
            f"[{self.source.id}] Playwright 미설치 — Phase 1에서 브라우저 렌더링 어댑터를 "
            "연결하세요 (requirements에 playwright 추가 후 `playwright install chromium`)."
        )

    def extract(self, doc: RawDocument) -> list[Deal]:
        return []

    def healthcheck(self, doc_count: int) -> AdapterHealth:
        return AdapterHealth(
            source_id=self.source.id,
            ok=False,
            doc_count=0,
            message="browser 어댑터 미구현 (Phase 0 스캐폴드)",
        )
