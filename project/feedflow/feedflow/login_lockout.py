import math
import sqlite3
import threading
import time


class LoginLockout:
    def __init__(self, max_attempts=5, window_seconds=900, lock_seconds=900,
                 time_fn=None, db_path=None):
        # 参数验证
        if max_attempts < 1 or window_seconds < 1 or lock_seconds < 1:
            raise ValueError("max_attempts, window_seconds, and lock_seconds must be >= 1")

        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._lock_seconds = lock_seconds
        self._db_path = db_path
        self._db_mode = db_path is not None
        self._store = {} if not self._db_mode else None

        # 根据模式选择时间源
        if self._db_mode:
            self._time_fn = time_fn if time_fn is not None else time.time
        else:
            self._time_fn = time_fn if time_fn is not None else time.monotonic

        self._lock = threading.Lock()
        if self._db_mode:
            self._ensure_table()

    def _ensure_table(self):
        # Use a short-lived connection
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS login_lockouts (ip TEXT PRIMARY KEY, failures INTEGER NOT NULL, first_fail REAL NOT NULL, locked_until REAL)')
        conn.commit()
        conn.close()

    def is_locked(self, key, now=None):
        if now is None:
            now = self._time_fn()

        with self._lock:
            if not self._db_mode:
                # 原生 dict 模式
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
            else:
                # SQLite 持久化模式
                with sqlite3.connect(self._db_path) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT locked_until FROM login_lockouts WHERE ip = ?",
                        (key,)
                    )
                    row = cur.fetchone()
                    if row is None:
                        return False
                    locked_until = row[0]
                    if locked_until is None:
                        return False
                    if now < locked_until:
                        return True
                    # 锁定已过期，删除记录
                    cur.execute(
                        "DELETE FROM login_lockouts WHERE ip = ?",
                        (key,)
                    )
                    conn.commit()
                    return False

    def record_failure(self, key, now=None):
        if now is None:
            now = self._time_fn()

        with self._lock:
            if not self._db_mode:
                # 原生 dict 模式
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
            else:
                # SQLite 持久化模式
                with sqlite3.connect(self._db_path) as conn:
                    cur = conn.cursor()
                    # 删除当前 ip 的过期记录（锁定期或窗口期）
                    cur.execute(
                        """
                        DELETE FROM login_lockouts
                        WHERE ip = ?
                          AND (locked_until <= ? OR
                               (locked_until IS NULL AND first_fail + ? <= ?))
                        """,
                        (key, now, self._window_seconds, now)
                    )
                    # 查询当前状态
                    cur.execute(
                        "SELECT failures, first_fail, locked_until FROM login_lockouts WHERE ip = ?",
                        (key,)
                    )
                    row = cur.fetchone()
                    if row is not None:
                        failures, first_fail, locked_until = row
                        if locked_until is not None and now < locked_until:
                            remaining = locked_until - now
                            conn.commit()
                            return (True, remaining)
                        if now - first_fail >= self._window_seconds:
                            # 窗口期结束，重置计数
                            cur.execute(
                                "REPLACE INTO login_lockouts (ip, failures, first_fail, locked_until) VALUES (?, ?, ?, ?)",
                                (key, 1, now, None)
                            )
                            conn.commit()
                            return (False, 0.0)
                        # 窗口内失败累积
                        new_fail = failures + 1
                        cur.execute(
                            "UPDATE login_lockouts SET failures = ? WHERE ip = ?",
                            (new_fail, key)
                        )
                        if new_fail >= self._max_attempts:
                            locked_until = now + self._lock_seconds
                            cur.execute(
                                "UPDATE login_lockouts SET locked_until = ? WHERE ip = ?",
                                (locked_until, key)
                            )
                            conn.commit()
                            return (True, float(self._lock_seconds))
                        conn.commit()
                        return (False, 0.0)
                    else:
                        # 首次失败，插入新记录
                        cur.execute(
                            "INSERT INTO login_lockouts (ip, failures, first_fail, locked_until) VALUES (?, ?, ?, ?)",
                            (key, 1, now, None)
                        )
                        conn.commit()
                        return (False, 0.0)

    def record_success(self, key):
        with self._lock:
            if not self._db_mode:
                self._store.pop(key, None)
            else:
                with sqlite3.connect(self._db_path) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "DELETE FROM login_lockouts WHERE ip = ?",
                        (key,)
                    )
                    conn.commit()

    def retry_after(self, key, now=None):
        if now is None:
            now = self._time_fn()

        with self._lock:
            if not self._db_mode:
                entry = self._store.get(key)
                if entry is not None and entry["locked_until"] is not None and now < entry["locked_until"]:
                    return max(1, math.ceil(entry["locked_until"] - now))
                return 0
            else:
                with sqlite3.connect(self._db_path) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT locked_until FROM login_lockouts WHERE ip = ?",
                        (key,)
                    )
                    row = cur.fetchone()
                    if row is None:
                        return 0
                    locked_until = row[0]
                    if locked_until is not None:
                        if now < locked_until:
                            return max(1, math.ceil(locked_until - now))
                        else:
                            # 锁定已过期，清除记录
                            cur.execute(
                                "DELETE FROM login_lockouts WHERE ip = ?",
                                (key,)
                            )
                            conn.commit()
                            return 0
                    return 0

    def _maybe_cleanup(self, now):
        # 仅用于原生 dict 模式；持久化模式不会调用此方法
        if len(self._store) <= 10000:
            return
        expired_keys = []
        for k, v in self._store.items():
            if v["locked_until"] is not None and now >= v["locked_until"] or \
               v["locked_until"] is None and now - v["first_fail"] >= self._window_seconds:
                expired_keys.append(k)
        for k in expired_keys:
            del self._store[k]
