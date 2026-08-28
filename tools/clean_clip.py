#!/usr/bin/env python
"""클립 파일의 인라인 svg를 텍스트나 라벨로 줄인다.

    uv run python tools/clean_clip.py <클립.md> ...            # 무엇이 바뀔지만 보고
    uv run python tools/clean_clip.py <클립.md> ... --write     # 제자리에서 고쳐 쓴다

**create_source가 자동으로 부르지 않는다.** 캡처는 원문 그대로여야 한다는 게 계약이고,
도구가 조용히 본문을 줄이면 나중에 "이 source는 원문인가 가공본인가"를 파일에서 알 수 없다.
그래서 명시적인 앞 단계로 둔다. 순서는 CLAUDE.md의 Inbox 처리 절차와 같다:

    1. 클립을 먼저 커밋한다 (원본 바이트가 git에 남아야 되돌릴 수 있다)
    2. 이 스크립트를 --write로 돌린다
    3. 줄어든 클립을 커밋한다 (여기 diff가 무엇을 버렸는지의 영수증이다)
    4. create_source에 content_path로 줄어든 파일을 넘긴다

svg가 없는 파일은 건드리지 않는다. 여러 개를 한 번에 넘겨도 되고, 바뀐 파일만 보고한다.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wiki_toolkit.core import sources  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+", type=Path, help="클립 md 파일")
    ap.add_argument("--write", action="store_true",
                    help="제자리에서 고쳐 쓴다 (기본은 보고만)")
    args = ap.parse_args()

    touched = 0
    for p in args.paths:
        if not p.is_file():
            print(f"[건너뜀] 파일이 아님: {p}", file=sys.stderr)
            continue
        before = p.read_text(encoding="utf-8")
        after, report = sources.strip_svg(before)
        if not report:
            continue
        touched += 1
        counts = Counter(r["kind"] for r in report)
        kinds = ", ".join(f"{k} {n}개" for k, n in counts.most_common())
        print(f"{p.name}\n  {len(before):,}자 -> {len(after):,}자 "
              f"({(1 - len(after) / len(before)) * 100:.1f}% 감소), svg {len(report)}개: {kinds}")
        for r in report:
            print(f"    {r['kind']:9} {r['before']:>8,}자 -> {r['after']:>7,}자")
        if args.write:
            p.write_text(after, encoding="utf-8")

    if not touched:
        print("svg가 있는 파일이 없다. 바꾼 것 없음.")
    elif not args.write:
        print("\n보고만 했다. 실제로 고치려면 --write를 붙인다 (먼저 원본을 커밋할 것).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
