"""Next free sequence number for {prefix}-{yyyymmdd}-{NNN} ids.

파일 개수가 아니라 해당 날짜의 최대 시퀀스 + 1을 쓴다. 파일이 다른 상태 폴더로
이동(승격)하거나 삭제되어도 기존 ID를 재사용하지 않는다.

id를 파일명에서만 읽으면 파일 이름을 바꾸는 순간 번호가 리셋된다. 2026-08-28에 source
파일명을 사람이 읽을 제목으로 바꿔보니 004까지 있는데도 1이 나왔고, 그대로 두면 다음
create_source가 이미 있는 id를 다시 발급한다. 그래서 파일명이 id 모양이 아니면
frontmatter의 `id`를 읽는다. id의 단일 출처는 frontmatter다 (AGENTS.md §2).
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from .. import schema


def next_seq(vault: Path, prefix: str, date_str: str, subdirs: Iterable[str]) -> int:
    compact = date_str.replace("-", "")
    pat = re.compile(rf"^{re.escape(prefix)}-{compact}-(\d+)$")
    top = 0
    for sub in subdirs:
        base = Path(vault) / sub
        if not base.exists():
            continue
        for p in base.rglob("*.md"):
            m = pat.match(p.stem)
            if m is None:
                # 파일명이 id가 아닐 때만 파일을 연다 (claim은 파일명이 곧 id라 안 연다)
                m = pat.match(_frontmatter_id(p) or "")
            if m:
                top = max(top, int(m.group(1)))
    return top + 1


def _frontmatter_id(path: Path) -> str:
    """frontmatter의 `id`. 못 읽으면 빈 문자열 (깨진 파일은 lint의 몫)."""
    try:
        meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ""
    return str(meta.get("id") or "")
