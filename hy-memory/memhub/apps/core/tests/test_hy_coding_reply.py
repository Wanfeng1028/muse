"""R-07: HY's coding-shaped replies read as "no memories at all".

`search_ids` reads `memories` and `_listed_memories` reads `vdb.memories`.
HY has a second reply shape — `{"scene": "productivity", "coding_memories":
[...]}` (`hy_memory/client.py:1145`, `client.py:1038`) — and neither parser
recognises it, so it comes back as an empty tuple. Empty is indistinguishable
from "this person has no memories", which is the failure this codebase
already paid for once on the profile path: see `_basic_info_memories`, which
raises on a payload it does not recognise for exactly that reason.

Read from HY's source, the requirement's diagnosis does not hold: the coding
path is not reachable from here at all, in either direction. Both preconditions
are pinned below as green controls, because they are what makes this fix a
guard rather than a repair — and they are the two things that would have to
change before a coding memory could ever be recalled.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from one_memory.hy_memory_bridge import (
    HyMemoryBridge,
    HyMemoryBridgeError,
    HyMemoryTurn,
    _listed_memories,
    build_hy_memory_config,
)
from one_memory.model_profiles import ModelProfileSnapshot, ProviderKind

CODING_SEARCH_REPLY: Mapping[str, object] = {
    "request_id": "req-1",
    "scene": "productivity",
    "coding_memories": [
        {"memory_id": "coding-1", "content": "用户在 recall.py 里用过滤下推替换了内存过滤"},
        {"memory_id": "coding-2", "content": "用户的分页上限是 500"},
    ],
    "elapsed_ms": 12.0,
}

CODING_LIST_REPLY: Mapping[str, object] = {
    "scene": "productivity",
    "coding_memories": [
        {"memory_id": "coding-1", "agent_id": "workspace-a"},
        {"memory_id": "coding-2", "agent_id": "workspace-b"},
    ],
}


class CodingSceneClient:
    """A client that answers in HY's coding shape rather than the chat shape."""

    def __init__(self, *, search_reply=CODING_SEARCH_REPLY, list_reply=CODING_LIST_REPLY):
        self.search_reply = search_reply
        self.list_reply = list_reply

    def search(self, query: str, **_kwargs) -> Mapping[str, object]:
        return self.search_reply

    def list_memories(self, **_kwargs) -> Mapping[str, object]:
        return self.list_reply

    def close(self) -> None:
        return None


def _profile() -> ModelProfileSnapshot:
    return ModelProfileSnapshot(
        profile_id="profile",
        revision=1,
        provider_kind=ProviderKind.OLLAMA,
        base_url="http://127.0.0.1:11434",
        model="memory-model",
        embedding_model="embedding-model",
        embedding_provider_kind=None,
        embedding_base_url=None,
        embedding_dimensions=768,
        timeout_seconds=30,
        max_concurrency=1,
        context_window=8192,
        has_api_key=False,
    )


def _bridge(client, tmp_path) -> HyMemoryBridge:
    return HyMemoryBridge(
        profile=_profile(),
        api_key=None,
        data_dir=tmp_path,
        client=client,
    )


def test_a_coding_shaped_search_reply_is_not_read_as_no_memories(tmp_path) -> None:
    bridge = _bridge(CodingSceneClient(), tmp_path)

    found = asyncio.run(bridge.search_ids(query="过滤下推", user_id="local", agent_id="*"))

    assert found == ("coding-1", "coding-2")


def test_a_coding_shaped_listing_is_not_read_as_no_scopes(tmp_path) -> None:
    bridge = _bridge(CodingSceneClient(), tmp_path)

    scopes = asyncio.run(bridge.list_agent_ids(user_id="local"))

    assert scopes == ("workspace-a", "workspace-b")


def test_an_unrecognised_search_reply_is_an_error_not_an_empty_recall(tmp_path) -> None:
    """A shape we do not understand must not be reported as an empty library.

    Returning `()` here is what made a coding reply look like "you have no
    memories". Whatever HY adds next, the honest answer is that we could not
    read it.
    """
    bridge = _bridge(CodingSceneClient(search_reply={"request_id": "req-2"}), tmp_path)

    with pytest.raises(HyMemoryBridgeError):
        asyncio.run(bridge.search_ids(query="过滤下推", user_id="local", agent_id="*"))


def test_an_unrecognised_listing_is_an_error_too(tmp_path) -> None:
    bridge = _bridge(CodingSceneClient(list_reply={"unexpected": {}}), tmp_path)

    with pytest.raises(HyMemoryBridgeError):
        asyncio.run(bridge.list_agent_ids(user_id="local"))


#: What HY 0.1.6.5 actually answers a chat-path search with
#: (`client.py:2378-2389`): `memories` is three channels, not a list. Our
#: parser required a list, so every semantic search read as zero hits.
THREE_CHANNEL_REPLY: Mapping[str, object] = {
    "request_id": "req-3",
    "memories": {
        "schema": [
            {"memory_id": "schema-1", "score": 0.61, "layer": "L0_BASIC_INFO"},
        ],
        "proactive": [
            {"memory_id": "intention-1", "score": 0.44, "layer": "L7_INTENTION"},
        ],
        "normal": [
            {"memory_id": "fact-1", "score": 0.88, "layer": "L2_FACT"},
            {"memory_id": "fact-2", "score": 0.52, "layer": "L2_FACT"},
        ],
    },
    "rewrite": {"used": False, "scene": "normal"},
    "elapsed_ms": 41.0,
}

#: The failure branch (`client.py:2253`), which is the shape this machine has
#: actually been getting: same three channels, all empty. HY logs
#: "[search] failed" and returns this.
FAILED_SEARCH_REPLY: Mapping[str, object] = {
    "request_id": "req-4",
    "memories": {"schema": [], "proactive": [], "normal": []},
    "elapsed_ms": 3.0,
}


def test_the_three_channels_hy_actually_returns_are_all_read(tmp_path) -> None:
    """The real defect behind R-07, and it is not about coding at all.

    `memories` is a dict of schema / proactive / normal channels in the current
    HY SDK; our parser asked `isinstance(memories, list)` and returned an empty
    tuple otherwise. So semantic recall was dead — including the schema channel,
    which is the whole reason
    `schema_min_score` and `schema_limit` are passed in.
    """
    bridge = _bridge(CodingSceneClient(search_reply=THREE_CHANNEL_REPLY), tmp_path)

    found = asyncio.run(bridge.search_ids(query="花名", user_id="local", agent_id="*"))

    assert set(found) == {"fact-1", "schema-1", "fact-2", "intention-1"}


def test_the_channels_are_merged_in_hys_own_order_not_ours(tmp_path) -> None:
    """Recall ranks by the order these ids come back in, so the order matters.

    Bucketing into channels loses HY's ranking, but every item still carries
    the `score` HY ranked it by — a field we were also dropping. Sorting the
    union by it restores HY's judgement instead of substituting a channel
    preference of our own, which would be a retrieval-quality decision and
    not ours to make here.
    """
    bridge = _bridge(CodingSceneClient(search_reply=THREE_CHANNEL_REPLY), tmp_path)

    found = asyncio.run(bridge.search_ids(query="花名", user_id="local", agent_id="*"))

    assert found == ("fact-1", "schema-1", "fact-2", "intention-1")


def test_search_scores_carries_hys_relevance(tmp_path) -> None:
    """D102: the score is what lets recall blend the two lanes by relevance."""
    bridge = _bridge(CodingSceneClient(search_reply=THREE_CHANNEL_REPLY), tmp_path)

    found = asyncio.run(bridge.search_scores(query="花名", user_id="local", agent_id="*"))

    assert found == (
        ("fact-1", 0.88),
        ("schema-1", 0.61),
        ("fact-2", 0.52),
        ("intention-1", 0.44),
    )


def test_a_failed_hy_search_is_not_an_error_here_but_is_still_empty(tmp_path) -> None:
    """HY reports search failure only in its log, and returns empty channels.

    On this machine every real search has been `[search] failed: Connection
    error.` — the embedding endpoint is unreachable — and the reply is
    indistinguishable from a genuine zero-hit search. We cannot tell them
    apart at this seam, so this must not become a hard error; it is recorded
    as an upstream gap instead.
    """
    bridge = _bridge(CodingSceneClient(search_reply=FAILED_SEARCH_REPLY), tmp_path)

    assert asyncio.run(bridge.search_ids(query="花名", user_id="local", agent_id="*")) == ()


def test_the_chat_shape_still_reads_the_same(tmp_path) -> None:
    """The control: the shape we actually get today must not move.

    Green before and after. Every real reply on this machine is this one, so
    a change here would be the fix breaking recall to satisfy a shape we have
    never seen.
    """
    chat_client = CodingSceneClient(
        search_reply={"memories": [{"memory_id": "chat-1"}, {"id": "chat-2"}]},
        list_reply={"vdb": {"memories": [{"agent_id": "one-memory"}]}},
    )
    bridge = _bridge(chat_client, tmp_path)

    assert asyncio.run(bridge.search_ids(query="花名", user_id="local", agent_id="*")) == (
        "chat-1",
        "chat-2",
    )
    assert asyncio.run(bridge.list_agent_ids(user_id="local")) == ("one-memory",)
    assert _listed_memories({"vdb": {"memories": []}}) == ()


def test_an_empty_chat_reply_is_still_just_empty(tmp_path) -> None:
    """No memories yet is not a shape error, and must stay quiet."""
    bridge = _bridge(
        CodingSceneClient(search_reply={"memories": []}, list_reply={"vdb": {"memories": []}}),
        tmp_path,
    )

    assert asyncio.run(bridge.search_ids(query="花名", user_id="local", agent_id="*")) == ()
    assert asyncio.run(bridge.list_agent_ids(user_id="local")) == ()


def test_a_tool_message_can_reach_hy_so_it_can_judge_the_route_itself() -> None:
    """HY only considers its coding writer when the messages contain a
    tool-role message (`has_any_tool_message`). Kristin's call: send the turn
    as it happened, tool calls included, and let HY decide."""
    assert HyMemoryTurn(role="tool", content="[Bash] ls -la").role == "tool"
    with pytest.raises(ValidationError):
        HyMemoryTurn(role="system", content="hidden")


def test_our_search_call_shape_cannot_reach_hys_coding_path(tmp_path) -> None:
    """Why no coding reply can arrive today — the read side.

    HY decides the scene per search (`client.py:2020-2116`): an explicit
    `scene`, or an LLM judge when query rewrite is on, or the multi-`queries`
    judge. Otherwise a single query defaults to `normal`. We pass one query,
    no scene, and leave rewrite at HY's default of off, so the coding branch
    is unreachable — `config.coding.enable` being true only pays for the
    store, not the routing.

    Turning any of that on costs an LLM call per search and, with the store
    empty, buys nothing. Left as Kristin's call rather than switched on here.
    """
    config = build_hy_memory_config(_profile(), api_key=None, data_dir=tmp_path)

    assert config.coding.enable is True
    assert config.llm.enable_query_rewrite is False
