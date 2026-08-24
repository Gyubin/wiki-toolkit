"""파이프라인 진행 상태와 "다음에 할 일" 계산 (순수, 결정론적).

파이프라인은 clip -> source -> claim(unverified) -> verified -> wiki page -> learning item
순인데, 각 단계가 사람의 다음 행동을 기다린다. 그 대기 지점을 사람이 기억하지 않아도 되게
도구가 매번 계산해 알려준다. 프롬프트에 적어두는 것과 달리 이건 데이터 경로에 있어서
Claude Code, 웹앱, SDK 에이전트 어느 쪽으로 들어와도 똑같이 나온다.
"""
from __future__ import annotations

from pathlib import Path

from .. import schema

# 사람의 행동을 기다리는 단계들을 앞선 것부터. 앞 단계가 밀려 있으면 뒤는 말하지 않는다.
_INBOX = "00_Inbox"
_PENDING = "10_Claims/pending"
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
    """각 대기 지점의 개수. 파일명(=id)만 보므로 claim 본문은 파싱하지 않는다."""
    vault = Path(vault)
    verified = _stems(vault, _VERIFIED, "claim-*.md")
    from . import learning  # 지연 import: core 내부 순환 방지
    return {
        "unstructured_inbox": _unstructured_inbox(vault),
        "pending_claims": sorted(_stems(vault, _PENDING, "claim-*.md")),
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
    if s["pending_claims"]:
        n = len(s["pending_claims"])
        return (f"다음: pending claim {n}개가 검토를 기다린다 "
                f"(증거가 있으면 verified로 승격, 없으면 웹 Verify 탭에서 승인)")
    if s["verified_unlinked"]:
        n = len(s["verified_unlinked"])
        return (f"다음: 어떤 wiki page에도 안 실린 verified claim {n}개가 있다 "
                f"(주제별로 묶어 wiki page로 승격)")
    if s["due_reviews"]:
        n = len(s["due_reviews"])
        return f"다음: 복습할 학습카드 {n}개가 도래했다"
    return None
