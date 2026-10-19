"""银行账单侦探：三路匹配纯函数引擎。

本模块为纯函数，不访问数据库、不导入任何 ledger 其他模块。
所有金额单位为「分」（整数），日期为 ISO 字符串（YYYY-MM-DD）。
"""

from __future__ import annotations

import datetime
import hashlib
import re

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
    include_rule_id: bool = False,
) -> tuple[int, int] | tuple[int, int, int | None] | None:
    """关键词规则匹配，返回 (category_id, 95) 或 None。\n\n    include_rule_id=True 时返回 (category_id, 95, rule_id)。

    命中多条时取 priority 最大者，并列取 keyword 最长者。
    """
    haystack = normalize(counterparty + summary)
    if not haystack:
        return None
    best: dict | None = None
    best_keyword_len = 0
    for rule in rules:
        if int(rule.get("is_enabled", 1)) != 1:
            continue
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
    if include_rule_id:
        return int(best["category_id"]), 95, best.get("id")
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


def detect_transfer_pair_cross_batch(
    new_items: list[dict],
    old_items: list[dict],
    account_names: dict[int, str],
    abs_tol_cents: int = 100,
    pct_tol: float = 1,
    date_window_days: int = 3,
) -> list[tuple[int, int]]:
    """跨批次转账配对：new_items 与 old_items 之间做一出一入的配对。

    new_items 为当前批次条目，old_items 为其他批次候选条目（调用方已过滤为
    未配对、未认领）。两者 dict 形状与 detect_transfer_pair 的 items 完全一致。

    只生成跨批次配对：
      - new 的 out 配 old 的 in；
      - new 的 in 配 old 的 out；
      - new-new 与 old-old 之间绝不配对。

    每个条目最多用一次（new 侧与 old 侧各自全局互斥）。贪心顺序：先处理
    new 的 out（按 id 升序），再处理 new 的 in（按 id 升序）；每个 new 条目在
    old 侧按 id 升序取第一个满足条件的候选。

    配对条件与 detect_transfer_pair 完全一致：方向相反、amount_within 金额
    容差、within_date_window 日期窗口、至少一方 counterparty 经 detect_transfer
    能对上任一自有账户名。

    返回 [(out_id, in_id), ...]，out 在前；当 new 的 in 配 old 的 out 时，
    元组为 (old_out_id, new_in_id)。
    """
    if not new_items or not old_items:
        return []

    new_outs = sorted(
        (item for item in new_items if (item.get("direction") or "") == "out"),
        key=lambda item: int(item["id"]),
    )
    new_ins = sorted(
        (item for item in new_items if (item.get("direction") or "") == "in"),
        key=lambda item: int(item["id"]),
    )
    old_ins = sorted(
        (item for item in old_items if (item.get("direction") or "") == "in"),
        key=lambda item: int(item["id"]),
    )
    old_outs = sorted(
        (item for item in old_items if (item.get("direction") or "") == "out"),
        key=lambda item: int(item["id"]),
    )

    used_new: set[int] = set()
    used_old: set[int] = set()
    pairs: list[tuple[int, int]] = []

    # new 的 out 配 old 的 in
    for new_out in new_outs:
        new_out_id = int(new_out["id"])
        if new_out_id in used_new:
            continue
        for old_in in old_ins:
            old_in_id = int(old_in["id"])
            if old_in_id in used_old:
                continue
            if not amount_within(
                int(new_out["amount_cents"]),
                int(old_in["amount_cents"]),
                abs_tol_cents,
                pct_tol,
            ):
                continue
            if not within_date_window(
                str(new_out["occurred_on"]),
                str(old_in["occurred_on"]),
                date_window_days,
            ):
                continue
            if (
                detect_transfer(str(new_out.get("counterparty") or ""), account_names) is None
                and detect_transfer(str(old_in.get("counterparty") or ""), account_names) is None
            ):
                continue
            used_new.add(new_out_id)
            used_old.add(old_in_id)
            pairs.append((new_out_id, old_in_id))
            break

    # new 的 in 配 old 的 out
    for new_in in new_ins:
        new_in_id = int(new_in["id"])
        if new_in_id in used_new:
            continue
        for old_out in old_outs:
            old_out_id = int(old_out["id"])
            if old_out_id in used_old:
                continue
            if not amount_within(
                int(old_out["amount_cents"]),
                int(new_in["amount_cents"]),
                abs_tol_cents,
                pct_tol,
            ):
                continue
            if not within_date_window(
                str(old_out["occurred_on"]),
                str(new_in["occurred_on"]),
                date_window_days,
            ):
                continue
            if (
                detect_transfer(str(old_out.get("counterparty") or ""), account_names) is None
                and detect_transfer(str(new_in.get("counterparty") or ""), account_names) is None
            ):
                continue
            used_new.add(new_in_id)
            used_old.add(old_out_id)
            pairs.append((old_out_id, new_in_id))
            break

    return pairs



def compile_rule_pattern(pattern: str):
    """编译用户正则，失败或不安全返回 None（调用方跳过该规则，绝不抛异常）。

    不安全指 check_pattern_safety 判定有 ReDoS 风险的模式。
    """
    if check_pattern_safety(pattern) is not None:
        return None
    try:
        return re.compile(pattern)
    except re.error:
        return None


def _regex_candidates(rules: list[dict], direction: str) -> list[dict]:
    """筛选启用中的正则规则，且方向为 any 或与当前方向一致。"""
    result: list[dict] = []
    for rule in rules:
        if rule.get("pattern_type") != "regex":
            continue
        if int(rule.get("is_enabled", 1)) != 1:
            continue
        rule_direction = rule.get("direction")
        if rule_direction not in ("any", direction):
            continue
        result.append(rule)
    return result


def _pick_best_regex(candidates: list[dict], haystack: str) -> dict | None:
    """在候选中挑出命中且最优的正则规则；决胜逻辑与关键词一致。"""
    best: dict | None = None
    best_priority = 0
    best_len = 0
    best_id = 0
    for rule in candidates:
        pattern = rule.get("keyword") or ""
        compiled = compile_rule_pattern(str(pattern))
        if compiled is None:
            continue
        if not safe_regex_search(compiled, haystack):
            continue
        priority = int(rule.get("priority") or 0)
        kw_len = len(str(pattern))
        rule_id = int(rule.get("id") or 0)
        if best is None:
            best = rule
            best_priority = priority
            best_len = kw_len
            best_id = rule_id
            continue
        better = (
            priority > best_priority
            or (priority == best_priority and kw_len > best_len)
            or (priority == best_priority and kw_len == best_len and rule_id < best_id)
        )
        if better:
            best = rule
            best_priority = priority
            best_len = kw_len
            best_id = rule_id
    return best


def _pick_best_keyword(
    kw_rules: list[dict],
    counterparty: str,
    summary: str,
    direction: str,
) -> dict | None:
    """在关键词规则中挑出命中且最优者，决胜与 match_by_rules 保持一致。"""
    haystack = normalize(counterparty + summary)
    if not haystack:
        return None
    best: dict | None = None
    best_priority = 0
    best_len = 0
    best_id = 0
    for rule in kw_rules:
        keyword = rule.get("keyword") or ""
        norm_kw = normalize(str(keyword))
        if not norm_kw:
            continue
        rule_direction = rule.get("direction") or "any"
        if rule_direction != "any" and rule_direction != direction:
            continue
        if norm_kw not in haystack:
            continue
        priority = int(rule.get("priority") or 0)
        kw_len = len(norm_kw)
        rule_id = int(rule.get("id") or 0)
        if best is None:
            best = rule
            best_priority = priority
            best_len = kw_len
            best_id = rule_id
            continue
        better = (
            priority > best_priority
            or (priority == best_priority and kw_len > best_len)
            or (priority == best_priority and kw_len == best_len and rule_id < best_id)
        )
        if better:
            best = rule
            best_priority = priority
            best_len = kw_len
            best_id = rule_id
    return best


def match_best(
    counterparty: str,
    summary: str,
    direction: str,
    *,
    rules: list[dict],
    aliases: list[dict],
    history: list[dict],
    top_categories: list[tuple[int, int]],
) -> dict:
    """统一调度：别名记忆 > 正则规则 > 关键词规则 > 历史 > 候选 > 无匹配。

    返回 dict，键为 category_id/confidence/source/rule_id/reason。
    """
    alias_hit = match_by_alias(counterparty, direction, aliases)
    if alias_hit is not None:
        cid, conf = alias_hit
        return {
            "category_id": cid,
            "confidence": conf,
            "source": "alias",
            "rule_id": None,
            "reason": "别名记忆命中",
        }

    haystack = normalize(counterparty + " " + summary)
    regex_candidates = _regex_candidates(rules, direction)
    best_regex = _pick_best_regex(regex_candidates, haystack)

    kw_rules: list[dict] = []
    for rule in rules:
        if rule.get("pattern_type", "keyword") != "keyword":
            continue
        if int(rule.get("is_enabled", 1)) != 1:
            continue
        kw_rules.append(rule)
    best_kw = _pick_best_keyword(kw_rules, counterparty, summary, direction)

    winner = None
    winner_source = ""
    if best_regex is not None and best_kw is not None:
        rp = int(best_regex.get("priority") or 0)
        kp = int(best_kw.get("priority") or 0)
        if kp > rp:
            winner, winner_source = best_kw, "rule_keyword"
        elif rp > kp:
            winner, winner_source = best_regex, "rule_regex"
        else:
            winner, winner_source = best_regex, "rule_regex"
    elif best_regex is not None:
        winner, winner_source = best_regex, "rule_regex"
    elif best_kw is not None:
        winner, winner_source = best_kw, "rule_keyword"
    if winner is not None:
        if winner_source == "rule_regex":
            return {
                "category_id": int(winner["category_id"]),
                "confidence": 97,
                "source": "rule_regex",
                "rule_id": int(winner.get("id") or 0),
                "reason": "正则规则「" + str(winner.get("keyword") or "") + "」命中",
            }
        return {
            "category_id": int(winner["category_id"]),
            "confidence": 95,
            "source": "rule_keyword",
            "rule_id": int(winner.get("id") or 0),
            "reason": "关键词规则「" + str(winner.get("keyword") or "") + "」命中",
        }

    history_hit = match_by_history(counterparty, summary, direction, history)
    if history_hit is not None:
        cid, conf = history_hit
        return {
            "category_id": cid,
            "confidence": conf,
            "source": "history",
            "rule_id": None,
            "reason": "历史记录推断",
        }

    suggestions = suggest_candidates(counterparty, summary, direction, history, top_categories)
    if suggestions:
        cid, reason, conf = suggestions[0]
        return {
            "category_id": cid,
            "confidence": conf,
            "source": "suggest",
            "rule_id": None,
            "reason": reason,
        }

    return {
        "category_id": None,
        "confidence": 0,
        "source": "none",
        "rule_id": None,
        "reason": "无匹配",
    }


MAX_REGEX_HAYSTACK = 500

_NESTED_QUANTIFIER_RE = re.compile(
    r"(\([^()]*[+*][^()]*\))[+*]|\([^()]*\)\{[0-9]+,[^}]*\}[+{]"
)
_BACKREF_RE = re.compile(r"\\[1-9]")
_MULTI_DOTSTAR_RE = re.compile(r"\.\*.*\.\*")


def check_pattern_safety(pattern: str) -> str | None:
    """检查用户正则的安全性，返回 None 表示安全，否则返回拒绝原因。"""
    if pattern is None or pattern.strip() == "":
        return "正则不能为空"
    if len(pattern) > 200:
        return "正则过长（>200字符），请拆分成多条关键词规则"
    if _NESTED_QUANTIFIER_RE.search(pattern):
        return "含嵌套量词，有灾难性回溯风险"
    if _BACKREF_RE.search(pattern):
        return "暂不支持回溯引用，请用普通分组改写"
    if _MULTI_DOTSTAR_RE.search(pattern):
        return "连续多个 .* 有回溯风险，请收紧表达"
    return None


def safe_regex_search(compiled, haystack: str) -> bool:
    """带 haystack 长度熔断的正则匹配，超长直接返回 False，绝不抛异常。"""
    if haystack is None:
        return False
    if len(haystack) > MAX_REGEX_HAYSTACK:
        return False
    return bool(compiled.search(haystack))
