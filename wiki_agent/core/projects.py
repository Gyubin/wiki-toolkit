"""Project-scoped knowledge under 01_Projects/<repo>/: sessions and ADRs."""
from __future__ import annotations

import re
from pathlib import Path

from .. import schema
from . import index


def project_slug(repo: Path | str) -> str:
    name = Path(repo).name
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


def ensure_project(vault: Path, repo: Path | str) -> Path:
    slug = project_slug(repo)
    base = Path(vault) / "01_Projects" / slug
    for sub in ("sessions", "decisions"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    idx = base / "project-index.md"
    if not idx.exists():
        idx.write_text(f"# Project: {slug}\n\n", encoding="utf-8")
    return base


def create_session_summary(
    vault: Path, *, repo: Path | str, title: str, body: str,
    date_str: str, seq: int, sensitivity: str = "work",
) -> Path:
    base = ensure_project(vault, repo)
    sid = schema.make_id("session", date_str, seq)
    meta = {
        "type": "session", "id": sid, "repo": project_slug(repo),
        "title": title, "sensitivity": sensitivity, "created": date_str,
    }
    path = base / "sessions" / f"{sid}.md"
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.append_log(vault, "ingest-log", f"session {sid} ({project_slug(repo)})")
    return path


def create_decision(
    vault: Path, *, repo: Path | str, title: str, context: str, decision: str,
    alternatives: str, consequences: str, date_str: str, seq: int,
    sensitivity: str = "work",
) -> Path:
    base = ensure_project(vault, repo)
    did = schema.make_id("decision", date_str, seq)
    meta = {
        "type": "decision", "id": did, "repo": project_slug(repo),
        "title": title, "status": "accepted", "sensitivity": sensitivity,
        "created": date_str,
    }
    body = (
        f"## Context\n\n{context}\n\n## Decision\n\n{decision}\n\n"
        f"## Alternatives\n\n{alternatives}\n\n## Consequences\n\n{consequences}\n"
    )
    path = base / "decisions" / f"{did}.md"
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    return path
