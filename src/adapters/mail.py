"""뉴스레터(이메일) 어댑터 — 기획서 §3 방식 'MAIL' (항공사·카드사 뉴스레터 등).

Phase 0 스캐폴드는 IMAP/수신함 연동 없이 인터페이스만 제공한다. 실제
구현 시 사용자 본인의 수신함(전용 별칭 주소 권장)만 읽고, 서버가 카드사
계정으로 로그인하지 않는다는 원칙(§3.5)을 이메일 경로에도 동일 적용한다.
"""
from __future__ import annotations

from ..models import Deal, RawDocument
from .base import AdapterHealth, BaseAdapter


class MailNotConfiguredError(RuntimeError):
    pass


class MailAdapter(BaseAdapter):
    def fetch(self) -> list[RawDocument]:
        raise MailNotConfiguredError(
            f"[{self.source.id}] 메일 수신함 연동 미구성 — Phase 1에서 IMAP 자격증명을 "
            "환경변수로 주입하고 이 어댑터를 구현하세요."
        )

    def extract(self, doc: RawDocument) -> list[Deal]:
        return []

    def healthcheck(self, doc_count: int) -> AdapterHealth:
        return AdapterHealth(
            source_id=self.source.id,
            ok=False,
            doc_count=0,
            message="mail 어댑터 미구현 (Phase 0 스캐폴드)",
        )
