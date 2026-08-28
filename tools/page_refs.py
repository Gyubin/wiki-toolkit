"""페이지 본문에서 claim id를 뽑아 `claim_refs`로 쓸 목록을 만든다.

    uv run --directory wiki-toolkit python tools/page_refs.py <페이지 본문 디렉터리>

`claim_refs` frontmatter와 본문 `## 근거` 표가 어긋나면 근거를 되짚을 수 없거나 없는 근거를
주장하게 된다. 손으로 옮겨 적지 말고 이 출력에서 가져온다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main() -> None:
    for p in sorted(Path(sys.argv[1]).glob("*.md")):
        ids = sorted(set(re.findall(r"claim-\d{8}-\d{3}", p.read_text(encoding="utf-8"))))
        print(f"{p.name}  ({len(ids)}건)")
        print(json.dumps(ids, ensure_ascii=False))


if __name__ == "__main__":
    main()
