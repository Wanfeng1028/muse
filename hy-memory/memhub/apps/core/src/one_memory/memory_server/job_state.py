"""A2-05: legal transitions for the durable write job, and what `unknown` means.

`unknown` is the state this module exists to protect. It records "HY was
called and we cannot prove whether it committed". Because A0-03 measured that
the SDK has no idempotency key, the two tempting resolutions are both wrong:

- retry blindly -> the user gets two copies of the same memory;
- drop it      -> the memory is lost silently.

So `unknown` is non-terminal and must be resolved by inquiry (A0-03 found the
SDK can look a result up by request_id), never by guessing.

The enum itself is re-exported from `contracts` rather than redeclared. A
second copy of the same enum would be exactly the "three adjacent state
machines" problem docs/ARCHITECTURE.md lists as a current defect, and two
enums with equal-looking members do not compare equal at runtime.
"""

from __future__ import annotations

from enum import StrEnum

from one_memory.memory_server.contracts import WriteJobState as JobState


class JobEvent(StrEnum):
    CLAIM = "claim"
    SUCCEED = "succeed"
    FAIL = "fail"
    #: HY returned, but we could not prove whether it committed.
    INDETERMINATE = "indeterminate"
    #: An inquiry resolved an earlier `unknown`.
    RESOLVED = "resolved"
    RETRY = "retry"
    CANCEL = "cancel"
    #: Retries exhausted, or an inquiry found the job unrecoverable.
    GIVE_UP = "give_up"


#: States from which no further work may happen.
#:
#: `unknown` is absent because it still needs resolving. `FAILED` is absent
#: too, deliberately: a failed write is retryable up to `MAX_ATTEMPTS`, so
#: calling it finished would strand recoverable work. A failed job becomes
#: truly final only when retries are exhausted (`GIVE_UP` -> DEAD).
#:
#: Implementation note — `durable_queue` treats its `failed` rows as final and
#: never re-claims them. That is not a contradiction of this table: the durable
#: queue only writes `failed` for deterministic *pre-send* refusals
#: (`hy_memory_evidence_changed`, `hy_memory_input_exceeds_window`, other
#: `model_content_*` raised before the bridge), where replaying the same intent
#: fails identically, so retrying would spin without changing the outcome. The
#: task layer's retryable `failed` is a different situation (transient runner
#: failure, `hy_invoked` not yet proven). `tests/test_memory_server_durable_queue.py`
#: pins that behavior. If the product later decides pre-send refusals should
#: retry, change the durable claim SQL and that test together, not this comment.
TERMINAL_STATES = frozenset({JobState.COMPLETED, JobState.CANCELLED, JobState.DEAD})

MAX_ATTEMPTS = 3


class IllegalTransition(ValueError):
    """Raised when an event cannot apply to the current state."""


def _transitions() -> dict[tuple[JobState, JobEvent], JobState]:
    return {
        (JobState.PENDING, JobEvent.CLAIM): JobState.RUNNING,
        (JobState.PENDING, JobEvent.CANCEL): JobState.CANCELLED,
        (JobState.RUNNING, JobEvent.SUCCEED): JobState.COMPLETED,
        (JobState.RUNNING, JobEvent.FAIL): JobState.FAILED,
        (JobState.RUNNING, JobEvent.INDETERMINATE): JobState.UNKNOWN,
        (JobState.RUNNING, JobEvent.CANCEL): JobState.CANCELLED,
        # An unknown may be re-attested either way, but only by an inquiry.
        (JobState.UNKNOWN, JobEvent.RESOLVED): JobState.COMPLETED,
        (JobState.UNKNOWN, JobEvent.FAIL): JobState.FAILED,
        (JobState.UNKNOWN, JobEvent.GIVE_UP): JobState.DEAD,
        (JobState.FAILED, JobEvent.RETRY): JobState.PENDING,
    }


def next_state(state: JobState, event: JobEvent) -> JobState:
    """Apply one event, or raise. There is no silent no-op path.

    Raising matters: a transition that quietly ignores a bad event would let a
    completed job be re-run, or an unknown be forgotten.
    """
    target = _transitions().get((state, event))
    if target is None:
        raise IllegalTransition(f"cannot apply {event} to {state}")
    return target


def can_retry(state: JobState, attempts: int) -> bool:
    """Whether a failed or unknown job may be attempted again.

    `unknown` is retryable only in the sense that an inquiry may retry the
    *question*, not the write; the caller must not re-invoke HY on an unknown
    job, because A0-03 proved the SDK would accept a duplicate.
    """
    if attempts >= MAX_ATTEMPTS:
        return False
    return state in {JobState.FAILED, JobState.PENDING}


def is_terminal(state: JobState) -> bool:
    return state in TERMINAL_STATES
