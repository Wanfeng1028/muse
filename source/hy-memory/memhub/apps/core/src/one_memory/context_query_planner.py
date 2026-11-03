"""One-shot optional query planning behind an injected audited transport."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from one_memory.retrieval.models import QueryPlan


class PlannerAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    profile_revision: int | None = Field(default=None, ge=1, strict=True)
    receiver_digest: str | None = Field(default=None, min_length=64, max_length=64)
    input_token_budget: int = Field(default=1536, ge=1, le=1536, strict=True)
    output_token_budget: int = Field(default=512, ge=1, le=512, strict=True)
    call_budget: Literal[1] = 1


class PlannerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan: QueryPlan
    attempted: bool
    used: bool
    reason: Literal[
        "local_only",
        "not_authorized",
        "insufficient_budget",
        "timed_out",
        "transport_failed",
        "invalid_plan",
        "planned",
    ]
    profile_revision: int | None = None


PlannerAuthorizer = Callable[[str], Awaitable[PlannerAuthorization]]
AuditedPlannerTransport = Callable[[str, QueryPlan, PlannerAuthorization], Awaitable[QueryPlan]]


async def plan_query_once(
    local: QueryPlan,
    *,
    enhancement: Literal["local", "auto"],
    deadline: float,
    authorize: PlannerAuthorizer,
    audited_transport: AuditedPlannerTransport,
) -> PlannerResult:
    """Attempt one authorized model plan; never persists or retries its output."""
    if enhancement == "local":
        return PlannerResult(plan=local, attempted=False, used=False, reason="local_only")
    remaining = deadline - time.monotonic()
    if remaining <= 0.15:
        return PlannerResult(plan=local, attempted=False, used=False, reason="insufficient_budget")
    try:
        permission = await asyncio.wait_for(authorize(local.original_query), timeout=remaining)
    except (TimeoutError, Exception):
        return PlannerResult(plan=local, attempted=False, used=False, reason="not_authorized")
    if (
        not permission.allowed
        or permission.profile_revision is None
        or permission.receiver_digest is None
    ):
        return PlannerResult(plan=local, attempted=False, used=False, reason="not_authorized")
    remaining = min(1.5, deadline - time.monotonic())
    if remaining <= 0.15:
        return PlannerResult(plan=local, attempted=False, used=False, reason="insufficient_budget")
    try:
        planned = await asyncio.wait_for(
            audited_transport(local.original_query, local, permission), timeout=remaining
        )
    except TimeoutError:
        return PlannerResult(
            plan=local,
            attempted=True,
            used=False,
            reason="timed_out",
            profile_revision=permission.profile_revision,
        )
    except Exception:
        return PlannerResult(
            plan=local,
            attempted=True,
            used=False,
            reason="transport_failed",
            profile_revision=permission.profile_revision,
        )
    try:
        validated = QueryPlan.model_validate(planned.model_dump())
    except Exception:
        return PlannerResult(
            plan=local,
            attempted=True,
            used=False,
            reason="invalid_plan",
            profile_revision=permission.profile_revision,
        )
    if validated.original_query != local.original_query:
        return PlannerResult(
            plan=local,
            attempted=True,
            used=False,
            reason="invalid_plan",
            profile_revision=permission.profile_revision,
        )
    return PlannerResult(
        plan=validated,
        attempted=True,
        used=True,
        reason="planned",
        profile_revision=permission.profile_revision,
    )
