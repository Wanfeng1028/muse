import re

from feedflow.db import execute_write, query_all, query_one
from feedflow.seed import FEED_SPECS, ensure_seed


def _feed_id_map(db_path):
    rows = query_all(db_path, "SELECT id, feed_url FROM feeds")
    return {r["feed_url"]: r["id"] for r in rows}


def _article_count(db_path):
    row = query_one(db_path, "SELECT COUNT(*) AS c FROM articles")
    return row["c"]


def _guid_set(db_path):
    rows = query_all(db_path, "SELECT guid FROM articles")
    return {r["guid"] for r in rows}


def test_ensure_seed_feed_id_mapping_stable_across_two_calls(tmp_db):
    ensure_seed(tmp_db)
    first_map = _feed_id_map(tmp_db)
    first_count = _article_count(tmp_db)
    first_guids = _guid_set(tmp_db)

    ensure_seed(tmp_db)
    second_map = _feed_id_map(tmp_db)
    second_count = _article_count(tmp_db)
    second_guids = _guid_set(tmp_db)

    assert first_map == second_map
    assert first_count == second_count
    assert first_guids == second_guids


def test_gate_only_checks_feeds_table(tmp_db):
    ensure_seed(tmp_db)
    assert _article_count(tmp_db) > 0

    execute_write(tmp_db, "DELETE FROM articles")
    assert _article_count(tmp_db) == 0

    ensure_seed(tmp_db)
    assert _article_count(tmp_db) == 0


def test_preexisting_folder_is_preserved(tmp_db):
    execute_write(tmp_db, "INSERT INTO folders (name, position, created_at) VALUES (?, ?, ?)", ("我的分组", 99, "2025-01-01T00:00:00+00:00"))

    ensure_seed(tmp_db)

    rows = query_all(tmp_db, "SELECT name FROM folders")
    names = {r["name"] for r in rows}
    assert len(rows) == 3
    assert "技术博客" in names
    assert "科技资讯" in names
    assert "我的分组" in names


def test_feed_urls_match_feed_specs(tmp_db):
    ensure_seed(tmp_db)

    rows = query_all(tmp_db, "SELECT feed_url FROM feeds")
    actual = {r["feed_url"] for r in rows}
    expected = {s["feed_url"] for s in FEED_SPECS}
    assert actual == expected


def test_interval_min_matches_specs(tmp_db):
    ensure_seed(tmp_db)

    rows = query_all(tmp_db, "SELECT feed_url, interval_min FROM feeds")
    actual = {r["feed_url"]: r["interval_min"] for r in rows}

    for spec in FEED_SPECS:
        assert actual[spec["feed_url"]] == spec["interval"]


def test_article_guid_format(tmp_db):
    ensure_seed(tmp_db)

    rows = query_all(tmp_db, "SELECT guid FROM articles")
    pattern = re.compile(r"^demo-(ruanyf|coolshell|sspai|jiqizhixin|36kr|v2ex)-\d+$|^demo-cluster-\d+-\d+$")
    assert rows
    for r in rows:
        assert pattern.match(r["guid"]), r["guid"]


def test_starred_articles_are_second_per_feed(tmp_db):
    ensure_seed(tmp_db)

    rows = query_all(
        tmp_db,
        "SELECT guid, feed_id FROM articles WHERE is_starred = 1",
    )
    assert rows

    by_feed = {}
    for r in rows:
        by_feed.setdefault(r["feed_id"], []).append(r["guid"])

    feed_count = query_one(tmp_db, "SELECT COUNT(*) AS c FROM feeds")["c"]
    assert len(by_feed) == feed_count

    for guids in by_feed.values():
        assert len(guids) == 1
        assert guids[0].endswith("-2")