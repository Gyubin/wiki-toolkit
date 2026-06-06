"""Create the vault folder structure and seed index/log files."""
from __future__ import annotations

from pathlib import Path

DIRS = [
    "00_Inbox/raw", "00_Inbox/browser-clips", "00_Inbox/chatgpt-gemini-clips",
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

SEED_FILES = {
    "06_Metadata/indexes/claim-index.md": "# Claim Index\n\n",
    "06_Metadata/indexes/wiki-index.md": "# Wiki Index\n\n",
    "06_Metadata/indexes/learning-index.md": "# Learning Index\n\n",
    "06_Metadata/logs/ingest-log.md": "# Ingest Log\n\n",
}


def scaffold_vault(vault: Path) -> None:
    vault = Path(vault)
    for d in DIRS:
        (vault / d).mkdir(parents=True, exist_ok=True)
    for rel, content in SEED_FILES.items():
        p = vault / rel
        if not p.exists():
            p.write_text(content, encoding="utf-8")
