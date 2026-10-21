"""The order extraction work is taken in.

Two separate defects met here (R-02). The sort key had no time dimension at
all — `(record exists, no workspace first, verbatim length)` — so the order
was uncorrelated with time, and its second term sent every conversation
written while coding to the back, which is nearly all of them. And the
ordering was applied once, up front, by turning the whole list into
`asyncio.Task`s: evidence that arrived a minute later queued behind all 675
catch-up extractions, which no priority scheme can fix.

So order lives here, is decided per dispatch, and is split into two classes
with a hard share between them. A share rather than a preference because
"newest first" alone starves the backlog for as long as anything keeps
arriving, and on a machine in daily use that is forever.

A third lane sits in front of both. Evidence that just arrived through live
sync is taken before the fresh share and before the backlog, newest first
inside that lane. It does not spend the fresh quota: once the synced turns
are gone, the four-to-one share continues where it left off.
"""

from __future__ import annotations

import heapq
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum

#: How recent evidence has to be to count as new rather than catch-up.
#:
#: A day, because that is the span a person means by "what I just said". It
#: only decides which share a piece of work draws from; both classes are
#: worked newest first, so nothing is mis-ordered when everything is old.
FRESH_WINDOW = timedelta(hours=24)

#: How far back automatic extraction reaches.
#:
#: Ninety days, because that is long enough for a first-run experience to
#: fill with recent memories and short enough that a two-year import does
#: not put 675 catch-up tasks ahead of anything the user just said. Evidence
#: older than this is still imported and searchable; it simply does not
#: enter the extraction queue until the window is widened or the user picks
#: it by hand. Profile-shaped evidence (no workspace) is exempt.
EXTRACTION_WINDOW = timedelta(days=90)

#: How many deferred tasks one manual "next batch" promotes into the queue.
#: Small on purpose: widening the window must not recreate the 675-at-once
#: scheduling that put every later arrival behind the whole catch-up.
MANUAL_EXTRACT_BATCH_SIZE = 25


class ExtractionState(StrEnum):
    EXTRACTED = "extracted"
    OUTSIDE_WINDOW = "outside_window"
    QUEUED = "queued"


class ExtractionWindowPreset(StrEnum):
    THREE_MONTHS = "3m"
    SIX_MONTHS = "6m"
    ONE_YEAR = "1y"
    ALL = "all"


def extraction_window_for(preset: ExtractionWindowPreset) -> timedelta | None:
    """Return the timedelta for a preset, or None when nothing is deferred."""
    if preset is ExtractionWindowPreset.THREE_MONTHS:
        return timedelta(days=90)
    if preset is ExtractionWindowPreset.SIX_MONTHS:
        return timedelta(days=180)
    if preset is ExtractionWindowPreset.ONE_YEAR:
        return timedelta(days=365)
    return None


def resolve_extraction_state(
    *,
    task_status: object | None,
    at: datetime | None,
    imported_at: datetime | None,
    workspace: str | None,
    now: datetime,
    extraction_window: timedelta | None = EXTRACTION_WINDOW,
) -> ExtractionState:
    """Map a piece of evidence onto the three states the product shows.

    `task_status` is typed loosely so callers need not import the task store
    enum into every UI path; known completed / deferred / queued strings and
    enums are recognised, and anything else falls through to the window check.
    """
    status = str(task_status) if task_status is not None else None
    if status == "completed":
        return ExtractionState.EXTRACTED
    if status == "deferred_outside_window":
        return ExtractionState.OUTSIDE_WINDOW
    if status in {
        "pending",
        "running",
        "waiting_for_permission",
        "waiting_for_model",
        "failed",
        "unknown",
    }:
        return ExtractionState.QUEUED
    # No task yet (or cancelled): decide from the window alone, with the same
    # profile exemption classify() uses.
    if workspace is None:
        return ExtractionState.QUEUED
    if extraction_window is None:
        return ExtractionState.QUEUED
    moment = at or imported_at
    if moment is None:
        return ExtractionState.QUEUED
    if within_extraction_window(moment, now=now, window=extraction_window):
        return ExtractionState.QUEUED
    return ExtractionState.OUTSIDE_WINDOW


#: Four new for every one from the backlog.
FRESH_PER_CYCLE = 4
BACKLOG_PER_CYCLE = 1

#: Where work whose evidence has gone missing sorts: last, as it did before.
_UNDATABLE = datetime.min.replace(tzinfo=UTC)
QueueOrder = tuple[int, float, bool, int, str]
QueueHeap = list[tuple[QueueOrder, "QueuedWork"]]


@dataclass(frozen=True, slots=True)
class QueuedWork:
    task_id: str
    #: The evidence's own time, falling back to when it was imported.
    at: datetime
    fresh: bool
    #: Evidence with no workspace, which is the profile-shaped kind.
    all_apps: bool
    length: int
    #: Set when this task was prepared from a live-sync arrival. Those jump
    #: the fresh/backlog share; a later ordinary classify leaves this false.
    live: bool = False
    #: `(user, source, conversation)`. Work sharing one runs in order: HY
    #: decides whether a new memory supersedes an older one from what it has
    #: already been told, so two extractions from the same conversation in
    #: the model at once can each conclude without seeing the other. `None`
    #: when the evidence has gone missing and there is nothing to order by;
    #: that work holds nothing up and is held up by nothing.
    session: tuple[str, str, str] | None = None

    @property
    def order(self) -> QueueOrder:
        """Newest first, then the two terms the old key led with.

        `all_apps` is kept, demoted to a tie-break: cold start really does
        want profile memories landing first, which
        `test_cold_start_prioritizes_all_apps_before_workspace` pins. As a
        leading term it was a penalty on age-appropriate work; between two
        pieces of evidence of the same age it is just the old reason.
        """
        workbuddy_live_rank = int(
            not (self.live and self.session is not None and self.session[1] == "workbuddy")
        )
        return (
            workbuddy_live_rank,
            -self.at.timestamp(),
            not self.all_apps,
            self.length,
            self.task_id,
        )


def _free(work: QueuedWork, busy: Collection[tuple[str, str, str]]) -> bool:
    return work.session is None or work.session not in busy


def free_to_run(
    work: QueuedWork,
    busy: Collection[tuple[str, str, str]],
    harness_load: Mapping[str, int] | None = None,
    harness_limit: int | None = None,
) -> bool:
    """Whether this piece of work may start now.

    Two independent rules, and it is worth keeping them separate because they
    exist for different reasons:

    - `busy` is correctness. Two extractions from one conversation cannot run
      together: HY decides whether a memory supersedes an older one from what
      it has already been told, so each would conclude without seeing the
      other. That is a per-conversation serialisation and has no number.
    - `harness_load` is fairness. One source must not be able to occupy every
      worker. Ten synced sources are not ten times the work, and without a
      per-harness cap the ones that arrived first take the machine.

    `None` for either argument disables that rule, so callers that have not
    adopted it behave exactly as before.
    """
    if not _free(work, busy):
        return False
    if harness_limit is None or harness_load is None:
        return True
    if work.session is None:
        return True
    source = work.session[1]
    return harness_load.get(source, 0) < harness_limit


@dataclass(frozen=True, slots=True)
class QueueDepths:
    """What the app shows instead of one total.

    675 as a single number reads as "stuck". "3 new, 672 historical" reads
    as "the new ones are about to be done", which is what is actually true.
    """

    fresh: int
    backlog: int
    recent_completions: tuple[datetime, ...] = ()


def within_extraction_window(
    moment: datetime,
    *,
    now: datetime,
    window: timedelta = EXTRACTION_WINDOW,
) -> bool:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return moment >= now - window


def classify(
    task_id: str,
    *,
    at: datetime | None,
    imported_at: datetime | None,
    workspace: str | None,
    length: int,
    now: datetime,
    extraction_window: timedelta | None = EXTRACTION_WINDOW,
    live: bool = False,
    session: tuple[str, str, str] | None = None,
    exempt_all_apps_from_window: bool = True,
) -> QueuedWork | None:
    """Return queue work, or None when the evidence is outside the window.

    Profile-shaped evidence (`workspace is None`) always enters the queue:
    cold start would otherwise only reflect the last few months of profile
    facts. Everything else older than `extraction_window` is left out — the
    verbatim stays in the store and in search; only automatic extraction is
    deferred. A `None` window means extract everything.
    """
    moment = at or imported_at
    if moment is None:
        return QueuedWork(
            task_id=task_id,
            at=_UNDATABLE,
            fresh=False,
            all_apps=False,
            length=length,
            live=live,
            session=session,
        )
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    all_apps = workspace is None
    if (
        (not all_apps or not exempt_all_apps_from_window)
        and extraction_window is not None
        and not within_extraction_window(moment, now=now, window=extraction_window)
    ):
        return None
    return QueuedWork(
        task_id=task_id,
        at=moment,
        fresh=moment >= now - FRESH_WINDOW,
        all_apps=all_apps,
        length=length,
        live=live,
        session=session,
    )


class MemoryWorkQueue:
    """Newest-first within each class, with a hard catch-up share.

    Deliberately not `asyncio.PriorityQueue`: the choice of which class to
    serve next has to be made when a worker is free, not when work is added,
    because the whole point is that work added later can be taken sooner.
    """

    def __init__(
        self,
        *,
        fresh_per_cycle: int = FRESH_PER_CYCLE,
        backlog_per_cycle: int = BACKLOG_PER_CYCLE,
    ) -> None:
        self._live: QueueHeap = []
        self._fresh: QueueHeap = []
        self._backlog: QueueHeap = []
        self._queued: set[str] = set()
        self._fresh_per_cycle = fresh_per_cycle
        self._backlog_per_cycle = backlog_per_cycle
        self._served_fresh = 0
        self._served_backlog = 0

    def add(self, work: QueuedWork) -> bool:
        if work.task_id in self._queued:
            if work.live:
                self._promote_live(work.task_id)
            return False
        self._queued.add(work.task_id)
        heapq.heappush(self._lane(work), (work.order, work))
        return True

    def take(
        self,
        busy: Collection[tuple[str, str, str]] = (),
        harness_load: Mapping[str, int] | None = None,
        harness_limit: int | None = None,
    ) -> QueuedWork | None:
        """The next piece of work whose conversation is not already running.

        `busy` is the conversations in the model right now. Work belonging to
        one of them is left where it is rather than dropped: it is the next
        thing taken once that conversation is free, and in the meantime the
        lane behind it still moves.

        `harness_load` / `harness_limit` add the per-source fairness cap; see
        `free_to_run`.
        """
        gate = (harness_load, harness_limit)
        live = self._take_from(self._live, busy, *gate)
        if live is not None:
            return live
        if self._served_fresh >= self._fresh_per_cycle:
            work = self._take_from(self._backlog, busy, *gate)
            if work is not None:
                self._served_backlog += 1
                if self._served_backlog >= self._backlog_per_cycle:
                    self._served_fresh = 0
                    self._served_backlog = 0
                return work
        work = self._take_from(self._fresh, busy, *gate)
        if work is not None:
            self._served_fresh += 1
            return work
        # Nothing new to hold the share for, so the backlog gets the whole
        # machine rather than sitting behind an empty queue.
        return self._take_from(self._backlog, busy, *gate)

    def ready(
        self,
        busy: Collection[tuple[str, str, str]] = (),
        harness_load: Mapping[str, int] | None = None,
        harness_limit: int | None = None,
    ) -> bool:
        """Whether anything could be started now.

        Asked before another worker is set going: a queue that is full but
        entirely blocked on conversations already running must not keep
        starting workers that find nothing and exit, each one starting the
        next.
        """
        return any(
            free_to_run(work, busy, harness_load, harness_limit)
            for heap in (self._live, self._fresh, self._backlog)
            for _order, work in heap
        )

    def live_ready(
        self,
        busy: Collection[tuple[str, str, str]] = (),
        harness_load: Mapping[str, int] | None = None,
        harness_limit: int | None = None,
    ) -> bool:
        return any(
            free_to_run(work, busy, harness_load, harness_limit) for _order, work in self._live
        )

    def clear(self) -> None:
        self._live.clear()
        self._fresh.clear()
        self._backlog.clear()
        self._queued.clear()

    def __len__(self) -> int:
        return len(self._live) + len(self._fresh) + len(self._backlog)

    def task_ids(self) -> frozenset[str]:
        return frozenset(self._queued)

    def _lane(self, work: QueuedWork) -> QueueHeap:
        if work.live:
            return self._live
        return self._fresh if work.fresh else self._backlog

    def _promote_live(self, task_id: str) -> None:
        """Move work already waiting onto the live lane.

        A conversation can be classified as fresh, then a newer sync of the
        same task arrives. `add` would otherwise keep it where it was.
        """
        for heap in (self._fresh, self._backlog):
            for index, (_order, queued) in enumerate(heap):
                if queued.task_id != task_id:
                    continue
                heap.pop(index)
                heapq.heapify(heap)
                promoted = replace(queued, live=True)
                heapq.heappush(self._live, (promoted.order, promoted))
                return

    def _take_from(
        self,
        heap: QueueHeap,
        busy: Collection[tuple[str, str, str]],
        harness_load: Mapping[str, int] | None = None,
        harness_limit: int | None = None,
    ) -> QueuedWork | None:
        """The first piece in this lane that is free to run, order kept.

        Anything passed over goes back, so a blocked conversation keeps its
        place and is not sent to the end of the lane each time it is skipped.
        """
        passed_over = []
        taken = None
        while heap:
            entry = heapq.heappop(heap)
            if free_to_run(entry[1], busy, harness_load, harness_limit):
                taken = entry[1]
                break
            passed_over.append(entry)
        for entry in passed_over:
            heapq.heappush(heap, entry)
        if taken is not None:
            self._queued.discard(taken.task_id)
        return taken
