"""The workspace lookup behind an external recall must not run on the loop.

The loop watchdog caught this read on the loop thread in 27 of the 60 stalls it
reported: `known_workspaces` answers from a covering index but still walks
hundreds of thousands of index entries, and every recall from an installed host
paid for it serially. This pins the thread it runs on, because a test that only
asserts the answer would pass either way — the bug was never a wrong answer, it
was an unanswered loop.
"""

import asyncio
import threading
from typing import Any

from fastapi import FastAPI
from starlette.requests import Request

from one_memory.api import _require_external_recall_scope
from one_memory.workspace_resolution import resolve_workspace_scopes


class _Access:
    def require(self, tool: str, scopes: frozenset[str]) -> None:
        return None


class _FakeEvidenceStore:
    known: "list[int]" = []

    def known_workspaces(self, *, user_id: str) -> list[Any]:
        _FakeEvidenceStore.known.append(threading.get_ident())
        return []


def test_workspace_lookup_for_an_external_recall_runs_off_the_loop(monkeypatch) -> None:
    _FakeEvidenceStore.known = []
    monkeypatch.setattr("one_memory.api.external_access", lambda headers: _Access())
    monkeypatch.setattr("one_memory.api._evidence_store", lambda app: _FakeEvidenceStore())

    async def scenario() -> None:
        loop_thread = threading.get_ident()
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/recall",
                "headers": [],
                "query_string": b"",
            }
        )
        await _require_external_recall_scope(
            FastAPI(),
            request,
            "all-apps",
            None,
            "om_recall",
        )
        assert _FakeEvidenceStore.known, "the workspace lookup was never called"
        assert _FakeEvidenceStore.known[0] != loop_thread, (
            "known_workspaces ran on the event loop thread; it must run in a worker"
        )

    asyncio.run(scenario())


def test_the_ask_path_also_reads_the_workspace_lookup_off_the_loop(monkeypatch) -> None:
    """Same read, other door: /ask reaches it through MemoryAnswerer.retrieve.

    That file is not ours to edit, so the read is done in `_request_answerer`
    — where both ask paths meet — and the answerer is handed a callable that
    only resolves against the list already fetched. Two things have to hold:
    the read is off the loop, and the scopes are exactly what the inline
    version would have returned. The second is the one that matters: this
    callable decides which memories a host may be answered from.
    """
    known = [_Known("/repo", "p")]
    seen: list[int] = []

    class Store:
        def known_workspaces(self, *, user_id: str) -> list[Any]:
            seen.append(threading.get_ident())
            return known

    class Access:
        scopes = frozenset({"all-apps"})

        def require(self, tool: str, scopes: frozenset[str]) -> None:
            return None

    import one_memory.api as api

    monkeypatch.setattr(api, "external_access", lambda headers: Access())
    monkeypatch.setattr(api, "_evidence_store", lambda app: Store())

    answerer = _BareAnswerer()
    answerer.resolve_workspace = lambda path: ("replaced-by-the-fix",)
    monkeypatch.setattr(api, "_memory_answerer", lambda app: answerer)

    async def scenario() -> None:
        loop_thread = threading.get_ident()
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/memories/ask",
                "headers": [],
                "query_string": b"",
            }
        )
        resolved = await api._request_answerer(FastAPI(), request, workspace_path="/repo")

        assert seen, "the workspace lookup was never called"
        assert seen[0] != loop_thread, (
            "known_workspaces ran on the event loop thread; it must run in a worker"
        )
        # The boundary must be unchanged, not merely non-empty.
        assert resolved.resolve_workspace("/repo") == resolve_workspace_scopes("/repo", known)

    asyncio.run(scenario())


class _Known:
    def __init__(self, workspace: str, project: str) -> None:
        self.source_id = "cursor"
        self.workspace = workspace
        self.project = project


class _BareAnswerer:
    """Just enough of MemoryAnswerer for the per-request copy to work."""

    filter_memories = staticmethod(tuple)
    resolve_workspace = None
