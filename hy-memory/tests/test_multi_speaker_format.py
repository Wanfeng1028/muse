"""多真人对话（named multi-party）渲染与 name 透传测试。

覆盖 docs/multi_speaker_design.md 的定稿格式：
    用户名叫Tim
    [user]: ...
    [John]: ...

要点：
- role=user 恒渲染成 [user]（即使带 name），视角信息留在标签里
- role=assistant + name → 对方**真人**，渲染成 [<name>]
- role=assistant 无 name → AI assistant，渲染成 [assistant]
- 名字行只在 role=user 带 name 时出现，整段一次，语言随内容
- 不传 name 时渲染与历史行为逐字一致
"""

import pytest

from hy_memory.pipelines.base import (
    ChatMessage,
    WriteRequest,
    parse_user_name_line,
    render_user_name_line,
)
from hy_memory.client import HyMemoryClient


class TestSpeakerLabel:
    def test_user_label_never_uses_name(self):
        assert ChatMessage(role="user", content="x").speaker_label() == "user"
        assert ChatMessage(role="user", content="x", name="Tim").speaker_label() == "user"

    def test_named_assistant_is_a_real_person(self):
        m = ChatMessage(role="assistant", content="x", name="John")
        assert m.speaker_label() == "John"

    def test_nameless_assistant_is_the_ai(self):
        assert ChatMessage(role="assistant", content="x").speaker_label() == "assistant"

    def test_other_roles_fall_back_to_role(self):
        assert ChatMessage(role="system", content="x").speaker_label() == "system"
        assert ChatMessage(role="tool", content="x", tool_name="Read").speaker_label() == "tool"


class TestFlatContentUnchangedWithoutName:
    """不传 name 时必须与历史行为逐字一致（单方 chat 是主场景）"""

    def test_plain_chat_rendering(self):
        req = WriteRequest(messages=[
            ChatMessage(role="user", content="我喜欢咖啡"),
            ChatMessage(role="assistant", content="好的，我记下了"),
        ])
        assert req.get_flat_content() == "[user]: 我喜欢咖啡\n[assistant]: 好的，我记下了"

    def test_no_name_line_when_user_has_no_name(self):
        req = WriteRequest(messages=[
            ChatMessage(role="user", content="hi"),
            ChatMessage(role="assistant", content="John here", name="John"),
        ])
        # 对方带 name 但 user 没有 → 不插名字行
        assert req.get_flat_content() == "[user]: hi\n[John]: John here"

    def test_content_only_input_untouched(self):
        assert WriteRequest(content="plain text").get_flat_content() == "plain text"


class TestFlatContentWithNames:
    def test_zh_rendering(self):
        req = WriteRequest(messages=[
            ChatMessage(role="user", content="我喜欢咖啡", name="Tim"),
            ChatMessage(role="assistant", content="我也喜欢茶", name="John"),
        ])
        assert req.get_flat_content() == (
            "用户名叫Tim\n"
            "[user]: 我喜欢咖啡\n"
            "[John]: 我也喜欢茶"
        )

    def test_en_rendering(self):
        req = WriteRequest(messages=[
            ChatMessage(role="user", content="I like coffee", name="Tim"),
            ChatMessage(role="assistant", content="I prefer tea", name="John"),
        ])
        assert req.get_flat_content() == (
            "The user's name is Tim\n"
            "[user]: I like coffee\n"
            "[John]: I prefer tea"
        )

    def test_named_user_with_nameless_ai(self):
        req = WriteRequest(messages=[
            ChatMessage(role="user", content="I like coffee", name="Tim"),
            ChatMessage(role="assistant", content="Noted"),
        ])
        assert req.get_flat_content() == (
            "The user's name is Tim\n"
            "[user]: I like coffee\n"
            "[assistant]: Noted"
        )

    def test_name_line_appears_once_across_many_turns(self):
        req = WriteRequest(messages=[
            ChatMessage(role="user", content="a", name="Tim"),
            ChatMessage(role="assistant", content="b", name="John"),
            ChatMessage(role="user", content="c", name="Tim"),
        ])
        out = req.get_flat_content()
        assert out.count("The user's name is Tim") == 1
        assert out.splitlines()[0] == "The user's name is Tim"

    def test_user_name_helper(self):
        req = WriteRequest(messages=[
            ChatMessage(role="assistant", content="b", name="John"),
            ChatMessage(role="user", content="a", name="Tim"),
        ])
        assert req.user_name() == "Tim"
        assert WriteRequest(messages=[ChatMessage(role="user", content="a")]).user_name() is None


class TestNameLineRoundTrip:
    """L1_RAW 回读要能把名字行识别出来（否则会被当成裸消息）"""

    @pytest.mark.parametrize("line,expected", [
        ("用户名叫Tim", "Tim"),
        ("The user's name is Tim", "Tim"),
        ("用户名叫 Mary Jane ", "Mary Jane"),
        ("[user]: hi", None),
        ("[John]: hi", None),
        ("我喜欢咖啡", None),
        ("", None),
    ])
    def test_parse(self, line, expected):
        assert parse_user_name_line(line) == expected

    def test_render_then_parse(self):
        for zh in (True, False):
            line = render_user_name_line("Tim", zh)
            assert parse_user_name_line(line) == "Tim"

    def test_render_empty_name(self):
        assert render_user_name_line("", True) == ""
        assert render_user_name_line("   ", False) == ""

    def test_flat_content_first_line_is_parseable(self):
        req = WriteRequest(messages=[
            ChatMessage(role="user", content="我喜欢咖啡", name="Tim"),
        ])
        first = req.get_flat_content().splitlines()[0]
        assert parse_user_name_line(first) == "Tim"


class TestNormalizeMessageReadsName:
    def test_speaker_name_kept_for_user_and_assistant(self):
        _, msgs, ctype = HyMemoryClient._parse_input([
            {"role": "user", "name": "Tim", "content": "hi"},
            {"role": "assistant", "name": "John", "content": "yo"},
        ])
        assert ctype == "messages"
        assert msgs[0].name == "Tim"
        assert msgs[1].name == "John"
        # 说话人名字不该被塞进 tool_name
        assert msgs[0].tool_name is None and msgs[1].tool_name is None

    def test_tool_message_name_is_still_the_tool_name(self):
        _, msgs, _ = HyMemoryClient._parse_input([
            {"role": "tool", "tool_call_id": "t1", "name": "Read", "content": "42 lines"},
        ])
        assert msgs[0].tool_name == "Read"
        assert msgs[0].name is None

    def test_anthropic_blocks_keep_speaker_name(self):
        _, msgs, _ = HyMemoryClient._parse_input([
            {"role": "assistant", "name": "John",
             "content": [{"type": "text", "text": "hello"}]},
        ])
        assert msgs[0].name == "John" and msgs[0].content == "hello"

    def test_to_dict_omits_name_when_absent(self):
        assert ChatMessage(role="user", content="hi").to_dict() == {
            "role": "user", "content": "hi",
        }

    def test_to_dict_from_dict_round_trip(self):
        d = ChatMessage(role="assistant", content="yo", name="John").to_dict()
        assert d["name"] == "John"
        assert ChatMessage.from_dict(d).name == "John"
