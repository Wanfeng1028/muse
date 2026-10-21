"""Local-owner call history; external host credentials cannot enumerate history."""

import asyncio
from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.params import Depends
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from one_memory.call_event_references import (
    CallReferencesUnavailable,
    SourceRecordRef,
    resolve_call_references,
)
from one_memory.call_event_store import (
    CallEvent,
    CallEventStoreUnavailable,
    HostId,
    HostSessionId,
)
from one_memory.context_feedback import (
    FeedbackReference,
    make_offline_feedback,
)


class CallHistoryPage(BaseModel):
    schema_version: Literal[1] = 1
    available: bool
    recording_error: bool
    total: int
    offset: int
    limit: int
    items: tuple[CallEvent, ...]
    retention_days: int | None
    max_events: int | None


class _ConfirmedClear(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_confirmed: StrictBool

    @field_validator("user_confirmed")
    @classmethod
    def confirmed(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("call_history_confirmation_required")
        return value


class ClearCallEvents(_ConfirmedClear):
    event_ids: list[UUID] = Field(min_length=1, max_length=100)


class ClearAllCallEvents(_ConfirmedClear):
    pass


class DeliveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    delivery: Literal["delivered", "not_delivered"]
    host_session_id: HostSessionId
    injection_elapsed_ms: float = Field(ge=0, allow_inf_nan=False)


class FeedbackReport(BaseModel):
    """A user's explicit label; behavioral proxies are rejected before storage."""

    model_config = ConfigDict(extra="forbid", strict=True)

    search_event_id: UUID | None = None

    @field_validator("search_event_id", mode="before")
    @classmethod
    def parse_event_id(cls, value: object) -> UUID:
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            return UUID(value)
        raise ValueError("call_event_feedback_event_id_required")

    @field_validator("search_event_id")
    @classmethod
    def require_event_id(cls, value: UUID | None) -> UUID:
        if value is None:
            raise ValueError("call_event_feedback_event_id_required")
        return value

    feedback_kind: Literal["relevant", "irrelevant", "corrected_selection"]
    selected_refs: list[FeedbackReference] = Field(min_length=1, max_length=16)
    actor: Literal["user"]
    signal: Literal["explicit_feedback"]
    consent_version: int = Field(ge=1)
    retention_days: int = Field(ge=1, le=365)


def call_event_router(dependencies: Sequence[Depends]) -> APIRouter:
    router = APIRouter(prefix="/api/v1/call-events", dependencies=dependencies)

    @router.get("", response_model=CallHistoryPage)
    async def history(
        request: Request,
        response: Response,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0, le=100000),
        host_id: HostId | None = None,
    ) -> CallHistoryPage:
        response.headers["Cache-Control"] = "no-store"
        store = getattr(request.app.state, "call_event_store", None)
        settings = request.app.state.settings
        if store is None:
            return CallHistoryPage(
                available=False,
                recording_error=False,
                total=0,
                offset=offset,
                limit=limit,
                items=(),
                retention_days=None,
                max_events=None,
            )
        try:
            page = await asyncio.to_thread(store.list, limit=limit, offset=offset, host_id=host_id)
        except CallEventStoreUnavailable:
            raise HTTPException(503, "call_history_unavailable") from None
        return CallHistoryPage(
            available=True,
            recording_error=bool(request.app.state.call_event_recording_error),
            total=page.total,
            offset=offset,
            limit=limit,
            items=page.items,
            retention_days=settings.call_event_retention_days,
            max_events=settings.call_event_max_events,
        )

    @router.post("/clear")
    async def clear(value: ClearCallEvents, request: Request, response: Response) -> dict[str, int]:
        response.headers["Cache-Control"] = "no-store"
        store = getattr(request.app.state, "call_event_store", None)
        if store is None:
            raise HTTPException(409, "call_history_disabled")
        try:
            removed = await asyncio.to_thread(store.clear, expected_event_ids=value.event_ids)
        except CallEventStoreUnavailable:
            raise HTTPException(503, "call_history_unavailable") from None
        return {"removed": removed}

    @router.post("/clear-all")
    async def clear_all(
        value: ClearAllCallEvents, request: Request, response: Response
    ) -> dict[str, int]:
        response.headers["Cache-Control"] = "no-store"
        store = getattr(request.app.state, "call_event_store", None)
        if store is None:
            raise HTTPException(409, "call_history_disabled")
        try:
            removed = await asyncio.to_thread(store.clear_all)
        except CallEventStoreUnavailable:
            raise HTTPException(503, "call_history_unavailable") from None
        return {"removed": removed}

    @router.post("/{event_id}/delivery")
    async def delivery(
        event_id: UUID, value: DeliveryReport, request: Request, response: Response
    ) -> dict[str, str]:
        """Record host delivery separately from unobservable answer adoption."""
        response.headers["Cache-Control"] = "no-store"
        store = getattr(request.app.state, "call_event_store", None)
        if store is None:
            raise HTTPException(409, "call_history_disabled")
        try:
            recorded = await asyncio.to_thread(
                store.mark_delivery,
                event_id,
                delivery=value.delivery,
                host_session_id=value.host_session_id,
                injection_elapsed_ms=value.injection_elapsed_ms,
            )
            if recorded is None:
                raise HTTPException(404, "call_event_not_found")
            settled = await asyncio.to_thread(store.get, event_id)
            if settled is None:
                raise HTTPException(404, "call_event_not_found")
        except CallEventStoreUnavailable:
            raise HTTPException(503, "call_history_unavailable") from None
        return {"delivery": settled.delivery, "adoption": settled.adoption}

    @router.post("/feedback")
    async def feedback(
        value: FeedbackReport, request: Request, response: Response
    ) -> dict[str, str]:
        """Append an explicit retrieval label without turning it into memory."""
        response.headers["Cache-Control"] = "no-store"
        store = getattr(request.app.state, "call_event_store", None)
        if store is None:
            raise HTTPException(409, "call_history_disabled")
        try:
            retained = await asyncio.to_thread(
                make_offline_feedback,
                search_event_id=str(value.search_event_id),
                feedback_kind=value.feedback_kind,
                selected_refs=tuple(value.selected_refs),
                actor=value.actor,
                signal=value.signal,
                consent_version=value.consent_version,
                retention_until=store.feedback_retention_until(retention_days=value.retention_days),
            )
            recorded = await asyncio.to_thread(
                store.record_feedback,
                value.search_event_id,
                retained,
            )
            if recorded is None:
                raise HTTPException(404, "call_event_not_found")
        except CallEventStoreUnavailable:
            raise HTTPException(503, "call_history_unavailable") from None
        except ValueError:
            raise HTTPException(422, "call_event_feedback_invalid") from None
        return {"stage": "feedback", "adoption": "unknown"}

    @router.get("/{event_id}/references", response_model=list[SourceRecordRef])
    async def references(
        event_id: UUID, request: Request, response: Response
    ) -> list[SourceRecordRef]:
        response.headers["Cache-Control"] = "no-store"
        store = getattr(request.app.state, "call_event_store", None)
        if store is None:
            raise HTTPException(409, "call_history_disabled")
        try:
            event = await asyncio.to_thread(store.get, event_id)
            if event is None:
                raise HTTPException(404, "call_event_not_found")
            return await asyncio.to_thread(
                resolve_call_references,
                request.app.state.evidence_store.database_path,
                event,
            )
        except (CallEventStoreUnavailable, CallReferencesUnavailable):
            raise HTTPException(503, "call_references_unavailable") from None

    return router
