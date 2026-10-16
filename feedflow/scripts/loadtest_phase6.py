#!/usr/bin/env python3
"""Phase 6 load-test for FeedFlow: fills the untested gaps in
docs/LOADTEST_2026-10-16.md.

Design constraints (inherited from scripts/loadtest.py):
  * strictly zero network
  * RSS entries contain no <link>
  * feed_url points to a local RSS file
  * no store.create_feed; insert feeds directly via db.get_conn
  * fetch_feed uses retries=0, extract_timeout=1

This script only *reads* from the feedflow package (imports) and never
modifies it.  All numbers printed come from real executions.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import os
import random
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

# ---------------------------------------------------------------------------
# Locate the repo root so that `feedflow` is importable and so we can load
# scripts/loadtest.py dynamically for its word lists / helpers.
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from feedflow import db as ff_db  # noqa: E402
from feedflow import store as ff_store  # noqa: E402


def _load_loadtest_module():
    """Dynamically import scripts/loadtest.py for reuse of WORDS / helpers."""
    path = _REPO_ROOT / "scripts" / "loadtest.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("_ff_loadtest", str(path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    return mod


_LOADTEST = _load_loadtest_module()

# Fall back to local copies only if scripts/loadtest.py is unimportable.
_FALLBACK_WORDS = {
    "TECH": [
        "kubernetes", "docker", "rust", "python", "async", "compiler", "kernel",
        "memory", "thread", "cache", "latency", "throughput", "sharding",
        "replication", "queue", "socket", "protocol", "binary", "runtime",
        "garbage", "collector", "coroutine", "scheduler", "mutex", "lockfree",
        "concurrency", "parallelism", "vector", "register", "instruction",
        "pipeline", "branch", "prediction", "bytecode", "jit", "interpreter",
        "virtual", "machine", "container", "namespace", "cgroup", "syscall",
    ],
    "FINANCE": [
        "equity", "bond", "yield", "derivative", "hedge", "leverage", "margin",
        "portfolio", "volatility", "liquidity", "spread", "swap", "option",
        "future", "arbitrage", "rebalance", "drawdown", "sharpe", "alpha",
        "beta", "duration", "convexity", "notional", "counterparty", "clearing",
        "settlement", "custody", "collateral", "haircut", "repo", "reverse",
        "coupon", "amortization", "accrual", "benchmark", "curve", "basis",
        "carry", "rollover", "tranche", "securitization", "underwriting",
    ],
    "SPORTS": [
        "offense", "defense", "midfield", "striker", "goalkeeper", "penalty",
        "corner", "freekick", "offsides", "tackle", "dribble", "volley",
        "header", "assist", "rebound", "dunk", "three", "pointer", "layup",
        "steal", "block", "fastbreak", "sprint", "marathon", "relay", "hurdle",
        "javelin", "discus", "hammer", "shotput", "longjump", "triplejump",
        "highjump", "polevault", "decathlon", "heptathlon", "tournament",
        "playoff", "championship", "qualifier", "semifinal", "overtime",
    ],
    "LIFE": [
        "recipe", "kitchen", "garden", "morning", "coffee", "tea", "bread",
        "sourdough", "roast", "simmer", "season", "marinade", "herb", "spice",
        "harvest", "compost", "seedling", "prune", "water", "sunlight",
        "minimalism", "declutter", "journal", "habit", "routine", "mindful",
        "meditation", "yoga", "stretch", "breathe", "sleep", "nap", "walk",
        "hike", "camp", "picnic", "craft", "knit", "sew", "paint", "sketch",
        "pottery", "woodwork",
    ],
}

WORDS = getattr(_LOADTEST, "WORDS", None) or _FALLBACK_WORDS


# ---------------------------------------------------------------------------
# Fixture generation (zero network).  Mirrors loadtest.py's approach.
# ---------------------------------------------------------------------------

RSS_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>{title}</title>
<link>file://{path}</link>
<description>phase6 fixture</description>
{items}
</channel></rss>
"""

ITEM_TEMPLATE = """<item>
<title>{title}</title>
<description>{desc}</description>
<guid isPermaLink="false">{guid}</guid>
</item>
"""


def _random_text(words: Sequence[str], n: int, rng: random.Random) -> str:
    return " ".join(rng.choice(words) for _ in range(n))


def _write_rss(path: Path, title: str, items: List[Tuple[str, str]], rng: random.Random) -> None:
    rendered = []
    for guid, desc in items:
        rendered.append(
            ITEM_TEMPLATE.format(
                title=_random_text(rng.choice(list(WORDS.values())), 5, rng),
                desc=desc,
                guid=guid,
            )
        )
    path.write_text(
        RSS_TEMPLATE.format(title=title, path=str(path), items="\n".join(rendered)),
        encoding="utf-8",
    )


def build_fixture(
    db_path: Path,
    feeds_dir: Path,
    n_feeds: int,
    n_articles: int,
    seed: int = 20261016,
) -> Tuple[int, int]:
    """Create a zero-network fixture DB.

    Returns (n_feeds, n_articles) actually inserted.
    """
    rng = random.Random(seed)
    feeds_dir.mkdir(parents=True, exist_ok=True)

    # 建表：get_conn 不建表，必须先调 init_db（对标 scripts/loadtest.py:226）。
    ff_db.init_db(str(db_path))
    conn = ff_db.get_conn(str(db_path))
    try:
        # feeds table
        now_iso = "2026-10-16T00:00:00+00:00"
        rows_feeds = []
        rows_articles = []
        for i in range(n_feeds):
            feed_id = i + 1
            slug = f"feed-{feed_id:05d}"
            rss_path = feeds_dir / f"{slug}.xml"
            # Build item payloads (guid, description) without <link>.
            item_payloads = []
            for j in range(n_articles):
                guid = f"{slug}-item-{j:06d}"
                words = list(WORDS.values())[(feed_id + j) % len(WORDS)]
                desc = _random_text(words, 25, rng)
                item_payloads.append((guid, desc))
            _write_rss(rss_path, slug, item_payloads, rng)
            feed_url = rss_path.as_uri()
            rows_feeds.append(
                (
                    slug,              # title
                    "",                # site_url
                    feed_url,          # feed_url
                    "phase6",          # description
                    30,                # interval_min
                    1,                 # enabled
                    None,              # last_fetched_at
                    "ok",              # last_status
                    "",                # last_error
                    i,                 # position
                    now_iso,           # created_at
                )
            )
            for j, (guid, desc) in enumerate(item_payloads):
                rows_articles.append(
                    (
                        feed_id,
                        guid,
                        f"item-{j}",   # title
                        "",            # author
                        "",            # link
                        desc,          # summary
                        "",            # content_html
                        desc,          # content_text
                        now_iso,       # published_at
                        now_iso,       # fetched_at
                    )
                )

        cur = conn.cursor()
        cur.executemany(
            "INSERT OR REPLACE INTO feeds "
            "(title, site_url, feed_url, description, interval_min, enabled, "
            "last_fetched_at, last_status, last_error, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows_feeds,
        )
        cur.executemany(
            "INSERT OR REPLACE INTO articles "
            "(feed_id, guid, title, author, link, summary, content_html, "
            "content_text, published_at, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows_articles,
        )
        conn.commit()

        n_feeds_db = cur.execute("SELECT COUNT(*) FROM feeds").fetchone()[0]
        n_articles_db = cur.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        return int(n_feeds_db), int(n_articles_db)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

class TimeoutError(Exception):
    pass


def _percentile(samples: List[float], pct: float) -> float:
    if not samples:
        return float("nan")
    s = sorted(samples)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _fmt_ms(x: float) -> str:
    return f"{x:.2f}"


def time_call(fn: Callable[[], object]) -> float:
    t0 = time.perf_counter()
    fn()
    return (time.perf_counter() - t0) * 1000.0


def run_repeated(
    fn: Callable[[], object],
    iterations: int,
    timeout_s: float = 120.0,
) -> Tuple[List[float], bool]:
    samples: List[float] = []
    t_start = time.perf_counter()
    for _ in range(iterations):
        if time.perf_counter() - t_start > timeout_s:
            return samples, True
        samples.append(time_call(fn))
    return samples, False


# ---------------------------------------------------------------------------
# Measurement A: due_feeds + stats, 200 iterations each
# ---------------------------------------------------------------------------

def measure_a(db_path: Path, iterations: int, timeout_s: float) -> dict:
    now_iso = "2026-10-16T00:00:00+00:00"
    default_interval = 30

    def _due() -> object:
        return ff_store.due_feeds(str(db_path), now_iso, default_interval)

    def _stats() -> object:
        return ff_store.stats(str(db_path))

    due_samples, due_timeout = run_repeated(_due, iterations, timeout_s)
    stats_samples, stats_timeout = run_repeated(_stats, iterations, timeout_s)

    conn = ff_db.get_conn(str(db_path))
    try:
        cur = conn.cursor()
        n_feeds = int(cur.execute("SELECT COUNT(*) FROM feeds").fetchone()[0])
        n_articles = int(cur.execute("SELECT COUNT(*) FROM articles").fetchone()[0])
    finally:
        conn.close()

    return {
        "due_samples": due_samples,
        "stats_samples": stats_samples,
        "due_timeout": due_timeout,
        "stats_timeout": stats_timeout,
        "n_feeds": n_feeds,
        "n_articles": n_articles,
        "iterations": iterations,
    }


# ---------------------------------------------------------------------------
# Measurement B: 8-thread concurrent list_articles(scope=all, limit=50)
# ---------------------------------------------------------------------------

def measure_b(
    db_path: Path,
    threads: int,
    per_thread: int,
    limit: int,
    timeout_s: float,
) -> dict:
    max_offset_probe = 1000

    lock_errors: List[str] = []
    other_errors: List[str] = []

    def _worker(seed: int) -> List[float]:
        rng = random.Random(seed)
        local: List[float] = []
        for _ in range(per_thread):
            offset = rng.randint(0, max_offset_probe)
            t0 = time.perf_counter()
            try:
                ff_store.list_articles(
                    str(db_path), scope="all", limit=limit, offset=offset
                )
            except sqlite3.OperationalError as exc:  # e.g. "database is locked"
                msg = str(exc)
                if "lock" in msg.lower() or "busy" in msg.lower():
                    lock_errors.append(msg)
                else:
                    other_errors.append(msg)
            except Exception as exc:  # pragma: no cover - defensive
                other_errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                local.append((time.perf_counter() - t0) * 1000.0)
        return local

    t_start = time.perf_counter()
    samples: List[float] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as ex:
        futs = [ex.submit(_worker, i * 7919 + 13) for i in range(threads)]
        for fut in concurrent.futures.as_completed(futs):
            if time.perf_counter() - t_start > timeout_s:
                for f in futs:
                    f.cancel()
                return {
                    "samples": samples,
                    "lock_errors": lock_errors,
                    "other_errors": other_errors,
                    "timed_out": True,
                    "threads": threads,
                    "per_thread": per_thread,
                    "limit": limit,
                }
            samples.extend(fut.result())

    return {
        "samples": samples,
        "lock_errors": lock_errors,
        "other_errors": other_errors,
        "timed_out": False,
        "threads": threads,
        "per_thread": per_thread,
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# Measurement C: cold-cache first stats() vs warm-cache second stats()
# ---------------------------------------------------------------------------

_CHILD_SNIPPET = (
    "import sys, time, json;"
    "sys.path.insert(0, {repo!r});"
    "from feedflow import store as s;"
    "t0 = time.perf_counter();"
    "s.stats({db!r});"
    "print(json.dumps((time.perf_counter() - t0) * 1000.0))"
)


def measure_c(db_path: Path, rounds: int, timeout_s: float) -> dict:
    cold: List[float] = []
    warm: List[float] = []

    for _ in range(rounds):
        # Cold: fresh interpreter, first call to stats().
        snippet = _CHILD_SNIPPET.format(repo=str(_REPO_ROOT), db=str(db_path))
        t_start = time.perf_counter()
        try:
            proc = subprocess.run(
                [sys.executable, "-c", snippet],
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "cold": cold,
                "warm": warm,
                "timed_out": True,
                "rounds": rounds,
            }
        if proc.returncode != 0:
            raise RuntimeError(
                f"cold-cache child failed: rc={proc.returncode} stderr={proc.stderr!r}"
            )
        try:
            cold.append(float(proc.stdout.strip()))
        except ValueError as exc:
            raise RuntimeError(
                f"cold-cache child produced non-numeric output: {proc.stdout!r}"
            ) from exc

        # Warm: same process, second call.
        ff_store.stats(str(db_path))
        warm.append(time_call(lambda: ff_store.stats(str(db_path))))

        if time.perf_counter() - t_start > timeout_s:
            return {
                "cold": cold,
                "warm": warm,
                "timed_out": True,
                "rounds": rounds,
            }

    return {"cold": cold, "warm": warm, "timed_out": False, "rounds": rounds}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _summary_row(label: str, samples: List[float], note: str = "") -> str:
    if not samples:
        return f"| {label} | — | — | — | {note or 'no samples'} |"
    return (
        f"| {label} | {len(samples)} | "
        f"{_fmt_ms(_percentile(samples, 50))} | "
        f"{_fmt_ms(_percentile(samples, 95))} | "
        f"{_fmt_ms(statistics.fmean(samples))} |"
        f"{'' if not note else ' ' + note}"
    )


def render_report(
    a: dict,
    b: dict,
    c: dict,
    quick: bool,
) -> str:
    lines: List[str] = []
    lines.append("# Phase 6 Load-Test Results (loadtest_phase6.py)")
    lines.append("")
    lines.append(f"- Mode: `{'--quick' if quick else 'full'}`")
    lines.append(f"- Feeds in DB: {a['n_feeds']}")
    lines.append(f"- Articles in DB: {a['n_articles']}")
    lines.append("")

    # --- A ---
    lines.append("## A. `due_feeds` and `stats` — repeated single-thread timing")
    lines.append("")
    lines.append(
        f"Iterations per function: {a['iterations']} "
        f"(due_feeds timed out: {a['due_timeout']}, stats timed out: {a['stats_timeout']})"
    )
    lines.append("")
    lines.append("| function | n | p50 (ms) | p95 (ms) | mean (ms) |")
    lines.append("| --- | --- | --- | --- | --- |")
    lines.append(_summary_row("due_feeds", a["due_samples"]))
    lines.append(_summary_row("stats", a["stats_samples"]))
    lines.append("")

    # --- B ---
    lines.append("## B. Multi-threaded `list_articles(scope='all', limit=50)`")
    lines.append("")
    lines.append(
        f"Threads: {b['threads']} | calls per thread: {b['per_thread']} | "
        f"total calls: {len(b['samples'])} | limit: {b['limit']} | "
        f"offset: random in [0, 1000] | timed out: {b['timed_out']}"
    )
    lines.append("")
    lines.append("| workload | n | p50 (ms) | p95 (ms) | mean (ms) |")
    lines.append("| --- | --- | --- | --- | --- |")
    lines.append(_summary_row("8-thread list_articles", b["samples"]))
    lines.append("")
    lines.append(
        "Comparison vs. Phase 5 single-thread p50=22.38 ms "
        "(from docs/LOADTEST_2026-10-16.md): see p50 above."
    )
    lines.append("")
    if b["lock_errors"]:
        lines.append(
            f"- sqlite lock/busy errors observed: {len(b['lock_errors'])} "
            f"(first: `{b['lock_errors'][0]}`)"
        )
    else:
        lines.append("- sqlite lock/busy errors observed: 0")
    if b["other_errors"]:
        lines.append(f"- other errors observed: {len(b['other_errors'])}")
        for e in b["other_errors"][:3]:
            lines.append(f"  - `{e}`")
    else:
        lines.append("- other errors observed: 0")
    lines.append("")

    # --- C ---
    lines.append("## C. Cold-cache vs. warm-cache first `stats()`")
    lines.append("")
    lines.append(
        f"Rounds: {c['rounds']} | timed out: {c['timed_out']} "
        "(cold = fresh `python -c` subprocess, first call; "
        "warm = same interpreter, second call)"
    )
    lines.append("")
    lines.append("| scenario | n | p50 (ms) | p95 (ms) | mean (ms) |")
    lines.append("| --- | --- | --- | --- | --- |")
    lines.append(_summary_row("cold (subprocess)", c["cold"]))
    lines.append(_summary_row("warm (same process)", c["warm"]))
    lines.append("")

    # --- Honest boundaries ---
    lines.append("## Honest boundaries")
    lines.append("")
    lines.append(
        "- Fixture feeds are synthetic RSS files on local disk; "
        "`feed_url` is a `file://` URI. This measures the reader path only, "
        "not real HTTP latency, DNS, TLS, redirects, or remote throttling."
    )
    lines.append(
        "- Articles are inserted directly via `db.get_conn` with raw SQL; "
        "no `store.create_feed` path, no `fetch_feed` retries, and no "
        "`extract_timeout` behavior are exercised here."
    )
    lines.append(
        "- Measurement A is single-threaded and sequential; it does not "
        "reproduce multi-user contention, OS scheduler jitter, or the "
        "presence of concurrent writers."
    )
    lines.append(
        "- Measurement B uses `ThreadPoolExecutor` on CPython; the GIL "
        "serializes Python bytecode, so this stresses sqlite I/O and the "
        "python/sqlite driver, not true CPU parallelism."
    )
    lines.append(
        "- Measurement B's offsets are random within a fixed 0..1000 window, "
        "not a uniform sample over the full article range, so it should not "
        "be read as an average across the entire corpus."
    )
    lines.append(
        "- Measurement C's 'cold' case includes Python interpreter startup "
        "and `feedflow` import time inside the timed region; the 'warm' case "
        "does not. The cold/warm delta therefore conflates process start with "
        "cache effects and must not be reported as a pure cache effect."
    )
    lines.append(
        "- Both cold and warm paths are measured on the same machine, same "
        "filesystem state, and same sqlite page cache; results are not "
        "portable across hardware or OS configurations."
    )
    lines.append(
        "- Timings are wall-clock from `time.perf_counter()`; no CPU pinning, "
        "no isolation from background processes, no repeated-trial statistics "
        "beyond the percentiles shown."
    )
    lines.append(
        "- This file does not modify any source under `feedflow/`; it only "
        "imports and reads from it."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--quick", action="store_true", help="1万篇冒烟规模 (10 feeds x 1000 items)")
    p.add_argument("--db", type=str, default=None, help="复用已有 sqlite 路径（默认临时目录）")
    p.add_argument("--timeout", type=float, default=120.0, help="单测量超时秒数")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if args.quick:
        n_feeds, n_articles = 10, 1000  # 1万篇
        iterations_a = 20
        threads_b, per_thread_b = 8, 10
        rounds_c = 2
    else:
        n_feeds, n_articles = 200, 500  # 10万篇
        iterations_a = 200
        threads_b, per_thread_b = 8, 50
        rounds_c = 5

    tmp_root = Path.home() / "workspace" / "muse-build" / "prompts" / "direct" / "phase6work"
    tmp_root.mkdir(parents=True, exist_ok=True)
    if args.db:
        db_path = Path(args.db)
    else:
        db_path = tmp_root / "phase6.sqlite"
    feeds_dir = tmp_root / "rss"

    sys.stderr.write(
        f"[phase6] building fixture: {n_feeds} feeds x {n_articles} articles "
        f"-> {db_path}\n"
    )
    n_f, n_a = build_fixture(db_path, feeds_dir, n_feeds, n_articles)
    sys.stderr.write(f"[phase6] fixture ready: feeds={n_f} articles={n_a}\n")

    sys.stderr.write("[phase6] measurement A ...\n")
    a = measure_a(db_path, iterations_a, args.timeout)

    sys.stderr.write("[phase6] measurement B ...\n")
    b = measure_b(db_path, threads_b, per_thread_b, limit=50, timeout_s=args.timeout)

    sys.stderr.write("[phase6] measurement C ...\n")
    c = measure_c(db_path, rounds_c, args.timeout)

    report = render_report(a, b, c, quick=args.quick)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
