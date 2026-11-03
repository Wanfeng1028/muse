"""Mechanical parity checks for the shared v2 coverage receipt contract."""

from __future__ import annotations

import re
from pathlib import Path

from one_memory.retrieval.models import Limit, RetrievalPath, RetrievalResponse

ROOT = Path(__file__).resolve().parents[3]
TS_CONTRACT = ROOT / "packages/contracts/src/context-v2.ts"


def _interface_body(source: str, name: str) -> str:
    match = re.search(rf"export interface {name} \{{(.*?)^\}}", source, re.M | re.S)
    assert match is not None, name
    return match.group(1)


def _field_names(body: str) -> set[str]:
    names: set[str] = set()
    depth = 0
    for line in body.splitlines():
        if depth == 0:
            match = re.match(r"^\s*([a-z][a-z0-9_]*)\??:", line)
            if match is not None:
                names.add(match.group(1))
        depth += line.count("{") - line.count("}")
    return names


def _literal_union(body: str, field: str) -> set[str]:
    match = re.search(rf"^\s*{field}:\s*(.*?);", body, re.M | re.S)
    assert match is not None, field
    literals = set(re.findall(r'"([a-z][a-z0-9_]*)"', match.group(1)))
    assert literals, field
    return literals


def test_retrieval_path_contract_fields_and_enums_match_python() -> None:
    source = TS_CONTRACT.read_text(encoding="utf-8")
    body = _interface_body(source, "RetrievalPathV2")

    assert _field_names(body) == set(RetrievalPath.model_fields)
    assert _literal_union(body, "status") == set(
        RetrievalPath.model_fields["status"].annotation.__args__
    )
    assert _literal_union(body, "coverage") == set(
        RetrievalPath.model_fields["coverage"].annotation.__args__
    )
    ts_limits = re.search(r"export type RetrievalLimit =(.*?);", source, re.S)
    assert ts_limits is not None
    assert set(re.findall(r'"([a-z][a-z0-9_]*)"', ts_limits.group(1))) == set(Limit.__args__)
    assert "index_incomplete" not in ts_limits.group(1)


def test_retrieval_response_keeps_coverage_separate_from_adoption() -> None:
    source = TS_CONTRACT.read_text(encoding="utf-8")
    body = _interface_body(source, "RetrievalResponseV2")

    assert _field_names(body) == set(RetrievalResponse.model_fields)
    assert re.search(r'adoption:\s*"unknown";', body)
