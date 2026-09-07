"""최소 cron due-check — 기획서 registry.yaml에서 실제 쓰는 패턴만 지원.

Phase 1에서 n8p/APScheduler/Claude Code Routine으로 교체 예정(기획서 §5.4).
지원 패턴: "*/N * * * *", "0 */N * * *", "0 H * * *", "0 H D * *"
(분 단위 * /N, 시간 단위 * /N, 고정 시:분, 월 1회 D일 H시)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DEFAULT_STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "state.json"


@dataclass
class CronField:
    raw: str

    def matches(self, value: int) -> bool:
        if self.raw == "*":
            return True
        if self.raw.startswith("*/"):
            step = int(self.raw[2:])
            return value % step == 0
        return int(self.raw) == value


def is_due(cron_expr: str, at: Optional[datetime] = None) -> bool:
    at = at or datetime.now(timezone.utc)
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError(f"지원하지 않는 cron 표현식: {cron_expr}")
    minute, hour, dom, month, dow = (CronField(p) for p in parts)
    return (
        minute.matches(at.minute)
        and hour.matches(at.hour)
        and dom.matches(at.day)
        and month.matches(at.month)
    )


class RunState:
    """소스별 마지막 실행 시각을 기록해 같은 tick에 중복 실행되지 않게 한다."""

    def __init__(self, path: Path = DEFAULT_STATE_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, str] = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def last_run(self, source_id: str) -> Optional[str]:
        return self._data.get(source_id)

    def mark_run(self, source_id: str, at: Optional[datetime] = None) -> None:
        at = at or datetime.now(timezone.utc)
        self._data[source_id] = at.isoformat()
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def already_ran_this_minute(self, source_id: str, at: Optional[datetime] = None) -> bool:
        at = at or datetime.now(timezone.utc)
        last = self.last_run(source_id)
        if not last:
            return False
        last_dt = datetime.fromisoformat(last)
        return last_dt.replace(second=0, microsecond=0) == at.replace(second=0, microsecond=0)
