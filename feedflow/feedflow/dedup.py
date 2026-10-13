"""SimHash 近似去重：64 位指纹 + 汉明距离聚类（纯标准库实现）。

设计要点：
- tokenize：中英文兼容。连续 CJK 字符按字二元组切分（单字也保留），英文数字按 [a-z0-9]+ 切词。
- simhash：对每个特征做 blake2b(64bit) 取整，按权重在 64 维向量上累加，最终按位生成 16 位十六进制。
- 聚类：在近 14 天、simhash 非空的文章里找汉明距离 <= threshold 的最近文章，复用其 cluster_id。
"""
import hashlib
import re
import unicodedata
from datetime import UTC, datetime, timedelta

from .db import get_conn, write_lock
from .logging import get_logger

log = get_logger(__name__)

# 近 14 天窗口（聚类只在这个范围内比较，兼顾性能与准确度）
CLUSTER_WINDOW_DAYS = 14
# 默认汉明距离阈值
DEFAULT_THRESHOLD = 3

# 英文/数字词：小写字母 + 数字
_ASCII_WORD_RE = re.compile(r"[a-z0-9]+")


def _is_cjk(ch: str) -> bool:
    """判断字符是否为 CJK 表意文字（覆盖常用与扩展 A 区）。"""
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF  # CJK 统一表意文字
        or 0x3400 <= code <= 0x4DBF  # 扩展 A
        or 0xF900 <= code <= 0xFAFF  # 兼容表意文字
    )


def tokenize(text):
    """中英文兼容分词，返回词列表。

    - 连续 CJK 字符按字二元组切分（长度 1 时保留单字）。
    - 英文数字按 [a-z0-9]+ 切词并小写。
    """
    if not text:
        return []
    # 统一做一次 NFKC 归一化，兼容全角/半角
    text = unicodedata.normalize("NFKC", text).lower()
    tokens = []
    cjk_run = []

    def flush_cjk():
        """把当前累积的 CJK 连续串按二元组切分输出。"""
        if not cjk_run:
            return
        if len(cjk_run) == 1:
            tokens.append(cjk_run[0])
        else:
            for i in range(len(cjk_run) - 1):
                tokens.append(cjk_run[i] + cjk_run[i + 1])
        cjk_run.clear()

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if _is_cjk(ch):
            cjk_run.append(ch)
            i += 1
            continue
        # 非 CJK：先把已累积的 CJK 串输出
        flush_cjk()
        # 尝试匹配英文数字词
        m = _ASCII_WORD_RE.match(text, i)
        if m:
            tokens.append(m.group(0))
            i = m.end()
        else:
            i += 1
    flush_cjk()
    return tokens


def _hash64(word):
    """用 blake2b 生成 64 位整数特征哈希。"""
    digest = hashlib.blake2b(word.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def simhash_features(features):
    """按 (词, 权重) 列表计算 64 位 SimHash，返回 16 位十六进制字符串。"""
    vector = [0] * 64
    for word, weight in features:
        if not word:
            continue
        h = _hash64(word)
        w = weight if weight else 1
        for bit in range(64):
            if (h >> bit) & 1:
                vector[bit] += w
            else:
                vector[bit] -= w
    fingerprint = 0
    for bit in range(64):
        if vector[bit] > 0:
            fingerprint |= 1 << bit
    return format(fingerprint, "016x")


def simhash(text):
    """对文本计算 SimHash，返回 16 位十六进制字符串。"""
    tokens = tokenize(text)
    features = [(tok, 1) for tok in tokens]
    return simhash_features(features)


def hamming(a_hex, b_hex):
    """计算两个十六进制 SimHash 的汉明距离。输入非法或长度不符时返回一个大值。"""
    if not a_hex or not b_hex:
        return 64
    try:
        a = int(a_hex, 16)
        b = int(b_hex, 16)
    except (ValueError, TypeError):
        return 64
    return (a ^ b).bit_count()


def is_near_dup(a_hex, b_hex, threshold=DEFAULT_THRESHOLD):
    """判断两个 SimHash 是否近似重复。"""
    return hamming(a_hex, b_hex) <= threshold


def get_text_for(article_dict):
    """返回用于计算 SimHash 的文本：标题加权（标题拼接两次）+ 正文。"""
    if not article_dict:
        return ""
    title = article_dict.get("title") or ""
    content = article_dict.get("content_text") or ""
    return (title + " ") * 2 + content


def _window_iso():
    """返回 14 天前的时间 ISO 字符串，用于过滤近期文章。"""
    since = datetime.now(UTC) - timedelta(days=CLUSTER_WINDOW_DAYS)
    return since.isoformat()


# 粗筛汉明距离上限（宽网，召回候选后再用 Jaccard 精排确认）
PREFILTER_HAMMING = 20
# Jaccard 相似度确认阈值
JACCARD_THRESHOLD = 0.35


def jaccard_similarity(text_a, text_b):
    """基于分词集合的 Jaccard 相似度，用于近似去重的二次确认。"""
    set_a = set(tokenize(text_a))
    set_b = set(tokenize(text_b))
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def find_or_create_cluster(db_path, simhash_hex, text="", threshold=DEFAULT_THRESHOLD):
    """两阶段近似去重，命中返回已有的 cluster_id，未命中返回 None。

    阶段一（粗筛）：用 SimHash 汉明距离 <= PREFILTER_HAMMING 召回候选，
    SimHash 在此充当快速索引，避免全量比对。
    阶段二（确认）：对候选按 Jaccard 分词相似度 >= JACCARD_THRESHOLD 确认。
    这样短文本的微小改动（如差几个字）也能被正确聚类，
    而纯汉明阈值 3 对短文本过于严格，会漏掉真实的近似重复。
    """
    if not simhash_hex:
        return None
    since = _window_iso()
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, simhash, cluster_id, title, content_text
              FROM articles
             WHERE simhash IS NOT NULL
               AND simhash != ''
               AND cluster_id IS NOT NULL
               AND (COALESCE(published_at, fetched_at) >= ?)
             ORDER BY id DESC
            """,
            (since,),
        ).fetchall()
    finally:
        conn.close()

    query_tokens = set(tokenize(text)) if text else set()
    best_cluster = None
    best_score = -1.0
    for r in rows:
        if hamming(simhash_hex, r["simhash"]) > PREFILTER_HAMMING:
            continue
        cand_text = get_text_for({"title": r["title"], "content_text": r["content_text"]})
        score = jaccard_similarity(text, cand_text) if query_tokens else 0.0
        if score >= JACCARD_THRESHOLD and score > best_score:
            best_score = score
            best_cluster = r["cluster_id"]
    # 兼容旧语义：文本为空时退化为纯汉明判定（threshold 参数保留）
    if not query_tokens:
        for r in rows:
            if hamming(simhash_hex, r["simhash"]) <= threshold:
                return r["cluster_id"]
        return None
    return best_cluster


def backfill_clusters(db_path):
    """给 simhash 为空的文章补算 simhash，并聚类。幂等。

    返回处理过的文章数。
    """
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, title, content_text, cluster_id
              FROM articles
             WHERE simhash IS NULL OR simhash = ''
             ORDER BY id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    processed = 0
    for r in rows:
        article = {"title": r["title"], "content_text": r["content_text"]}
        text = get_text_for(article)
        sh = simhash(text)
        cluster_id = find_or_create_cluster(db_path, sh, text)
        with write_lock:
            conn = get_conn(db_path)
            try:
                if cluster_id is None:
                    # 先写入 simhash 与自身 cluster_id，用文章 id 作为簇 id
                    conn.execute(
                        "UPDATE articles SET simhash = ?, cluster_id = ? WHERE id = ?",
                        (sh, r["id"], r["id"]),
                    )
                else:
                    conn.execute(
                        "UPDATE articles SET simhash = ?, cluster_id = ? WHERE id = ?",
                        (sh, cluster_id, r["id"]),
                    )
                conn.commit()
            finally:
                conn.close()
        processed += 1
    if processed:
        log.info("backfill_clusters 完成，处理 %d 篇文章", processed)
    return processed
