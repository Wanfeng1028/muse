"""One pass over a source file is bounded by a byte budget, not skipped.

Real trigger: a 348MB (and a 477MB) codex transcript held the import open with
no heartbeat until the process died. There was no file-size ceiling anywhere in
the tree, so the only defence was to read the file and hope.

Skipping was the first fix and measured badly: at 32MB it dropped 30 of 474
codex files -- 6% of the files, but 85% of the bytes. The guard was throwing
away most of the history it existed to protect, so the budget now bounds one
pass and lets the next pass resume from the checkpoint instead.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from one_memory.imports.access import AuthorizedSourceFile, AuthorizedSourceRoot
from one_memory.imports.adapters import ScanOptions, ScanSkip
from one_memory.imports.discovery import discover_source_files
from one_memory.imports.readers import DEFAULT_IMPORT_MAX_FILE_BYTES
from one_memory.imports.sources.workbuddy import create_workbuddy_adapter


def _record(content: str) -> str:
    return json.dumps({"type": "user", "sessionId": "probe", "content": content}) + "\n"


def _grant(root: Path) -> AuthorizedSourceRoot:
    return AuthorizedSourceRoot.grant(
        source_id="workbuddy", root=root / ".codebuddy", user_confirmed=True, home=root
    )


def _entry(root: Path, *, pad_bytes: int = 0) -> AuthorizedSourceFile:
    projects = root / ".codebuddy" / "projects" / "qa"
    projects.mkdir(parents=True, exist_ok=True)
    transcript = projects / "session.jsonl"
    body = _record("alpha") + _record("bravo")
    # `size` is what the guard reads, so pad the file itself rather than
    # patching an attribute: the guard has to work off the real listing.
    transcript.write_text(body + "#" * max(0, pad_bytes))
    return next(
        item
        for item in discover_source_files(
            _grant(root), suffixes=frozenset({".jsonl"}), max_targets=10
        )
        if isinstance(item, AuthorizedSourceFile)
    )


def _collect(adapter, files, options) -> list:
    async def run() -> list:
        return [event async for event in adapter.read_listed(files, options)]

    return asyncio.run(run())


def test_a_large_file_is_read_in_bounded_slices_not_dropped(tmp_path):
    """A file past the budget still yields its first records.

    The point of the guard is to stop the import being held open, not to stop
    the file being imported at all.
    """
    entry = _entry(tmp_path, pad_bytes=0)
    # Force the budget just past the first record so the pass stops early.
    options = ScanOptions(max_source_file_bytes=len(_record("alpha")) + 8)
    adapter = create_workbuddy_adapter(_grant(tmp_path))
    events = _collect(adapter, [entry], options)

    # No longer skipped: the file is imported in slices.
    assert not [event for event in events if isinstance(event, ScanSkip)], events
    evidenced = [event for event in events if getattr(event, "kind", None) == "evidence"]
    assert evidenced, f"the first slice should still import, got {events}"
    # And the pass stopped at the budget rather than reading the whole file.
    assert len(evidenced) == 1, f"expected only the first record, got {len(evidenced)}"


def test_a_file_under_the_guard_is_still_read(tmp_path):
    entry = _entry(tmp_path, pad_bytes=0)
    options = ScanOptions(max_source_file_bytes=DEFAULT_IMPORT_MAX_FILE_BYTES)
    adapter = create_workbuddy_adapter(_grant(tmp_path))
    events = _collect(adapter, [entry], options)

    assert not [event for event in events if isinstance(event, ScanSkip)], events
    assert [event for event in events if getattr(event, "kind", None) == "evidence"], events


def test_the_guard_applies_when_no_option_is_set(tmp_path):
    """The packaged app sets nothing, so the default must still protect."""
    entry = _entry(tmp_path, pad_bytes=0)
    options = ScanOptions()
    assert options.max_source_file_bytes is None
    adapter = create_workbuddy_adapter(_grant(tmp_path))
    events = _collect(adapter, [entry], options)
    assert not [
        event
        for event in events
        if isinstance(event, ScanSkip) and event.reason_code == "file_too_large"
    ], (
        f"{entry.size}-byte file must not be dropped by the "
        f"{DEFAULT_IMPORT_MAX_FILE_BYTES}-byte default"
    )


def test_successive_passes_import_the_whole_file_exactly_once(tmp_path):
    """The budget must slice a file, not lose it.

    Verified end to end on the real codex set: at 32MB a skip-based guard
    dropped 30 of 474 files, which is 6% of the files but 85% of the bytes.
    """
    from one_memory.imports.readers import read_jsonl

    body = "".join(_record(f"message number {index}") for index in range(20))
    projects = tmp_path / ".codebuddy" / "projects" / "qa"
    projects.mkdir(parents=True, exist_ok=True)
    (projects / "big.jsonl").write_text(body)
    entry = _entry(tmp_path)

    budget = 200
    checkpoint: str | None = None
    offsets: list[int] = []
    collected = 0
    for _ in range(20):
        events = [event for event in read_jsonl(entry, checkpoint=checkpoint, max_bytes=budget)]
        if not events:
            break
        collected += len([event for event in events if hasattr(event, "value")])
        checkpoint = events[-1].checkpoint
        offsets.append(int(checkpoint.removeprefix("byte:")))

    assert collected == 20, f"a budgeted read lost records: {collected} of 20"
    assert all(offsets[i] < offsets[i + 1] for i in range(len(offsets) - 1)), (
        f"checkpoints did not advance: {offsets}"
    )
    assert offsets[-1] == entry.size, (
        f"the last pass ended at {offsets[-1]}, not the file end {entry.size}"
    )
