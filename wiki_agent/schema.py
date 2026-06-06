"""Single source of truth: enums, IDs, frontmatter (mirrors design doc §6)."""
from __future__ import annotations

import datetime as _dt
import yaml

CLAIM_TYPES = (
    "technical_fact", "person_claim", "opinion", "hypothesis",
    "decision", "observation", "instruction", "misconception",
)
CLAIM_STATUSES = (
    "unverified", "verified", "attributed", "opinion", "partially_true",
    "accepted_for_now", "disputed", "outdated", "deprecated", "rejected",
)
SENSITIVITIES = ("personal", "work", "confidential")
WIKI_PAGE_TYPES = ("concept", "pattern", "glossary", "comparison", "misconception")
LEARNING_LEVELS = ("unknown", "seen", "explained", "used", "reviewed", "can-teach")


def today_str() -> str:
    return _dt.date.today().isoformat()


def make_id(prefix: str, date_str: str, seq: int) -> str:
    compact = date_str.replace("-", "")
    return f"{prefix}-{compact}-{seq:03d}"


def render_doc(meta: dict, body: str) -> str:
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{fm}\n---\n\n{body.rstrip()}\n"


def parse_doc(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    meta = yaml.safe_load(fm) or {}
    return meta, body.lstrip("\n")


def validate_claim_type(t: str) -> str:
    if t not in CLAIM_TYPES:
        raise ValueError(f"unknown claim_type: {t}")
    return t


def validate_status(s: str) -> str:
    if s not in CLAIM_STATUSES:
        raise ValueError(f"unknown status: {s}")
    return s
