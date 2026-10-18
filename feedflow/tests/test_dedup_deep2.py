import hashlib
from datetime import UTC, datetime, timedelta

from feedflow import db as db_module
from feedflow.dedup import (
    DEFAULT_THRESHOLD,
    PREFILTER_HAMMING,
    backfill_clusters,
    find_or_create_cluster,
    get_text_for,
    hamming,
    is_near_dup,
    jaccard_similarity,
    simhash,
    tokenize,
)
from feedflow.store import insert_article


def _flip_bits(hex_str, n_bits):
    """翻转最低的 n_bits 个 bit，返回 16 位十六进制字符串。"""
    val = int(hex_str, 16)
    mask = (1 << n_bits) - 1
    return format(val ^ mask, "016x")


def _insert_feed(db_path, title="feed"):
    db_module.execute_write(
        db_path,
        "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, ?, ?)",
        (title, f"http://example.com/{title}", 0, datetime.now(UTC).isoformat()),
    )
    conn = db_module.get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM feeds ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["id"]
    finally:
        conn.close()


# 1. is_near_dup 阈值边界
def test_is_near_dup_threshold_boundary(tmp_db):
    a = "0" * 16
    b_three = _flip_bits(a, 3)
    b_four = _flip_bits(a, 4)
    assert hamming(a, b_three) == 3
    assert hamming(a, b_four) == 4
    assert is_near_dup(a, b_three, threshold=3) is True
    assert is_near_dup(a, b_four, threshold=3) is False
    # DEFAULT_THRESHOLD 应为 3，与显式传值一致
    assert DEFAULT_THRESHOLD == 3
    assert is_near_dup(a, b_three) is True
    assert is_near_dup(a, b_four) is False


# 2. simhash("") 全零指纹
def test_simhash_empty_returns_zero_fingerprint():
    assert simhash("") == "0000000000000000"


# 3. tokenize 超长纯中文
def test_tokenize_long_cjk_run():
    text = "中" * 10000
    tokens = tokenize(text)
    assert len(tokens) == 9999
    assert all(tok == "中中" for tok in tokens)


# 4. find_or_create_cluster 纯汉明退化路径
def test_find_or_create_cluster_hamming_degenerate_path(tmp_db):
    feed_id = _insert_feed(tmp_db, "degen")
    insert_article(
        tmp_db,
        feed_id,
        "guid-degen-1",
        "标题",
        "作者",
        "http://example.com/degen-1",
        "摘要",
        "<p>正文</p>",
        "正文内容",
        datetime.now(UTC).isoformat(),
    )

    conn = db_module.get_conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT id, simhash, cluster_id FROM articles WHERE guid = ?",
            ("guid-degen-1",),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["simhash"]
    assert row["cluster_id"] == row["id"]

    # 文本为空 → 退化为纯汉明判定，同 simhash 应命中
    hit = find_or_create_cluster(tmp_db, row["simhash"], text="")
    assert hit == row["cluster_id"]

    # 全 f 与全 0 汉明距离 64，远超阈值 → None
    all_f = "f" * 16
    all_zero = "0" * 16
    assert hamming(all_f, all_zero) == 64
    miss = find_or_create_cluster(tmp_db, all_f, text="")
    assert miss is None


# 5. 14 天窗口排除
def test_cluster_window_excludes_old_articles(tmp_db):
    feed_id = _insert_feed(tmp_db, "window")
    text = "这是一段用于聚类窗口测试的固定文本内容。"
    insert_article(
        tmp_db,
        feed_id,
        "guid-win-a",
        text,
        "作者",
        "http://example.com/win-a",
        "摘要",
        f"<p>{text}</p>",
        text,
        datetime.now(UTC).isoformat(),
    )
    # 把 A 的 published_at 与 fetched_at 都改成 30 天前
    old_iso = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    db_module.execute_write(
        tmp_db,
        "UPDATE articles SET published_at = ?, fetched_at = ? WHERE guid = ?",
        (old_iso, old_iso, "guid-win-a"),
    )

    insert_article(
        tmp_db,
        feed_id,
        "guid-win-b",
        text,
        "作者",
        "http://example.com/win-b",
        "摘要",
        f"<p>{text}</p>",
        text,
        datetime.now(UTC).isoformat(),
    )

    conn = db_module.get_conn(tmp_db)
    try:
        row_b = conn.execute(
            "SELECT id, cluster_id FROM articles WHERE guid = ?",
            ("guid-win-b",),
        ).fetchone()
    finally:
        conn.close()
    assert row_b is not None
    # B 没有与窗口外的 A 聚类，簇 id 指向自身
    assert row_b["cluster_id"] == row_b["id"]


# 6. PREFILTER_HAMMING 粗筛边界
def test_prefilter_hamming_boundary(tmp_db):
    assert PREFILTER_HAMMING == 20
    feed_id = _insert_feed(tmp_db, "prefilter")
    title = "这是一段用于粗筛边界测试的中文文本内容"
    content = "这是一段用于粗筛边界测试的中文文本内容"
    text_for_article = get_text_for({"title": title, "content_text": content})
    sh = simhash(text_for_article)

    insert_article(
        tmp_db,
        feed_id,
        "guid-prefilter",
        title,
        "作者",
        "http://example.com/prefilter",
        "摘要",
        f"<p>{content}</p>",
        content,
        datetime.now(UTC).isoformat(),
    )

    conn = db_module.get_conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT id, simhash, cluster_id FROM articles WHERE guid = ?",
            ("guid-prefilter",),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["simhash"] == sh

    hex20 = _flip_bits(sh, 20)
    hex21 = _flip_bits(sh, 21)
    assert hamming(sh, hex20) == 20
    assert hamming(sh, hex21) == 21

    # 20 个 bit 翻转 → 仍在粗筛内，且文本相同 Jaccard 命中
    hit = find_or_create_cluster(tmp_db, hex20, text=text_for_article)
    assert hit == row["cluster_id"]

    # 21 个 bit 翻转 → 超出粗筛，返回 None
    miss = find_or_create_cluster(tmp_db, hex21, text=text_for_article)
    assert miss is None


# 7. jaccard_similarity 空输入
def test_jaccard_similarity_empty_inputs():
    assert jaccard_similarity("", "") == 0.0
    assert jaccard_similarity("", "abc") == 0.0


# 8. get_text_for 空输入
def test_get_text_for_empty_inputs():
    assert get_text_for({}) == ""
    assert get_text_for(None) == ""