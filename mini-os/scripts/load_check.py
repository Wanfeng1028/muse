#!/usr/bin/env python3
"""真实负载验证脚本（python3 标准库 only）。"""

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request


def post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read()
        return resp.status, body


def get_json(url):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read()
        return resp.status, body


def main():
    parser = argparse.ArgumentParser(description="mini-os 真实负载验证")
    parser.add_argument("--base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--files", type=int, default=300)
    parser.add_argument("--download-sample", type=int, default=30)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    n = args.files
    k = args.download_sample

    print(f"base-url: {base_url}")
    print(f"files: {n}")
    print(f"download-sample: {k}")

    created_ids = []
    latencies_ms = []

    for i in range(n):
        payload = {
            "parentId": None,
            "name": f"load-{i}",
            "kind": "file",
            "content": str(i),
        }
        t0 = time.monotonic()
        try:
            status, body = post_json(f"{base_url}/api/fs", payload)
        except Exception as exc:
            print(f"创建第 {i + 1} 个文件失败：请求异常 {exc}", file=sys.stderr)
            return 1
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)
        if status != 201:
            print(f"创建第 {i + 1} 个文件失败：HTTP {status}", file=sys.stderr)
            return 1
        try:
            node = json.loads(body.decode("utf-8"))
            created_ids.append(node["id"])
        except Exception as exc:
            print(f"创建第 {i + 1} 个文件失败：解析响应出错 {exc}", file=sys.stderr)
            return 1

    total_s = sum(latencies_ms) / 1000.0
    avg_ms = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
    max_ms = max(latencies_ms) if latencies_ms else 0.0

    try:
        status, body = get_json(f"{base_url}/api/fs")
    except Exception as exc:
        print(f"GET /api/fs 失败：请求异常 {exc}", file=sys.stderr)
        return 1
    if status != 200:
        print(f"GET /api/fs 失败：HTTP {status}", file=sys.stderr)
        return 1
    try:
        nodes = json.loads(body.decode("utf-8"))
    except Exception as exc:
        print(f"GET /api/fs 解析失败：{exc}", file=sys.stderr)
        return 1
    if not isinstance(nodes, list):
        print("GET /api/fs 返回值不是数组", file=sys.stderr)
        return 1
    if len(nodes) < n:
        print(f"GET /api/fs 数量不足：期望 >= {n}，实际 {len(nodes)}", file=sys.stderr)
        return 1

    rng = random.Random(42)
    sample_size = min(k, len(created_ids))
    sample_ids = rng.sample(created_ids, sample_size)
    verified = 0
    for node_id in sample_ids:
        try:
            status, body = get_json(f"{base_url}/api/fs/{node_id}")
        except Exception as exc:
            print(f"校验节点 {node_id} 失败：请求异常 {exc}", file=sys.stderr)
            return 1
        if status != 200:
            print(f"校验节点 {node_id} 失败：HTTP {status}", file=sys.stderr)
            return 1
        try:
            node = json.loads(body.decode("utf-8"))
        except Exception as exc:
            print(f"校验节点 {node_id} 解析失败：{exc}", file=sys.stderr)
            return 1
        expected = node.get("name", "")
        if expected.startswith("load-"):
            expected_content = expected[len("load-"):]
        else:
            expected_content = None
        if node.get("content") != expected_content:
            print(
                f"校验节点 {node_id} 内容不一致：期望 {expected_content!r} 实际 {node.get('content')!r}",
                file=sys.stderr,
            )
            return 1
        verified += 1

    summary = {
        "created": n,
        "failed": 0,
        "total_s": round(total_s, 3),
        "avg_ms": round(avg_ms, 2),
        "max_ms": round(max_ms, 2),
        "sample_verified": verified,
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
