import json
import runpy
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "matter_shadow.py"


def functions():
    return runpy.run_path(str(SCRIPT))


def database(path):
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE source_grants(user_id TEXT, source_id TEXT, revoked_at TEXT);
            CREATE TABLE evidence(
                evidence_id TEXT, user_id TEXT, source_id TEXT, conversation_id TEXT,
                role TEXT, written_by TEXT, created_at TEXT, imported_at TEXT,
                verbatim TEXT, revision INTEGER, content_hash TEXT, workspace TEXT,
                project TEXT, content_kind TEXT, source_ordinal TEXT
            );
        """)
        db.executemany(
            "INSERT INTO source_grants VALUES (?,?,?)",
            [
                ("local", "allowed", None),
                ("local", "revoked", "2026-09-01"),
                ("someone-else", "other", None),
            ],
        )
        for identifier, user, source, conversation, role, author, content in [
            (
                "u1",
                "local",
                "allowed",
                "c1",
                "user",
                "person",
                "This project uses local storage only.",
            ),
            (
                "a1",
                "local",
                "allowed",
                "c1",
                "assistant",
                "agent",
                "I proposed a local database for the application.",
            ),
            ("u2", "local", "revoked", "c2", "user", "person", "Revoked private record."),
            ("u3", "someone-else", "other", "c3", "user", "person", "Someone else's record."),
        ]:
            db.execute(
                "INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    user,
                    source,
                    conversation,
                    role,
                    author,
                    "2026-09-01T12:00:00+00:00",
                    "2026-09-02T12:00:00+00:00",
                    content,
                    1,
                    identifier,
                    "/project",
                    "project",
                    "raw_conversation",
                    identifier,
                ),
            )


def test_snapshot_filters_revoked_and_other_users_without_changing_source(tmp_path):
    path = tmp_path / "source.db"
    database(path)
    before = path.read_bytes()
    result = functions()["snapshot"](path, per_source=2)
    ids = {record["evidence_id"] for c in result["conversations"] for record in c["records"]}
    assert ids == {"u1", "a1"}
    assert result["coverage"][0]["source_id"] == "allowed"
    assert path.read_bytes() == before


def test_snapshot_is_read_only_even_when_a_write_is_attempted(tmp_path):
    path = tmp_path / "source.db"
    database(path)
    connect = functions()["connect_readonly"]
    with connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 4
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("DELETE FROM evidence")


def test_checked_claims_require_exact_supplied_quote_and_stay_unverified():
    records = [
        {
            "evidence_id": "a1",
            "text": "I proposed a local database for this project.",
            "role": "assistant",
            "written_by": "agent",
            "revision": 1,
        }
    ]
    output = {
        "title": "Project storage",
        "claims": [
            {"record_id": "a1", "quote": "I proposed a local database", "kind": "proposal"},
            {"record_id": "missing", "quote": "I proposed a local database", "kind": "decision"},
            {
                "record_id": "a1",
                "quote": "The database has been tested and deployed.",
                "kind": "progress",
            },
        ],
    }
    result = functions()["check_proposal"](output, records)
    assert len(result["claims"]) == 1
    assert result["rejected_claims"] == 2
    assert result["claims"][0]["evidence_status"] == "quote_linked_unverified"
    assert result["claims"][0]["speaker"] == "agent"


def test_private_tokens_redacted_before_model_input(tmp_path):
    path = tmp_path / "source.db"
    database(path)
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE evidence SET verbatim=? WHERE evidence_id='u1'",
            ("API_KEY=sk-abcdefghijklmnop123456789 this is private",),
        )
    result = functions()["snapshot"](path, per_source=1)
    encoded = json.dumps(result)
    assert "sk-abcdefghijklmnop123456789" not in encoded
    assert "redacted-secret" in encoded


def test_local_model_endpoint_rejects_remote_hosts_and_credentials():
    check = functions()["validate_local_endpoint"]
    check("http://127.0.0.1:11434")
    check("http://localhost:11434")
    for url in [
        "https://example.com",
        "http://127.0.0.1.example.com",
        "http://user:pass@localhost:11434",
    ]:
        with pytest.raises(ValueError):
            check(url)


def test_grouping_cannot_drop_duplicate_or_invent_proposals():
    check = functions()["check_groups"]
    proposals = [{"id": "p1"}, {"id": "p2"}]
    good = {"groups": [{"title": "Project", "proposal_ids": ["p1", "p2"]}]}
    assert check(good, proposals)[0]["proposal_ids"] == ["p1", "p2"]
    for ids in [["p1"], ["p1", "p1", "p2"], ["p1", "p2", "invented"]]:
        with pytest.raises(ValueError):
            check({"groups": [{"title": "Project", "proposal_ids": ids}]}, proposals)


def test_agent_authored_requests_are_context_not_relabelled_as_human(tmp_path):
    path = tmp_path / "source.db"
    database(path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE evidence SET written_by='agent' WHERE evidence_id='u1'")
    result = functions()["snapshot"](path, per_source=1)
    records = result["conversations"][0]["records"]
    assert records[0]["written_by"] == "agent"
    assert {item["evidence_id"] for item in records} == {"u1", "a1"}


def test_long_assistant_tail_keeps_request_anchor_and_marks_partial(tmp_path):
    path = tmp_path / "source.db"
    database(path)
    with sqlite3.connect(path) as db:
        for i in range(10):
            db.execute(
                "INSERT INTO evidence SELECT ?,user_id,source_id,conversation_id,role,"
                "written_by,created_at,imported_at,verbatim,revision,content_hash,workspace,"
                "project,content_kind,source_ordinal FROM evidence WHERE evidence_id='a1'",
                (f"tail-{i}",),
            )
    conversation = functions()["snapshot"](path, max_records=4)["conversations"][0]
    assert conversation["records"][0]["evidence_id"] == "u1"
    assert len(conversation["records"]) == 4
    assert conversation["partial"] is True


def test_saved_snapshot_is_refused_after_source_revocation(tmp_path):
    path = tmp_path / "source.db"
    database(path)
    api = functions()
    sample = api["snapshot"](path)
    api["verify_snapshot_grants"](path, sample)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE source_grants SET revoked_at='2026-09-11' WHERE source_id='allowed'")
    with pytest.raises(PermissionError, match="no longer active"):
        api["verify_snapshot_grants"](path, sample)
