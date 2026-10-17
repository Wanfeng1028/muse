"""内存令牌桶 IP 限流器。

语义：
- 每个 key（IP 字符串）一个令牌桶，容量 burst，每秒补充 rate_per_sec 个令牌。
- 每次请求消耗 1 个令牌；令牌不足 1 则拒绝。
- 时间源使用 time.monotonic()，单调递增不受系统时钟回拨影响。
- 无第三方依赖；内部使用 threading.Lock 保护共享状态。
"""

from __future__ import annotations

import math
import threading
import time

# 触发清理的桶数量阈值：超过后尝试清理长时间未活动的桶。
_MAX_BUCKETS = 10000
# 清理判定阈值：last 距现在超过该秒数视为不活跃。
_IDLE_SECONDS = 600.0


class RateLimiter:
    """内存令牌桶限流器。"""

    def __init__(self, rate_per_sec: float, burst: int) -> None:
        self._rate = float(rate_per_sec)
        self._burst = int(burst)
        self._lock = threading.Lock()
        # key -> (tokens: float, last: float)
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str) -> tuple[bool, float]:
        """尝试消费 1 个令牌。

        返回 (是否放行, retry_after 秒数)。被拒绝时 retry_after > 0，
        精确到 0.1 秒（向上取整）。
        """
        now = time.monotonic()
        with self._lock:
            # 防内存膨胀：桶数超阈值时做一次惰性清理。
            if len(self._buckets) > _MAX_BUCKETS:
                self._evict_idle(now)

            tokens, last = self._buckets.get(key, (float(self._burst), now))

            # 按经过时间补充令牌，上限为 burst。
            elapsed = now - last
            if elapsed > 0:
                tokens = min(float(self._burst), tokens + elapsed * self._rate)

            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[key] = (tokens, now)
                return True, 0.0

            # 令牌不足：计算需要等待多久才能攒够 1 个令牌。
            # 速率为 0 表示永不补充，直接返回正无穷。
            if self._rate > 0:
                retry_after = (1.0 - tokens) / self._rate
                retry_after = math.ceil(retry_after * 10.0) / 10.0
            else:
                retry_after = math.inf
            self._buckets[key] = (tokens, now)
            return False, retry_after

    def _evict_idle(self, now: float) -> None:
        """清理长时间未活动的桶。调用方需持有锁。"""
        stale = [
            k
            for k, (_, last) in self._buckets.items()
            if now - last > _IDLE_SECONDS
        ]
        for k in stale:
            self._buckets.pop(k, None)
