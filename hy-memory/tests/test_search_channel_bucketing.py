# -*- coding: utf-8 -*-
"""Search response channel bucketing regression tests."""

import importlib
import inspect
import re
import textwrap

from hy_memory.client import _search_memory_channel


def _extract_search_chat_layer_constants() -> tuple[set[str], set[str]]:
    """
    从 client.py 源码里抽出 _SCHEMA_LAYERS / _PROACTIVE_LAYERS
    常量集合（避免端到端跑整个 search，需要真实 client + embed + VDB）。
    """
    from hy_memory import client as client_mod
    src = inspect.getsource(client_mod)

    schema_match = re.search(
        r'_SCHEMA_LAYERS\s*=\s*\{([^}]+)\}',
        src,
    )
    proactive_match = re.search(
        r'_PROACTIVE_LAYERS\s*=\s*\{([^}]+)\}',
        src,
    )
    assert schema_match, "could not locate _SCHEMA_LAYERS in client.py"
    assert proactive_match, "could not locate _PROACTIVE_LAYERS in client.py"

    def _parse(set_body: str) -> set[str]:
        # set_body 形如 "\"l0_basic_info\", \"l4_identity\", ..."
        return set(re.findall(r'"([^"]+)"', set_body))

    return _parse(schema_match.group(1)), _parse(proactive_match.group(1))


class TestSearchChannelBucketing:

    def test_schema_is_l6_only(self):
        schema, _ = _extract_search_chat_layer_constants()
        assert schema == {"l6_schema"}

    def test_l0_is_not_in_search_schema(self):
        schema, _ = _extract_search_chat_layer_constants()
        assert "l0_basic_info" not in schema

    def test_schema_excludes_normal_layers(self):
        schema, _ = _extract_search_chat_layer_constants()
        assert {"l2_fact", "l3_summary", "l4_identity"}.isdisjoint(schema)

    def test_proactive_is_intention_only(self):
        _, proactive = _extract_search_chat_layer_constants()
        assert proactive == {"l7_intention"}

    def test_schema_proactive_disjoint(self):
        schema, proactive = _extract_search_chat_layer_constants()
        assert schema.isdisjoint(proactive), (
            f"Schema and Proactive must be disjoint. "
            f"Overlap: {schema & proactive}"
        )

    def test_docstring_matches_code(self):
        """Search docstring must advertise the L6-only Schema channel."""
        from hy_memory.client import HyMemoryClient

        doc = HyMemoryClient.search.__doc__ or ""
        schema_line_match = re.search(
            r'Schema.*?[:：](.+)', doc
        )
        assert schema_line_match, "no 'Schema' line in search() docstring"
        schema_line = schema_line_match.group(1).upper()

        schema_set, _ = _extract_search_chat_layer_constants()

        for code_layer in schema_set:
            doc_name = code_layer.upper()
            assert doc_name in schema_line, (
                f"Layer {doc_name} is in code _SCHEMA_LAYERS but not "
                f"mentioned in search() docstring: {schema_line!r}"
            )

    def test_reader_selected_reverse_schema_is_not_regated_by_client(self):
        memory = {
            "layer": "l6_schema",
            "score": 0.01,
            "_schema_channel": True,
        }
        assert _search_memory_channel(
            memory,
            schema_layers={"l6_schema"},
            proactive_layers={"l7_intention"},
            schema_min_score=0.4,
        ) == "schema"
        assert "_schema_channel" not in memory
