"""Append-only logs and upsert-by-id index lines under 06_Metadata."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path


def append_log(vault: Path, logname: str, line: str) -> None:
    p = Path(vault) / "06_Metadata/logs" / f"{logname}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    with p.open("a", encoding="utf-8") as f:
        f.write(f"- {ts} - {line}\n")


def update_index(vault: Path, indexname: str, entry_id: str, line: str) -> None:
    p = Path(vault) / "06_Metadata/indexes" / f"{indexname}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    header = p.read_text(encoding="utf-8") if p.exists() else f"# {indexname}\n\n"
    kept = [
        ln for ln in header.splitlines()
        if not ln.startswith(f"- [{entry_id}]")
    ]
    kept.append(f"- [{entry_id}] {line}")
    p.write_text("\n".join(kept) + "\n", encoding="utf-8")
