"""파이프라인 진행 상태와 "다음에 할 일" 계산 (순수, 결정론적).

파이프라인은 clip -> source -> claim(unverified) -> verified -> wiki page -> learning item
순인데, 각 단계가 사람의 다음 행동을 기다린다. 그 대기 지점을 사람이 기억하지 않아도 되게
도구가 매번 계산해 알려준다. 프롬프트에 적어두는 것과 달리 이건 데이터 경로에 있어서
Claude Code든 CLI든 어느 쪽으로 들어와도 똑같이 나온다.
"""
from __future__ import annotations

from pathlib import Path

from .. import schema

# 사람의 행동을 기다리는 단계들을 앞선 것부터. 앞 단계가 밀려 있으면 뒤는 말하지 않는다.
_INBOX = "00_Inbox"
_CLAIMS = "10_Claims"
_VERIFIED = "10_Claims/verified"
_WIKI = "03_Resources"
_LEARNING = "30_Learning"


def _stems(vault: Path, rel: str, pattern: str = "*.md") -> set[str]:
    return {p.stem for p in (Path(vault) / rel).glob(pattern)}


def _unstructured_inbox(vault: Path) -> list[str]:
    """00_Inbox에 있는 wiki 스키마 없는 파일 (클리퍼 드롭 등, 아직 ingest 전)."""
    out = []
    for p in (Path(vault) / _INBOX).rglob("*.md"):
        try:
            meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: S112 - 깨진 파일은 lint의 몫
            continue
        if not meta.get("id"):
            out.append(p.name)
    return sorted(out)


def _unverified_claims(vault: Path) -> list[str]:
    """`status: unverified`인 claim. 폴더가 아니라 status를 센다.

    예전에는 `10_Claims/pending` 폴더의 파일 수를 셌다. 그런데 `accepted_for_now`와
    `partially_true`도 그 폴더에 산다(`claims._STATUS_DIR`). 그래서 2026-08-28에 claim
    72건을 검토해 전부 승격한 뒤에도 안내가 "pending claim 53개가 검토를 기다린다"를
    계속 보고했다. 방금 끝낸 일을 남았다고 말하는 안내는 곧 통째로 무시된다.
    """
    out = []
    for p in (Path(vault) / _CLAIMS).rglob("claim-*.md"):
        try:
            meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: S112 - 깨진 파일은 lint의 몫
            continue
        if meta.get("status") == "unverified":
            out.append(p.stem)
    return sorted(out)


def _referenced_claims(vault: Path) -> set[str]:
    """어떤 wiki page의 claim_refs에든 등장하는 claim id."""
    refs: set[str] = set()
    for p in (Path(vault) / _WIKI).rglob("*.md"):
        try:
            meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: S112
            continue
        refs.update(str(r) for r in (meta.get("claim_refs") or []))
    return refs


def vault_state(vault: Path, today_str: str) -> dict:
    """각 대기 지점의 목록. 값은 파일 경로가 아니라 id(=파일 stem)다."""
    vault = Path(vault)
    verified = _stems(vault, _VERIFIED, "claim-*.md")
    from . import learning  # 지연 import: core 내부 순환 방지
    return {
        "unstructured_inbox": _unstructured_inbox(vault),
        "unverified_claims": _unverified_claims(vault),
        "verified_unlinked": sorted(verified - _referenced_claims(vault)),
        "verified_claims": sorted(verified),
        "wiki_pages": sorted(p.stem for p in (vault / _WIKI).rglob("*.md")),
        "learning_items": sorted(p.stem for p in (vault / _LEARNING).rglob("learning-*.md")),
        "due_reviews": [r["id"] for r in learning.list_due_reviews(vault, today_str)],
    }


def next_step(vault: Path, today_str: str) -> str | None:
    """다음에 사람이 해야 할 한 가지. 대기 중인 게 없으면 None.

    앞 단계가 밀려 있으면 뒤 단계는 말하지 않는다. 한 번에 하나만 준다.
    """
    s = vault_state(vault, today_str)
    if s["unstructured_inbox"]:
        n = len(s["unstructured_inbox"])
        return f"다음: 00_Inbox에 아직 ingest 안 된 클립 {n}개가 있다 (인제스트해줘)"
    if s["unverified_claims"]:
        n = len(s["unverified_claims"])
        return (f"다음: 아직 검토 안 한 claim {n}개가 있다 "
                f"(promote_claim으로 승격: verified는 evidence_refs 필수, "
                f"확신이 없으면 attributed/opinion/accepted_for_now)")
    if s["verified_unlinked"]:
        n = len(s["verified_unlinked"])
        return (f"다음: 어떤 wiki page에도 안 실린 verified claim {n}개가 있다 "
                f"(주제별로 묶어 wiki page로 승격)")
    if s["due_reviews"]:
        n = len(s["due_reviews"])
        return f"다음: 복습할 학습카드 {n}개가 도래했다"
    return None
