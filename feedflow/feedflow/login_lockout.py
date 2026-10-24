import math
import threading
import time


class LoginLockout:
    def __init__(self, max_attempts=5, window_seconds=900, lock_seconds=900, time_fn=None):
        if max_attempts < 1 or window_seconds < 1 or lock_seconds < 1:
            raise ValueError("max_attempts, window_seconds, and lock_seconds must be >= 1")
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._lock_seconds = lock_seconds
        self._time_fn = time_fn if time_fn is not None else time.monotonic
        self._store = {}
        self._lock = threading.Lock()

    def is_locked(self, key, now=None):
        if now is None:
            now = self._time_fn()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            locked_until = entry["locked_until"]
            if locked_until is None:
                return False
            if now < locked_until:
                return True
            del self._store[key]
            return False

    def record_failure(self, key, now=None):
        if now is None:
            now = self._time_fn()
        with self._lock:
            self._maybe_cleanup(now)
            entry = self._store.get(key)
            if entry is not None and entry["locked_until"] is not None and now < entry["locked_until"]:
                remaining = entry["locked_until"] - now
                return (True, remaining)
            if entry is not None and now - entry["first_fail"] >= self._window_seconds:
                entry["failures"] = 1
                entry["first_fail"] = now
                entry["locked_until"] = None
            elif entry is not None:
                entry["failures"] += 1
            else:
                entry = {"failures": 1, "first_fail": now, "locked_until": None}
                self._store[key] = entry
            if entry["failures"] >= self._max_attempts:
                entry["locked_until"] = now + self._lock_seconds
                return (True, float(self._lock_seconds))
            return (False, 0.0)

    def record_success(self, key):
        with self._lock:
            self._store.pop(key, None)

    def retry_after(self, key, now=None):
        if now is None:
            now = self._time_fn()
        with self._lock:
            entry = self._store.get(key)
            if entry is not None and entry["locked_until"] is not None and now < entry["locked_until"]:
                return max(1, math.ceil(entry["locked_until"] - now))
            return 0

    def _maybe_cleanup(self, now):
        if len(self._store) <= 10000:
            return
        expired_keys = []
        for k, v in self._store.items():
            if v["locked_until"] is not None and now >= v["locked_until"] or v["locked_until"] is None and now - v["first_fail"] >= self._window_seconds:
                expired_keys.append(k)
        for k in expired_keys:
            del self._store[k]
