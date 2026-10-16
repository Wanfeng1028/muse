#!/usr/bin/env python3
"""FeedFlow 真实负载验证脚本。

用途：造 200 订阅 × 500 文章 = 10 万篇真实数据，实测三大接口的 p50/p95：
- 定时抓取（fetcher.fetch_feed / store.insert_article）
- 全文搜索（store.search_articles，FTS5 trigram / LIKE 退化）
- 三栏阅读（store.list_articles / Flask 主页渲染 / store.due_feeds / store.stats）
- 去重簇扫描诊断（dedup.find_or_create_cluster）

设计要点（严格零网络）：
- RSS 条目一律不写 <link>，extract_text 无 link 时不走网络，直接用 description 文本。
- feeds.feed_url 全部指向本地 RSS 文件路径，fetch_feed 对本地路径直接 feedparser 解析。
- 不调用 store.create_feed（其内部可能走网络解析 feed 信息），feeds 表用 db.get_conn 直接 SQL 插入。
- fetch_feed 调用时 retries=0、extract_timeout=1，避免任何网络等待。

只使用标准库 + 项目内模块。
"""

from __future__ import annotations

import argparse
import gc
import os
import random
import sqlite3
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

# 项目根加入 sys.path（scripts/ 的上一级），以便 import feedflow 包。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from feedflow import db as ff_db  # noqa: E402
from feedflow import dedup as ff_dedup  # noqa: E402
from feedflow import fetcher as ff_fetcher  # noqa: E402
from feedflow import store as ff_store  # noqa: E402


# ---------------------------------------------------------------------------
# 词库：科技 / 财经 / 体育 / 生活 四类，每类 40+ 词。
# ---------------------------------------------------------------------------
WORDS_TECH = [
    "芯片", "算力", "大模型", "开源", "算法", "编译器", "分布式", "缓存",
    "数据库", "索引", "向量", "推理", "训练", "显卡", "并行", "延迟",
    "吞吐", "容器", "微服务", "网关", "协议", "加密", "哈希", "调度",
    "内存", "进程", "线程", "协程", "异步", "回调", "序列化", "反序列化",
    "字节码", "虚拟机", "内核", "驱动", "固件", "传感器", "边缘计算", "云原生",
    "可观测", "监控", "日志", "链路", "灰度", "回滚", "压测", "基准",
]
WORDS_FINANCE = [
    "利率", "通胀", "汇率", "债券", "股票", "基金", "期货", "期权",
    "对冲", "套利", "流动性", "估值", "市盈率", "财报", "营收", "净利",
    "毛利", "现金流", "资产负债表", "负债", "杠杆", "回购", "分红", "配股",
    "增发", "并购", "重组", "上市", "退市", "监管", "牌照", "合规",
    "关税", "贸易", "顺差", "逆差", "外汇", "储备", "央行", "财政",
    "税收", "补贴", "刺激", "紧缩", "宽松", "衰退", "复苏", "周期",
]
WORDS_SPORTS = [
    "联赛", "杯赛", "冠军", "亚军", "季军", "积分", "排名", "淘汰赛",
    "小组赛", "半决赛", "决赛", "点球", "任意球", "角球", "越位", "犯规",
    "红牌", "黄牌", "助攻", "篮板", "三分", "罚球", "盖帽", "抢断",
    "扣篮", "发球", "接发", "扣杀", "拦网", "吊球", "快攻", "防守",
    "进攻", "战术", "阵型", "教练", "替补", "转会", "续约", "伤病",
    "体能", "训练", "热身", "主场", "客场", "观众", "转播", "赞助",
]
WORDS_LIFE = [
    "早餐", "午餐", "晚餐", "夜宵", "咖啡", "奶茶", "水果", "蔬菜",
    "烹饪", "烘焙", "调味", "食材", "营养", "热量", "蛋白", "碳水",
    "睡眠", "作息", "运动", "散步", "跑步", "瑜伽", "冥想", "减压",
    "旅行", "露营", "徒步", "摄影", "阅读", "电影", "音乐", "展览",
    "收纳", "清洁", "装修", "家具", "绿植", "宠物", "园艺", "手作",
    "通勤", "租房", "理财", "记账", "购物", "折扣", "快递", "邻里",
]

ALL_WORDS = WORDS_TECH + WORDS_FINANCE + WORDS_SPORTS + WORDS_LIFE


# ---------------------------------------------------------------------------
# Phase 0：生成 RSS 文件
# ---------------------------------------------------------------------------
def _make_title(rng: random.Random, i: int, j: int) -> str:
    """组合一个中文标题：3~6 个词，含重复词以保证 FTS 有命中。"""
    n = rng.randint(3, 6)
    words = [rng.choice(ALL_WORDS) for _ in range(n)]
    return "".join(words)


def _make_description(rng: random.Random) -> str:
    """组合 200~500 字中文正文，词库随机拼接（词之间用标点/空格分隔）。"""
    seps = ["，", "。", "、", "；", " ", "："]
    target = rng.randint(200, 500)
    buf: list[str] = []
    length = 0
    while length < target:
        w = rng.choice(ALL_WORDS)
        buf.append(w)
        length += len(w)
        buf.append(rng.choice(seps))
        length += 1
    text = "".join(buf)
    return text[:target]


def _rfc822(dt: datetime) -> str:
    """转 RFC822 时间字符串（RSS 2.0 pubDate）。"""
    # 使用英文星期/月缩写，避免依赖 locale。
    wd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][dt.weekday()]
    mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][dt.month - 1]
    return f"{wd}, {dt.day:02d} {mon} {dt.year:04d} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} +0000"


def _write_rss(path: Path, feed_index: int, item_count: int,
               rng: random.Random, base_dt: datetime,
               start_j: int = 0) -> None:
    """写一个 RSS 2.0 XML 文件，含 item_count 个 <item>。

    start_j 允许从某个偏移开始（Phase 3 追加新条目时用）。
    item 不含 <link>，避免 extract_text 走网络。
    """
    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>\n')
    parts.append('<rss version="2.0">\n<channel>\n')
    parts.append(f"<title>LoadTest Feed {feed_index}</title>\n")
    parts.append(f"<description>loadtest feed {feed_index}</description>\n")
    for k in range(item_count):
        j = start_j + k
        guid = f"feed-{feed_index}-item-{j}"
        title = _make_title(rng, feed_index, j)
        desc = _make_description(rng)
        # 近 30 天内随机时间
        offset_sec = rng.randint(0, 30 * 24 * 3600)
        pub = base_dt - timedelta(seconds=offset_sec)
        parts.append("<item>\n")
        parts.append(f"<guid isPermaLink=\"false\">{xml_escape(guid)}</guid>\n")
        parts.append(f"<title>{xml_escape(title)}</title>\n")
        parts.append(f"<description>{xml_escape(desc)}</description>\n")
        parts.append(f"<pubDate>{_rfc822(pub)}</pubDate>\n")
        parts.append("</item>\n")
    parts.append("</channel>\n</rss>\n")
    path.write_text("".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# 工具：百分位（只用标准库）
# ---------------------------------------------------------------------------
def _percentile(sorted_data: list[float], p: float) -> float:
    """从已排序列表取百分位（线性插值）。p 为 0~100。"""
    if not sorted_data:
        return float("nan")
    if len(sorted_data) == 1:
        return float(sorted_data[0])
    k = (len(sorted_data) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_data) - 1)
    frac = k - lo
    return float(sorted_data[lo] * (1 - frac) + sorted_data[hi] * frac)


def _stats(data: list[float]) -> dict:
    """计算一组耗时的统计量（单位：毫秒）。输入为秒。"""
    if not data:
        return {"n": 0, "p50": float("nan"), "p95": float("nan"),
                "mean": float("nan"), "min": float("nan"), "max": float("nan")}
    ms = sorted(x * 1000.0 for x in data)
    return {
        "n": len(ms),
        "p50": _percentile(ms, 50),
        "p95": _percentile(ms, 95),
        "mean": statistics.fmean(ms),
        "min": ms[0],
        "max": ms[-1],
    }


def _fmt_ms(x: float) -> str:
    if x != x:  # NaN
        return "未测"
    return f"{x:.2f}"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="FeedFlow 真实负载验证")
    parser.add_argument("--db", required=True, help="SQLite 数据库路径")
    parser.add_argument("--feeds", type=int, default=200, help="订阅数（默认 200）")
    parser.add_argument("--per-feed", type=int, default=500, help="每源文章数（默认 500）")
    parser.add_argument("--rss-dir", required=True, help="RSS 文件输出目录")
    parser.add_argument("--force", action="store_true", help="允许覆盖已存在的 db")
    args = parser.parse_args()

    rng = random.Random(20261016)
    db_path = args.db
    rss_dir = Path(args.rss_dir)
    n_feeds = args.feeds
    per_feed = args.per_feed

    # ---- Phase 0：生成 RSS ----
    print(f"[Phase 0] 生成 {n_feeds} 个 RSS 文件，每源 {per_feed} 条 ...", flush=True)
    rss_dir.mkdir(parents=True, exist_ok=True)
    base_dt = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
    rss_paths: list[Path] = []
    t0 = time.perf_counter()
    for i in range(n_feeds):
        p = rss_dir / f"feed_{i}.xml"
        _write_rss(p, i, per_feed, rng, base_dt, start_j=0)
        rss_paths.append(p)
    t_phase0 = time.perf_counter() - t0
    print(f"[Phase 0] 完成，耗时 {t_phase0:.2f}s", flush=True)

    # ---- Phase 1：建库 ----
    print("[Phase 1] 建库 ...", flush=True)
    db_file = Path(db_path)
    if db_file.exists() and not args.force:
        print(f"错误：db 文件已存在：{db_path}（加 --force 覆盖）", file=sys.stderr)
        return 2
    if db_file.exists() and args.force:
        db_file.unlink()
    ff_db.init_db(db_path)

    conn = ff_db.get_conn(db_path)
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        # 直接 SQL 插入 feeds（不使用 store.create_feed，避免潜在网络）。
        for i, p in enumerate(rss_paths):
            conn.execute(
                "INSERT INTO feeds (title, site_url, feed_url, description, "
                "interval_min, enabled, last_fetched_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"LoadTest Feed {i}", "", str(p), "", 60, 1, None, now_iso),
            )
        conn.commit()
        feed_rows = conn.execute(
            "SELECT id, feed_url FROM feeds ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    print(f"[Phase 1] 完成，插入 {len(feed_rows)} 个源", flush=True)

    # ---- Phase 2：bulk 种子 ----
    print(f"[Phase 2] bulk 种子 {n_feeds * per_feed} 篇 ...", flush=True)
    import feedparser  # 项目已依赖

    total_seed = 0
    simhash_total = 0.0
    t0 = time.perf_counter()
    conn = ff_db.get_conn(db_path)
    try:
        for (feed_id, feed_url), rss_path in zip(feed_rows, rss_paths):
            conn.execute("BEGIN")
            parsed = feedparser.parse(str(rss_path))
            rows = []
            for entry in parsed.entries:
                guid = entry.get("id") or entry.get("link") or ""
                title = entry.get("title") or ""
                summary = entry.get("summary") or entry.get("description") or ""
                # 无 link 时 content_text 直接用 description（与 fetcher 行为一致）
                content_text = summary
                published = entry.get("published") or None
                ts = time.perf_counter()
                text = ff_dedup.get_text_for({"title": title, "content_text": content_text})
                sh = ff_dedup.simhash(text)
                simhash_total += time.perf_counter() - ts
                rows.append((
                    feed_id, guid, title, "", "", summary, "", content_text,
                    published, now_iso, sh, None,
                ))
            conn.executemany(
                "INSERT INTO articles (feed_id, guid, title, author, link, "
                "summary, content_html, content_text, published_at, fetched_at, "
                "simhash, cluster_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.execute(
                "UPDATE articles SET cluster_id = id "
                "WHERE feed_id = ? AND cluster_id IS NULL",
                (feed_id,),
            )
            total_seed += len(rows)
            conn.commit()
            if feed_id % 50 == 0:
                print(f"[Phase 2] 进度 {total_seed} 篇 ...", flush=True)
    finally:
        conn.close()
    t_phase2 = time.perf_counter() - t0
    per_10k = t_phase2 / (total_seed / 10000.0) if total_seed else float("nan")
    sh_ratio = (simhash_total / t_phase2 * 100.0) if t_phase2 else float("nan")
    print(f"[Phase 2] 完成，{total_seed} 篇，总 {t_phase2:.2f}s，"
          f"每万篇 {per_10k:.2f}s，simhash 占比 {sh_ratio:.1f}%", flush=True)

    # ---- Phase 3：抓取基准 ----
    print("[Phase 3] 抓取基准 ...", flush=True)
    # 先探测单篇 insert_article 成本，决定追加条目数（自动降级）。
    probe_guid = f"probe-{int(time.time())}"
    probe_feed = feed_rows[0]
    t_probe0 = time.perf_counter()
    ff_store.insert_article(
        db_path, probe_feed["id"], probe_guid, "探测标题", "",
        "", "探测摘要", "", "探测正文", None,
    )
    probe_sec = time.perf_counter() - t_probe0
    if probe_sec > 2.0:
        append_per_feed, fetch_feeds = 3, 5
        degrade_note = (f"单篇 insert_article 探测 {probe_sec*1000:.1f}ms > 2000ms，"
                        f"抓取基准降级为 5 个源 × 3 篇（采样实测，如实报告）")
    elif probe_sec > 0.2:
        append_per_feed, fetch_feeds = 10, n_feeds
        degrade_note = f"单篇 insert_article 探测 {probe_sec*1000:.1f}ms > 200ms，追加条目降级为 10"
    else:
        append_per_feed, fetch_feeds = 20, n_feeds
        degrade_note = f"单篇 insert_article 探测 {probe_sec*1000:.1f}ms <= 200ms，追加条目为 20"
    print(f"[Phase 3] {degrade_note}", flush=True)

    # 清理探测文章
    conn = ff_db.get_conn(db_path)
    try:
        conn.execute("DELETE FROM articles WHERE guid = ?", (probe_guid,))
        conn.commit()
    finally:
        conn.close()

    # 重写 RSS：追加 append_per_feed 条新 guid
    for i, p in enumerate(rss_paths):
        _write_rss(p, i, per_feed + append_per_feed, rng, base_dt, start_j=0)
    # 全部置 NULL 使得到期
    conn = ff_db.get_conn(db_path)
    try:
        conn.execute("UPDATE feeds SET last_fetched_at = NULL")
        conn.commit()
        feed_dicts = [dict(r) for r in conn.execute(
            "SELECT * FROM feeds ORDER BY id"
        ).fetchall()]
    finally:
        conn.close()

    fetch_times: list[float] = []
    fetch_added = 0
    t0 = time.perf_counter()
    for fd in feed_dicts[:fetch_feeds]:
        ts = time.perf_counter()
        res = ff_fetcher.fetch_feed(
            db_path, fd, user_agent="loadtest",
            timeout=5, retries=0, extract_timeout=1,
        )
        fetch_times.append(time.perf_counter() - ts)
        fetch_added += int(res.get("added", 0))
    t_phase3_fetch = time.perf_counter() - t0
    fetch_stats = _stats(fetch_times)
    print(f"[Phase 3] fetch_feed 完成，新增 {fetch_added} 篇，"
          f"总 {t_phase3_fetch:.2f}s，p50={_fmt_ms(fetch_stats['p50'])}ms "
          f"p95={_fmt_ms(fetch_stats['p95'])}ms", flush=True)

    # 单篇实时插入（含 cluster 扫描真实成本）
    insert_times: list[float] = []
    n_realtime = 20
    for k in range(n_realtime):
        ts = time.perf_counter()
        ff_store.insert_article(
            db_path, feed_dicts[k % len(feed_dicts)]["id"],
            f"realtime-{k}-{int(time.time()*1000)}",
            f"实时标题{k}", "", "", f"实时摘要{k}", "", f"实时正文{k}",
            None,
        )
        insert_times.append(time.perf_counter() - ts)
    insert_stats = _stats(insert_times)
    print(f"[Phase 3] insert_article {n_realtime} 次，"
          f"p50={_fmt_ms(insert_stats['p50'])}ms "
          f"p95={_fmt_ms(insert_stats['p95'])}ms", flush=True)

    # ---- Phase 4：搜索基准 ----
    print("[Phase 4] 搜索基准 ...", flush=True)
    common_2 = "科技"
    common_4 = "芯片算力"
    rare_4 = "玛瑙翡翠"  # 词库中不存在
    phrase_8 = "芯片算力大模型开源"

    def _search_bench(queries: list[str]) -> tuple[list[float], int, int]:
        times: list[float] = []
        hit_total = 0
        for q in queries:
            ts = time.perf_counter()
            rows = ff_store.search_articles(db_path, q, limit=50)
            times.append(time.perf_counter() - ts)
            hit_total += len(rows)
        return times, hit_total, len(queries)

    t2, hit2, n2 = _search_bench([common_2] * 50)
    t4c, hit4c, n4c = _search_bench([common_4] * 50)
    t4r, hit4r, n4r = _search_bench([rare_4] * 50)
    t8, hit8, n8 = _search_bench([phrase_8] * 50)
    all_search = t2 + t4c + t4r + t8
    search_all_stats = _stats(all_search)
    print(f"[Phase 4] 完成，总 {len(all_search)} 次，"
          f"p50={_fmt_ms(search_all_stats['p50'])}ms "
          f"p95={_fmt_ms(search_all_stats['p95'])}ms", flush=True)

    # ---- Phase 5：阅读基准 ----
    print("[Phase 5] 阅读基准 ...", flush=True)
    conn = ff_db.get_conn(db_path)
    try:
        total_articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    finally:
        conn.close()

    list_times: list[float] = []
    max_offset = max(0, total_articles - 50)
    for _ in range(200):
        off = rng.randint(0, max_offset) if max_offset > 0 else 0
        ts = time.perf_counter()
        ff_store.list_articles(db_path, scope="all", limit=50, offset=off)
        list_times.append(time.perf_counter() - ts)
    list_stats = _stats(list_times)

    # Flask 主页渲染
    os.environ["FEEDFLOW_NO_SCHEDULER"] = "1"
    from feedflow import create_app  # noqa: E402
    application = create_app({
        "db_path": db_path, "host": "127.0.0.1", "port": 8300,
        "fetch_interval": 30, "user_agent": "FeedFlow-test",
    })
    client = application.test_client()
    index_times: list[float] = []
    for _ in range(20):
        ts = time.perf_counter()
        resp = client.get("/")
        index_times.append(time.perf_counter() - ts)
        if resp.status_code != 200:
            print(f"[Phase 5] 警告：主页返回 {resp.status_code}", flush=True)
    index_stats = _stats(index_times)

    # due_feeds 计时 1 次
    ts = time.perf_counter()
    ff_store.due_feeds(db_path, datetime.now(timezone.utc).isoformat(), 60)
    due_sec = time.perf_counter() - ts

    # stats 计时 5 次取均值
    stats_times: list[float] = []
    for _ in range(5):
        ts = time.perf_counter()
        ff_store.stats(db_path)
        stats_times.append(time.perf_counter() - ts)
    stats_mean_ms = statistics.fmean(stats_times) * 1000.0

    print(f"[Phase 5] list_articles p50={_fmt_ms(list_stats['p50'])}ms "
          f"p95={_fmt_ms(list_stats['p95'])}ms；主页 p50={_fmt_ms(index_stats['p50'])}ms "
          f"p95={_fmt_ms(index_stats['p95'])}ms", flush=True)

    # ---- Phase 6：去重诊断 ----
    print("[Phase 6] 去重诊断 ...", flush=True)
    cluster_times: list[float] = []
    for _ in range(10):
        txt = _make_description(rng) + _make_title(rng, 0, 0)
        sh = ff_dedup.simhash(txt)
        ts = time.perf_counter()
        ff_dedup.find_or_create_cluster(db_path, sh, txt)
        cluster_times.append(time.perf_counter() - ts)
    cluster_stats = _stats(cluster_times)
    print(f"[Phase 6] find_or_create_cluster {len(cluster_times)} 次，"
          f"p50={_fmt_ms(cluster_stats['p50'])}ms "
          f"p95={_fmt_ms(cluster_stats['p95'])}ms", flush=True)

    # ---- 报告 ----
    print("[报告] 写入 docs/LOADTEST_2026-10-16.md ...", flush=True)
    docs_dir = _PROJECT_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    report_path = docs_dir / "LOADTEST_2026-10-16.md"

    # 机器信息
    sqlite_ver = sqlite3.sqlite_version
    py_ver = sys.version.split()[0]
    cpu_count = os.cpu_count()
    mem_info = "未测"
    try:
        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names and "SC_PHYS_PAGES" in os.sysconf_names:
            page = os.sysconf("SC_PAGE_SIZE")
            pages = os.sysconf("SC_PHYS_PAGES")
            mem_info = f"{page * pages / (1024**3):.2f} GiB"
    except (ValueError, OSError):
        mem_info = "未测"

    def _row(name: str, st: dict, extra: str = "") -> str:
        return (f"| {name} | {st['n']} | {_fmt_ms(st['p50'])} | "
                f"{_fmt_ms(st['p95'])} | {_fmt_ms(st['mean'])} | {extra} |")

    lines: list[str] = []
    lines.append("# FeedFlow 真实负载验证报告（2026-10-16）\n")
    lines.append("")
    lines.append("## 测试方法\n")
    lines.append("")
    lines.append(f"- 数据规模：{n_feeds} 订阅 × {per_feed} 文章 = "
                 f"{n_feeds * per_feed} 篇（Phase 2 种子）")
    lines.append("- 零网络：RSS 条目不含 `<link>`，`extract_text` 无 link 时直接使用 description；"
                 "`feed_url` 全部指向本地 RSS 文件路径，`fetch_feed` 对本地路径直接 feedparser 解析。")
    lines.append("- feeds 表通过 `db.get_conn` 直接 SQL 插入（不调用 `store.create_feed`，"
                 "避免其内部可能走网络）。")
    lines.append("- 抓取基准调用 `fetch_feed(..., timeout=5, retries=0, extract_timeout=1)`，"
                 "避免任何网络等待。")
    lines.append("")
    lines.append("### 诚实边界（必读）\n")
    lines.append("")
    lines.append("- **Phase 2 种子走 bulk 路径**（`executemany` 批量 INSERT + 批量 "
                 "`UPDATE ... cluster_id = id`），等价于真实批量导入/回填场景，"
                 "**不等价于单篇实时插入**。单篇实时插入成本（含 cluster 扫描）"
                 "在 Phase 3 单独实测。")
    lines.append(f"- 追加条目数自动降级判定：{degrade_note}。")
    lines.append(f"- Phase 2 simhash 计算为实测：累计 {simhash_total:.2f}s，"
                 f"占总种子耗时 {sh_ratio:.1f}%。")
    lines.append("")
    lines.append("## 机器信息\n")
    lines.append("")
    lines.append(f"- CPU 逻辑核数（`os.cpu_count()`）：{cpu_count}")
    lines.append(f"- 内存：{mem_info}")
    lines.append(f"- SQLite 版本：{sqlite_ver}")
    lines.append(f"- Python 版本：{py_ver}")
    lines.append("")
    lines.append("## 各 Phase 实测\n")
    lines.append("")
    lines.append("### Phase 2：bulk 种子\n")
    lines.append("")
    lines.append(f"- 总篇数：{total_seed}")
    lines.append(f"- 总耗时：{t_phase2:.2f}s")
    lines.append(f"- 每万篇耗时：{per_10k:.2f}s")
    lines.append(f"- simhash 计算累计耗时：{simhash_total:.2f}s（占比 {sh_ratio:.1f}%）")
    lines.append("")
    lines.append("### Phase 3：抓取基准\n")
    lines.append("")
    lines.append("| 指标 | 样本数 | p50(ms) | p95(ms) | 均值(ms) | 备注 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    lines.append(_row("fetch_feed（每源）", fetch_stats,
                      f"总新增 {fetch_added} 篇，总耗时 {t_phase3_fetch:.2f}s"))
    lines.append(_row("insert_article（单篇实时）", insert_stats,
                      "含 dedup.find_or_create_cluster 扫描成本"))
    lines.append("")
    lines.append("### Phase 4：搜索基准\n")
    lines.append("")
    lines.append("| 路径 | 样本数 | p50(ms) | p95(ms) | 均值(ms) | 平均返回篇数 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    lines.append(_row("2 字常见词（LIKE 退化）", _stats(t2),
                      f"{hit2 / n2:.1f}" if n2 else "未测"))
    lines.append(_row("4 字常见词（FTS）", _stats(t4c),
                      f"{hit4c / n4c:.1f}" if n4c else "未测"))
    lines.append(_row("4 字罕见词（FTS 低命中）", _stats(t4r),
                      f"{hit4r / n4r:.1f}" if n4r else "未测"))
    lines.append(_row("8 字短语（FTS）", _stats(t8),
                      f"{hit8 / n8:.1f}" if n8 else "未测"))
    lines.append(_row("总体", search_all_stats, ""))
    lines.append("")
    lines.append("### Phase 5：阅读基准\n")
    lines.append("")
    lines.append("| 指标 | 样本数 | p50(ms) | p95(ms) | 均值(ms) | 备注 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    lines.append(_row("list_articles(scope=all, limit=50, 随机 offset)", list_stats,
                      f"总文章数 {total_articles}"))
    lines.append(_row("Flask GET /（主页服务端渲染）", index_stats, ""))
    lines.append(f"| due_feeds | 1 | 未测 | 未测 | {due_sec * 1000:.2f} | 单次调用 |")
    lines.append(f"| stats | 5 | 未测 | 未测 | {stats_mean_ms:.2f} | 5 次均值 |")
    lines.append("")
    lines.append("### Phase 6：去重诊断\n")
    lines.append("")
    lines.append("| 指标 | 样本数 | p50(ms) | p95(ms) | 均值(ms) | 备注 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    lines.append(_row("find_or_create_cluster（随机文本）", cluster_stats,
                      "10 万规模下近 14 天全量扫描成本"))
    lines.append("")

    # Top 3 瓶颈：按"单次耗时 × 调用频率"综合，只写实测支持的结论。
    lines.append("## Top 3 瓶颈排名（按单次耗时 × 调用频率综合）\n")
    lines.append("")
    bottlenecks: list[tuple[float, str]] = []
    # fetch_feed 每轮全量调用
    bottlenecks.append((fetch_stats["p50"] * len(fetch_times),
                        f"fetch_feed：本批实测 {len(fetch_times)} 个源，"
                        f"p50={_fmt_ms(fetch_stats['p50'])}ms"))
    # insert_article 每新文章一次
    bottlenecks.append((insert_stats["p50"] * fetch_added,
                        f"insert_article：本批新增 {fetch_added} 篇各一次，"
                        f"p50={_fmt_ms(insert_stats['p50'])}ms"))
    # list_articles 前端每次翻页一次
    bottlenecks.append((list_stats["p50"] * 200,
                        f"list_articles：本批 {list_stats['n']} 次，"
                        f"p50={_fmt_ms(list_stats['p50'])}ms"))
    # 搜索总体
    bottlenecks.append((search_all_stats["p50"] * len(all_search),
                        f"search_articles：本批 {len(all_search)} 次，"
                        f"p50={_fmt_ms(search_all_stats['p50'])}ms"))
    # 去重扫描
    bottlenecks.append((cluster_stats["p50"] * 10,
                        f"find_or_create_cluster：本批 {cluster_stats['n']} 次，"
                        f"p50={_fmt_ms(cluster_stats['p50'])}ms"))
    bottlenecks.sort(reverse=True, key=lambda x: x[0])
    for rank, (score, desc) in enumerate(bottlenecks[:3], start=1):
        lines.append(f"{rank}. {desc}（综合指标 {score:.1f} ms·次）")
    lines.append("")
    lines.append("> 注：以上排名仅基于本批实测调用次数与 p50 的乘积，"
                 "不代表生产环境的真实调用频率。")
    lines.append("")

    # 未测项
    lines.append("## 未测项清单\n")
    lines.append("")
    lines.append("- 网络抓取（远程 HTTP）耗时：本批零网络，`fetch_feed` 仅解析本地 RSS。")
    lines.append("- `extract_text` 走 `trafilatura.fetch_url` 抓正文的网络路径：本批无 link。")
    lines.append("- `due_feeds` / `stats` 的 p50/p95：本批仅单次/均值计时，样本不足。")
    lines.append("- 多用户并发 / 多线程压力：本批为单进程串行。")
    lines.append("- 磁盘 I/O 饱和、SQLite WAL 模式差异、冷缓存首访：本批未隔离测量。")
    lines.append("- 生产规模下的真实调用频率分布：本批频率为脚本构造。")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[报告] 已写入 {report_path}", flush=True)

    # 收尾
    gc.collect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
