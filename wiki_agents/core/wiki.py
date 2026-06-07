"""Human-readable wiki pages with enforced frontmatter + index entry."""
from __future__ import annotations

import re
from pathlib import Path

from .. import schema
from . import index

_TYPE_DIR = {
    "concept": "Concepts", "pattern": "Patterns", "glossary": "Glossary",
    "comparison": "Comparisons", "misconception": "Misconceptions",
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "page"


def create_wiki_page(
    vault: Path, *, name: str, page_type: str, body: str,
    claim_refs: list[str], date_str: str, domain: list[str] | None = None,
    sensitivity: str = "personal",
) -> Path:
    if page_type not in schema.WIKI_PAGE_TYPES:
        raise ValueError(f"unknown page_type: {page_type}")
    meta = {
        "type": page_type, "name": name, "domain": domain or [],
        "status": "draft", "sensitivity": sensitivity,
        "created": date_str, "updated": date_str,
        "claim_refs": claim_refs, "code_refs": [],
    }
    path = Path(vault) / "03_Resources" / _TYPE_DIR[page_type] / f"{_slug(name)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.update_index(vault, "wiki-index", _slug(name), f"{name} ({page_type})")
    return path


def update_wiki_page(
    path: Path, *, body: str | None = None,
    add_claim_refs: list[str] | None = None, status: str | None = None,
) -> Path:
    path = Path(path)
    meta, old_body = schema.parse_doc(path.read_text(encoding="utf-8"))
    if add_claim_refs:
        refs = list(meta.get("claim_refs", []))
        for r in add_claim_refs:
            if r not in refs:
                refs.append(r)
        meta["claim_refs"] = refs
    if status:
        meta["status"] = status
    path.write_text(schema.render_doc(meta, body if body is not None else old_body),
                    encoding="utf-8")
    return path
