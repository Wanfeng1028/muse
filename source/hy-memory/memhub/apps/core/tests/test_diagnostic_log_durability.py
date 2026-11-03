"""写线程报告的「已落盘」必须是真的。

第一版把写入挪到后台线程后，出现了一类新的谎言：批次已经从队列里摘走、
写入抛了异常被吞掉、`_drained` 照样被置位 —— 于是 `flush()` 返回 True，
磁盘上什么都没有。这里用注入故障复现这组问题并固定为回归守卫。

这些断言的共同形状是：**不许用「我已经尽力了」冒充「数据在盘上」。**
"""

from __future__ import annotations

import json
import os
import threading
import time

import pytest

import one_memory.diagnostic_log as module
from one_memory.diagnostic_log import DiagnosticLog


def _emit(log: DiagnosticLog, index: int) -> None:
    log.write(
        level="info",
        component="memory.scheduler",
        event="memory_scheduler.idle",
        outcome="succeeded",
        details={"count": index},
    )


def _lines(log: DiagnosticLog) -> list[str]:
    if not log.path.exists():
        return []
    return [line for line in log.path.read_text(encoding="utf-8").splitlines() if line]


def _events(log: DiagnosticLog) -> list[dict[str, object]]:
    return [json.loads(line) for line in _lines(log)]


class _BrokenDisk:
    """让诊断文件写不进去，并且可以随时修好。"""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.failing = True
        self.opened = 0
        real_open = os.open

        def guarded(path, flags, mode=0o777, **kwargs):  # type: ignore[no-untyped-def]
            if str(path).endswith("diagnostic-core.jsonl"):
                self.opened += 1
                if self.failing:
                    raise OSError("disk is full")
            return real_open(path, flags, mode, **kwargs)

        monkeypatch.setattr(os, "open", guarded)


def test_flush_does_not_claim_success_when_the_write_failed(tmp_path, monkeypatch):
    """旧实现会失败：批次摘走 → 写入抛错被吞 → 仍然置位已排空。"""
    disk = _BrokenDisk(monkeypatch)
    log = DiagnosticLog(tmp_path)
    for index in range(5):
        _emit(log, index)

    persisted = log.flush(timeout=3)

    assert disk.opened > 0, "写线程根本没尝试写，这条守卫就失去意义了"
    assert _lines(log) == [], "盘上不该有内容"
    assert not persisted, "写入失败了，flush() 却报告已落盘"
    log.close(timeout=3)


def test_a_failed_batch_is_not_thrown_away_before_the_disk_recovers(tmp_path, monkeypatch):
    """盘坏时摘走的事件不许当成写过了；盘好了要么补上，要么明确记账。"""
    disk = _BrokenDisk(monkeypatch)
    log = DiagnosticLog(tmp_path)
    for index in range(5):
        _emit(log, index)
    log.flush(timeout=3)

    disk.failing = False
    for index in range(5, 10):
        _emit(log, index)
    assert log.close(timeout=10)

    events = _events(log)
    kept = [
        int(item["details"]["count"])  # type: ignore[index]
        for item in events
        if item["event"] == "memory_scheduler.idle"
    ]
    lost = sum(
        int(item["details"]["count"])  # type: ignore[index]
        for item in events
        if item["event"] == "diagnostic.events_dropped"
    )
    assert kept, "盘恢复之后连新事件都没写进去"
    # 要么 10 条都在，要么少掉的那些被明确记了账 —— 不许静默消失。
    assert len(kept) + lost == 10, f"10 条里只交代了 {len(kept)} 条留存 + {lost} 条记账"


def test_a_short_write_never_leaves_a_half_line_on_disk(tmp_path, monkeypatch):
    """os.write 可以只写一部分。返回值不看，文件里就会出现半截 JSON。"""
    real_write = os.write
    state = {"short": True}

    def short(descriptor, data):  # type: ignore[no-untyped-def]
        if state["short"] and data.startswith(b'{"schema_version"') and len(data) > 24:
            state["short"] = False
            return real_write(descriptor, data[:20])
        return real_write(descriptor, data)

    monkeypatch.setattr(os, "write", short)
    log = DiagnosticLog(tmp_path)
    for index in range(6):
        _emit(log, index)
        log.flush(timeout=3)
    assert log.close(timeout=5)

    for line in _lines(log):
        json.loads(line)  # 半截 JSON 会在这里炸
    assert len(_lines(log)) == 6, "短写之后行数对不上"


def test_a_clean_shutdown_actually_reaches_the_disk(tmp_path, monkeypatch):
    """承诺了退出时刷一次盘，就必须真的刷。

    旧实现里只有「写线程在观察到 closed 之后恰好又取到一批」才会 fsync。
    正常关停是 flush() 先把最后一条排空、close() 再进来时已经没有批次了，
    于是那次 fsync 从来没发生过。
    """
    synced = []
    real_fsync = os.fsync

    def counting(descriptor):  # type: ignore[no-untyped-def]
        synced.append(descriptor)
        return real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", counting)
    log = DiagnosticLog(tmp_path)
    _emit(log, 1)
    assert log.flush(timeout=3)  # 正常关停的顺序：先排空
    assert not synced, "排空阶段不该刷盘，那是每事件 fsync 的老毛病"

    assert log.close(timeout=5)
    assert synced, "干净退出没有刷过盘，STATUS 里的耐久性承诺是空的"


def test_close_does_not_claim_success_while_the_writer_is_still_stuck(tmp_path, monkeypatch):
    """第一次 close 超时之后，第二次不许因为「已经标记关闭」就报成功。"""
    release = threading.Event()
    real_write = os.write

    def blocking(descriptor, data):  # type: ignore[no-untyped-def]
        if data.startswith(b'{"schema_version"'):
            release.wait(30)
        return real_write(descriptor, data)

    monkeypatch.setattr(os, "write", blocking)
    log = DiagnosticLog(tmp_path)
    _emit(log, 1)
    time.sleep(0.1)

    try:
        assert not log.close(timeout=0.2), "写线程还卡着，第一次 close 不该报成功"
        assert not log.close(timeout=0.2), "写线程还卡着，第二次 close 更不该报成功"
    finally:
        release.set()
    assert log.close(timeout=10), "放开之后应该能正常收尾"


def test_every_emitted_event_is_either_on_disk_or_counted_as_dropped(tmp_path, monkeypatch):
    """守住账：留存 + 丢弃 == 发出。只断言「丢弃数 > 0」是放过了漏账。"""
    monkeypatch.setattr(module, "MAX_QUEUED_EVENTS", 4, raising=False)
    real_write = os.write

    def slow(descriptor, data):  # type: ignore[no-untyped-def]
        if data.startswith(b'{"schema_version"'):
            time.sleep(0.05)
        return real_write(descriptor, data)

    monkeypatch.setattr(os, "write", slow)
    log = DiagnosticLog(tmp_path)
    emitted = 120
    for index in range(emitted):
        _emit(log, index)
    assert log.close(timeout=30)

    events = _events(log)
    kept = sum(1 for item in events if item["event"] == "memory_scheduler.idle")
    dropped = sum(
        int(item["details"]["count"])  # type: ignore[index]
        for item in events
        if item["event"] == "diagnostic.events_dropped"
    )
    assert dropped > 0, "队列上限没触发，这轮没测到东西"
    assert kept + dropped == emitted, f"发了 {emitted}，只交代了 {kept} 留存 + {dropped} 丢弃"


def test_the_directory_is_scanned_once_per_throttle_window_not_once_per_batch(
    tmp_path, monkeypatch
):
    """用 flush 强制每条事件单独成批，避免「凑成一批」把弱断言蒙混过去。"""
    scans = []
    real_glob = type(tmp_path).glob
    root = (tmp_path / "logs").resolve()

    def counting(this, pattern, **kwargs):  # type: ignore[no-untyped-def]
        if this.resolve() == root:
            scans.append(pattern)
        return real_glob(this, pattern, **kwargs)

    monkeypatch.setattr(type(tmp_path), "glob", counting)
    log = DiagnosticLog(tmp_path)
    for index in range(20):
        _emit(log, index)
        assert log.flush(timeout=3)

    assert len(_lines(log)) == 20, "没有真的每条单独落盘，这条守卫就没意义"
    assert len(scans) == 1, f"20 个独立批次扫了 {len(scans)} 次目录，节流没生效"
    log.close(timeout=5)


def test_no_fsync_happens_before_shutdown_even_across_many_batches(tmp_path, monkeypatch):
    """同样用 flush 拆成 20 个独立批次：关停前一次 fsync 都不该有。"""
    synced = []
    real_fsync = os.fsync

    def counting(descriptor):  # type: ignore[no-untyped-def]
        synced.append(descriptor)
        return real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", counting)
    log = DiagnosticLog(tmp_path)
    for index in range(20):
        _emit(log, index)
        assert log.flush(timeout=3)

    assert len(_lines(log)) == 20
    assert synced == [], f"关停前刷了 {len(synced)} 次盘"
    assert log.close(timeout=5)
    assert len(synced) == 1, f"关停时应当恰好刷一次，实际 {len(synced)} 次"
