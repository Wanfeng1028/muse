"""Writers meet in this one file, and the loser used to lose data.

Catching up on old conversations records memory tasks while the runner works
through them; live sync imports while the interface reads. On a real corpus
the catch-up stopped partway with `database is locked`, and the memories it
had not recorded yet were simply gone. SQLite fails the second writer at once
unless every connection is told to wait its turn.
"""

import ast
import inspect
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from one_memory.database import WRITE_LOCK_WAIT_MS, enable_write_ahead_log
from one_memory.imports.adapters import SourceCursor
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_governance import MemoryGovernanceStore
from one_memory.memory_tasks import MemoryTaskStore
from one_memory.model_profiles import ModelProfileStore
from one_memory.onboarding import OnboardingStore

pytestmark = [pytest.mark.integration, pytest.mark.serial]

# Every store that opens the one database. A new one added without waiting for
# writers is a new way to lose a memory, so this list is meant to be a chore:
# adding a store and not adding it here fails the sweep below.
STORES = (
    EvidenceStore,
    ImportJobStore,
    MemoryGovernanceStore,
    MemoryTaskStore,
    ModelProfileStore,
    OnboardingStore,
    SourceGrantStore,
)


def build(store_class, tmp_path):
    database = tmp_path / "one-memory.sqlite3"
    if store_class is SourceGrantStore:
        return store_class(database, home=tmp_path)
    return store_class(database)


@pytest.mark.parametrize("store_class", STORES, ids=lambda cls: cls.__name__)
def test_every_store_waits_for_the_write_lock(store_class, tmp_path) -> None:
    store = build(store_class, tmp_path)

    with store._connect() as connection:  # noqa: SLF001 - the pragma is the point
        waiting = connection.execute("PRAGMA busy_timeout").fetchone()[0]

    assert waiting == WRITE_LOCK_WAIT_MS, (
        f"{store_class.__name__} fails its caller the moment another writer "
        "holds the lock, rather than waiting for it"
    )


def _write_methods_that_read_first(store_class) -> list[str]:
    """Methods that write inside a transaction they opened by reading.

    Read from the source rather than by calling: what matters is that no
    method is ever written this way again, and only the source can say that
    about a method no test happens to exercise.
    """
    source = Path(inspect.getfile(store_class)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    klass = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == store_class.__name__
    )
    unprotected = []
    for node in klass.body:
        if not isinstance(node, ast.FunctionDef) or node.name in {"__init__", "_connect"}:
            continue
        body = ast.get_source_segment(source, node) or ""
        # Either way of opening one counts. Some stores here go through a
        # context manager rather than `_connect` directly, and a sweep that
        # only knew the one spelling would pass them over.
        if "self._connect()" not in body and "self._connection()" not in body:
            continue
        if not any(word in body.upper() for word in ("UPDATE ", "INSERT ", "DELETE ", "REPLACE ")):
            continue
        # Taking the lock up front is the fix, however it is spelled: through
        # the shared helper, or by issuing the statement in place.
        if "writing=True" in body or "BEGIN IMMEDIATE" in body:
            continue
        unprotected.append(node.name)
    return unprotected


def _keeps_a_transaction_open_between_statements(store_class, tmp_path) -> bool:
    """Ask the connection, rather than reading the source for one spelling.

    This was decided by looking for `connection.autocommit = False` in the
    file, and two stores reach the same mode by simply not passing
    `autocommit=True` to `sqlite3.connect`. They were skipped as unaffected
    while being affected: `MemoryTaskStore` then lost the entire catch-up to
    `database is locked` on this machine, with the sweep green.
    """
    store = build(store_class, tmp_path)
    with store._connect() as connection:  # noqa: SLF001 - the mode is the point
        return connection.autocommit is not True


@pytest.mark.parametrize("store_class", STORES, ids=lambda cls: cls.__name__)
def test_no_store_writes_from_a_transaction_it_opened_by_reading(store_class, tmp_path) -> None:
    """A chore, on purpose: the next method written this way fails here.

    Only stores that hold one transaction across several statements can meet
    this refusal. The others commit statement by statement, so a read leaves
    no snapshot to be refused an upgrade from.
    """
    if not _keeps_a_transaction_open_between_statements(store_class, tmp_path):
        pytest.skip(f"{store_class.__name__} 不跨语句持有事务，不受此问题影响")

    unprotected = _write_methods_that_read_first(store_class)

    assert unprotected == [], (
        f"{store_class.__name__}.{', '.join(unprotected)} 先读后写，"
        "另一个写者提交后会被 SQLite 当场拒绝而不是等待；"
        "改用 self._connect(writing=True)"
    )


def test_the_journal_switch_waits_for_another_core_writing_to_the_same_file(
    tmp_path,
) -> None:
    """The one pragma `busy_timeout` does not cover.

    Changing the journal mode needs a moment with the file to itself, and
    SQLite refuses rather than waits. Two Cores opening a fresh database at
    once — a restart racing a not-quite-dead predecessor — met that refusal,
    and the newcomer failed to start at all.
    """
    database = tmp_path / "one-memory.sqlite3"
    setting_up = sqlite3.connect(database, autocommit=True)
    setting_up.execute("CREATE TABLE anything (value TEXT)")
    setting_up.close()
    holding = threading.Event()

    def write_for_half_a_second() -> None:
        # Opened and closed in its own thread, which is where SQLite insists a
        # connection stays, and is how the other Core would hold it anyway.
        # Writing, not reading: a reader does not stand in the way of this
        # switch, and the Core that lost the race was mid-schema.
        connection = sqlite3.connect(database, autocommit=True)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO anything (value) VALUES ('busy')")
            holding.set()
            time.sleep(0.5)
            connection.execute("COMMIT")
        finally:
            connection.close()

    reader = threading.Thread(target=write_for_half_a_second)
    reader.start()
    switching = sqlite3.connect(database, autocommit=True)
    try:
        assert holding.wait(10)

        enable_write_ahead_log(switching)

        assert switching.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        switching.close()
        reader.join(10)


def test_a_store_that_has_read_can_still_write_after_someone_else_wrote(
    tmp_path,
    monkeypatch,
) -> None:
    """The one contention `busy_timeout` does not cover either.

    Most writes here check something first — whose job this is, what version
    that memory is on — and then write. Read first and the connection holds a
    snapshot; write after someone else has committed and SQLite refuses at
    once rather than waiting, because waiting could only deadlock.

    This never happened while every write was made on the event loop, since
    the loop could only make one at a time. Now that they are made in threads
    so the app stays answerable, two of them really do meet: importing two
    sources at once failed a job partway with `database is locked`, evidence
    written but its cursor lost.
    """
    database = tmp_path / "one-memory.sqlite3"
    jobs = ImportJobStore(database)
    job = jobs.create(user_id="local", source_id="fixture")
    _, token = jobs.claim(job.job_id)
    somebody_else = ImportJobStore(database)
    reading = ImportJobStore._require_owner  # noqa: SLF001 - the interleaving is the point
    written_elsewhere = threading.Event()

    def write_from_another_thread() -> None:
        # A second import job, in its own thread, as the runner's bookkeeping
        # now runs.
        somebody_else.create(user_id="local", source_id="another")
        written_elsewhere.set()

    def read_then_let_the_other_writer_in(connection, job_id, runner_token):
        owner = reading(connection, job_id, runner_token)
        threading.Thread(target=write_from_another_thread).start()
        # Long enough for it to get in if nothing is stopping it, short
        # enough to be well inside the wait it is meant to be held in.
        written_elsewhere.wait(0.5)
        return owner

    monkeypatch.setattr(
        ImportJobStore,
        "_require_owner",
        staticmethod(read_then_let_the_other_writer_in),
    )

    recorded = jobs.record_evidence(
        job.job_id,
        runner_token=token,
        cursor=SourceCursor(
            file_key="a" * 64,
            file_identity="fixture:1",
            checkpoint="line:1",
            observed_size=100,
            observed_modified_ns=1,
        ),
        was_created=True,
        was_revised=False,
    )

    assert recorded.stored == 1
    # And the writer that was held gets its turn rather than being dropped.
    assert written_elsewhere.wait(10)
    assert {job.source_id for job in jobs.list_jobs()} == {"fixture", "another"}


def test_a_store_write_survives_another_writer_holding_the_lock(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    tasks = MemoryTaskStore(database)
    holding = threading.Event()
    released = threading.Event()

    def hold_the_write_lock() -> None:
        connection = sqlite3.connect(database, autocommit=True)
        try:
            connection.execute("BEGIN IMMEDIATE")
            holding.set()
            released.wait(10)
            connection.execute("COMMIT")
        finally:
            connection.close()

    holder = threading.Thread(target=hold_the_write_lock)
    holder.start()
    try:
        assert holding.wait(10)
        # Released well inside the wait, so a store that waits gets through
        # and a store that does not raises instead.
        threading.Timer(0.5, released.set).start()

        tasks.recover_running()
    finally:
        released.set()
        holder.join(10)
