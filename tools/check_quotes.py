"""인용문 후보를 source Raw와 대조한다.

    uv run --directory wiki-toolkit python tools/check_quotes.py <vault> <cand.json> [--apply]

입력 JSON은 `[{"key": ..., "source_id": ..., "quote": ...}, ...]` 배열이다.
출력은 후보마다 EXACT / FIXED / NOTFOUND 한 줄이고, FIXED면 원문에서 잘라낸 정확한 문자열을 찍는다.
`--apply`를 주면 그 문자열을 JSON에 되써준다.

**create_claim에 넘길 문자열은 항상 이 JSON에서 가져온다.** 손으로 옮겨 적으면 x와 ×,
하이픈과 en dash가 조용히 바뀐다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 대조용 정규화 표. 실제 인용문은 항상 source 원본에서 잘라 쓰므로 여기서 바꾼 글자가
# vault로 들어가지는 않는다.
FOLD = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", "‑": "-",
    "×": "x", "ᵀ": "T", " ": " ", "⠀": " ",
    "​": "", "﻿": "", "…": "...", "·": ".",
}


def fold_map(s: str) -> tuple[str, list[int]]:
    """정규화 문자열과, 정규화 인덱스에서 원본 인덱스로 가는 매핑을 함께 돌려준다."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    for i, ch in enumerate(s):
        rep = FOLD.get(ch, ch)
        if rep.isspace():
            if prev_space:
                continue
            rep = " "
            prev_space = True
        else:
            prev_space = False
        for c in rep:
            out.append(c)
            idx.append(i)
    return "".join(out), idx


def raw_body(vault: Path, source_id: str) -> str:
    """source 파일명은 원문 제목이라 glob으로 못 찾는다. frontmatter의 id로 찾는다."""
    for p in (vault / "00_Inbox" / "raw").glob("*.md"):
        text = p.read_text(encoding="utf-8")
        if f"\nid: {source_id}\n" in text:
            return text.split("## Raw", 1)[1].lstrip("\n")
    raise SystemExit(f"source not found: {source_id}")


def main() -> int:
    vault = Path(sys.argv[1]).resolve()
    cand = Path(sys.argv[2])
    apply = len(sys.argv) > 3 and sys.argv[3] == "--apply"

    rows = json.loads(cand.read_text(encoding="utf-8"))
    bodies: dict[str, str] = {}
    folded: dict[str, tuple[str, list[int]]] = {}
    fixed: list[str] = []
    nbad = 0

    for r in rows:
        sid = r["source_id"]
        if sid not in bodies:
            bodies[sid] = raw_body(vault, sid)
            folded[sid] = fold_map(bodies[sid])
        body = bodies[sid]
        nbody, nidx = folded[sid]
        quote = r["quote"]
        if quote in body:
            print(f"EXACT    {r['key']}")
            continue
        nquote, _ = fold_map(quote)
        pos = nbody.find(nquote)
        nbad += 1
        if pos < 0:
            print(f"NOTFOUND {r['key']}  (정규화 후에도 못 찾음)")
            print(f"  준 것: {quote[:120]!r}")
            continue
        start = nidx[pos]
        end = nidx[pos + len(nquote) - 1] + 1
        print(f"FIXED    {r['key']}  <- 아래 문자열을 그대로 써라")
        print(json.dumps(body[start:end], ensure_ascii=False))
        r["quote"] = body[start:end]
        fixed.append(r["key"])

    print(f"\n총 {len(rows)}건, 불일치 {nbad}건")
    if fixed and apply:
        cand.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print("JSON에 원문 문자열을 반영했다:", ", ".join(fixed))
    return 1 if nbad else 0


if __name__ == "__main__":
    raise SystemExit(main())
