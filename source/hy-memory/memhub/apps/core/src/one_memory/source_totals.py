"""How many messages each source has given us, without counting them again."""

import time
from collections.abc import Callable

from one_memory.background_work import in_the_background
from one_memory.imports.storage import EvidenceStore

# How stale the numbers on the sources screen are allowed to be. They are a
# count of progress, not a fact anyone acts on, and the screen asks for them
# once a second.
REFRESH_INTERVAL_SECONDS = 2.0


class SourceTotals:
    """The counts, recomputed only when they can have changed.

    Counting is a pass over every row of evidence — on this machine 89,227 of
    them, 0.08s warm and 1.37s from cold — and the desktop asks once a second
    while a catch-up is writing rows as fast as it can. Measured during one,
    the sources screen took 0.74 to 6.70 seconds to answer, nearly all of it
    this count, made again for each ask with the same answer.

    The index already covers the query, so there is nothing to be won there:
    what is expensive is doing it repeatedly. So it is done at most once per
    interval, and not at all unless a row has been added since.
    """

    def __init__(
        self,
        evidence: EvidenceStore,
        *,
        interval_seconds: float = REFRESH_INTERVAL_SECONDS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._evidence = evidence
        self._interval_seconds = interval_seconds
        self._now = now
        self._counted: dict[str, dict[str, tuple[int, int]]] = {}
        self._counted_at: float | None = None
        self._counted_mark: int | None = None

    async def by_source(self, *, user_id: str) -> dict[str, tuple[int, int]]:
        if await in_the_background(self._worth_counting_again, user_id):
            mark = await in_the_background(self._evidence.high_water_mark)
            counted = await in_the_background(
                self._evidence.source_totals_by_source,
                user_id=user_id,
            )
            self._counted[user_id] = counted
            self._counted_at = self._now()
            self._counted_mark = mark
        return self._counted.get(user_id, {})

    def _worth_counting_again(self, user_id: str) -> bool:
        if user_id not in self._counted or self._counted_at is None:
            return True  # never counted, so there is nothing to serve
        if self._now() - self._counted_at < self._interval_seconds:
            return False
        # The interval has passed, which only earns the right to check; a
        # machine sitting idle should cost nothing at all.
        return self._evidence.high_water_mark() != self._counted_mark
