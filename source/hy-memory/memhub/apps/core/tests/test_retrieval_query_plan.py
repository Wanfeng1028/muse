"""Local QueryPlan: extract URL/path objects. No HTTP, no store, no model."""

from datetime import UTC, datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest

from one_memory.retrieval.query_plan import plan_local_query

SHANGHAI = ZoneInfo("Asia/Shanghai")
# A Saturday, so week boundaries cannot pass by coinciding with the day ones.
NOW = datetime(2026, 9, 19, 14, 30, tzinfo=SHANGHAI)


def day(year: int, month: int, number: int) -> datetime:
    return datetime(year, month, number, tzinfo=SHANGHAI)


def test_url_in_query_is_an_object_key_and_keeps_the_original():
    query = "昨天最终选了哪个 https://github.com/one-memory/one-memory/pull/12"
    plan = plan_local_query(query)

    assert plan.original_query == query
    assert plan.queries[0] == query
    assert plan.object_keys == ("https://github.com/one-memory/one-memory/pull/12",)
    assert len(plan.queries) <= 3


def test_file_path_is_extracted_without_touching_the_filesystem(tmp_path):
    missing = tmp_path / "does-not-exist" / "notes.md"
    query = f"继续 {missing} 里的任务"
    plan = plan_local_query(query)

    assert plan.object_keys == (str(missing),)
    assert not missing.exists()


def test_yesterday_is_the_local_day_before_today_not_a_rolling_24_hours():
    plan = plan_local_query("昨天写了什么", now=NOW)

    assert plan.time_mode == "hard"
    assert plan.time_range is not None
    # Compared as instants: the plan stores UTC, the boundary is a Shanghai midnight.
    assert plan.time_range.start == day(2026, 9, 18).astimezone(UTC)
    assert plan.time_range.end == day(2026, 9, 19).astimezone(UTC)


@pytest.mark.parametrize(
    ("phrase", "start", "end"),
    [
        ("今天", day(2026, 9, 19), day(2026, 9, 20)),
        ("前天", day(2026, 9, 17), day(2026, 9, 18)),
        ("本周", day(2026, 9, 14), day(2026, 9, 21)),
        ("上周", day(2026, 9, 7), day(2026, 9, 14)),
        ("最近 3 天", day(2026, 9, 17), day(2026, 9, 20)),
    ],
)
def test_supported_time_phrases_resolve_to_half_open_local_ranges(phrase, start, end):
    plan = plan_local_query(f"{phrase}的结论是什么", now=NOW)

    assert plan.time_mode == "hard"
    assert plan.time_range is not None
    assert (plan.time_range.start, plan.time_range.end) == (
        start.astimezone(UTC),
        end.astimezone(UTC),
    )


def test_recently_without_a_number_stays_soft_rather_than_inventing_a_window():
    plan = plan_local_query("最近的决定是什么", now=NOW)

    assert plan.time_mode == "soft"
    assert plan.time_range is None


def test_a_date_mentioned_while_asking_about_now_does_not_filter_history():
    """The falsifiable half of this pair is the 昨天 test above, which is hard.

    Same phrase, different question: asking what is used *now* is not a request
    for yesterday's window, and filtering to it would hide the current answer.
    """
    plan = plan_local_query("我们昨天讨论过的方案现在用哪个", now=NOW)

    assert plan.time_mode == "none"
    assert plan.time_range is None
    assert plan.queries == (plan.original_query,)
    assert plan.ambiguous_constraints == ("time_reference_not_scoping",)


@pytest.mark.parametrize(
    ("phrase", "start", "end"),
    [
        ("2026-09-10", day(2026, 9, 10), day(2026, 9, 11)),
        ("2026-09-10 到 2026-09-12", day(2026, 9, 10), day(2026, 9, 13)),
    ],
)
def test_explicit_dates_and_ranges_are_read_as_written(phrase, start, end):
    plan = plan_local_query(f"{phrase} 的会议记录", now=NOW)

    assert plan.time_mode == "hard"
    assert plan.time_range is not None
    assert (plan.time_range.start, plan.time_range.end) == (
        start.astimezone(UTC),
        end.astimezone(UTC),
    )


def test_a_date_inside_a_link_is_part_of_the_object_not_a_time_filter():
    """Falsifiable against the explicit-date test above, which does filter."""
    plan = plan_local_query("看 https://blog.example/2026-09-10/release 这篇", now=NOW)

    assert plan.object_keys == ("https://blog.example/2026-09-10/release",)
    assert plan.time_mode == "none"
    assert plan.time_range is None


def test_no_time_expression_leaves_the_query_unfiltered():
    plan = plan_local_query("统一用 axios 还是 fetch", now=NOW)

    assert plan.time_mode == "none"
    assert plan.time_range is None
    assert plan.ambiguous_constraints == ()


def test_signed_url_query_token_is_not_kept_as_an_object_key():
    plan = plan_local_query("打开 https://files.example/doc?token=secret-value#page=2")
    assert plan.object_keys
    key = plan.object_keys[0]
    assert "secret-value" not in key
    assert urlsplit(key).hostname == "files.example"
