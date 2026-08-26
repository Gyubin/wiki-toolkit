#!/usr/bin/env python
"""한 source에서 나온 pending claim들의 검토표를 HTML로 찍는다.

    uv run python tools/render_review.py <vault> <source-id> --out review.html

**내용은 vault 파일에서만 읽는다.** 사람이나 모델이 claim 문장과 인용문을 다시 옮겨 적는
단계가 없다. 2026-08-27에 클립 4개를 인제스트하면서 바로 그 옮겨 적기가 곱슬따옴표 18개와
단어 하나를 바꿔놨기 때문이다. 검토표를 만들면서 같은 실수를 반복하면 검토 자체가 무의미하다.

표시(marks)도 전부 기계로 뽑는다. "이 claim이 원문을 비틀었다"는 판단은 claim을 쓴 쪽이
내릴 수 없으므로 넣지 않는다. 대신 사람이 어디를 봐야 하는지만 짚는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wiki_agents import schema  # noqa: E402
from wiki_agents.core import claims as claims_core  # noqa: E402

TEMPLATE = Path(__file__).with_name("review_template.html")

# 인용문 안의 생략 표시. lint의 quote_not_in_source와 같은 기준이어야 한다.
ELISION = "(...)"

# 숫자 토큰: 자릿수 구분 쉼표와 소수점을 품는다 (59,136 / 2.4 / 41.8).
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

MIN_QUOTE_CHARS = 40


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def norm_numbers(s: str) -> str:
    """자릿수 쉼표를 없앤다. 59,136과 59136이 같은 숫자로 보이게."""
    return re.sub(r"(?<=\d),(?=\d)", "", s)


def read_source(vault: Path, source_id: str) -> tuple[dict, str]:
    for p in (vault / "00_Inbox").rglob(f"{source_id}.md"):
        return schema.parse_doc(p.read_text(encoding="utf-8"))
    raise SystemExit(f"source를 찾을 수 없습니다: {source_id}")


def clip_title(raw_body: str) -> str:
    """클립이 들고 온 자기 frontmatter에서 title을 꺼낸다. 없으면 빈 문자열."""
    m = re.search(r'^\s*title:\s*"?(.+?)"?\s*$', raw_body, re.M)
    return m.group(1).strip() if m else ""


def marks_for(claim: str, quote: str, source_hay: str, meta: dict) -> list[dict]:
    """사람이 어디를 봐야 하는지 기계로 짚는다. 판단은 넣지 않는다."""
    out: list[dict] = []

    if not quote:
        out.append({"text": "인용문이 없습니다. 원문을 직접 열어 대조해야 합니다.", "detail": ""})
        return out

    segments = [norm_ws(x) for x in quote.split(ELISION)]
    missing = [s for s in segments if s and s not in source_hay]
    if missing:
        out.append({
            "text": "이 인용문이 source 본문에 그대로 없습니다. 인용문 자체가 틀렸을 수 있습니다.",
            "detail": missing[0][:80],
        })

    if len(norm_ws(quote)) < MIN_QUOTE_CHARS:
        out.append({
            "text": f"인용문이 {len(norm_ws(quote))}자로 짧습니다. 근거로 충분한지 보세요.",
            "detail": "",
        })

    hay_num = norm_numbers(norm_ws(quote))
    absent = []
    for tok in NUMBER.findall(norm_numbers(norm_ws(claim))):
        if tok not in hay_num and tok not in absent:
            absent.append(tok)
    if absent:
        out.append({
            "text": "제 문장에는 있는데 인용문에는 없는 숫자가 있습니다. "
                    "숫자는 특히 잘못 옮기기 쉽습니다.",
            "detail": ", ".join(absent),
        })

    if meta.get("proposed_status") in ("attributed", "opinion") and not meta.get("speaker"):
        out.append({
            "text": "누구의 주장인지로 제안했는데 speaker가 비어 있습니다.",
            "detail": "",
        })

    return out


def build(vault: Path, source_id: str, title: str | None) -> dict:
    meta_src, raw_body = read_source(vault, source_id)
    source_hay = norm_ws(raw_body)

    rows = []
    for p in sorted((vault / "10_Claims").rglob("claim-*.md")):
        meta, body = schema.parse_doc(p.read_text(encoding="utf-8"))
        if source_id not in (meta.get("source_refs") or []):
            continue
        quote = claims_core.extract_quote(body)
        rows.append({
            "id": meta["id"],
            "claim": meta.get("claim", ""),
            "quote": quote,
            "claim_type": meta.get("claim_type", ""),
            "proposed_status": meta.get("proposed_status", ""),
            "speaker": meta.get("speaker", ""),
            "status": meta.get("status", ""),
            "marks": marks_for(meta.get("claim", ""), quote, source_hay, meta),
        })

    if not rows:
        raise SystemExit(f"{source_id}를 참조하는 claim이 없습니다. vault 경로를 확인하세요.")

    return {
        "source": {
            "id": source_id,
            "url": meta_src.get("url", ""),
            "origin": meta_src.get("origin", ""),
            "captured_at": str(meta_src.get("captured_at", "")),
            "title": title or clip_title(raw_body) or source_id,
        },
        "claims": rows,
        "flagged": sum(1 for r in rows if r["marks"]),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "generator": "tools/render_review.py",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("vault", type=Path)
    ap.add_argument("source_id")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--title", default=None, help="페이지 제목 (기본값은 클립의 title)")
    args = ap.parse_args()

    data = build(args.vault.resolve(), args.source_id, args.title)
    page = TEMPLATE.read_text(encoding="utf-8")

    # </script>가 데이터 안에 있으면 블록이 거기서 닫힌다. 유일한 탈출 지점이다.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("__DATA__", payload)
    page = page.replace("__TITLE__", html.escape(data["source"]["title"]))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")
    print(f"{args.out}  claim {len(data['claims'])}건, 표시된 것 {data['flagged']}건")
    for r in data["claims"]:
        for m in r["marks"]:
            print(f"  [{r['id']}] {m['text']} {m['detail']}".rstrip())


if __name__ == "__main__":
    main()
