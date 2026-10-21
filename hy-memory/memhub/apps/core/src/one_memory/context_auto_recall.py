"""Deterministic RCL-13 trigger semantics, independent of any host hook."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

_HISTORY = re.compile(
    r"之前|以前|上次|历史|过去|当时|刚才|前面|记得|回忆|"
    r"previous|before|last time|history|earlier|remember",
    re.I,
)
_CONTINUE = re.compile(
    r"继续|接着|续接|接上|做到哪|下一步|未完成|"
    r"continue|resume|pick up|where (?:did|were) we",
    re.I,
)
_PERSONAL = re.compile(
    r"我的.{0,12}(偏好|习惯|要求|决定)|我.{0,8}(喜欢|不喜欢|要求|决定)|"
    r"my (?:preference|decision)|what did i decide",
    re.I,
)
_GREETING = re.compile(r"^(?:你好|您好|嗨|哈喽|hello|hi|hey)[!！,.，。\s]*$", re.I)


class AutoRecallDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: Literal["search", "skip", "skill_guidance"]
    reason: Literal[
        "explicit_query",
        "history_reference",
        "task_continuation",
        "past_preference_or_decision",
        "disabled",
        "permission_required",
        "already_satisfied",
        "ordinary_message",
        "turn_identity_unavailable",
    ]
    automatic: bool


def decide_auto_recall(
    query: str,
    *,
    explicit_lookup: bool = False,
    enabled: bool = True,
    read_allowed: bool = True,
    reliable_turn_identity: bool = True,
    already_satisfied: bool = False,
) -> AutoRecallDecision:
    """Choose whether a host may search; never reads context or creates a grant."""
    text = query.strip()
    if not text:
        raise ValueError("auto_recall_query_required")
    if explicit_lookup:
        if not read_allowed:
            return AutoRecallDecision(action="skip", reason="permission_required", automatic=False)
        return AutoRecallDecision(action="search", reason="explicit_query", automatic=False)
    if not enabled:
        return AutoRecallDecision(action="skip", reason="disabled", automatic=True)
    if not read_allowed:
        return AutoRecallDecision(action="skip", reason="permission_required", automatic=True)
    if already_satisfied:
        return AutoRecallDecision(action="skip", reason="already_satisfied", automatic=True)
    reason: (
        Literal["history_reference", "task_continuation", "past_preference_or_decision"] | None
    ) = None
    if _CONTINUE.search(text):
        reason = "task_continuation"
    elif _PERSONAL.search(text):
        reason = "past_preference_or_decision"
    elif _HISTORY.search(text):
        reason = "history_reference"
    if reason is None or _GREETING.fullmatch(text):
        return AutoRecallDecision(action="skip", reason="ordinary_message", automatic=True)
    if not reliable_turn_identity:
        return AutoRecallDecision(
            action="skill_guidance", reason="turn_identity_unavailable", automatic=True
        )
    return AutoRecallDecision(action="search", reason=reason, automatic=True)
