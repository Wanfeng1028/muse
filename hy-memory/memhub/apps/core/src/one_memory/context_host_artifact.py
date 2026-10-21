"""Host-specific consumption artifacts over an already validated v2 response."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from one_memory.retrieval.models import (
    EvidenceGroup,
    RawEvidence,
    RetrievalPaths,
    RetrievalResponse,
)

TruncationReason = Literal[
    "character_budget",
    "deadline",
    "coverage_budget",
    "metadata_budget",
    "index_incomplete",
]


class HostConsumptionProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    host_id: str = Field(min_length=1, max_length=128)
    delivery_mode: Literal["hook", "mcp", "skill", "hook_or_mcp"]
    character_budget: int = Field(ge=200, le=20000, strict=True)
    deadline_ms: int = Field(ge=50, le=30000, strict=True)


class HostConsumptionArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    host_id: str = Field(min_length=1, max_length=128)
    delivery_mode: Literal["hook", "mcp", "skill", "hook_or_mcp"]
    source_request_id: str = Field(min_length=1, max_length=64)
    source_state: Literal["grounded", "empty", "partial", "unavailable"]
    source_paths: RetrievalPaths
    delivery_state: Literal["delivered", "empty", "partial", "timeout", "denied"]
    groups: tuple[EvidenceGroup, ...] = Field(max_length=8)
    delivered_characters: int = Field(ge=0, le=20000, strict=True)
    truncated_by: tuple[TruncationReason, ...] = ()
    adoption: Literal["unknown"] = "unknown"


def _characters(group: EvidenceGroup) -> int:
    return sum(
        sum(len(span.text) for span in item.spans)
        if isinstance(item, RawEvidence)
        else len(item.content)
        for item in group.items
    ) + sum(len(reference.span.text) for reference in group.object_refs)


def _source_coverage_limits(response: RetrievalResponse) -> tuple[TruncationReason, ...]:
    limits: list[TruncationReason] = []
    for path in (response.paths.raw, response.paths.memory):
        for reason in path.truncated_by:
            if (
                reason in {"coverage_budget", "metadata_budget", "index_incomplete"}
                and reason not in limits
            ):
                limits.append(reason)
        if (
            path.coverage == "partial"
            and path.reason == "index_incomplete"
            and "index_incomplete" not in limits
        ):
            limits.append("index_incomplete")
    return tuple(limits)


def build_host_consumption_artifact(
    response: RetrievalResponse, profile: HostConsumptionProfile
) -> HostConsumptionArtifact:
    """Apply a host's delivery budget without changing source coverage semantics."""
    source_limits = _source_coverage_limits(response)
    if response.budget.total_ms >= profile.deadline_ms:
        return HostConsumptionArtifact(
            host_id=profile.host_id,
            delivery_mode=profile.delivery_mode,
            source_request_id=response.request_id,
            source_state=response.state,
            source_paths=response.paths,
            delivery_state="timeout",
            groups=(),
            delivered_characters=0,
            truncated_by=("deadline", *source_limits),
        )
    selected: list[EvidenceGroup] = []
    used = 0
    truncated = False
    for group in response.groups:
        size = _characters(group)
        if used + size > profile.character_budget:
            truncated = True
            continue
        selected.append(group)
        used += size
    denied = all(
        path.status in {"not_requested", "not_authorized"}
        for path in (response.paths.raw, response.paths.memory)
    )
    state: Literal["delivered", "empty", "partial", "denied"]
    if denied:
        state = "denied"
    elif selected and not truncated and response.state == "grounded":
        state = "delivered"
    elif selected or truncated or response.state == "partial":
        state = "partial"
    else:
        state = "empty"
    host_limits: tuple[TruncationReason, ...] = ("character_budget",) if truncated else ()
    return HostConsumptionArtifact(
        host_id=profile.host_id,
        delivery_mode=profile.delivery_mode,
        source_request_id=response.request_id,
        source_state=response.state,
        source_paths=response.paths,
        delivery_state=state,
        groups=tuple(selected),
        delivered_characters=used,
        truncated_by=host_limits + source_limits,
    )
