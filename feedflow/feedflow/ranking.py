"""文章重要性排序模块。

公式概览（每分项均归一到 0~1）：
    recency = 0.5 ** (age_hours / RECENCY_HALFLIFE_HOURS)
    heat    = min(1.0, log2(max(1, cluster_size)) / 3.0)
    source  = min(1.0, feed_weight * learned / SOURCE_NORM)
    keyword = min(hits, KEYWORD_HIT_CAP) / KEYWORD_HIT_CAP
    unread  = 1.0 未读 / 0.0 已读
    score   = Σ WEIGHTS[k] * part[k]   (保留 4 位)
确定性：无随机，输入相同输出相同；可解释：返回 parts 与 reasons。
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from . import db
from .cluster_scoring import cluster_importance_score

RECENCY_HALFLIFE_HOURS = 48
WEIGHTS = {
    "recency": 0.30,
    "heat": 0.25,
    "source": 0.20,
    "keyword": 0.15,
    "unread": 0.10,
}
KEYWORD_TITLE_BOOST = 2.0
KEYWORD_HIT_CAP = 4.0
SOURCE_NORM = 2.5
FEED_WEIGHT_MIN = 0.1
FEED_WEIGHT_MAX = 5.0
LEARNED_MIN = 0.5
LEARNED_MAX = 2.0


def get_keywords(db_path) -> list[dict]:
    """全部关键词，按 id 升序。"""
    rows = db.query_all(
        db_path,
        "SELECT id, keyword, weight FROM keywords ORDER BY id ASC",
    )
    return [{"id": r["id"], "keyword": r["keyword"], "weight": r["weight"]} for r in rows]


def add_keyword(db_path, keyword: str) -> int:
    """新增关键词；空串抛 ValueError；大小写不敏感去重，返回 id。"""
    text = (keyword or "").strip()
    if not text:
        raise ValueError("keyword 不能为空")
    row = db.query_one(
        db_path,
        "SELECT id FROM keywords WHERE LOWER(keyword) = LOWER(?)",
        (text,),
    )
    if row is not None:
        return int(row["id"])
    now = db.utcnow()
    with db.write_lock:
        conn = db.get_conn(db_path)
        cur = conn.execute(
            "INSERT INTO keywords (keyword, weight, created_at) VALUES (?, 1.0, ?)",
            (text, now),
        )
        conn.commit()
        return int(cur.lastrowid)


def delete_keyword(db_path, kid: int) -> bool:
    """删除关键词，不存在返回 False。"""
    row = db.query_one(db_path, "SELECT id FROM keywords WHERE id = ?", (int(kid),))
    if row is None:
        return False
    db.execute_write(db_path, "DELETE FROM keywords WHERE id = ?", (int(kid),))
    return True


def get_feed_weights(db_path) -> list[dict]:
    """每个 feed 的手动权重与学习权重，LEFT JOIN feeds 取 title。"""
    rows = db.query_all(
        db_path,
        """
        SELECT f.id AS feed_id, f.title AS title,
               COALESCE(fw.weight, 1.0) AS weight,
               COALESCE(fw.learned, 1.0) AS learned
        FROM feeds f
        LEFT JOIN feed_weights fw ON fw.feed_id = f.id
        ORDER BY f.position ASC, f.id ASC
        """,
    )
    return [
        {
            "feed_id": int(r["feed_id"]),
            "title": r["title"],
            "weight": float(r["weight"]),
            "learned": float(r["learned"]),
        }
        for r in rows
    ]


def set_feed_weight(db_path, feed_id: int, weight) -> None:
    """设置手动权重；feed 不存在或 weight 非法抛 ValueError；保留 learned。"""
    row = db.query_one(db_path, "SELECT id FROM feeds WHERE id = ?", (int(feed_id),))
    if row is None:
        raise ValueError(f"feed 不存在: {feed_id}")
    try:
        w = float(weight)
    except (TypeError, ValueError):
        raise ValueError(f"weight 非法: {weight!r}") from None
    if w < FEED_WEIGHT_MIN or w > FEED_WEIGHT_MAX:
        raise ValueError(f"weight 超出范围 [{FEED_WEIGHT_MIN}, {FEED_WEIGHT_MAX}]: {w}")
    now = db.utcnow()
    db.execute_write(
        db_path,
        """
        INSERT INTO feed_weights (feed_id, weight, learned, updated_at)
        VALUES (?, ?, 1.0, ?)
        ON CONFLICT(feed_id) DO UPDATE SET
            weight = excluded.weight,
            updated_at = excluded.updated_at
        """,
        (int(feed_id), w, now),
    )


def get_setting(db_path, key: str, default: str = "") -> str:
    """读取 settings，缺失返回 default。"""
    row = db.query_one(db_path, "SELECT value FROM settings WHERE key = ?", (key,))
    if row is None:
        return default
    return row["value"]


def set_setting(db_path, key: str, value) -> None:
    """写入 settings（upsert），value 转字符串。"""
    now = db.utcnow()
    db.execute_write(
        db_path,
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, str(value), now),
    )


def get_digest_n(db_path, default: int = 20) -> int:
    """读取 digest_n；非法或缺失返回 default。"""
    raw = get_setting(db_path, "digest_n", "")
    if raw is None:
        return default
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    if n <= 0:
        return default
    return n


def learn_source_weights(db_path) -> None:
    """按源统计行为，更新 learned；无文章源为 1.0。确定性。"""
    rows = db.query_all(
        db_path,
        """
        SELECT feed_id,
               COUNT(*) AS n,
               SUM(CASE WHEN is_read = 1 THEN 1 ELSE 0 END) AS r,
               SUM(CASE WHEN is_starred = 1 THEN 1 ELSE 0 END) AS s
        FROM articles
        WHERE feed_id IS NOT NULL
        GROUP BY feed_id
        """,
    )
    now = db.utcnow()
    for row in rows:
        n = int(row["n"] or 0)
        if n == 0:
            learned = 1.0
        else:
            r = int(row["r"] or 0)
            s = int(row["s"] or 0)
            read_rate = r / n
            star_rate = s / n
            val = 1.0 + 1.0 * star_rate + 0.3 * read_rate
            learned = round(min(LEARNED_MAX, max(LEARNED_MIN, val)), 3)
        db.execute_write(
            db_path,
            """
            INSERT INTO feed_weights (feed_id, weight, learned, updated_at)
            VALUES (?, 1.0, ?, ?)
            ON CONFLICT(feed_id) DO UPDATE SET
                learned = excluded.learned,
                updated_at = excluded.updated_at
            """,
            (int(row["feed_id"]), learned, now),
        )


def _parse_iso(value) -> datetime | None:
    """解析 ISO8601，失败返回 None；naive 视为 UTC。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _age_hours(published_at, fetched_at, now: datetime) -> float:
    """距 now 的小时数；优先 published_at，其次 fetched_at，最后 now。"""
    t = _parse_iso(published_at) or _parse_iso(fetched_at)
    if t is None:
        return 0.0
    delta = (now - t).total_seconds() / 3600.0
    return max(0.0, delta)


def _format_age(age_hours: float) -> str:
    """大白话时长。"""
    if age_hours < 1.0:
        minutes = int(age_hours * 60)
        return "刚刚" if minutes <= 0 else f"{minutes} 分钟前"
    if age_hours < 48.0:
        return f"{int(age_hours)} 小时前"
    return f"{int(age_hours / 24)} 天前"


def score_article(
    article: dict,
    *,
    now: datetime,
    cluster_size: int,
    feed_weight: float,
    learned: float,
    keywords: list,
) -> dict:
    """计算单篇分数与解释，见模块 docstring 公式。"""
    age_hours = _age_hours(article.get("published_at"), article.get("fetched_at"), now)

    recency = 0.5 ** (age_hours / RECENCY_HALFLIFE_HOURS)

    size = max(1, int(cluster_size))
    heat = min(1.0, math.log2(size) / 3.0)

    eff = float(feed_weight) * float(learned)
    source = min(1.0, eff / SOURCE_NORM)

    hits = 0.0
    matched: list[str] = []
    title = (article.get("title") or "").casefold()
    body_src = article.get("content_text") or article.get("summary") or ""
    body = body_src.casefold()
    for kw in keywords:
        t = kw.get("keyword") or ""
        if not t:
            continue
        try:
            w = float(kw.get("weight", 1.0))
        except (TypeError, ValueError):
            w = 1.0
        needle = t.casefold()
        if not needle:
            continue
        hit_title = needle in title
        hit_body = needle in body
        if hit_title:
            hits += w * KEYWORD_TITLE_BOOST
            matched.append(t)
        elif hit_body:
            hits += w
            matched.append(t)
        else:
            continue
    hits = min(hits, KEYWORD_HIT_CAP)
    keyword = hits / KEYWORD_HIT_CAP

    unread = 1.0 if int(article.get("is_read") or 0) == 0 else 0.0

    parts = {
        "recency": recency,
        "heat": heat,
        "source": source,
        "keyword": keyword,
        "unread": unread,
    }
    score = round(sum(WEIGHTS[k] * v for k, v in parts.items()), 4)

    reasons: list[str] = []
    if recency >= 0.5:
        reasons.append(f"{_format_age(age_hours)}发布")
    if size >= 2:
        reasons.append(f"同事件 {size} 篇在跟")
    if eff >= 1.5:
        reasons.append("这个源你常看")
    elif eff <= 0.7:
        reasons.append("这个源平时看得少")
    if matched:
        reasons.append("命中关键词「" + "」「".join(matched[:2]) + "」")

    return {
        "score": score,
        "parts": {k: round(v, 4) for k, v in parts.items()},
        "reasons": reasons,
        "cluster_size": size,
        "age_hours": round(age_hours, 1),
    }


def rank_articles(db_path, articles: list[dict], now=None) -> list[dict]:
    """对文章排序：先刷新 learned，再按分数降序返回。"""
    if now is None:
        now = datetime.now(UTC)

    learn_source_weights(db_path)

    cluster_rows = db.query_all(
        db_path,
        """
        SELECT cluster_id, COUNT(*) AS c
        FROM articles
        WHERE cluster_id IS NOT NULL
        GROUP BY cluster_id
        """,
    )
    cluster_sizes = {int(r["cluster_id"]): int(r["c"]) for r in cluster_rows}

    fw_rows = db.query_all(
        db_path,
        "SELECT feed_id, weight, learned FROM feed_weights",
    )
    feed_map: dict[int, tuple[float, float]] = {}
    for r in fw_rows:
        feed_map[int(r["feed_id"])] = (float(r["weight"]), float(r["learned"]))

    keywords = get_keywords(db_path)

    scored: list[tuple[float, str, int, dict]] = []
    for art in articles:
        fid = art.get("feed_id")
        fw, learned = feed_map.get(int(fid), (1.0, 1.0)) if fid is not None else (1.0, 1.0)
        cid = art.get("cluster_id")
        size = cluster_sizes.get(int(cid), 1) if cid is not None else 1

        info = score_article(
            art,
            now=now,
            cluster_size=size,
            feed_weight=fw,
            learned=learned,
            keywords=keywords,
        )
        out = dict(art)
        out["score_info"] = info

        pub = art.get("published_at")
        pub_key = "" if pub is None else str(pub)
        try:
            aid = int(art.get("id") or 0)
        except (TypeError, ValueError):
            aid = 0
        scored.append((info["score"], pub_key, aid, out))

    # score 降序；published_at 降序（NULL 排后）；id 降序
    scored.sort(
        key=lambda x: (
            -x[0],
            0 if x[1] else 1,
            _neg_str_key(x[1]),
            -x[2],
        )
    )
    return [item[3] for item in scored]


def _neg_str_key(s: str):
    """字符串降序的稳定替代：用逐字符取反码实现降序排序键。"""
    if not s:
        return ()
    return tuple(-ord(c) for c in s)


def get_digest(db_path, n: int = 20, now=None) -> list[dict]:
    """未读文章排序后取前 n 篇。"""
    if n is None:
        n = 20
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 20
    if n <= 0:
        return []

    rows = db.query_all(
        db_path,
        """
        SELECT a.*, f.title AS feed_title
        FROM articles a
        JOIN feeds f ON f.id = a.feed_id
        WHERE a.is_read = 0
        """,
    )
    articles = [dict(r) for r in rows]
    ranked = rank_articles(db_path, articles, now=now)
    return ranked[:n]


def get_digest_clusters(db_path, n: int = 10, now=None) -> list[dict]:
    """聚类 Top N 视图：未读文章按 cluster_id 分组，返回每组摘要。

    返回 list[dict]，按 cluster_score 降序取前 n。每个 dict 形状：
        {
            "cluster_id": int,              # solo 组用文章 id
            "topic": str,                   # 代表文章标题
            "members": int,                 # 簇内文章总数（含已读）
            "sources": int,                 # 簇内不同 feed_id 数
            "source_titles": list[str],     # 最多 5 个来源标题，按首次出现顺序
            "unread": int,                  # 簇内未读数
            "representative": dict,         # 代表文章行 dict（含 score_info）
            "cluster_score": float,         # 代表文章分数
            "cluster_reasons": list[str],   # 代表 reasons；多篇时补"同事件"
            "latest_at": str,               # 成员最大 COALESCE(published_at, fetched_at)
        }
    n 非法（<=0 或非数字）时返回 []。
    """
    if n is None:
        return []
    try:
        n_int = int(n)
    except (TypeError, ValueError):
        return []
    if n_int <= 0:
        return []

    rows = db.query_all(
        db_path,
        """
        SELECT a.*, f.title AS feed_title
        FROM articles a
        JOIN feeds f ON f.id = a.feed_id
        WHERE a.is_read = 0
        """,
    )
    unread_articles = [dict(r) for r in rows]
    ranked = rank_articles(db_path, unread_articles, now=now)

    groups: dict[object, list[dict]] = {}
    for art in ranked:
        cid = art.get("cluster_id")
        if cid is None:
            try:
                aid = int(art.get("id") or 0)
            except (TypeError, ValueError):
                aid = 0
            key: object = ("solo", aid)
        else:
            try:
                key = int(cid)
            except (TypeError, ValueError):
                key = ("solo", int(art.get("id") or 0))
        groups.setdefault(key, []).append(art)

    out: list[dict] = []
    for key, members in groups.items():
        rep = members[0]
        rep_info = rep.get("score_info") or {}
        rep_score = float(rep_info.get("score", 0.0))

        if isinstance(key, tuple) and key and key[0] == "solo":
            solo_id = int(key[1])
            cluster_id_val = solo_id
            meta = db.query_one(
                db_path,
                """
                SELECT COUNT(*) AS members,
                       COUNT(DISTINCT feed_id) AS sources,
                       SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) AS unread,
                       MAX(COALESCE(published_at, fetched_at)) AS latest_at
                FROM articles
                WHERE id = ?
                """,
                (solo_id,),
            )
            title_rows = db.query_all(
                db_path,
                """
                SELECT f.title AS title
                FROM articles a
                JOIN feeds f ON f.id = a.feed_id
                WHERE a.id = ?
                ORDER BY a.id ASC
                """,
                (solo_id,),
            )
        else:
            cluster_id_val = int(key)
            meta = db.query_one(
                db_path,
                """
                SELECT COUNT(*) AS members,
                       COUNT(DISTINCT feed_id) AS sources,
                       SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) AS unread,
                       MAX(COALESCE(published_at, fetched_at)) AS latest_at
                FROM articles
                WHERE cluster_id = ?
                """,
                (cluster_id_val,),
            )
            title_rows = db.query_all(
                db_path,
                """
                SELECT f.title AS title
                FROM articles a
                JOIN feeds f ON f.id = a.feed_id
                WHERE a.cluster_id = ?
                ORDER BY a.id ASC
                """,
                (cluster_id_val,),
            )

        members_count = int((meta or {}).get("members") or 0)
        sources_count = int((meta or {}).get("sources") or 0)
        unread_count = int((meta or {}).get("unread") or 0)
        latest_at_raw = (meta or {}).get("latest_at")
        latest_at_str = "" if latest_at_raw is None else str(latest_at_raw)

        seen_titles: list[str] = []
        for r in title_rows:
            t = r["title"]
            if t is None:
                continue
            if t not in seen_titles:
                seen_titles.append(t)
            if len(seen_titles) >= 5:
                break

        reasons_src = rep_info.get("reasons") or []
        cluster_reasons = list(reasons_src)
        if members_count >= 2 and not any("同事件" in str(x) for x in cluster_reasons):
            cluster_reasons.append(f"同事件 {members_count} 篇在跟")

        out.append(
            {
                "cluster_id": cluster_id_val,
                "topic": rep.get("title") or "",
                "members": members_count,
                "sources": sources_count,
                "source_titles": seen_titles,
                "unread": unread_count,
                "representative": rep,
                "cluster_score": cluster_importance_score(
                    rep_score, members_count, sources_count, unread_count, latest_at_str
                ),
                "cluster_reasons": cluster_reasons,
                "latest_at": latest_at_str,
            }
        )

    out.sort(key=lambda d: (-d["cluster_score"], -d["cluster_id"]))
    return out[:n_int]

