import json

import pytest

from one_memory.source_query_preview import display_query_projection


def test_preserves_exact_user_text_and_span():
    text = "  请保留这段原话。  "
    result = json.loads(display_query_projection(text, "user", "person"))
    assert result["excerpt"] == text[result["query_start"] : result["query_end"]]
    assert result["projection_version"] == 1 and not result["truncated"]


def test_supported_outer_wrapper_is_stripped_without_paraphrasing():
    text = "<user_info>系统背景</user_info><user_query>我这次的问题</user_query>"
    result = json.loads(display_query_projection(text, "user", "person"))
    assert result["excerpt"] == "我这次的问题"
    assert text[result["query_start"] : result["query_end"]] == result["excerpt"]


@pytest.mark.parametrize(
    "prefix",
    [
        "<timestamp>Wednesday, Sep 23, 2026, 7:34 AM (UTC+8)</timestamp>\n",
        (
            "[Image]\n"
            "<image_files>\n"
            "The following images were provided by the user:\n"
            "1. /private/project/assets/image.png\n"
            "</image_files>\n"
            "<timestamp>Wednesday, Sep 23, 2026, 7:34 AM (UTC+8)</timestamp>\n"
        ),
    ],
)
def test_cursor_host_prefixes_are_not_shown_as_the_user_query(prefix):
    text = f"{prefix}<user_query>只保留这个问题</user_query>"
    result = json.loads(display_query_projection(text, "user", "person"))
    assert result["excerpt"] == "只保留这个问题"
    assert text[result["query_start"] : result["query_end"]] == result["excerpt"]


@pytest.mark.parametrize(
    "text",
    [
        "<user_query>不完整",
        "<user_query>一</user_query><user_query>二</user_query>",
        "<user_info>只有系统</user_info>",
        "<subagent_notification>任务完成</subagent_notification>",
        "<codex_delegation>执行指令</codex_delegation>",
        "<dynamic_tool_catalog>工具列表",
        "<user_info>旧版错误落库的主机上下文</user_info>",
        "<dynamic_tools>旧版错误落库的工具目录</dynamic_tools>",
        "[Image] 旧版图片消息缺少显式 query 包装",
        "# AGENTS.md instructions for /private/workspace\nproject context",
        "# Files mentioned by the user:\nattachment context",
        "Briefly inform the user about the task result and perform any follow-up actions",
        "<rules>重复</rules><user_query>重复</user_query>",
        "x" * 65537,
    ],
)
def test_ambiguous_or_generated_content_is_withheld(text):
    assert display_query_projection(text, "user", "person") is None


@pytest.mark.parametrize(
    "role,author",
    [("assistant", "agent"), ("user", "agent"), ("user", "unknown"), ("tool", "tool")],
)
def test_role_user_alone_is_not_human_authorship(role, author):
    assert display_query_projection("任务已完成", role, author) is None


def test_long_display_is_truncated_without_changing_full_span():
    text = "真正用户的问题" * 120
    result = json.loads(display_query_projection(text, "user", "person"))
    assert len(result["excerpt"]) == 600 and result["truncated"]
    assert result["query_end"] == len(text)


def test_receipt_qualifies_user_queries_before_sampling_and_preserves_originals(tmp_path):
    import hashlib

    from one_memory.imports.models import WrittenBy
    from one_memory.imports.storage import EvidenceStore
    from one_memory.source_import_receipts import build_source_import_receipt
    from tests.test_source_import_receipts import record

    path = tmp_path / "receipt.sqlite3"
    store = EvidenceStore(path)
    valid = record(1, text="<user_query>真正的问题</user_query>")
    store.put(valid)
    for index in range(2, 102):
        store.put(record(index, author=WrittenBy.AGENT, text="助手消息"))
    store.put(record(200, text="<user_query>残缺"))
    store.put(record(201, user="other", text="其他用户"))
    store.put(record(202, source="other", text="其他来源"))
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = build_source_import_receipt(path, user_id="local", source_id="claude-code")
    assert len(receipt.query_examples) == 1
    item = receipt.query_examples[0]
    assert item.evidence_id == valid.evidence_id and item.evidence_revision == 1
    assert item.excerpt == "真正的问题" and item.written_by == "person"
    assert store.get(valid.evidence_id).verbatim == valid.verbatim
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_receipt_examples_strip_cursor_host_prefixes_before_sampling(tmp_path):
    from one_memory.imports.models import WrittenBy
    from one_memory.imports.storage import EvidenceStore
    from one_memory.source_import_receipts import build_source_import_receipt
    from tests.test_source_import_receipts import record

    path = tmp_path / "receipt-cursor.sqlite3"
    store = EvidenceStore(path)
    valid = record(
        1,
        text=(
            "[Image]\n<image_files>/private/image.png</image_files>\n"
            "<timestamp>Wednesday, Sep 23, 2026, 7:34 AM (UTC+8)</timestamp>\n"
            "<user_query>历史里的真实问题</user_query>"
        ),
    )
    store.put(valid)
    for index in range(2, 102):
        store.put(record(index, author=WrittenBy.AGENT, text="助手消息"))

    receipt = build_source_import_receipt(path, user_id="local", source_id="claude-code")

    assert [item.excerpt for item in receipt.query_examples] == ["历史里的真实问题"]
