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
    # 펜스는 줄 단위로만 인식한다. 값이나 본문 중간의 "---"는 구분자가 아니다.
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 3)
    if end != -1:
        fm, body = text[4:end], text[end + 5:]
    elif text.endswith("\n---"):
        fm, body = text[4:-4], ""
    else:
        return {}, text  # 닫는 펜스 없음: frontmatter 없는 문서로 취급
    meta = yaml.safe_load(fm) or {}
    if not isinstance(meta, dict):
        return {}, text
    return meta, body.lstrip("\n")


def validate_claim_type(t: str) -> str:
    if t not in CLAIM_TYPES:
        raise ValueError(f"unknown claim_type: {t}")
    return t


def validate_status(s: str) -> str:
    if s not in CLAIM_STATUSES:
        raise ValueError(f"unknown status: {s}")
    return s
