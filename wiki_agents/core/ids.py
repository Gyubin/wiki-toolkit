"""Next free sequence number for {prefix}-{yyyymmdd}-{NNN}.md files.

파일 개수가 아니라 해당 날짜의 최대 시퀀스 + 1을 쓴다. 파일이 다른 상태 폴더로
이동(승격)하거나 삭제되어도 기존 ID를 재사용하지 않는다.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path


def next_seq(vault: Path, prefix: str, date_str: str, subdirs: Iterable[str]) -> int:
    compact = date_str.replace("-", "")
    pat = re.compile(rf"^{re.escape(prefix)}-{compact}-(\d+)$")
    top = 0
    for sub in subdirs:
        base = Path(vault) / sub
        if not base.exists():
            continue
        for p in base.rglob(f"{prefix}-{compact}-*.md"):
            m = pat.match(p.stem)
            if m:
                top = max(top, int(m.group(1)))
    return top + 1
