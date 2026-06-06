"""Raw capture (sources), triage records, and URL/html conversion."""
from __future__ import annotations

from pathlib import Path

from markdownify import markdownify

from .. import schema
from . import index


def create_source(
    vault: Path, *, origin: str, content: str, sensitivity: str = "personal",
    date_str: str, seq: int, url: str | None = None, subdir: str = "raw",
) -> Path:
    if sensitivity not in schema.SENSITIVITIES:
        raise ValueError(f"unknown sensitivity: {sensitivity}")
    if sensitivity != "personal":
        raise PermissionError(
            "work/confidential content must go to the work vault, not this personal vault"
        )
    sid = schema.make_id("source", date_str, seq)
    meta = {
        "type": "source", "id": sid, "origin": origin,
        "captured_at": date_str, "sensitivity": sensitivity, "url": url or "",
    }
    body = f"## Raw\n\n{content}\n"
    path = Path(vault) / "00_Inbox" / subdir / f"{sid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.append_log(vault, "ingest-log", f"captured {sid} from {origin}")
    return path


def triage_record(vault: Path, source_id: str, decision: str, date_str: str) -> None:
    if decision not in ("drop", "keep-as-link", "deep"):
        raise ValueError(f"unknown triage decision: {decision}")
    index.append_log(vault, "ingest-log", f"triage {source_id} -> {decision}")


def html_to_markdown(html: str) -> str:
    return markdownify(html, heading_style="ATX").strip()
