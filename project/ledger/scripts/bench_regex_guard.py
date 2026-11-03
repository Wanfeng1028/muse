#!/usr/bin/env python3
"""Benchmark for ledger.matching regex guard.

Run from repository root:
    python3 scripts/bench_regex_guard.py
"""
from __future__ import annotations

import os
import re
import sys
import time
from typing import Any, Dict, List

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_REPO_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from ledger.matching import (  # noqa: E402
    check_pattern_safety,
    safe_regex_search,
    match_best,
)


def _fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.4f}"


def bench_catastrophic_regex() -> List[List[str]]:
    rows: List[List[str]] = []
    pattern = "(a+)+$"

    # Demonstrates exponential blowup trend with small inputs.
    for n in (5, 7, 9):
        haystack = "a" * n + "!"
        t0 = time.perf_counter()
        re.search(pattern, haystack)
        dt = time.perf_counter() - t0
        rows.append(
            [
                f"直接 re.search (n={n})",
                f"{n}",
                _fmt_ms(dt),
                "增长趋势",
            ]
        )

    # Guarded rejection path: check_pattern_safety refuses, 0 match cost.
    haystack = "a" * 30 + "!"
    t0 = time.perf_counter()
    safe = check_pattern_safety(pattern)
    dt = time.perf_counter() - t0
    rows.append(
        [
            "check_pattern_safety 拒绝",
            "30",
            _fmt_ms(dt),
            "True" if not safe else "False",
        ]
    )
    return rows


def _build_rules() -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    keywords = ["超市", "餐厅", "地铁", "打车", "药房", "书店", "咖啡", "影院"]
    for i in range(200):
        if i % 2 == 0:
            kw = keywords[i % len(keywords)]
            rules.append(
                {
                    "id": i,
                    "name": f"kw_{i}",
                    "pattern": kw,
                    "match_type": "keyword",
                    "category_id": 1,
                    "priority": i,
                }
            )
        else:
            rules.append(
                {
                    "id": i,
                    "name": f"rx_{i}",
                    "pattern": r"^[0-9]{1,6}\.[0-9]{2}$",
                    "match_type": "regex",
                    "category_id": 1,
                    "priority": i,
                }
            )
    return rules


def _build_transactions(n: int) -> List[Dict[str, Any]]:
    txs: List[Dict[str, Any]] = []
    samples = [
        "沃尔玛超市购物",
        "星巴克咖啡",
        "地铁通勤",
        "滴滴打车",
        "同仁堂药房",
        "新华书店购书",
        "电影院观影",
        "12.50",
        "100.00",
        "吃饭餐厅",
    ]
    for i in range(n):
        txs.append({"id": i, "description": samples[i % len(samples)], "amount_cents": 1000 + i})
    return txs


def bench_match_best() -> List[List[str]]:
    rules = _build_rules()
    txs = _build_transactions(1000)

    t0 = time.perf_counter()
    for tx in txs:
        match_best(rules, tx["description"])
    total = time.perf_counter() - t0
    avg = total / len(txs)

    return [
        [
            "match_best 200 规则 x 1000 交易",
            "1000",
            _fmt_ms(total),
            f"avg={_fmt_ms(avg)}ms",
        ]
    ]


def bench_safe_regex_search() -> List[List[str]]:
    pattern = r"a+b"
    haystack = "x" * 600
    t0 = time.perf_counter()
    result = safe_regex_search(pattern, haystack)
    dt = time.perf_counter() - t0
    return [
        [
            "safe_regex_search 熔断 (len=600)",
            "600",
            _fmt_ms(dt),
            f"result={result}",
        ]
    ]


def _print_table(title: str, header: List[str], rows: List[List[str]]) -> None:
    print()
    print(f"### {title}")
    print()
    print("| " + " | ".join(header) + " |")
    print("| " + " | ".join(["---"] * len(header)) + " |")
    for row in rows:
        print("| " + " | ".join(row) + " |")


def main() -> None:
    print("# Regex Guard Benchmark")

    _print_table(
        "灾难正则 (a+)+$ 防护前后对比",
        ["场景", "输入长度", "耗时(ms)", "备注"],
        bench_catastrophic_regex(),
    )

    _print_table(
        "正常规则集 match_best 调度",
        ["场景", "交易数", "总耗时(ms)", "平均"],
        bench_match_best(),
    )

    _print_table(
        "safe_regex_search 熔断",
        ["场景", "haystack 长度", "耗时(ms)", "结果"],
        bench_safe_regex_search(),
    )


if __name__ == "__main__":
    main()
</｜DSML｜ parameter>
