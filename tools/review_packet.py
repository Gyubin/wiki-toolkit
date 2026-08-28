"""claim을 "내 문장 + 원문 인용" 짝으로 묶은 교차검증용 파일을 만든다.

    uv run --directory wiki-toolkit python tools/review_packet.py <vault> <claim-id-접두사> <out.md>

두 번째 리더에게 넘길 파일이다. vault 파일에서만 읽으므로 claim 문장을 다시 옮겨 적는 단계가 없다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from wiki_toolkit import schema

sys.path.insert(0, str(Path(__file__).parent))
from audit_claims import unquote  # noqa: E402  (경로를 넣은 뒤에야 import된다)


def main() -> None:
    vault = Path(sys.argv[1]).resolve()
    prefix = sys.argv[2]
    out = Path(sys.argv[3])

    rows = []
    for p in sorted((vault / "10_Claims").rglob("claim-*.md")):
        meta, body = schema.parse_doc(p.read_text(encoding="utf-8"))
        if not meta["id"].startswith(prefix):
            continue
        rows.append((meta, unquote(body).strip()))

    assert rows, f"claim 0개. vault 경로와 접두사를 확인해라: {vault} {prefix!r}"

    buf = [f"# 검토 대상 claim {len(rows)}건\n"]
    for meta, quote in rows:
        sources = ",".join(meta.get("source_refs") or [])
        buf.append(
            f"## {meta['id']}  [{meta['claim_type']}] "
            f"proposed={meta.get('proposed_status')} source={sources}"
        )
        buf.append(f"\n### 내 문장 (한국어 요약)\n{meta['claim']}")
        buf.append(f"\n### 원문 인용 (source에서 그대로)\n{quote}\n")

    out.write_text("\n".join(buf), encoding="utf-8")
    print(out, len(rows), "claims,", len(out.read_text(encoding="utf-8")), "chars")


if __name__ == "__main__":
    main()
