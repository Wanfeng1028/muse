"""银行账单侦探：三路匹配纯函数引擎。

本模块为纯函数，不访问数据库、不导入任何 ledger 其他模块。
所有金额单位为「分」（整数），日期为 ISO 字符串（YYYY-MM-DD）。
"""

from __future__ import annotations

import datetime
import hashlib

_PUNCTUATION = "，。、；：！？,.!?:;·•|/-"


def normalize(text: str) -> str:
    """归一化文本：去首尾空白、删空白与常见标点、转小写。"""
    if not text:
        return ""
    stripped = text.strip()
    chars: list[str] = []
    for ch in stripped:
        if ch.isspace():
            continue
        if ch in _PUNCTUATION:
            continue
        chars.append(ch)
    return "".join(chars).lower()


def fingerprint(
    occurred_on: str,
    amount_cents: int,
    direction: str,
    counterparty: str,
    summary: str,
) -> str:
    """生成明细唯一指纹：sha256 前 32 位 hex。"""
    raw = f"{occurred_on}|{amount_cents}|{direction}|{normalize(counterparty)}|{normalize(summary)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def match_by_rules(
    counterparty: str,
    summary: str,
    direction: str,
    rules: list[dict],
) -> tuple[int, int] | None:
    """关键词规则匹配，返回 (category_id, 95) 或 None。

    命中多条时取 priority 最大者，并列取 keyword 最长者。
    """
    haystack = normalize(counterparty + summary)
    if not haystack:
        return None
    best: dict | None = None
    best_keyword_len = 0
    for rule in rules:
        keyword = rule.get("keyword") or ""
        norm_kw = normalize(keyword)
        if not norm_kw:
            continue
        rule_direction = rule.get("direction") or "any"
        if rule_direction != "any" and rule_direction != direction:
            continue
        if norm_kw not in haystack:
            continue
        priority = int(rule.get("priority") or 0)
        kw_len = len(norm_kw)
        if best is None:
            best = rule
            best_keyword_len = kw_len
            continue
        best_priority = int(best.get("priority") or 0)
        if priority > best_priority or (priority == best_priority and kw_len > best_keyword_len):
            best = rule
            best_keyword_len = kw_len
    if best is None:
        return None
    return int(best["category_id"]), 95


def match_by_history(
    counterparty: str,
    summary: str,
    direction: str,
    history: list[dict],
) -> tuple[int, int] | None:
    """历史记录匹配，先精确后模糊，返回 (category_id, confidence) 或 None。"""
    norm_cp = normalize(counterparty)
    norm_sm = normalize(summary)
    if not norm_cp and not norm_sm:
        return None

    exact_counts: dict[int, int] = {}
    for item in history:
        if (item.get("direction") or "") != direction:
            continue
        if norm_cp and normalize(item.get("counterparty") or "") == norm_cp:
            cid = int(item["category_id"])
            exact_counts[cid] = exact_counts.get(cid, 0) + 1
    if exact_counts:
        cid, votes = _top_vote(exact_counts)
        if votes >= 2:
            return cid, min(90, 60 + votes * 10)

    fuzzy_counts: dict[int, int] = {}
    for item in history:
        if (item.get("direction") or "") != direction:
            continue
        if not _fuzzy_hit(norm_cp, normalize(item.get("counterparty") or "")):
            if not _fuzzy_hit(norm_sm, normalize(item.get("summary") or "")):
                continue
        cid = int(item["category_id"])
        fuzzy_counts[cid] = fuzzy_counts.get(cid, 0) + 1
    if fuzzy_counts:
        cid, votes = _top_vote(fuzzy_counts)
        if votes >= 2:
            return cid, 65
    return None


def _top_vote(counts: dict[int, int]) -> tuple[int, int]:
    """返回票数最多的 (category_id, 票数)，并列取较小 id。"""
    best_id = -1
    best_votes = -1
    for cid in sorted(counts):
        votes = counts[cid]
        if votes > best_votes:
            best_id = cid
            best_votes = votes
    return best_id, best_votes


def _fuzzy_hit(a: str, b: str) -> bool:
    """判断两段归一化文本是否互包含（长度需 >= 2）。"""
    if len(a) < 2 or len(b) < 2:
        return False
    return a in b or b in a


def suggest_candidates(
    counterparty: str,
    summary: str,
    direction: str,
    history: list[dict],
    top_categories: list[tuple[int, int]],
) -> list[tuple[int, str, int]]:
    """给出候选分类，返回 [(category_id, reason, confidence)]，最多 3 条。"""
    result: list[tuple[int, str, int]] = []
    seen: set[int] = set()

    history_counts: dict[int, int] = {}
    for item in history:
        if (item.get("direction") or "") != direction:
            continue
        cid = int(item["category_id"])
        history_counts[cid] = history_counts.get(cid, 0) + 1
    ranked_history = sorted(history_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    for cid, _count in ranked_history:
        if cid in seen:
            continue
        seen.add(cid)
        result.append((cid, "该商户历史多归为此分类", 0))
        if len(result) >= 3:
            break

    for cid, _count in top_categories:
        if len(result) >= 3:
            break
        if cid in seen:
            continue
        seen.add(cid)
        result.append((cid, "同方向常用分类", 0))

    confidences = [55, 45, 35]
    final: list[tuple[int, str, int]] = []
    for idx, (cid, reason, _unused) in enumerate(result[:3]):
        final.append((cid, reason, confidences[idx]))
    return final


def detect_transfer(counterparty: str, account_names: dict[int, str]) -> int | None:
    """识别转账：对方名称与账户名匹配则返回 account_id，否则 None。"""
    norm_cp = normalize(counterparty)
    if not norm_cp:
        return None
    for account_id in sorted(account_names):
        norm_name = normalize(account_names[account_id])
        if not norm_name:
            continue
        if norm_cp == norm_name:
            return account_id
        if _fuzzy_hit(norm_cp, norm_name):
            return account_id
    return None


def amount_within(a_cents: int, b_cents: int, abs_tol_cents: int, pct_tol: float) -> bool:
    """判断两金额是否"相当"：绝对差 <= abs_tol_cents，或相对差 <= pct_tol%。

    相对差按 max(|a|, |b|) 计算；a、b 均为 0 时视为相当；
    pct_tol <= 0 时只看绝对容差。用整数运算避免浮点误差。
    """
    diff = abs(a_cents - b_cents)
    if diff <= abs_tol_cents:
        return True
    if pct_tol <= 0:
        return False
    base = max(abs(a_cents), abs(b_cents))
    if base == 0:
        return True
    return diff * 100 <= base * pct_tol


def within_date_window(d1: str, d2: str, n_days: int) -> bool:
    """两日期（YYYY-MM-DD）相差绝对值 <= n_days 天。任一非法返回 False。"""
    try:
        date1 = datetime.date.fromisoformat(d1)
        date2 = datetime.date.fromisoformat(d2)
    except ValueError:
        return False
    return abs((date1 - date2).days) <= n_days


def match_by_alias(
    counterparty: str,
    direction: str,
    aliases: list[dict],
) -> tuple[int, int] | None:
    """商户别名匹配：归一化后精确相等，返回 (category_id, 85) 或 None。

    aliases 元素形如 {"alias": <已归一化的别名>, "category_id": int, "direction": "in"/"out"}。
    direction 不一致的别名跳过。
    """
    norm_cp = normalize(counterparty)
    if not norm_cp:
        return None
    for alias in aliases:
        stored = str(alias.get("alias") or "")
        if stored != norm_cp:
            continue
        if (alias.get("direction") or "") != direction:
            continue
        return int(alias["category_id"]), 85
    return None


def detect_transfer_pair(
    items: list[dict],
    account_names: dict[int, str],
    abs_tol_cents: int = 100,
    pct_tol: float = 1,
    date_window_days: int = 3,
) -> list[tuple[int, int]]:
    """在同批次条目中找转账配对：方向一出一入、金额容差内、日期窗口内、
    且至少一方的 counterparty 能对上某个自有账户名（用 detect_transfer）。

    items 元素形如 {"id": int, "occurred_on": str, "amount_cents": int,
    "direction": "in"/"out", "counterparty": str}。
    贪心配对：out 按 id 升序、in 按 id 升序，每个条目最多用一次。
    返回 [(out_id, in_id), ...]（out 在前）。
    """
    outs = sorted(
        (item for item in items if (item.get("direction") or "") == "out"),
        key=lambda item: int(item["id"]),
    )
    ins = sorted(
        (item for item in items if (item.get("direction") or "") == "in"),
        key=lambda item: int(item["id"]),
    )
    used: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for out in outs:
        out_id = int(out["id"])
        if out_id in used:
            continue
        for in_ in ins:
            in_id = int(in_["id"])
            if in_id in used:
                continue
            if not amount_within(
                int(out["amount_cents"]),
                int(in_["amount_cents"]),
                abs_tol_cents,
                pct_tol,
            ):
                continue
            if not within_date_window(
                str(out["occurred_on"]),
                str(in_["occurred_on"]),
                date_window_days,
            ):
                continue
            if (
                detect_transfer(str(out.get("counterparty") or ""), account_names) is None
                and detect_transfer(str(in_.get("counterparty") or ""), account_names) is None
            ):
                continue
            used.add(out_id)
            used.add(in_id)
            pairs.append((out_id, in_id))
            break
    return pairs
