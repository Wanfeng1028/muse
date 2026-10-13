"""测试 simhash 去重与文章聚类逻辑。

覆盖：
- 相同文本 simhash 一致，hamming 距离为 0
- 仅几字之差的中文文章被两阶段判定聚到同一簇
- 完全不同的文章不聚类
- 通过 store.insert_article 插入近似文章，验证 cluster_id 相同、cluster_size=2
"""

from datetime import UTC, datetime

from feedflow import db as db_mod
from feedflow import dedup, store


def _now():
    return datetime.now(UTC).isoformat()


def _make_feed_id(db_path):
    """直接插 feed 行（避免走网络解析元信息），返回 feed id。"""
    conn = db_mod.get_conn(db_path)
    try:
        with db_mod.write_lock:
            cur = conn.execute(
                "INSERT INTO feeds (title, site_url, feed_url, description,"
                " interval_min, enabled, etag, modified, position, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("测试源", "http://example.com", "http://example.com/feed", "",
                 0, 1, "", "", 0, _now()),
            )
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def test_identical_text_simhash():
    """相同文本的 simhash 必须完全一致，hamming 距离为 0。"""
    text = "这是一篇用于测试的中文文章，内容完全相同，用于验证 simhash 的稳定性。"
    h1 = dedup.simhash(text)
    h2 = dedup.simhash(text)
    assert h1 == h2
    assert dedup.hamming(h1, h2) == 0
    assert dedup.is_near_dup(h1, h2, threshold=3) is True


def test_similar_chinese_articles_clustered(tmp_db):
    """仅几个字差别的中文文章应被聚到同一簇（两阶段判定）。"""
    db_mod.init_db(tmp_db)
    feed_id = _make_feed_id(tmp_db)
    base = (
        "人工智能正在深刻改变我们的生活方式，从智能手机到自动驾驶汽车，"
        "从医疗诊断到金融风控，AI 技术已经渗透到各行各业。"
    )
    variant = (
        "人工智能正在深刻改变我们的生活方式，从智能手机到自动驾驶汽车，"
        "从医疗诊断到金融风控，AI 技术已经渗透到各个行业。"
    )
    aid1 = store.insert_article(
        tmp_db, feed_id, "g-1", "文章一", "", "http://example.com/a1",
        "", "", base, _now(),
    )
    text2 = ("文章二 " * 2) + variant
    sh2 = dedup.simhash(text2)
    cluster = dedup.find_or_create_cluster(tmp_db, sh2, text2)
    row = store.get_article(tmp_db, aid1)
    assert cluster == row["cluster_id"], (
        f"近似文章应命中同一簇，got={cluster} want={row['cluster_id']}"
    )


def test_different_articles_not_dup():
    """内容完全不同的两篇文章 hamming 距离应当很大，不判定为重复。"""
    text_a = "今天天气晴朗，适合出门散步，公园里的樱花开得正好。"
    text_b = "量子计算的原理基于量子比特的叠加态与纠缠态，能实现并行计算。"
    h1 = dedup.simhash(text_a)
    h2 = dedup.simhash(text_b)
    dist = dedup.hamming(h1, h2)
    assert dist > 3
    assert dedup.is_near_dup(h1, h2, threshold=3) is False
    assert dedup.jaccard_similarity(text_a, text_b) < 0.35


def test_insert_article_clustering(tmp_db):
    """插入近似文章应归入同一 cluster，cluster_size=2；不同文章另起一 cluster。"""
    db_mod.init_db(tmp_db)
    feed_id = _make_feed_id(tmp_db)

    text_a = (
        "人工智能正在深刻改变我们的生活方式，从智能手机到自动驾驶汽车，"
        "从医疗诊断到金融风控，AI 技术已经渗透到各行各业。"
    )
    text_b = (
        "人工智能正在深刻改变我们的生活方式，从智能手机到自动驾驶汽车，"
        "从医疗诊断到金融风控，AI 技术已经渗透到各个行业。"
    )
    text_c = "量子计算的原理基于量子比特的叠加态与纠缠态，能实现并行计算。"

    aid1 = store.insert_article(
        tmp_db, feed_id, "g-1", "文章一", "", "http://example.com/a1",
        "", "", text_a, _now(),
    )
    aid2 = store.insert_article(
        tmp_db, feed_id, "g-2", "文章二", "", "http://example.com/a2",
        "", "", text_b, _now(),
    )
    aid3 = store.insert_article(
        tmp_db, feed_id, "g-3", "文章三", "", "http://example.com/a3",
        "", "", text_c, _now(),
    )

    a1 = store.get_article(tmp_db, aid1)
    a2 = store.get_article(tmp_db, aid2)
    a3 = store.get_article(tmp_db, aid3)
    assert a1["cluster_id"] == a2["cluster_id"], "近似文章应在同一簇"
    assert a3["cluster_id"] != a1["cluster_id"], "不同文章不应在同一簇"

    total, rows = store.list_articles(tmp_db, scope="all", limit=50)
    assert total == 3
    by_id = {r["id"]: r for r in rows}
    assert by_id[aid1]["cluster_size"] == 2
    assert by_id[aid2]["cluster_size"] == 2
    assert by_id[aid3]["cluster_size"] == 1

    members = store.get_cluster_members(tmp_db, a1["cluster_id"], exclude_id=aid1)
    assert [m["id"] for m in members] == [aid2]
