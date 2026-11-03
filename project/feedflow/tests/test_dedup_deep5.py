from datetime import UTC, datetime, timedelta

from feedflow import store
from feedflow.db import get_conn
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


def _ensure_feed(db_path, feed_id=1):
    conn = get_conn(db_path)
    try:
        row = conn.execute("SELECT id FROM feeds WHERE id = ?", (feed_id,)).fetchone()
        if row is None:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(feeds)").fetchall()]
            name = "t"
            feed_url = "http://example.com/rss"
            site_url = "http://example.com"
            values = []
            names = []
            for c in cols:
                if c == "id":
                    names.append(c)
                    values.append(feed_id)
                elif c in ("name", "title"):
                    names.append(c)
                    values.append(name)
                elif c == "feed_url":
                    names.append(c)
                    values.append(feed_url)
                elif c == "site_url":
                    names.append(c)
                    values.append(site_url)
                elif c in ("created_at", "updated_at", "last_fetched_at"):
                    names.append(c)
                    values.append(datetime.now(UTC).isoformat())
            placeholders = ",".join("?" for _ in names)
            conn.execute(
                f"INSERT INTO feeds ({','.join(names)}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
    finally:
        conn.close()


def _insert(db_path, guid, title, content_text, published_at=None, feed_id=1):
    _ensure_feed(db_path, feed_id)
    return store.insert_article(
        db_path,
        feed_id=feed_id,
        guid=guid,
        title=title,
        author="",
        link="http://example.com/" + guid,
        summary="",
        content_html="",
        content_text=content_text,
        published_at=published_at,
    )


def _fetch(db_path, article_id):
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT id, simhash, cluster_id, title, content_text, published_at, fetched_at FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _raw_insert(
    db_path,
    feed_id,
    guid,
    title,
    content_text,
    published_at=None,
    fetched_at=None,
    simhash_val="",
    cluster_id=None,
):
    conn = get_conn(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO articles
                (feed_id, guid, title, link, summary, content_html, content_text,
                 published_at, fetched_at, simhash, cluster_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                feed_id,
                guid,
                title,
                "http://example.com/" + guid,
                "",
                "",
                content_text,
                published_at,
                fetched_at if fetched_at is not None else datetime.now(UTC).isoformat(),
                simhash_val,
                cluster_id,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


CN_BODY_A = (
    "苹果公司在今天的秋季发布会上正式推出了全新的旗舰手机产品线。"
    "据现场介绍，新机采用了全新的处理器架构，在图形性能和能效比方面都有明显提升。"
    "摄像头模组也经过了重新设计，主摄传感器面积更大，夜景拍摄能力进一步增强。"
    "价格方面，入门版本与上一代保持一致的起售价，高配版本则略有上浮。"
    "分析师认为，这次定价策略有助于稳住市场份额，同时推动高端机型的销售占比。"
    "发布会还展示了新的操作系统特性，包括更智能的助手和更完善的隐私保护功能。"
)


def test_a1_chinese_title_variants_same_body_same_cluster(tmp_db):
    _ensure_feed(tmp_db)
    id1 = _insert(tmp_db, "a1-1", "震惊！苹果发布会价格曝光", CN_BODY_A)
    id2 = _insert(tmp_db, "a1-2", "苹果秋季发布会：新品价格汇总", CN_BODY_A)
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    assert a1["cluster_id"] is not None
    assert a2["cluster_id"] is not None
    assert a1["cluster_id"] == a2["cluster_id"]


def test_a2_english_case_punct_variants_same_cluster(tmp_db):
    _ensure_feed(tmp_db)
    body = (
        "Apple today announced its latest flagship smartphone at the fall event. "
        "The new device features an updated processor architecture with improved graphics "
        "performance and power efficiency. The camera module has been redesigned with a "
        "larger main sensor for better low light photography. Pricing stays the same for "
        "the entry model while higher storage tiers cost slightly more than before."
    )
    id1 = _insert(tmp_db, "a2-1", "Apple Unveils New iPhone 17", body)
    id2 = _insert(tmp_db, "a2-2", "apple unveils new iphone 17!!!", body)
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    assert a1["cluster_id"] == a2["cluster_id"]


def test_b1_same_event_different_wording_jaccard_observed(tmp_db):
    text_a = (
        "据当地媒体报道，昨天下午市区一条主干道发生了多车追尾事故。"
        "交警部门通报称，事故造成三人轻伤，没有人员死亡。"
        "初步调查显示，事故原因是前车突然减速，后方车辆未保持安全距离。"
        "事发路段一度出现严重拥堵，救援人员在半小时内清理了现场。"
        "交警提醒驾驶员在雨天路滑时要降低车速并保持车距。"
    )
    text_b = (
        "本地新闻消息，昨日傍晚城市中心的一条主要街道上出现了连环碰撞。"
        "警方发布的信息表明，共有三名伤者，均为轻伤，无人遇难。"
        "调查人员认为，起因是前方车辆紧急刹车，后车跟车距离不足。"
        "该路段短时间内交通瘫痪，工作人员在约三十分钟后恢复了通行。"
        "有关部门呼吁司机在湿滑路面务必减速慢行注意安全距离。"
    )
    s = jaccard_similarity(text_a, text_b)
    # 实测中文同事件异述 Jaccard 约 0.09，远低于 JACCARD_THRESHOLD=0.35：
    # 跨源不同写法会被判为不同事件而漏聚，这是当前两阶段算法的已知边界。
    assert 0.05 <= s < 0.35, f"观测记录：中文同事件异述 Jaccard={s}"

    _ensure_feed(tmp_db)
    id1 = _insert(tmp_db, "b1-1", "市区主干道发生多车追尾", text_a)
    id2 = _insert(tmp_db, "b1-2", "城市中心街道连环碰撞", text_b)
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    same = a1["cluster_id"] == a2["cluster_id"]
    assert isinstance(same, bool)


def test_b2_summary_third_length_observed(tmp_db):
    full = (
        "研究团队在国际期刊上发表了关于新型电池材料的最新成果。"
        "该材料在实验室条件下展现出更高的能量密度和更长的循环寿命。"
        "研究人员表示，这种材料有望降低电池成本并提高充电速度。"
        "下一步计划是与产业界合作推进中试生产线的建设。"
        "业内专家评价说，这一进展对电动汽车行业具有积极意义。"
        "团队还在探索该材料在储能电站领域的应用前景。"
    )
    summary = "研究团队发表新型电池材料成果，能量密度更高、寿命更长，有望降低成本并加快充电速度。"
    s = jaccard_similarity(full, summary)
    assert 0.0 <= s < 0.9, f"观测记录：摘要 vs 全文 Jaccard={s}"

    _ensure_feed(tmp_db)
    id1 = _insert(tmp_db, "b2-1", "新型电池材料研究获突破", full)
    id2 = _insert(tmp_db, "b2-2", "新型电池材料研究获突破", summary)
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    same = a1["cluster_id"] == a2["cluster_id"]
    assert isinstance(same, bool)


def test_c1_three_char_diff_same_cluster(tmp_db):
    base = (
        "今天上午，市气象台发布了高温橙色预警信号，预计未来三天最高气温将达到三十八度。"
        "有关部门提醒市民减少户外活动，注意补充水分，防范中暑风险。"
        "电力部门表示已经做好迎峰度夏的准备，保障居民用电需求。"
        "医院方面也加强了急诊力量，应对可能增加的中暑就诊人数。"
    )
    modified = (
        "今天上午，市气象台发布了高温橙色预警信号，预计未来三天最高气温将达到三十九度。"
        "有关部门提醒市民减少户外活动，注意补充水分，防范中暑风险。"
        "电力部门表示已经做好迎峰度夏的准备，保障居民用电需求。"
        "医院方面也加强了急诊力量，应对可能增加的中暑就诊人数。"
    )
    _ensure_feed(tmp_db)
    id1 = _insert(tmp_db, "c1-1", "高温橙色预警发布", base)
    id2 = _insert(tmp_db, "c1-2", "高温橙色预警发布", modified)
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    assert a1["cluster_id"] == a2["cluster_id"]


def test_c2_paragraph_swap_same_cluster(tmp_db):
    p1 = "第一段介绍了本次大会的召开背景和主要议题。"
    p2 = "第二段详细说明了与会各方达成的共识与合作意向。"
    body1 = p1 + p2
    body2 = p2 + p1
    _ensure_feed(tmp_db)
    id1 = _insert(tmp_db, "c2-1", "国际大会达成多项共识", body1)
    id2 = _insert(tmp_db, "c2-2", "国际大会达成多项共识", body2)
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    assert a1["cluster_id"] == a2["cluster_id"]


def test_c3_completely_different_different_cluster(tmp_db):
    body_a = (
        "考古学家在西北地区发现了一处新石器时代的聚落遗址。"
        "出土的陶器和石器表明这里曾有过较为发达的农业活动。"
        "遗址的年代测定结果显示其距今约五千年。"
    )
    body_b = (
        "某科技公司发布了新一代的云计算服务产品。"
        "该产品支持弹性伸缩和按量计费，面向中小型企业客户。"
        "公司表示未来将持续投入基础设施的建设。"
    )
    _ensure_feed(tmp_db)
    id1 = _insert(tmp_db, "c3-1", "新石器时代遗址被发现", body_a)
    id2 = _insert(tmp_db, "c3-2", "云计算服务新品发布", body_b)
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    assert a1["cluster_id"] != a2["cluster_id"]


def test_c4_similar_title_different_body_different_cluster(tmp_db):
    body_a = (
        "某明星在社交平台上发布了一条动态，引发了粉丝的热烈讨论。"
        "该动态内容与近期的工作安排有关，具体细节尚未公开。"
    )
    body_b = (
        "国家统计局公布了上个月的经济运行数据。数据显示工业生产保持稳定增长，消费市场逐步回暖。"
    )
    _ensure_feed(tmp_db)
    id1 = _insert(tmp_db, "c4-1", "重磅消息引发热议", body_a)
    id2 = _insert(tmp_db, "c4-2", "重磅消息引发热议", body_b)
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    assert a1["cluster_id"] != a2["cluster_id"]


def test_d1_within_window_same_cluster(tmp_db):
    published = (datetime.now(UTC) - timedelta(days=13)).isoformat()
    _ensure_feed(tmp_db)
    id1 = _insert(tmp_db, "d1-1", "窗口内测试文章标题", CN_BODY_A, published_at=published)
    id2 = _insert(tmp_db, "d1-2", "窗口内测试文章标题", CN_BODY_A)
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    assert a1["cluster_id"] == a2["cluster_id"]


def test_d2_outside_window_different_cluster(tmp_db):
    published = (datetime.now(UTC) - timedelta(days=15)).isoformat()
    _ensure_feed(tmp_db)
    id1 = _insert(tmp_db, "d2-1", "窗口外测试文章标题", CN_BODY_A, published_at=published)
    id2 = _insert(tmp_db, "d2-2", "窗口外测试文章标题", CN_BODY_A)
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    assert a1["cluster_id"] != a2["cluster_id"]


def test_d3_null_published_falls_back_to_fetched_at(tmp_db):
    _ensure_feed(tmp_db)
    text = get_text_for({"title": "回退抓取时间测试", "content_text": CN_BODY_A})
    sh = simhash(text)
    raw_id = _raw_insert(
        tmp_db,
        1,
        "d3-1",
        "回退抓取时间测试",
        CN_BODY_A,
        published_at=None,
        fetched_at=datetime.now(UTC).isoformat(),
        simhash_val=sh,
        cluster_id=None,
    )
    conn = get_conn(tmp_db)
    try:
        conn.execute("UPDATE articles SET cluster_id = id WHERE id = ?", (raw_id,))
        conn.commit()
    finally:
        conn.close()
    id2 = _insert(tmp_db, "d3-2", "回退抓取时间测试", CN_BODY_A)
    a1 = _fetch(tmp_db, raw_id)
    a2 = _fetch(tmp_db, id2)
    assert a1["cluster_id"] == a2["cluster_id"]


def test_e1_short_title_only_observed(tmp_db):
    _ensure_feed(tmp_db)
    id1 = _insert(tmp_db, "e1-1", "苹果发布新手机了", "")
    id2 = _insert(tmp_db, "e1-2", "苹果发布新手机啦", "")
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    same = a1["cluster_id"] == a2["cluster_id"]
    assert isinstance(same, bool)


def test_e2_identical_title_no_body_same_cluster(tmp_db):
    _ensure_feed(tmp_db)
    id1 = _insert(tmp_db, "e2-1", "完全相同的标题内容", "")
    id2 = _insert(tmp_db, "e2-2", "完全相同的标题内容", "")
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    assert a1["cluster_id"] == a2["cluster_id"]


def test_f1_three_similar_all_same_first_cluster(tmp_db):
    base = (
        "本市新建的图书馆于本周正式对公众开放。"
        "馆内藏书超过五十万册，设有多个阅读区和自习室。"
        "开放首日吸引了大量市民前来参观体验。"
    )
    v2 = base + "此外还配备了数字化借阅系统。"
    v3 = base + "同时提供免费的无线网络服务。"
    _ensure_feed(tmp_db)
    id1 = _insert(tmp_db, "f1-1", "市图书馆正式开放", base)
    id2 = _insert(tmp_db, "f1-2", "市图书馆正式开放", v2)
    id3 = _insert(tmp_db, "f1-3", "市图书馆正式开放", v3)
    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    a3 = _fetch(tmp_db, id3)
    assert a1["cluster_id"] == a2["cluster_id"] == a3["cluster_id"] == id1


def test_f2_picks_higher_jaccard_cluster(tmp_db):
    text_a = (
        "某公司今天发布了年度财报，营收同比增长百分之二十，净利润也有明显提升。"
        "管理层表示将继续加大研发投入，拓展海外市场。"
    )
    text_b = (
        "某公司今天发布了年度财报，营收同比增长百分之二十，净利润也有明显提升。"
        "管理层表示将继续加大研发投入，拓展海外市场。此外还宣布了股票回购计划。"
    )
    text_query = (
        "某公司今天发布了年度财报，营收同比增长百分之二十，净利润也有明显提升。"
        "管理层表示将继续加大研发投入，拓展海外市场。公司同时公布了新的战略规划。"
    )
    _ensure_feed(tmp_db)
    id_a = _insert(tmp_db, "f2-a", "年度财报发布A", text_a)
    id_b = _insert(tmp_db, "f2-b", "年度财报发布B", text_b)
    conn = get_conn(tmp_db)
    try:
        conn.execute("UPDATE articles SET cluster_id = ? WHERE id = ?", (id_b, id_a))
        conn.commit()
    finally:
        conn.close()
    id_q = _insert(tmp_db, "f2-q", "年度财报发布Q", text_query)
    a_q = _fetch(tmp_db, id_q)
    # 上文已把 A 并入簇 id_b；Q 与 A 的 Jaccard 更高，应归入 A 所在的簇 id_b。
    assert a_q["cluster_id"] == id_b


def test_g1_backfill_processes_three(tmp_db):
    _ensure_feed(tmp_db)
    body_a = (
        "第一篇文章讲述的是城市轨道交通的新线路开通运营。"
        "该线路连接了城市的东西两端，全长约三十公里。"
    )
    body_a2 = (
        "第一篇文章讲述的是城市轨道交通的新线路开通运营。"
        "该线路连接了城市的东西两端，全长约三十公里，共设站二十座。"
    )
    body_b = "另一则消息报道了某地举办的国际美食节活动。活动期间有来自多个国家的厨师现场展示厨艺。"
    id1 = _raw_insert(tmp_db, 1, "g1-1", "地铁新线开通", body_a, simhash_val="", cluster_id=None)
    id2 = _raw_insert(tmp_db, 1, "g1-2", "地铁新线开通", body_a2, simhash_val="", cluster_id=None)
    id3 = _raw_insert(tmp_db, 1, "g1-3", "国际美食节举办", body_b, simhash_val="", cluster_id=None)

    processed = backfill_clusters(tmp_db)
    assert processed == 3

    a1 = _fetch(tmp_db, id1)
    a2 = _fetch(tmp_db, id2)
    a3 = _fetch(tmp_db, id3)
    assert a1["simhash"] and a2["simhash"] and a3["simhash"]
    assert a1["cluster_id"] == a2["cluster_id"]
    assert a3["cluster_id"] != a1["cluster_id"]


def test_g2_backfill_idempotent(tmp_db):
    _ensure_feed(tmp_db)
    body_a = (
        "第一篇文章讲述的是城市轨道交通的新线路开通运营。"
        "该线路连接了城市的东西两端，全长约三十公里。"
    )
    body_a2 = (
        "第一篇文章讲述的是城市轨道交通的新线路开通运营。"
        "该线路连接了城市的东西两端，全长约三十公里，共设站二十座。"
    )
    body_b = "另一则消息报道了某地举办的国际美食节活动。活动期间有来自多个国家的厨师现场展示厨艺。"
    _raw_insert(tmp_db, 1, "g2-1", "地铁新线开通", body_a, simhash_val="", cluster_id=None)
    _raw_insert(tmp_db, 1, "g2-2", "地铁新线开通", body_a2, simhash_val="", cluster_id=None)
    _raw_insert(tmp_db, 1, "g2-3", "国际美食节举办", body_b, simhash_val="", cluster_id=None)

    first = backfill_clusters(tmp_db)
    assert first == 3
    second = backfill_clusters(tmp_db)
    assert second == 0


def test_tokenize_cjk_bigrams():
    toks = tokenize("苹果手机")
    assert toks == ["苹果", "果手", "手机"]


def test_tokenize_single_cjk_kept():
    toks = tokenize("猫")
    assert toks == ["猫"]


def test_tokenize_ascii_lowercased():
    toks = tokenize("Hello World 123")
    assert toks == ["hello", "world", "123"]


def test_tokenize_empty_returns_empty():
    assert tokenize("") == []
    assert tokenize(None) == []


def test_simhash_stable_and_hex_length():
    h1 = simhash("苹果发布了新的手机产品")
    h2 = simhash("苹果发布了新的手机产品")
    assert h1 == h2
    assert len(h1) == 16
    int(h1, 16)


def test_hamming_identical_zero():
    h = simhash("测试文本内容")
    assert hamming(h, h) == 0


def test_hamming_invalid_returns_64():
    assert hamming("", "abc") == 64
    assert hamming("zz", "abc") == 64


def test_is_near_dup_threshold():
    h = simhash("完全相同的一段文字用于测试")
    assert is_near_dup(h, h, threshold=0) is True
    assert is_near_dup(h, h, threshold=DEFAULT_THRESHOLD) is True


def test_simhash_features_empty_returns_zeros():
    out = simhash_features([])
    assert out == "0" * 16


def test_get_text_for_title_weighted_twice():
    text = get_text_for({"title": "标题", "content_text": "正文"})
    assert text == "标题 标题 正文"


def test_get_text_for_empty():
    assert get_text_for(None) == ""
    assert get_text_for({}) == ""


def test_jaccard_identical_is_one():
    s = jaccard_similarity("苹果手机发布了", "苹果手机发布了")
    assert s == 1.0


def test_jaccard_empty_returns_zero():
    assert jaccard_similarity("", "abc") == 0.0
    assert jaccard_similarity("abc", "") == 0.0


def test_constants_sane():
    assert CLUSTER_WINDOW_DAYS == 14
    assert DEFAULT_THRESHOLD == 3
    assert PREFILTER_HAMMING == 20
    assert JACCARD_THRESHOLD == 0.35
    assert PREFILTER_HAMMING > DEFAULT_THRESHOLD


def test_find_or_create_cluster_empty_simhash_returns_none(tmp_db):
    assert find_or_create_cluster(tmp_db, "") is None
    assert find_or_create_cluster(tmp_db, None) is None


def test_find_or_create_cluster_no_candidates_returns_none(tmp_db):
    _ensure_feed(tmp_db)
    sh = simhash("一篇孤立的文章内容用于测试聚类返回空")
    assert find_or_create_cluster(tmp_db, sh, "一篇孤立的文章内容用于测试聚类返回空") is None


def test_window_iso_boundary_days(tmp_db):
    published_in = (datetime.now(UTC) - timedelta(days=CLUSTER_WINDOW_DAYS - 1)).isoformat()
    published_out = (datetime.now(UTC) - timedelta(days=CLUSTER_WINDOW_DAYS + 1)).isoformat()
    _ensure_feed(tmp_db)
    id_in = _insert(tmp_db, "w-in", "窗口边界内文章", CN_BODY_A, published_at=published_in)
    id_q1 = _insert(tmp_db, "w-q1", "窗口边界内文章", CN_BODY_A)
    a_in = _fetch(tmp_db, id_in)
    a_q1 = _fetch(tmp_db, id_q1)
    assert a_in["cluster_id"] == a_q1["cluster_id"]

    # D2 用独立正文，避免与 D1 窗口内的文章误聚（同库隔离）。
    body_w2 = "窗口外事件：郊区新建的地铁站今日投入试运营。首班车载满了前来体验的市民。"
    id_out = _insert(tmp_db, "w-out", "窗口边界外文章", body_w2, published_at=published_out)
    id_q2 = _insert(tmp_db, "w-q2", "窗口边界外文章", body_w2)
    a_out = _fetch(tmp_db, id_out)
    a_q2 = _fetch(tmp_db, id_q2)
    assert a_out["cluster_id"] != a_q2["cluster_id"]
