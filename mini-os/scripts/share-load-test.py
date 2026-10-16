#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mini-os 分享读接口压测脚本

用法示例:
    python3 scripts/share-load-test.py --rpm 30 --burst 30 --duration 20 --concurrency 8

流程:
    1. 起 mini-os serve 子进程 (PORT=18099, DATABASE_PATH 指向临时 db)
    2. 轮询 /api/health 等待就绪 (最多 15s)
    3. 注册用户 -> 建文件 -> 建分享 (得到主 token)
    4. 再建第二个分享 (作为"正常用户不受影响"对照 token)
    5. 多线程按固定并发压 GET /api/s/{token}, duration 秒后停
    6. 统计: 总请求数 / 200 / 429 / Retry-After 分布 / p50 / p99
    7. 压测结束后立即用第二 token 请求 5 次, 统计 200 比例
    8. finally 中 kill 服务进程 + 删除临时 db

仅使用 python3 标准库。
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# 路径 / 常量
# ---------------------------------------------------------------------------

# 脚本所在目录 (scripts/)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 仓库根目录 (scripts/ 的上一级)
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
# mini-os 二进制
BIN_PATH = os.path.join(REPO_ROOT, "target", "release", "mini-os")
# static 目录
STATIC_DIR = os.path.join(REPO_ROOT, "static")
# 临时 db 路径 (脚本同目录下)
TMP_DB_PATH = os.path.join(SCRIPT_DIR, "test-share-load.db")
# 固定端口
PORT = 18099
BASE_URL = "http://127.0.0.1:%d" % PORT
HEALTH_URL = BASE_URL + "/api/health"


# ---------------------------------------------------------------------------
# HTTP 辅助
# ---------------------------------------------------------------------------

def http_request(method, url, body=None, headers=None, cookie=None, timeout=10):
    """发一个 HTTP 请求, 返回 (status, headers_dict, body_bytes)。

    不抛异常, 网络错误返回 (None, {}, b"")。
    """
    hdrs = {}
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
    if cookie:
        hdrs["Cookie"] = cookie

    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        # 4xx/5xx 也属于正常响应, 读取 body
        try:
            body_bytes = e.read()
        except Exception:
            body_bytes = b""
        return e.code, dict(e.headers) if e.headers else {}, body_bytes
    except Exception:
        return None, {}, b""


def get_set_cookie(headers):
    """从响应头中提取 Set-Cookie 的 cookie 键值对 (仅第一段)。"""
    raw = headers.get("Set-Cookie") or headers.get("set-cookie")
    if not raw:
        return None
    # 只取 "name=value" 部分
    return raw.split(";")[0].strip()


# ---------------------------------------------------------------------------
# 服务生命周期
# ---------------------------------------------------------------------------

def start_server(rpm, burst, log_file):
    """启动 mini-os serve 子进程, 返回 Popen 对象。"""
    env = dict(os.environ)
    env["PORT"] = str(PORT)
    env["DATABASE_PATH"] = TMP_DB_PATH
    env["STATIC_DIR"] = STATIC_DIR
    env["MINIOS_SHARE_READ_RPM"] = str(rpm)
    env["MINIOS_SHARE_READ_BURST"] = str(burst)

    log_fp = open(log_file, "wb")
    proc = subprocess.Popen(
        [BIN_PATH, "serve"],
        env=env,
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        cwd=REPO_ROOT,
    )
    # 把日志文件句柄挂在 proc 上, 便于后续关闭
    proc._log_fp = log_fp  # type: ignore[attr-defined]
    return proc


def wait_ready(timeout_s=15.0):
    """轮询 /api/health 直到返回 200, 超时返回 False。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status, _, _ = http_request("GET", HEALTH_URL, timeout=2)
        if status == 200:
            return True
        time.sleep(0.2)
    return False


def stop_server(proc):
    """尽力终止服务进程。"""
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
    except Exception:
        pass
    finally:
        log_fp = getattr(proc, "_log_fp", None)
        if log_fp is not None:
            try:
                log_fp.close()
            except Exception:
                pass


def port_in_use():
    """检测目标端口是否已被占用 (用于端口冲突时快速报错)。"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except Exception:
        return False
    finally:
        s.close()


# ---------------------------------------------------------------------------
# 业务准备
# ---------------------------------------------------------------------------

def setup_business():
    """注册用户 -> 建文件 -> 建分享。

    返回 (main_token, second_token)。
    """
    username = "loaduser_%d" % int(time.time() * 1000 % 10**9)
    password = "loadpass123"

    # 注册
    status, headers, body = http_request(
        "POST", BASE_URL + "/api/auth/register",
        body={"username": username, "password": password},
    )
    if status not in (200, 201):
        raise RuntimeError("注册失败: status=%s body=%s" % (status, body[:200]))
    cookie = get_set_cookie(headers)
    if not cookie:
        raise RuntimeError("注册响应缺少 Set-Cookie: headers=%s" % headers)

    # 建文件
    content = "x" * 1024
    status, _, body = http_request(
        "POST", BASE_URL + "/api/fs",
        body={"name": "load.txt", "kind": "file", "content": content},
        cookie=cookie,
    )
    if status not in (200, 201):
        raise RuntimeError("建文件失败: status=%s body=%s" % (status, body[:200]))
    try:
        node = json.loads(body.decode("utf-8"))
    except Exception as e:
        raise RuntimeError("建文件响应解析失败: %s body=%s" % (e, body[:200]))
    node_id = node.get("id") or node.get("nodeId") or node.get("node_id")
    if not node_id:
        raise RuntimeError("建文件响应缺少 id: %s" % node)

    # 建分享 1 (主 token)
    status, _, body = http_request(
        "POST", BASE_URL + "/api/shares",
        body={"nodeId": node_id},
        cookie=cookie,
    )
    if status not in (200, 201):
        raise RuntimeError("建分享1失败: status=%s body=%s" % (status, body[:200]))
    try:
        share1 = json.loads(body.decode("utf-8"))
    except Exception as e:
        raise RuntimeError("建分享1响应解析失败: %s body=%s" % (e, body[:200]))
    main_token = share1.get("token")
    if not main_token:
        raise RuntimeError("建分享1响应缺少 token: %s" % share1)

    # 建分享 2 (对照 token, 用于验证正常用户不受影响)
    status, _, body = http_request(
        "POST", BASE_URL + "/api/shares",
        body={"nodeId": node_id},
        cookie=cookie,
    )
    if status not in (200, 201):
        raise RuntimeError("建分享2失败: status=%s body=%s" % (status, body[:200]))
    try:
        share2 = json.loads(body.decode("utf-8"))
    except Exception as e:
        raise RuntimeError("建分享2响应解析失败: %s body=%s" % (e, body[:200]))
    second_token = share2.get("token")
    if not second_token:
        raise RuntimeError("建分享2响应缺少 token: %s" % share2)

    return main_token, second_token


# ---------------------------------------------------------------------------
# 压测主体
# ---------------------------------------------------------------------------

class LoadStats:
    """线程安全的压测统计容器。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.total = 0
        self.ok_200 = 0
        self.limited_429 = 0
        self.other = 0
        self.retry_after_values = []
        self.latencies_ms = []  # 仅 200 的延迟

    def record(self, status, retry_after, latency_ms):
        with self.lock:
            self.total += 1
            if status == 200:
                self.ok_200 += 1
                self.latencies_ms.append(latency_ms)
            elif status == 429:
                self.limited_429 += 1
                if retry_after is not None:
                    self.retry_after_values.append(retry_after)
            else:
                self.other += 1


def worker(url, stop_event, stats):
    """压测线程: 循环请求直到 stop_event 被设置。"""
    while not stop_event.is_set():
        t0 = time.time()
        status, headers, _ = http_request("GET", url, timeout=10)
        t1 = time.time()
        latency_ms = (t1 - t0) * 1000.0

        retry_after = None
        if status == 429:
            ra = headers.get("Retry-After") or headers.get("retry-after")
            if ra is not None:
                try:
                    retry_after = int(ra)
                except (ValueError, TypeError):
                    retry_after = None
        stats.record(status, retry_after, latency_ms)


def run_load(token, duration_s, concurrency):
    """按固定并发压 duration 秒, 返回 LoadStats。"""
    url = BASE_URL + "/api/s/" + token
    stats = LoadStats()
    stop_event = threading.Event()
    threads = []
    for _ in range(concurrency):
        t = threading.Thread(target=worker, args=(url, stop_event, stats), daemon=True)
        t.start()
        threads.append(t)

    time.sleep(duration_s)
    stop_event.set()

    for t in threads:
        t.join(timeout=5)

    return stats


def percentile(values, p):
    """计算百分位 (线性插值)。values 需非空。"""
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return float(d0 + d1)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="mini-os 分享读接口压测")
    parser.add_argument("--rpm", type=int, default=30, help="每分钟允许的分享读请求数")
    parser.add_argument("--burst", type=int, default=30, help="令牌桶突发容量")
    parser.add_argument("--duration", type=int, default=20, help="压测持续秒数")
    parser.add_argument("--concurrency", type=int, default=8, help="并发线程数")
    args = parser.parse_args()

    if args.duration <= 0:
        print("错误: --duration 必须 > 0", file=sys.stderr)
        sys.exit(1)
    if args.concurrency <= 0:
        print("错误: --concurrency 必须 > 0", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(BIN_PATH):
        print("错误: 未找到 mini-os 二进制: %s" % BIN_PATH, file=sys.stderr)
        print("请先执行: cargo build --release", file=sys.stderr)
        sys.exit(1)

    # 端口占用检查: 快速失败, 不悬挂进程
    if port_in_use():
        print("错误: 端口 %d 已被占用, 请先释放" % PORT, file=sys.stderr)
        sys.exit(1)

    # 清理可能残留的旧临时 db
    try:
        if os.path.exists(TMP_DB_PATH):
            os.remove(TMP_DB_PATH)
    except Exception:
        pass

    log_file = os.path.join(tempfile.gettempdir(), "mini-os-share-load.log")
    proc = None
    try:
        print("[*] 启动 mini-os serve (PORT=%d, rpm=%d, burst=%d)" % (PORT, args.rpm, args.burst))
        proc = start_server(args.rpm, args.burst, log_file)

        print("[*] 等待 /api/health 就绪 (最多 15s)...")
        if not wait_ready(timeout_s=15.0):
            print("错误: 服务未在 15s 内就绪, 日志: %s" % log_file, file=sys.stderr)
            sys.exit(1)
        print("[*] 服务已就绪")

        # 业务准备
        print("[*] 准备业务数据 (注册/建文件/建分享)...")
        main_token, second_token = setup_business()
        print("[*] 主 token=%s..., 对照 token=%s..." % (main_token[:8], second_token[:8]))

        # 压测
        print("[*] 开始压测: duration=%ds concurrency=%d" % (args.duration, args.concurrency))
        stats = run_load(main_token, args.duration, args.concurrency)

        # 正常用户不受影响验证: 压测结束后立即用第二 token 请求 5 次
        print("[*] 验证正常用户不受影响 (第二 token x5)...")
        second_url = BASE_URL + "/api/s/" + second_token
        second_ok = 0
        for _ in range(5):
            status, _, _ = http_request("GET", second_url, timeout=10)
            if status == 200:
                second_ok += 1
            # 轻微间隔, 避免瞬时突发
            time.sleep(0.05)
        second_ok_ratio = second_ok / 5.0

        # 统计
        latencies = stats.latencies_ms
        p50 = percentile(latencies, 50) if latencies else 0.0
        p99 = percentile(latencies, 99) if latencies else 0.0

        retry_dist = {}
        for v in stats.retry_after_values:
            retry_dist[v] = retry_dist.get(v, 0) + 1

        # 人类可读摘要
        print("")
        print("========== 压测结果摘要 ==========")
        print("rpm                     : %d" % args.rpm)
        print("burst                   : %d" % args.burst)
        print("duration_s              : %d" % args.duration)
        print("concurrency             : %d" % args.concurrency)
        print("total                   : %d" % stats.total)
        print("ok_200                  : %d" % stats.ok_200)
        print("limited_429             : %d" % stats.limited_429)
        print("other                   : %d" % stats.other)
        print("retry_after_values      : %s" % json.dumps(retry_dist, sort_keys=True))
        print("p50_ms                  : %.2f" % p50)
        print("p99_ms                  : %.2f" % p99)
        print("other_token_ok_ratio    : %.2f" % second_ok_ratio)
        print("==================================")
        print("")

        # 一行 JSON
        result = {
            "rpm": args.rpm,
            "burst": args.burst,
            "duration_s": args.duration,
            "concurrency": args.concurrency,
            "total": stats.total,
            "ok_200": stats.ok_200,
            "limited_429": stats.limited_429,
            "retry_after_values": retry_dist,
            "p50_ms": round(p50, 2),
            "p99_ms": round(p99, 2),
            "other_token_ok_ratio": round(second_ok_ratio, 2),
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))

    finally:
        # 进程清理
        stop_server(proc)
        # 临时 db 清理
        try:
            if os.path.exists(TMP_DB_PATH):
                os.remove(TMP_DB_PATH)
        except Exception:
            pass


if __name__ == "__main__":
    main()
