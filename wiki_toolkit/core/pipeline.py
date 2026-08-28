"""파이프라인 진행 상태와 "다음에 할 일" 계산 (순수, 결정론적).

파이프라인은 clip -> source -> claim(unverified) -> 검토 -> wiki page -> learning item
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
_WIKI = "03_Resources"
_LEARNING = "30_Learning"

# wiki page가 정당하게 인용할 수 있는 status. verified 폴더만 세면 안 된다:
# 실사용 검토 결과는 거의 전부 attributed/accepted_for_now라 (2026-08-25 실측 18건 중
# verified 0건) "wiki page로 승격" 단계가 한 번도 발화하지 않았다.
_CITABLE_STATUSES = ("verified", "attributed", "accepted_for_now", "partially_true")


def _inbox_scan(vault: Path) -> tuple[list[str], list[str]]:
    """(아직 ingest 안 된 클립, ingest는 끝났고 삭제만 남은 클립 원본).

    id 없는 00_Inbox 파일이 클립이다. 그중 frontmatter의 url이 이미 등록된 source의
    url과 일치하면 ingest가 끝난 원본이다 (절차상 원본 삭제는 ingest 뒤에 온다). 이걸
    구분하지 않으면 세션이 끊긴 뒤 새 세션이 "인제스트해줘" 안내를 따라 같은 클립을
    다시 ingest해 중복 source를 만든다.

    파싱이 안 되는 파일도 ingest 대상으로 센다. 제목에 콜론이 든 클립이 YAML을 깨뜨리는
    일이 실제로 있었고, 조용히 건너뛰면 안내가 "클립 0개"라며 다음 단계로 넘어간다.
    """
    source_urls: set[str] = set()
    clips: list[tuple[str, str]] = []  # (파일명, 클립 frontmatter의 url)
    for p in (Path(vault) / _INBOX).rglob("*.md"):
        try:
            meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 깨진 클립도 ingest 대상이다 (lint가 unparseable로 보고)
            clips.append((p.name, ""))
            continue
        if meta.get("id"):
            if meta.get("url"):
                source_urls.add(str(meta["url"]))
            continue
        clips.append((p.name, str(meta.get("url") or meta.get("source") or "")))
    pending = sorted(n for n, u in clips if not (u and u in source_urls))
    leftovers = sorted(n for n, u in clips if u and u in source_urls)
    return pending, leftovers


def _claim_statuses(vault: Path) -> dict[str, str]:
    """claim id -> status. 폴더가 아니라 status를 센다.

    예전에는 `10_Claims/pending` 폴더의 파일 수를 셌다. 그런데 `accepted_for_now`와
    `partially_true`도 그 폴더에 산다(`claims._STATUS_DIR`). 그래서 2026-08-28에 claim
    72건을 검토해 전부 승격한 뒤에도 안내가 "pending claim 53개가 검토를 기다린다"를
    계속 보고했다. 방금 끝낸 일을 남았다고 말하는 안내는 곧 통째로 무시된다.
    """
    out: dict[str, str] = {}
    for p in (Path(vault) / _CLAIMS).rglob("claim-*.md"):
        try:
            meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: S112 - 깨진 파일은 lint의 몫
            continue
        if meta.get("id") and meta.get("status"):
            out[str(meta["id"])] = str(meta["status"])
    return out


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
    """각 대기 지점의 목록. 값은 파일 경로가 아니라 id(=파일 stem)나 파일명이다."""
    vault = Path(vault)
    pending_clips, leftovers = _inbox_scan(vault)
    statuses = _claim_statuses(vault)
    citable = {i for i, s in statuses.items() if s in _CITABLE_STATUSES}
    from . import learning  # 지연 import: core 내부 순환 방지
    return {
        "unstructured_inbox": pending_clips,
        "ingested_leftovers": leftovers,
        "unverified_claims": sorted(i for i, s in statuses.items() if s == "unverified"),
        "verified_claims": sorted(i for i, s in statuses.items() if s == "verified"),
        "citable_unlinked": sorted(citable - _referenced_claims(vault)),
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
    if s["ingested_leftovers"]:
        n = len(s["ingested_leftovers"])
        return (f"다음: ingest가 끝난 클립 원본 {n}개가 00_Inbox에 남아 있다 "
                f"(git rm으로 지우고 커밋; 원문은 source와 vault 히스토리에 있다)")
    if s["unverified_claims"]:
        n = len(s["unverified_claims"])
        return (f"다음: 아직 검토 안 한 claim {n}개가 있다 "
                f"(promote_claim으로 승격: verified는 evidence_refs 필수, "
                f"확신이 없으면 attributed/opinion/accepted_for_now; "
                f"검토표는 tools/render_review.py <vault> <source-id>로 찍는다)")
    if s["citable_unlinked"]:
        n = len(s["citable_unlinked"])
        return (f"다음: 어떤 wiki page에도 안 실린 검토 끝난 claim {n}개가 있다 "
                f"(주제별로 묶어 wiki page로 승격)")
    if s["due_reviews"]:
        n = len(s["due_reviews"])
        return f"다음: 복습할 학습카드 {n}개가 도래했다"
    return None
