import time
from datetime import UTC, datetime, timedelta

from feedflow.db import get_conn, write_lock
from feedflow.dedup import (
    CLUSTER_WINDOW_DAYS,
    DEFAULT_THRESHOLD,
    JACCARD_THRESHOLD,
    PREFILTER_HAMMING,
    backfill_clusters,
    find_or_create_cluster,
    get_text_for,
    hamming,
    is_near_dup,
    jaccard_similarity,
    simhash,
    simhash_features,
    tokenize,
)

_HEX_CHARS = set("0123456789abcdef")


def _insert_article(
    db_path,
    guid,
    title="",
    content_text="",
    simhash_hex="",
    cluster_id=None,
    published_at=None,
    feed_id=1,
):
    if published_at is None:
        published_at = datetime.now(UTC).isoformat()
    with write_lock:
        conn = get_conn(db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO articles
                    (feed_id, guid, title, link, summary, content_text,
                     published_at, fetched_at, simhash, cluster_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feed_id,
                    guid,
                    title,
                    "http://example.com/" + guid,
                    "",
                    content_text,
                    published_at,
                    datetime.now(UTC).isoformat(),
                    simhash_hex,
                    cluster_id,
                ),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def test_simhash_deterministic_and_hex_format(tmp_db):
    text = "人工智能 与 machine learning 的未来 2024"
    a = simhash(text)
    b = simhash(text)
    assert a == b
    assert len(a) == 16
    assert all(c in _HEX_CHARS for c in a)


def test_simhash_empty_and_none_do_not_raise(tmp_db):
    a = simhash("")
    b = simhash(None)
    assert isinstance(a, str) and len(a) == 16
    assert isinstance(b, str) and len(b) == 16
    assert all(c in _HEX_CHARS for c in a)
    assert all(c in _HEX_CHARS for c in b)


def test_tokenize_empty_returns_empty_list(tmp_db):
    assert tokenize("") == []
    assert tokenize(None) == []


def test_jaccard_empty_returns_zero(tmp_db):
    assert jaccard_similarity("", "x") == 0.0
    assert jaccard_similarity("x", "") == 0.0
    assert jaccard_similarity("", "") == 0.0


def test_hamming_same_fingerprint_is_zero(tmp_db):
    h = simhash("some stable text about databases")
    assert hamming(h, h) == 0


def test_hamming_all_zero_vs_all_f_is_64(tmp_db):
    assert hamming("0" * 16, "f" * 16) == 64


def test_hamming_invalid_inputs_return_64(tmp_db):
    assert hamming("", "f" * 16) == 64
    assert hamming("0" * 16, "") == 64
    assert hamming(None, "0" * 16) == 64
    assert hamming("0" * 16, None) == 64
    assert hamming("zzz", "0" * 16) == 64
    assert hamming("0" * 16, "zzz") == 64


def test_is_near_dup_threshold_boundary_equal_is_true(tmp_db):
    a = "0" * 16
    # 距离恰好等于 threshold
    for k in (1, 2, 3, 5):
        b = format((1 << k) - 1, "016x")
        assert hamming(a, b) == k
        assert is_near_dup(a, b, threshold=k) is True
        assert is_near_dup(a, b, threshold=k + 1) is True


def test_is_near_dup_threshold_boundary_above_is_false(tmp_db):
    a = "0" * 16
    # 距离 = k+1，阈值 = k 时应为 False
    for k in (1, 2, 3, 4):
        b = format((1 << (k + 1)) - 1, "016x")
        assert hamming(a, b) == k + 1
        assert is_near_dup(a, b, threshold=k) is False


def test_find_or_create_cluster_hit_same_cluster(tmp_db):
    text = "深度学习模型在图像识别任务中取得了显著进展，研究者们提出了多种新架构。"
    sh = simhash(text)
    _art_id = _insert_article(
        tmp_db,
        guid="hit-1",
        title=text,
        content_text=text,
        simhash_hex=sh,
        cluster_id=999,
    )
    # 高度相似文本，应命中同一 cluster
    similar = "深度学习模型在图像识别任务中取得了显著进展，研究者们提出了多种新架构！"
    hit = find_or_create_cluster(tmp_db, simhash(similar), similar)
    assert hit == 999


def test_find_or_create_cluster_miss_returns_none(tmp_db):
    text = "深度学习模型在图像识别任务中取得了显著进展，研究者们提出了多种新架构。"
    sh = simhash(text)
    _insert_article(
        tmp_db,
        guid="miss-1",
        title=text,
        content_text=text,
        simhash_hex=sh,
        cluster_id=777,
    )
    unrelated = "苹果香蕉橘子西瓜芒果菠萝柠檬草莓蓝莓树莓黑莓樱桃葡萄"
    miss = find_or_create_cluster(tmp_db, simhash(unrelated), unrelated)
    assert miss is None


def test_find_or_create_cluster_window_excludes_old_articles(tmp_db):
    text = "量子计算在密码学与优化问题上的应用前景非常广阔。"
    sh = simhash(text)
    old_pub = (
        datetime.now(UTC) - timedelta(days=CLUSTER_WINDOW_DAYS + 1)
    ).isoformat()
    _insert_article(
        tmp_db,
        guid="old-1",
        title=text,
        content_text=text,
        simhash_hex=sh,
        cluster_id=555,
        published_at=old_pub,
    )
    hit = find_or_create_cluster(tmp_db, sh, text)
    assert hit is None


def test_find_or_create_cluster_empty_simhash_returns_none(tmp_db):
    assert find_or_create_cluster(tmp_db, "", "some text") is None
    assert find_or_create_cluster(tmp_db, None, "some text") is None


def test_find_or_create_cluster_empty_text_falls_back_to_hamming(tmp_db):
    text = "气候变化对全球农业产生了深远的影响，需要更多研究。"
    sh = simhash(text)
    _insert_article(
        tmp_db,
        guid="empty-text-1",
        title=text,
        content_text=text,
        simhash_hex=sh,
        cluster_id=321,
    )
    # 空文本走纯汉明退化路径，相同指纹应命中
    hit = find_or_create_cluster(tmp_db, sh, "")
    assert hit == 321


def test_backfill_clusters_handles_empty_title(tmp_db):
    content = "只有正文没有标题的文章，仍然应该可以计算 simhash 并聚类。"
    art_id = _insert_article(
        tmp_db,
        guid="notitle-1",
        title="",
        content_text=content,
        simhash_hex="",
        cluster_id=None,
    )
    processed = backfill_clusters(tmp_db)
    assert processed == 1
    conn = get_conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT simhash, cluster_id FROM articles WHERE id = ?", (art_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["simhash"]
    assert len(row["simhash"]) == 16
    assert all(c in _HEX_CHARS for c in row["simhash"])
    assert row["cluster_id"] == art_id


def test_simhash_long_content_returns_hex(tmp_db):
    long_text = ("人工智能与机器学习的前沿研究 " * 6000)[:100000]
    assert len(long_text) == 90000
    start = time.monotonic()
    sh = simhash(long_text)
    elapsed = time.monotonic() - start
    assert isinstance(sh, str)
    assert len(sh) == 16
    assert all(c in _HEX_CHARS for c in sh)
    # 合理时间保护（避免死循环式实现）
    assert elapsed < 30.0


def test_backfill_clusters_idempotent(tmp_db):
    contents = [
        "第一篇关于数据库索引优化与查询计划的文章内容。",
        "第二篇关于分布式系统一致性与共识算法的文章。",
        "第三篇关于编译器前端词法分析与语法分析的内容。",
    ]
    ids = []
    for i, c in enumerate(contents):
        ids.append(
            _insert_article(
                tmp_db,
                guid=f"idem-{i:d}",
                title=c,
                content_text=c,
                simhash_hex="",
                cluster_id=None,
            )
        )
    first = backfill_clusters(tmp_db)
    assert first == 3

    conn = get_conn(tmp_db)
    try:
        before = {
            r["id"]: r["simhash"]
            for r in conn.execute(
                "SELECT id, simhash FROM articles WHERE id IN ({})".format(",".join("?" * len(ids))),
                ids,
            ).fetchall()
        }
    finally:
        conn.close()
    assert all(v for v in before.values())

    second = backfill_clusters(tmp_db)
    assert second == 0

    conn = get_conn(tmp_db)
    try:
        after = {
            r["id"]: r["simhash"]
            for r in conn.execute(
                "SELECT id, simhash FROM articles WHERE id IN ({})".format(",".join("?" * len(ids))),
                ids,
            ).fetchall()
        }
    finally:
        conn.close()
    assert after == before


def test_tokenize_chinese_bigrams(tmp_db):
    toks = tokenize("人工智能")
    assert "人工" in toks
    assert "工智" in toks
    assert "智能" in toks


def test_tokenize_ascii_lowercased(tmp_db):
    toks = tokenize("Hello World 123")
    assert "hello" in toks
    assert "world" in toks
    assert "123" in toks


def test_tokenize_fullwidth_nfkc_normalized(tmp_db):
    a = tokenize("ＡＩ")
    b = tokenize("ai")
    assert a == b
    assert "ai" in a


def test_get_text_for_title_weighted(tmp_db):
    text = get_text_for({"title": "标题", "content_text": "正文"})
    # 标题拼接两次，再拼正文
    assert text == "标题 标题 正文"


def test_simhash_features_skip_empty_word(tmp_db):
    # 空词应被跳过，只贡献非空词
    a = simhash_features([("", 1), ("hello", 1)])
    b = simhash_features([("hello", 1)])
    assert a == b
    assert len(a) == 16


def test_prefilter_and_jaccard_constants_sane(tmp_db):
    # 粗筛上限必须不小于默认阈值，否则严格阈值会被粗筛卡掉
    assert PREFILTER_HAMMING >= DEFAULT_THRESHOLD
    assert 0.0 < JACCARD_THRESHOLD <= 1.0


def test_find_or_create_cluster_short_text_jaccard_path(tmp_db):
    # 短文本差异几个字，汉明阈值 3 可能漏，但 Jaccard 路径应能召回
    base = "今天天气很好我们去公园散步吧"
    sh = simhash(base)
    _insert_article(
        tmp_db,
        guid="jaccard-1",
        title=base,
        content_text=base,
        simhash_hex=sh,
        cluster_id=4242,
    )
    query = "今天天气很好我们去公园散步啦"
    hit = find_or_create_cluster(tmp_db, simhash(query), query)
    assert hit == 4242