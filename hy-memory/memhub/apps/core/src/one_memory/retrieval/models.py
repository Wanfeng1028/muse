"""RCL v2 bounded contracts; not an exposed route or an authorization grant."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from one_memory.context_models import ContextSearchRequest

Identifier = Annotated[str, Field(min_length=1, max_length=512)]
QueryText = Annotated[str, Field(min_length=1, max_length=2000)]
ReasonText = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")]
Intent = Literal["artifact", "fact", "decision", "timeline", "resume"]
Channel = Literal["lexical", "semantic", "object", "governed_semantic"]
Limit = Literal[
    "count_budget",
    "character_budget",
    "timeout_budget",
    "metadata_budget",
    "candidate_budget",
    "coverage_budget",
]


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class ContextHints(Contract):
    task_text: str = Field(default="", max_length=1200)
    already_seen_refs: tuple[Identifier, ...] = Field(default=(), max_length=32)

    @field_validator("already_seen_refs")
    @classmethod
    def unique_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate_seen_refs")
        return value


class ContextSearchRequestV2(ContextSearchRequest):
    operation: Literal["search"] = "search"
    intent: Literal["auto", "artifact", "fact", "decision", "timeline", "resume"] = "auto"
    context_hints: ContextHints = Field(default_factory=ContextHints)
    enhancement: Literal["local", "auto"] = "local"
    limit: int = Field(default=8, ge=1, le=8, strict=True)
    character_budget: int = Field(default=6000, ge=200, le=20000, strict=True)


class ContextExpandRequestV2(Contract):
    operation: Literal["expand"]
    expand_ref: str = Field(min_length=1, max_length=4096)
    character_budget: int = Field(default=6000, ge=200, le=6000, strict=True)
    message_limit: int = Field(default=4, ge=1, le=4, strict=True)
    timeout_ms: int = Field(default=2000, ge=50, le=30000, strict=True)

    @field_validator("expand_ref")
    @classmethod
    def opaque_ref(cls, value: str) -> str:
        if any(char.isspace() or ord(char) < 32 for char in value):
            raise ValueError("invalid_expand_ref")
        return value


# Search keeps its omitted-operation default; branches still reject each other's fields.
ContextRequestV2 = ContextSearchRequestV2 | ContextExpandRequestV2


class TimeRange(Contract):
    start: AwareDatetime
    end: AwareDatetime

    @field_validator("start", "end")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def ordered(self) -> "TimeRange":
        if self.start >= self.end:
            raise ValueError("invalid_time_range")
        return self


class QueryPlan(Contract):
    original_query: QueryText
    intent: Intent = "fact"
    queries: tuple[QueryText, ...] = Field(min_length=1, max_length=3)
    lexical_terms: tuple[Identifier, ...] = Field(default=(), max_length=32)
    object_keys: tuple[Identifier, ...] = Field(default=(), max_length=32)
    time_range: TimeRange | None = None
    time_mode: Literal["none", "hard", "soft"] = "none"
    topic_hints: tuple[Identifier, ...] = Field(default=(), max_length=16)
    required_evidence: tuple[ReasonText, ...] = Field(default=(), max_length=16)
    ambiguous_constraints: tuple[ReasonText, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def preserve_original(self) -> "QueryPlan":
        if not self.original_query.strip() or self.queries[0] != self.original_query:
            raise ValueError("original_query_required")
        if len(set(self.queries)) != len(self.queries) or any(not q.strip() for q in self.queries):
            raise ValueError("invalid_query_expansion")
        if self.time_mode == "hard" and self.time_range is None:
            raise ValueError("hard_time_requires_range")
        if self.time_mode == "none" and self.time_range is not None:
            raise ValueError("unexpected_time_range")
        return self


class EvidenceSpan(Contract):
    start_cp: int = Field(ge=0, strict=True)
    end_cp: int = Field(gt=0, strict=True)
    text: str = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def exact_length(self) -> "EvidenceSpan":
        if self.end_cp - self.start_cp != len(self.text):
            raise ValueError("span_length_mismatch")
        return self


class RawEvidence(Contract):
    kind: Literal["raw"] = "raw"
    evidence_id: Identifier
    revision: int = Field(ge=1, strict=True)
    source_id: str = Field(min_length=1, max_length=128)
    conversation_id: Identifier
    role: str = Field(min_length=1, max_length=32)
    written_by: Literal["person", "agent", "tool", "unknown"]
    event_time: AwareDatetime | None
    spans: tuple[EvidenceSpan, ...] = Field(min_length=1, max_length=4)
    matched_by: tuple[Literal["lexical", "semantic", "object"], ...] = Field(
        min_length=1, max_length=3
    )
    expand_ref: str | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def ordered_spans(self) -> "RawEvidence":
        if any(a.end_cp > b.start_cp for a, b in zip(self.spans, self.spans[1:], strict=False)):
            raise ValueError("overlapping_spans")
        if len(set(self.matched_by)) != len(self.matched_by):
            raise ValueError("duplicate_channels")
        return self


class GovernedEvidence(Contract):
    kind: Literal["memory"] = "memory"
    memory_id: Identifier
    revision: int = Field(ge=1, strict=True)
    content: str = Field(min_length=1, max_length=20000)
    memory_kind: str = Field(min_length=1, max_length=64)
    updated_at: AwareDatetime
    evidence_ids: tuple[Identifier, ...] = Field(default=(), max_length=128)
    matched_by: tuple[Literal["lexical", "governed_semantic"], ...] = Field(
        min_length=1, max_length=2
    )

    @model_validator(mode="after")
    def unique_metadata(self) -> "GovernedEvidence":
        if len(set(self.evidence_ids)) != len(self.evidence_ids) or len(
            set(self.matched_by)
        ) != len(self.matched_by):
            raise ValueError("duplicate_memory_metadata")
        return self


EvidenceItem = Annotated[RawEvidence | GovernedEvidence, Field(discriminator="kind")]


class ObjectReference(Contract):
    kind: Literal["url", "path", "explicit_id"]
    evidence_id: Identifier
    revision: int = Field(ge=1, strict=True)
    span: EvidenceSpan


class EvidenceGroup(Contract):
    group_id: Identifier
    answer_target: Intent
    object_refs: tuple[ObjectReference, ...] = Field(default=(), max_length=8)
    decision_status: Literal[
        "supported", "ambiguous", "missing_confirmation", "conflicting", "coverage_limited"
    ]
    missing_requirements: tuple[
        Literal["relevance_confirmation"] | ReasonText,
        ...,
    ] = Field(default=(), max_length=16)
    items: tuple[EvidenceItem, ...] = Field(min_length=1, max_length=4)


class RetrievalPath(Contract):
    status: Literal["ok", "empty", "not_requested", "not_authorized", "unavailable", "degraded"]
    reason: ReasonText | None = None
    returned_count: int = Field(ge=0, le=32, strict=True)
    searched_channels: tuple[Channel, ...] = Field(default=(), max_length=4)
    coverage: Literal["complete", "partial", "not_searched", "unavailable"]
    truncated_by: tuple[Limit, ...] = Field(default=(), max_length=6)

    @model_validator(mode="after")
    def no_forbidden_results(self) -> "RetrievalPath":
        if (
            self.status in {"not_requested", "not_authorized", "unavailable", "empty"}
            and self.returned_count
        ):
            raise ValueError("path_cannot_return_items")
        if self.status in {"not_requested", "not_authorized"} and (
            self.searched_channels or self.coverage != "not_searched"
        ):
            raise ValueError("forbidden_path_searched")
        if self.status in {"ok", "empty"} and (
            not self.searched_channels or self.coverage == "not_searched"
        ):
            raise ValueError("successful_path_not_searched")
        if len(set(self.searched_channels)) != len(self.searched_channels):
            raise ValueError("duplicate_channels")
        return self


class RetrievalPaths(Contract):
    raw: RetrievalPath
    memory: RetrievalPath


class PlanSummary(Contract):
    intent: Intent
    interpreted_time_range: TimeRange | None = None
    time_origin: Literal["none", "explicit", "rule", "model"] = "none"
    unresolved_constraints: tuple[ReasonText, ...] = Field(default=(), max_length=16)


class EnhancementReceipt(Contract):
    attempted: bool = Field(default=False, strict=True)
    used: bool = Field(default=False, strict=True)
    reason: ReasonText | None = None
    model_profile_revision: int | None = Field(default=None, ge=1, strict=True)
    usage_state: Literal["not_attempted", "known", "unknown"] = "not_attempted"

    @model_validator(mode="after")
    def consistent_usage(self) -> "EnhancementReceipt":
        if (
            (self.used and not self.attempted)
            or (
                not self.attempted
                and (self.usage_state != "not_attempted" or self.model_profile_revision is not None)
            )
            or (
                self.attempted
                and (self.usage_state == "not_attempted" or self.model_profile_revision is None)
            )
        ):
            raise ValueError("invalid_enhancement_receipt")
        return self


class RetrievalBudget(Contract):
    used_characters: int = Field(ge=0, le=20000, strict=True)
    total_ms: float = Field(ge=0, strict=True)
    truncated: bool = Field(strict=True)
    stage_ms: dict[str, float] = Field(default_factory=dict)


class RetrievalResponse(Contract):
    schema_version: Literal[2] = 2
    request_id: str = Field(min_length=1, max_length=64)
    state: Literal["grounded", "empty", "partial", "unavailable"]
    paths: RetrievalPaths
    plan: PlanSummary
    groups: tuple[EvidenceGroup, ...] = Field(max_length=8)
    enhancement: EnhancementReceipt = Field(default_factory=EnhancementReceipt)
    budget: RetrievalBudget
    adoption: Literal["unknown"] = "unknown"

    @model_validator(mode="after")
    def accountable_response(self) -> "RetrievalResponse":
        if len({group.group_id for group in self.groups}) != len(self.groups):
            raise ValueError("duplicate_group")
        counts = {"raw": 0, "memory": 0}
        characters = 0
        identities = set()
        for group in self.groups:
            raw = {item.evidence_id: item for item in group.items if isinstance(item, RawEvidence)}
            for reference in group.object_refs:
                anchor = raw.get(reference.evidence_id)
                if (
                    anchor is None
                    or anchor.revision != reference.revision
                    or not any(
                        span.start_cp
                        <= reference.span.start_cp
                        < reference.span.end_cp
                        <= span.end_cp
                        and span.text[
                            reference.span.start_cp - span.start_cp : reference.span.end_cp
                            - span.start_cp
                        ]
                        == reference.span.text
                        for span in anchor.spans
                    )
                ):
                    raise ValueError("object_reference_not_grounded")
                characters += len(reference.span.text)
            for item in group.items:
                identity = (
                    item.kind,
                    item.evidence_id if isinstance(item, RawEvidence) else item.memory_id,
                )
                if identity in identities:
                    raise ValueError("duplicate_evidence")
                identities.add(identity)
                counts[item.kind] += 1
                path = self.paths.raw if item.kind == "raw" else self.paths.memory
                if not set(item.matched_by) <= set(path.searched_channels):
                    raise ValueError("unsearched_item_channel")
                characters += (
                    sum(len(s.text) for s in item.spans)
                    if isinstance(item, RawEvidence)
                    else len(item.content)
                )
        if counts != {
            "raw": self.paths.raw.returned_count,
            "memory": self.paths.memory.returned_count,
        }:
            raise ValueError("path_count_mismatch")
        if characters != self.budget.used_characters:
            raise ValueError("character_count_mismatch")
        paths = (self.paths.raw, self.paths.memory)
        if "governed_semantic" in self.paths.raw.searched_channels or set(
            self.paths.memory.searched_channels
        ) - {"lexical", "governed_semantic"}:
            raise ValueError("wrong_path_channel")
        complete = all(
            p.status in {"ok", "empty", "not_requested", "not_authorized"}
            and p.coverage in {"complete", "not_searched"}
            and not p.truncated_by
            for p in paths
        )
        searched = any(p.status in {"ok", "empty", "degraded"} for p in paths)
        if self.state == "grounded" and (not self.groups or not complete or self.budget.truncated):
            raise ValueError("incomplete_grounded_response")
        if (
            self.enhancement.attempted
            and not self.enhancement.used
            and self.state in {"grounded", "empty"}
        ):
            raise ValueError("enhancement_incomplete")
        if self.state == "empty" and (
            self.groups or not complete or not searched or self.budget.truncated
        ):
            raise ValueError("incomplete_empty_response")
        if self.state == "unavailable" and (self.groups or searched):
            raise ValueError("invalid_unavailable_response")
        if self.state == "partial" and not searched:
            raise ValueError("partial_requires_searched_path")
        return self


def validate_response_budget(
    request: ContextRequestV2, response: RetrievalResponse
) -> RetrievalResponse:
    """Structural checks before release; does not replace database/host reauthorization."""
    if response.budget.used_characters > request.character_budget:
        raise ValueError("response_character_budget_exceeded")
    if response.groups and response.budget.total_ms >= request.timeout_ms:
        raise ValueError("response_deadline_exceeded")
    if isinstance(request, ContextSearchRequestV2):
        if len(response.groups) > request.limit:
            raise ValueError("response_group_budget_exceeded")
        for kind in ("raw", "memory"):
            path = getattr(response.paths, kind)
            if kind not in request.kinds and path.status != "not_requested":
                raise ValueError("unrequested_path")
        if request.raw_source_ids is not None and any(
            isinstance(item, RawEvidence) and item.source_id not in request.raw_source_ids
            for group in response.groups
            for item in group.items
        ):
            raise ValueError("response_raw_filter_mismatch")
        if request.enhancement == "local" and response.enhancement.attempted:
            raise ValueError("unexpected_model_enhancement")
    else:
        if response.paths.memory.status != "not_requested" or response.enhancement.attempted:
            raise ValueError("expand_cannot_generate_or_read_memory")
        if response.paths.raw.returned_count > request.message_limit:
            raise ValueError("expand_message_budget_exceeded")
    return response
