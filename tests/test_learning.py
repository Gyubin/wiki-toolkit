from wiki_agents import schema
from wiki_agents.core import learning


def test_create_learning_item(vault):
    path = learning.create_learning_item(
        vault, topic="useEffect timing", skill_area="frontend",
        date_str="2026-06-07", seq=1, wiki_refs=["useeffect-timing"],
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["type"] == "learning_item"
    assert meta["level"] == "unknown"
    assert meta["next_review"] == "2026-06-07"  # due immediately


def test_due_reviews(vault):
    learning.create_learning_item(
        vault, topic="t", skill_area="frontend", date_str="2026-06-07", seq=1,
    )
    due = learning.list_due_reviews(vault, "2026-06-08")
    assert any(d["id"] == "learning-20260607-001" for d in due)


def test_record_review_advances_level_and_schedules(vault):
    learning.create_learning_item(
        vault, topic="t", skill_area="frontend", date_str="2026-06-07", seq=1,
    )
    path = learning.record_review(
        vault, "learning-20260607-001", passed=True, today_str="2026-06-08",
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["level"] == "seen"          # advanced one step
    assert meta["next_review"] == "2026-06-09"  # +1 day at first stage


def test_record_review_fail_reschedules_next_day(vault):
    learning.create_learning_item(
        vault, topic="t", skill_area="frontend", date_str="2026-06-07", seq=1,
    )
    path = learning.record_review(
        vault, "learning-20260607-001", passed=False, today_str="2026-06-08",
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["level"] == "unknown"        # no advance
    assert meta["next_review"] == "2026-06-09"
