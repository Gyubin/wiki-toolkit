"""Create the vault folder structure and seed index/log/template files."""
from __future__ import annotations

from pathlib import Path

DIRS = [
    "00_Inbox/raw", "00_Inbox/browser-clips", "00_Inbox/chatgpt-gemini-clips",
    "00_Inbox/coding-agent-sessions", "00_Inbox/unprocessed",
    "01_Projects", "02_Areas",
    "03_Resources/Concepts", "03_Resources/Patterns", "03_Resources/Glossary",
    "03_Resources/Comparisons", "03_Resources/Misconceptions",
    "10_Claims/pending", "10_Claims/verified", "10_Claims/attributed",
    "10_Claims/disputed", "10_Claims/rejected", "10_Claims/outdated",
    "30_Learning/skill-maps", "30_Learning/flashcards", "30_Learning/quizzes",
    "30_Learning/exercises", "30_Learning/weekly-synthesis",
    "06_Metadata/templates", "06_Metadata/schema",
    "06_Metadata/indexes", "06_Metadata/logs",
]

_TPL_NOTE = ("<!-- 참고용 템플릿. 실제 생성은 core 함수/mcp__wiki__* 도구를 쓴다. "
             "스키마의 원본은 코드 repo의 schema.py다. -->\n")

_TEMPLATES = {
    "source": """---
type: source
id: source-YYYYMMDD-NNN
origin: chatgpt|gemini|browser|coding_agent|manual
captured_at: YYYY-MM-DD
sensitivity: personal|work|confidential
url: ''
---

## Raw

(원문 붙여넣기)
""",
    "claim": """---
type: claim
id: claim-YYYYMMDD-NNN
# claim_type 종류: technical_fact, person_claim, opinion, hypothesis,
#   decision, observation, instruction, misconception
claim_type: technical_fact
status: unverified
proposed_status: ''
claim: 한 문장짜리 원자적 주장
speaker: ''
source_refs: []
evidence_refs: []
sensitivity: personal
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

## Claim

한 문장짜리 원자적 주장
""",
    "wiki-page": """---
type: concept|pattern|glossary|comparison|misconception
name: 페이지 이름
domain: []
status: draft
sensitivity: personal
created: YYYY-MM-DD
updated: YYYY-MM-DD
claim_refs: []
code_refs: []
---

## Verified Knowledge

(verified claim에 근거한 내용만)

## Unverified / Notes

(아직 검증 안 된 메모)
""",
    "learning-item": """---
type: learning_item
id: learning-YYYYMMDD-NNN
topic: 학습 주제
skill_area: 분야
level: unknown
source_refs: []
wiki_refs: []
created: YYYY-MM-DD
next_review: YYYY-MM-DD
---

## Topic

플래시카드 질문/답, 미니 연습문제
""",
    "session": """---
type: session
id: session-YYYYMMDD-NNN
repo: repo-slug
title: 세션 제목
sensitivity: work
created: YYYY-MM-DD
---

목표, 바뀐 것, 핵심 파일, 테스트 결과, 디버깅, 설계 선택의 이유
""",
    "decision": """---
type: decision
id: decision-YYYYMMDD-NNN
repo: repo-slug
title: 결정 제목
status: accepted
sensitivity: work
created: YYYY-MM-DD
---

## Context

## Decision

## Alternatives

## Consequences
""",
}

SEED_FILES = {
    "06_Metadata/indexes/claim-index.md": "# Claim Index\n\n",
    "06_Metadata/indexes/wiki-index.md": "# Wiki Index\n\n",
    "06_Metadata/indexes/learning-index.md": "# Learning Index\n\n",
    "06_Metadata/logs/ingest-log.md": "# Ingest Log\n\n",
    **{f"06_Metadata/templates/{name}.md": body + "\n" + _TPL_NOTE
       for name, body in _TEMPLATES.items()},
}


def scaffold_vault(vault: Path) -> None:
    vault = Path(vault)
    for d in DIRS:
        (vault / d).mkdir(parents=True, exist_ok=True)
        keep = vault / d / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
    for rel, content in SEED_FILES.items():
        p = vault / rel
        if not p.exists():
            p.write_text(content, encoding="utf-8")
