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


def test_interval_ladder_and_level_cap(vault):
    learning.create_learning_item(
        vault, topic="t", skill_area="frontend", date_str="2026-06-07", seq=1,
    )
    # unknown -> seen -> explained -> used -> reviewed -> can-teach (그 후 유지)
    expected = [
        ("seen", "2026-06-09"),        # +1
        ("explained", "2026-06-11"),   # +3
        ("used", "2026-06-15"),        # +7
        ("reviewed", "2026-06-24"),    # +16
        ("can-teach", "2026-07-13"),   # +35
        ("can-teach", "2026-08-01"),   # 캡 유지, 간격은 마지막 값(+35) 반복
    ]
    days = ["2026-06-08", "2026-06-08", "2026-06-08",
            "2026-06-08", "2026-06-08", "2026-06-27"]
    for (level, next_review), day in zip(expected, days, strict=True):
        path = learning.record_review(
            vault, "learning-20260607-001", passed=True, today_str=day,
        )
        meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
        assert (meta["level"], meta["next_review"]) == (level, next_review)


def test_due_reviews_survive_yaml_date_values(vault):
    # Obsidian에서 따옴표를 지우면 next_review가 str이 아닌 date로 파싱된다
    path = learning.create_learning_item(
        vault, topic="t", skill_area="frontend", date_str="2026-06-07", seq=1,
    )
    text = path.read_text(encoding="utf-8")
    assert "next_review: '2026-06-07'" in text
    path.write_text(text.replace("next_review: '2026-06-07'", "next_review: 2026-06-07"),
                    encoding="utf-8")
    due = learning.list_due_reviews(vault, "2026-06-08")
    assert any(d["id"] == "learning-20260607-001" for d in due)


def test_record_review_fail_without_level_key(vault):
    # level 키가 아예 없는 파일을 불합격 처리해도 KeyError 없이 동작해야 한다
    path = learning.create_learning_item(
        vault, topic="t", skill_area="frontend", date_str="2026-06-07", seq=1,
    )
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("level: unknown\n", ""), encoding="utf-8")
    path = learning.record_review(
        vault, "learning-20260607-001", passed=False, today_str="2026-06-08",
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["level"] in schema.LEARNING_LEVELS


def test_record_review_tolerates_unknown_level_value(vault):
    path = learning.create_learning_item(
        vault, topic="t", skill_area="frontend", date_str="2026-06-07", seq=1,
    )
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("level: unknown", "level: 손으로고친값"), encoding="utf-8")
    path = learning.record_review(
        vault, "learning-20260607-001", passed=True, today_str="2026-06-08",
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["level"] in schema.LEARNING_LEVELS
