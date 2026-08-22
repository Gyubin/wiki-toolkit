"""Learning items + spaced-repetition review driver."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from .. import schema
from . import index

_INTERVALS = [1, 3, 7, 16, 35]  # days per successful stage


def _add_days(date_str: str, days: int) -> str:
    return (_dt.date.fromisoformat(date_str) + _dt.timedelta(days=days)).isoformat()


def create_learning_item(
    vault: Path, *, topic: str, skill_area: str, date_str: str, seq: int,
    source_refs: list[str] | None = None, wiki_refs: list[str] | None = None,
) -> Path:
    lid = schema.make_id("learning", date_str, seq)
    meta = {
        "type": "learning_item", "id": lid, "topic": topic,
        "skill_area": skill_area, "level": "unknown",
        "source_refs": source_refs or [], "wiki_refs": wiki_refs or [],
        "created": date_str, "next_review": date_str,
    }
    path = Path(vault) / "30_Learning/flashcards" / f"{lid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"{lid} already exists; pick a fresh seq")
    path.write_text(schema.render_doc(meta, f"## Topic\n\n{topic}\n"), encoding="utf-8")
    index.update_index(vault, "learning-index", lid, f"{topic} - unknown")
    return path


def _find(vault: Path, learning_id: str) -> Path:
    for p in (Path(vault) / "30_Learning").rglob(f"{learning_id}.md"):
        return p
    raise FileNotFoundError(learning_id)


def list_due_reviews(vault: Path, today_str: str) -> list[dict]:
    due = []
    for p in (Path(vault) / "30_Learning").rglob("learning-*.md"):
        meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        # YAML이 따옴표 없는 날짜를 date 객체로 파싱해도 문자열 비교가 되게 강제
        nr = meta.get("next_review")
        if nr and str(nr) <= today_str:
            due.append({"id": meta["id"], "topic": meta.get("topic", ""),
                        "level": meta.get("level", "unknown")})
    return sorted(due, key=lambda r: r["id"])


def record_review(vault: Path, learning_id: str, *, passed: bool, today_str: str) -> Path:
    path = _find(vault, learning_id)
    meta, body = schema.parse_doc(path.read_text(encoding="utf-8"))
    levels = list(schema.LEARNING_LEVELS)
    lvl = str(meta.get("level", "unknown"))
    cur = levels.index(lvl) if lvl in levels else 0
    if passed:
        new_idx = min(cur + 1, len(levels) - 1)
        meta["level"] = levels[new_idx]
        meta["next_review"] = _add_days(today_str, _INTERVALS[min(cur, len(_INTERVALS) - 1)])
    else:
        meta["next_review"] = _add_days(today_str, 1)
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.update_index(vault, "learning-index", learning_id,
                       f"{meta.get('topic','')} - {meta['level']}")
    return path
