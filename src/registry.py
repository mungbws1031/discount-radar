"""Source Registry 로더 — 기획서 §3.5, §5.1 Source Registry."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "sources" / "registry.yaml"


@dataclass
class Source:
    id: str
    name: str
    domain: list[str]
    method: str  # api | rss | html | browser | mail | manual
    extract: str  # rules | llm
    policy: str  # allowed | gray | blocked
    schedule: str  # cron
    url: str = ""
    priority: int = 1
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Source":
        known = {"id", "name", "domain", "method", "extract", "policy", "schedule", "url", "priority"}
        extra = {k: v for k, v in d.items() if k not in known}
        return cls(
            id=d["id"],
            name=d["name"],
            domain=d.get("domain", []),
            method=d["method"],
            extract=d.get("extract", "rules"),
            policy=d.get("policy", "gray"),
            schedule=d.get("schedule", "0 * * * *"),
            url=d.get("url", "") or "",
            priority=d.get("priority", 1),
            extra=extra,
        )


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> list[Source]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return [Source.from_dict(s) for s in raw.get("sources", [])]


def fetchable(sources: list[Source]) -> list[Source]:
    """robots.txt·약관상 자동 수집이 금지된(policy=blocked) 소스는 제외.

    기획서 §3.5: blocked 소스는 MAIL/MAN 대체 경로로만 다룬다.
    """
    return [s for s in sources if s.policy != "blocked" and s.url]
