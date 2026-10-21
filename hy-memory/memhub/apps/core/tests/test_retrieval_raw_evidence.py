import sqlite3
import time
from contextlib import closing

import pytest

from one_memory.retrieval.index_worker import RetrievalIndexWorker
from one_memory.retrieval.raw_evidence import materialize_raw_candidates
from tests.test_retrieval_index_store import fixture, put  # noqa: F401
from tests.test_retrieval_index_worker import Encoder, forbid_network  # noqa: F401
from tests.test_retrieval_raw_candidates import indexed as indexed_fixture
from tests.test_retrieval_raw_candidates import search

indexed = indexed_fixture


def materialize(indexed, candidates=None, **kwargs):
    options = dict(
        source_ids=frozenset({"codex"}), deadline=time.monotonic() + 10, character_budget=6000
    )
    options.update(kwargs)
    return materialize_raw_candidates(
        indexed[0][3], candidates or search(indexed), generation_id=indexed[1], **options
    )


def test_materialized_text_is_exact_current_original(indexed):
    result = materialize(indexed)
    assert result.complete and len(result.items) == 1
    item = result.items[0]
    assert item.evidence_id == indexed[2].evidence_id
    assert item.spans[0].text == indexed[2].verbatim
    assert item.written_by == "person" and item.matched_by == ("semantic",)


@pytest.mark.parametrize("change", ["revision", "revoke", "unrecorded"])
def test_stale_candidates_do_not_authorize_original_read(indexed, change):
    candidates = search(indexed)
    assert candidates.hits
    f = indexed[0]
    if change == "revision":
        put(f[1], "updated original")
    elif change == "revoke":
        f[2].revoke(user_id="local", source_id="codex")
    else:
        with closing(sqlite3.connect(f[0])) as db, db:
            db.execute(
                "UPDATE evidence SET verbatim='unrecorded' WHERE evidence_id=?",
                (indexed[2].evidence_id,),
            )
    result = materialize(indexed, candidates)
    assert not result.items and not result.complete and result.reason == "evidence_changed"


def test_budget_does_not_cut_a_chunk_into_fake_partial_object(indexed):
    result = materialize(indexed, character_budget=5)
    assert not result.items and not result.complete and result.reason == "character_budget"


def test_forged_offsets_and_modified_manifest_do_not_release_body(indexed):
    candidates = search(indexed)
    with closing(sqlite3.connect(indexed[0][0])) as db, db:
        db.execute("UPDATE retrieval_chunks SET start_cp=2")
    result = materialize(indexed, candidates)
    assert not result.items and not result.complete


def test_empty_authority_and_expired_deadline_return_no_body(indexed):
    candidates = search(indexed)
    assert not materialize(indexed, candidates, source_ids=frozenset()).items
    assert not materialize(indexed, candidates, deadline=time.monotonic() - 1).items


def test_overlapping_unicode_chunks_merge_without_duplicate_characters(indexed):
    f, generation, _, vectors = indexed
    text = "\u6c49\u5b57\U0001f680e\u0301 " * 180 + " /project/final-design.png"
    put(f[1], text)
    worker = RetrievalIndexWorker(
        f[3], vectors, Encoder(f[4]), generation_id=generation, owner="test"
    )
    assert worker.run_once().state == "ready"
    candidates = search(indexed)
    assert len(candidates.hits) > 1
    result = materialize(indexed, candidates)
    assert result.complete and len(result.items) == 1
    assert len(result.items[0].spans) == 1
    assert result.items[0].spans[0].text == text
    assert result.used_characters == len(text)
