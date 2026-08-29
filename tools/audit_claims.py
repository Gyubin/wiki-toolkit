"""vault의 claim 파일에서 직접 세고, 인용문을 source Raw와 대조한다.

    uv run --directory wiki-toolkit python tools/audit_claims.py <vault> [claim-id-접두사]

ingest가 끝나면 기억이 아니라 이 스크립트로 확인한다. claim 파일의 `## 원문`은 blockquote로
저장되므로(줄마다 `> `, 빈 줄은 `>`) 그것을 벗겨내고 대조한다.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from wiki_toolkit import schema
from wiki_toolkit.core.lint import _ELISION  # 생략 표시 정의는 lint 하나만 갖는다

sys.path.insert(0, str(Path(__file__).parent))
from check_quotes import fold_map  # noqa: E402  (경로를 넣은 뒤에야 import된다)


def unquote(body: str) -> str:
    """`## 원문` blockquote를 원래 텍스트로 되돌린다."""
    if "## 원문" not in body:
        return ""
    lines = []
    for ln in body.split("## 원문", 1)[1].strip("\n").split("\n"):
        if ln.startswith("> "):
            lines.append(ln[2:])
        elif ln.strip() == ">":
            lines.append("")
        elif ln.startswith(">"):
            lines.append(ln[1:])
        else:
            lines.append(ln)
    return "\n".join(lines)


def main() -> None:
    vault = Path(sys.argv[1]).resolve()
    only = sys.argv[2] if len(sys.argv) > 2 else ""

    raws: dict[str, str] = {}
    for p in (vault / "00_Inbox" / "raw").glob("*.md"):
        text = p.read_text(encoding="utf-8")
        m = re.search(r"^id: (source-\S+)$", text, re.M)
        if m:
            raws[m.group(1)] = text.split("## Raw", 1)[1].lstrip("\n")

    rows = []
    for p in sorted((vault / "10_Claims").rglob("claim-*.md")):
        meta, body = schema.parse_doc(p.read_text(encoding="utf-8"))
        if only and not meta["id"].startswith(only):
            continue
        rows.append((meta, unquote(body)))

    assert rows, f"claim 0개. vault 경로를 확인해라: {vault} (필터 {only!r})"

    metas = [m for m, _ in rows]
    print("claim 개수:", len(rows))
    print("status:", dict(Counter(m.get("status") for m in metas)))
    print("evidence_refs 빈 것:", [m["id"] for m in metas if not m.get("evidence_refs")] or "없음")
    print("source_refs 없는 것:", [m["id"] for m in metas if not m.get("source_refs")] or "없음")
    print(
        "proposed_status 없는 것:",
        [m["id"] for m in metas if not m.get("proposed_status")] or "없음",
    )
    print("claim_type:", dict(Counter(m.get("claim_type") for m in metas)))
    print("proposed_status 분포:", dict(Counter(m.get("proposed_status") for m in metas)))
    bad_type = [m["id"] for m in metas if m.get("claim_type") not in schema.CLAIM_TYPES]
    print("claim_type 스키마 밖:", bad_type or "없음")
    print("source별:", dict(Counter((m.get("source_refs") or ["?"])[0] for m in metas)))

    noq, miss = [], []
    for meta, quote in rows:
        q = quote.strip()
        if not q:
            noq.append(meta["id"])
            continue
        sid = (meta.get("source_refs") or [None])[0]
        raw = raws.get(sid)
        if raw is None:
            miss.append((meta["id"], "source raw 없음"))
            continue
        # "(...)"는 인용문 안에서 "여기를 건너뛰었다"를 나타내는 표시다. core/lint.py의
        # quote_not_in_source가 이 기준으로 쪼개 조각별로 찾으므로 여기도 같게 맞춘다.
        # 안 맞추면 생략 인용문이 전부 "원문에 없음"으로 나와, 멀쩡한 claim을 결함으로 읽게 된다
        # (2026-08-30에 claim-20260827의 13건이 그렇게 보였다).
        parts = [p for p in (s.strip() for s in q.split(_ELISION)) if p]
        if all(p in raw for p in parts):
            continue
        nr, _ = fold_map(raw)
        folded_ok = all(fold_map(p)[0] in nr for p in parts)
        why = "정규화 후 일치(공백이나 기호 차이)" if folded_ok else "원문에 없음"
        miss.append((meta["id"], why))
    print("인용문 없는 claim:", noq or "없음")
    print("인용문 불일치:", miss or "없음")
    short = [m["id"] for m, q in rows if q.strip() and len(q.strip()) < 40]
    print("인용문 40자 미만:", short or "없음")


if __name__ == "__main__":
    main()
