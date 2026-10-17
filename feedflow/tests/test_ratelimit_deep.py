"""RateLimiter 深度测试：令牌桶语义、并发、清理、边界与时间行为。

被测模块：feedflow.ratelimit.RateLimiter
测试策略：
- 用真实 time.monotonic 与真实线程，不 mock 被测核心逻辑。
- 对依赖时间的断言留足裕量，避免在慢机器上抖动。
- 每个用例至少 2 个断言点，arrange-act-assert 结构完整。
"""

from __future__ import annotations

import math
import threading
import time

import pytest

from feedflow import ratelimit
from feedflow.ratelimit import RateLimiter


# ---------------------------------------------------------------------------
# 基础令牌桶语义
# ---------------------------------------------------------------------------

def test_burst_then_reject_and_retry_after():
    # arrange: 容量 3，补充速率 1/s，桶初始满。
    limiter = RateLimiter(rate_per_sec=1.0, burst=3)

    # act: 连续 3 次消费应全部放行。
    results = [limiter.allow("1.1.1.1") for _ in range(3)]

    # assert: 前三次都放行且 retry_after 为 0。
    assert [ok for ok, _ in results] == [True, True, True]
    assert [ra for _, ra in results] == [0.0, 0.0, 0.0]

    # act: 第 4 次应被拒绝。
    ok, retry_after = limiter.allow("1.1.1.1")

    # assert: 拒绝，且 retry_after 精确到 0.1 秒向上取整。
    assert ok is False
    assert retry_after == 1.0
    assert retry_after > 0.0


def test_retry_after_rounds_up_to_tenth():
    # arrange: 速率 0.5/s，桶容量 1，先耗尽。
    limiter = RateLimiter(rate_per_sec=0.5, burst=1)
    first_ok, _ = limiter.allow("2.2.2.2")

    # act: 立即再请求，此时 tokens 略小于 0。
    ok, retry_after = limiter.allow("2.2.2.2")

    # assert: 首次放行；第二次拒绝。
    assert first_ok is True
    assert ok is False

    # assert: 0.5/s 补 1 个令牌需 2 秒，向上取整到 0.1 秒网格。
    assert retry_after == pytest.approx(2.0, abs=0.2)
    assert retry_after * 10 == pytest.approx(round(retry_after * 10), abs=1e-9)


def test_tokens_refill_over_time():
    # arrange: 容量 1，速率 20/s（每 50ms 补 1 个），先耗尽。
    limiter = RateLimiter(rate_per_sec=20.0, burst=1)
    ok1, _ = limiter.allow("3.3.3.3")
    ok2, _ = limiter.allow("3.3.3.3")

    # assert: 耗尽前两次结果。
    assert ok1 is True
    assert ok2 is False

    # act: 等 150ms，足够补满（20/s * 0.15s = 3 个令牌，被 burst 截到 1）。
    time.sleep(0.15)
    ok3, retry3 = limiter.allow("3.3.3.3")

    # assert: 补充后放行。
    assert ok3 is True
    assert retry3 == 0.0


def test_refill_capped_at_burst():
    # arrange: 容量 2，速率 100/s，长期空闲后桶不会超过 2。
    limiter = RateLimiter(rate_per_sec=100.0, burst=2)
    limiter.allow("4.4.4.4")
    limiter.allow("4.4.4.4")

    # act: 空闲 1 秒（理论上可补 100 个），实际只补到 burst=2。
    time.sleep(0.2)
    a = limiter.allow("4.4.4.4")
    b = limiter.allow("4.4.4.4")
    c = limiter.allow("4.4.4.4")

    # assert: 前两次放行，第三次拒绝，证明补充被 burst 封顶。
    assert a[0] is True
    assert b[0] is True
    assert c[0] is False
    assert c[1] > 0.0


# ---------------------------------------------------------------------------
# 多 key 隔离
# ---------------------------------------------------------------------------

def test_keys_isolated():
    # arrange: 容量 1，两个不同 IP。
    limiter = RateLimiter(rate_per_sec=0.1, burst=1)

    # act
    a1 = limiter.allow("10.0.0.1")
    b1 = limiter.allow("10.0.0.2")
    a2 = limiter.allow("10.0.0.1")
    b2 = limiter.allow("10.0.0.2")

    # assert: 每个 key 各自独立计桶。
    assert a1[0] is True and b1[0] is True
    assert a2[0] is False and b2[0] is False


def test_distinct_keys_all_pass_when_burst_large():
    # arrange: burst 足够大，1000 个不同 key。
    limiter = RateLimiter(rate_per_sec=1.0, burst=1000)
    keys = [f"192.168.1.{i}" for i in range(1000)]

    # act
    results = [limiter.allow(k) for k in keys]

    # assert: 全部放行，且无 retry。
    assert all(ok for ok, _ in results)
    assert all(ra == 0.0 for _, ra in results)


# ---------------------------------------------------------------------------
# 清理逻辑（_evict_idle）
# ---------------------------------------------------------------------------

def test_evict_idle_removes_stale_buckets():
    # arrange: 手工塞入一个远超过 _IDLE_SECONDS 未活动的桶。
    limiter = RateLimiter(rate_per_sec=1.0, burst=1)
    now = time.monotonic()
    stale_key = "stale-ip"
    fresh_key = "fresh-ip"
    with limiter._lock:
        limiter._buckets[stale_key] = (0.0, now - ratelimit._IDLE_SECONDS - 1.0)
        limiter._buckets[fresh_key] = (0.0, now)

    # act: 直接调用清理。
    with limiter._lock:
        limiter._evict_idle(time.monotonic())
        remaining = set(limiter._buckets.keys())

    # assert: 过期的被移除，新鲜保留。
    assert stale_key not in remaining
    assert fresh_key in remaining


def test_evict_idle_threshold_boundary():
    # arrange: 刚好等于阈值不算过期（条件是 >，不是 >=）。
    limiter = RateLimiter(rate_per_sec=1.0, burst=1)
    now = time.monotonic()
    boundary_key = "boundary-ip"
    with limiter._lock:
        limiter._buckets[boundary_key] = (0.5, now - ratelimit._IDLE_SECONDS)

    # act: 复用同一个 now，消除两次 time.monotonic() 之间的 epsilon，
    # 使 now - last 精确等于阈值，验证"等于不删除"的边界语义。
    with limiter._lock:
        limiter._evict_idle(now)

    # assert: 边界桶保留；桶内容未被篡改。
    assert boundary_key in limiter._buckets
    tokens, last = limiter._buckets[boundary_key]
    assert tokens == 0.5


def test_bucket_overflow_triggers_lazy_eviction():
    # arrange: 把桶数顶到 _MAX_BUCKETS 之上，全部标为过期。
    limiter = RateLimiter(rate_per_sec=1.0, burst=1)
    now = time.monotonic()
    over = ratelimit._MAX_BUCKETS + 10
    with limiter._lock:
        for i in range(over):
            limiter._buckets[f"ip-{i}"] = (1.0, now - ratelimit._IDLE_SECONDS - 1.0)

    # act: 触发一次 allow，应触发惰性清理。
    ok, retry = limiter.allow("trigger-ip")

    # assert: 触发请求放行；清理后桶数大幅下降。
    assert ok is True
    assert retry == 0.0
    with limiter._lock:
        remaining = len(limiter._buckets)
    assert remaining < over
    assert remaining <= 2


# ---------------------------------------------------------------------------
# 并发与线程安全
# ---------------------------------------------------------------------------

def test_concurrent_allow_respects_burst_limit():
    # arrange: 容量 50，速率 0（不允许自然补充），20 个线程各请求 10 次。
    limiter = RateLimiter(rate_per_sec=0.0, burst=50)
    threads = 20
    per_thread = 10
    barrier = threading.Barrier(threads)
    passed = []
    passed_lock = threading.Lock()

    def worker():
        barrier.wait()
        local = 0
        for _ in range(per_thread):
            ok, _ = limiter.allow("shared-key")
            if ok:
                local += 1
        with passed_lock:
            passed.append(local)

    # act
    workers = [threading.Thread(target=worker) for _ in range(threads)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()

    # assert: 总放行数恰好等于 burst，不会超发。
    total_passed = sum(passed)
    assert total_passed == 50
    assert len(passed) == threads
    with limiter._lock:
        tokens, _ = limiter._buckets["shared-key"]
    assert tokens == pytest.approx(0.0, abs=1e-6)


def test_concurrent_distinct_keys_no_cross_contention():
    # arrange: 每个线程独立 key，容量 1，速率 0。
    limiter = RateLimiter(rate_per_sec=0.0, burst=1)
    threads = 30
    results = [None] * threads
    barrier = threading.Barrier(threads)

    def worker(idx: int):
        barrier.wait()
        results[idx] = limiter.allow(f"key-{idx}")

    # act
    workers = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()

    # assert: 每个 key 首次都放行，互不干扰。
    assert all(r is not None for r in results)
    assert all(r[0] is True for r in results)
    assert all(r[1] == 0.0 for r in results)


# ---------------------------------------------------------------------------
# 边界与不变量
# ---------------------------------------------------------------------------

def test_zero_rate_never_refills():
    # arrange: 速率 0，容量 2。
    limiter = RateLimiter(rate_per_sec=0.0, burst=2)

    # act
    a = limiter.allow("0.0.0.0")
    b = limiter.allow("0.0.0.0")
    time.sleep(0.05)
    c = limiter.allow("0.0.0.0")

    # assert: 只有 burst 次放行，等待也无法补充。
    assert a[0] is True
    assert b[0] is True
    assert c[0] is False


def test_empty_key_is_valid_bucket():
    # arrange: 空字符串也是合法 key。
    limiter = RateLimiter(rate_per_sec=0.0, burst=1)

    # act
    first = limiter.allow("")
    second = limiter.allow("")

    # assert: 空 key 独立成桶，行为与普通 key 一致。
    assert first[0] is True
    assert second[0] is False
    assert "" in limiter._buckets


def test_retry_after_formula_matches_token_deficit():
    # arrange: 速率 2/s，容量 1，耗尽后立刻请求。
    limiter = RateLimiter(rate_per_sec=2.0, burst=1)
    limiter.allow("5.5.5.5")

    # act
    ok, retry_after = limiter.allow("5.5.5.5")

    # assert: 拒绝。
    assert ok is False

    # assert: 2/s 补 1 个令牌需 0.5 秒，落在 0.1 秒网格上。
    assert retry_after == pytest.approx(0.5, abs=0.15)
    assert retry_after == math.ceil(retry_after * 10.0) / 10.0