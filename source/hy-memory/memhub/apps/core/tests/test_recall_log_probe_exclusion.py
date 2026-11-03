"""A-21：R-10 一旦引入召回日志，「探针不污染」必须自动变红而不是静默失效。

现状（假绿）：R-24 验收「探针不进用户可见召回日志」目前靠 core **根本没有
召回日志表**成立，不是靠过滤。R-10 加上日志表之后，`__om_probe__` 会开始
进日志，而旧测试不会红。

本文件做两件事：
1. 把这条写进 R-10 验收清单（见 docs/mvp/R-10-acceptance.md）；
2. 一条结构守卫：仓库里一旦出现召回日志 schema 标记，就必须同时存在
   探针排除声明。今天没有日志表时守卫检查「标记不存在」；这不是永远绿的
   占位——人为植入 `CREATE TABLE recall_logs` 且不声明排除时会红。
"""

from __future__ import annotations

import re
from pathlib import Path

CORE_SRC = Path(__file__).resolve().parents[1] / "src" / "one_memory"

RECALL_LOG_SCHEMA_MARKERS = (
    "recall_logs",
    "recall_events",
    "memory_recall_log",
    "recall_log_entries",
)

PROBE_EXCLUSION_SYMBOL = "PROBE_EXCLUDED_FROM_RECALL_LOG"


def _schema_sql() -> str:
    texts: list[str] = []
    for path in CORE_SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "CREATE TABLE" in text or "create table" in text.lower():
            texts.append(text)
    return "\n".join(texts)


def _recall_source() -> str:
    return (CORE_SRC / "recall.py").read_text(encoding="utf-8")


def assert_recall_logs_exclude_probe(*, schema: str, recall: str) -> None:
    """Shared so the tripwire and its meta-guard cannot drift apart."""
    present = [marker for marker in RECALL_LOG_SCHEMA_MARKERS if marker in schema]
    if not present:
        return
    assert PROBE_EXCLUSION_SYMBOL in recall, (
        f"recall log schema found ({', '.join(present)}) but "
        f"{PROBE_EXCLUSION_SYMBOL} is missing from recall.py — "
        "probe queries would start appearing in user-visible logs"
    )
    assert re.search(rf"{PROBE_EXCLUSION_SYMBOL}\s*=\s*True", recall)
    assert "PROBE_QUERY" in recall
    assert "request.query == PROBE_QUERY" in recall


def test_recall_log_schema_must_come_with_an_explicit_probe_exclusion() -> None:
    assert_recall_logs_exclude_probe(schema=_schema_sql(), recall=_recall_source())


def test_planting_a_recall_log_table_without_exclusion_turns_this_red() -> None:
    """Meta-guard: the tripwire is not a forever-green placeholder."""
    schema = _schema_sql() + "\nCREATE TABLE recall_logs (id TEXT);\n"
    recall = _recall_source()
    try:
        assert_recall_logs_exclude_probe(schema=schema, recall=recall)
    except AssertionError:
        return
    raise AssertionError(
        "tripwire stayed green after planting recall_logs without exclusion — "
        "it has become a forever-green placeholder"
    )
