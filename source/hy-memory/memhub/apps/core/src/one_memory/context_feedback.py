"""Non-persistent RCL-16 feedback records for explicit offline evaluation only."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

FeedbackKind = Literal["relevant", "irrelevant", "corrected_selection"]


class FeedbackReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["raw", "memory"]
    reference_id: str = Field(min_length=1, max_length=512)
    revision: int = Field(ge=1, strict=True)


class ExplicitRetrievalFeedback(BaseModel):
    """A label request, not a preference, fact, memory write or online update."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    search_event_id: str = Field(min_length=1, max_length=128)
    feedback_kind: FeedbackKind
    selected_refs: tuple[FeedbackReference, ...] = Field(min_length=1, max_length=16)
    actor: Literal["user_explicit"]
    purpose: Literal["offline_retrieval_evaluation"]
    consent_version: int = Field(ge=1, strict=True)
    retention_until: AwareDatetime
    created_at: AwareDatetime

    @field_validator("selected_refs")
    @classmethod
    def unique_references(
        cls, value: tuple[FeedbackReference, ...]
    ) -> tuple[FeedbackReference, ...]:
        identities = {(item.kind, item.reference_id, item.revision) for item in value}
        if len(identities) != len(value):
            raise ValueError("duplicate_feedback_reference")
        return value

    @field_validator("retention_until", "created_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class OfflineFeedbackSample(BaseModel):
    """De-identified, versioned label for offline retrieval evaluation only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    feedback_kind: FeedbackKind
    reference_kinds: tuple[Literal["raw", "memory"], ...] = Field(min_length=1, max_length=16)
    reference_revisions: tuple[int, ...] = Field(min_length=1, max_length=16)
    consent_version: int = Field(ge=1, strict=True)
    created_at: AwareDatetime
    retention_until: AwareDatetime


def export_offline_feedback_samples(
    records: tuple[ExplicitRetrievalFeedback, ...],
    *,
    now: datetime,
) -> tuple[OfflineFeedbackSample, ...]:
    """Drop event/reference identities; never emit query, body or weight fields."""
    moment = now.astimezone(UTC)
    samples: list[OfflineFeedbackSample] = []
    for record in records:
        if record.retention_until <= moment:
            continue
        samples.append(
            OfflineFeedbackSample(
                feedback_kind=record.feedback_kind,
                reference_kinds=tuple(reference.kind for reference in record.selected_refs),
                reference_revisions=tuple(reference.revision for reference in record.selected_refs),
                consent_version=record.consent_version,
                created_at=record.created_at,
                retention_until=record.retention_until,
            )
        )
    return tuple(samples)


def make_offline_feedback(
    *,
    search_event_id: str,
    feedback_kind: FeedbackKind,
    selected_refs: tuple[FeedbackReference, ...],
    actor: str,
    signal: str,
    consent_version: int,
    retention_until: datetime,
    now: datetime | None = None,
) -> ExplicitRetrievalFeedback:
    """Accept a direct user label; reject behavioral proxies and assistant claims."""
    if actor != "user" or signal != "explicit_feedback":
        raise ValueError("feedback_requires_explicit_user_signal")
    created = now or datetime.now(UTC)
    if retention_until <= created:
        raise ValueError("feedback_retention_expired")
    return ExplicitRetrievalFeedback(
        search_event_id=search_event_id,
        feedback_kind=feedback_kind,
        selected_refs=selected_refs,
        actor="user_explicit",
        purpose="offline_retrieval_evaluation",
        consent_version=consent_version,
        retention_until=retention_until,
        created_at=created,
    )
