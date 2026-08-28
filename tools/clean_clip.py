#!/usr/bin/env python
"""클립 파일의 인라인 svg를 텍스트나 라벨로 줄인다.

    uv run python tools/clean_clip.py <클립.md> ...            # 무엇이 바뀔지만 보고
    uv run python tools/clean_clip.py <클립.md> ... --write     # 제자리에서 고쳐 쓴다

**ingest에 이 단계는 필요 없다.** `create_source`와 `update_source_raw`가 같은 함수
(`core.sources.strip_svg`)를 자동으로 부르고, 무엇을 줄였는지는 ingest-log의 `captured ...`
줄에 남는다. 이 스크립트는 두 가지 용도로 남아 있다:

    - 넘기기 전에 무엇이 바뀔지 미리 보기 (기본 동작이 보고만이다)
    - 캡처가 뒤틀렸는지 볼 때, 커밋된 원본 클립을 같은 함수에 통과시킨 결과와
      저장된 Raw를 비교하기 위한 기준값 만들기

--write는 클립 파일 자체를 줄일 때만 쓴다. 그때는 먼저 원본을 커밋해서 git에 남긴다.
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
