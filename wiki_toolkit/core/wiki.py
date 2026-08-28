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
    return re.sub(r"[^a-z0-9가-힣]+", "-", name.lower()).strip("-") or "page"


def create_wiki_page(
    vault: Path, *, name: str, page_type: str, body: str,
    claim_refs: list[str], date_str: str, domain: list[str] | None = None,
    sensitivity: str = "personal", aliases: list[str] | None = None,
    overwrite: bool = False,
) -> Path:
    if page_type not in schema.WIKI_PAGE_TYPES:
        raise ValueError(f"unknown page_type: {page_type}")
    meta = {
        "type": page_type, "name": name, "domain": domain or [],
        # aliases: 한글 제목의 영문 원어 등 다른 이름. 검색 색인(head)과 Obsidian
        # 퀵 스위처가 둘 다 이 키를 읽는다.
        "aliases": aliases or [],
        "status": "draft", "sensitivity": sensitivity,
        "created": date_str, "updated": date_str,
        "claim_refs": claim_refs, "code_refs": [],
    }
    path = Path(vault) / "03_Resources" / _TYPE_DIR[page_type] / f"{_slug(name)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"{path.name} already exists; use update_wiki_page or overwrite=True"
        )
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.update_index(vault, "wiki-index", _slug(name), f"{name} ({page_type})")
    return path


def update_wiki_page(
    path: Path, *, body: str | None = None,
    add_claim_refs: list[str] | None = None, status: str | None = None,
    aliases: list[str] | None = None, date_str: str | None = None,
) -> Path:
    path = Path(path)
    meta, old_body = schema.parse_doc(path.read_text(encoding="utf-8"))
    if aliases is not None:
        meta["aliases"] = aliases
    if add_claim_refs:
        refs = list(meta.get("claim_refs", []))
        for r in add_claim_refs:
            if r not in refs:
                refs.append(r)
        meta["claim_refs"] = refs
    if status:
        meta["status"] = status
    if date_str:
        # 다른 모든 update 경로는 updated를 갱신한다. 여기만 안 하면 frontmatter가
        # 마지막 변경 시점을 속인다 (Obsidian과 사람이 보는 값이다).
        meta["updated"] = date_str
    path.write_text(schema.render_doc(meta, body if body is not None else old_body),
                    encoding="utf-8")
    return path
