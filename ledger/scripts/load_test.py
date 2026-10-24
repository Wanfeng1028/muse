"""ledger 真实负载验证：仿真账单走真实 HTTP 全链路压测。"""

from __future__ import annotations

import argparse
import json
import os
import resource
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from loadgen import COLUMN_MAPPING, MERCHANTS, generate_month_csv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

CONFIRM_S_PER_300 = 30.0
ZERO_HTTP_5XX = True
DEDUP_MUST_MATCH = True
DEFAULT_SEED = 20261024


def find_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server(db_path: Path):
    port = find_free_port()
    env = dict(os.environ)
    env["LEDGER_DB"] = str(db_path)
    log_path = db_path.parent / "uvicorn.log"
    log_file = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            "-m",
            "uvicorn",
            "ledger.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, port, log_path, log_file


def wait_for_health(port: int, timeout: float = 60.0) -> None:
    # trust_env=False：本机沙箱 httpx 解析 NO_PROXY 中 [::1] 条目会抛 InvalidURL，绕过环境代理
    deadline = time.time() + timeout
    with httpx.Client(trust_env=False, timeout=5) as hc:
        while time.time() < deadline:
            try:
                r = hc.get(f"http://127.0.0.1:{port}/api/health")
                if r.status_code == 200:
                    return
            except Exception:
                pass
            time.sleep(0.5)
    raise RuntimeError("uvicorn 健康检查超时")


def stop_server(proc, log_file) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    try:
        log_file.close()
    except Exception:
        pass


def ensure_account(client: httpx.Client) -> tuple[int, str]:
    r = client.get("/api/accounts")
    r.raise_for_status()
    for a in r.json():
        if a["name"] == "招商银行储蓄卡":
            return a["id"], a["name"]
    r = client.post(
        "/api/accounts",
        json={"name": "招商银行储蓄卡", "type": "savings", "currency": "CNY", "opening_balance_cents": 0},
    )
    r.raise_for_status()
    j = r.json()
    return j["id"], j["name"]


def get_category_map(client: httpx.Client) -> dict[str, int]:
    r = client.get("/api/categories")
    r.raise_for_status()
    return {c["name"]: c["id"] for c in r.json()}


def seed_rules(client: httpx.Client, cat_map: dict[str, int]) -> int:
    n = 0
    for m in MERCHANTS:
        if m["monthly"] < 4 or m["category"] not in cat_map:
            continue
        r = client.post(
            "/api/match-rules",
            json={
                "keyword": m["name"],
                "category_id": cat_map[m["category"]],
                "direction": m["direction"],
                "priority": 10,
                "pattern_type": "keyword",
                "is_enabled": 1,
            },
        )
        if r.status_code == 409:
            continue
        r.raise_for_status()
        n += 1
    return n


def upload_month(
    client: httpx.Client, aid: int, year: int, month: int, seed: int, account_name: str, csv_dir: Path
) -> dict:
    csv_text, expected = generate_month_csv(year, month, seed)
    csv_text = csv_text.replace("__OWN_ACCOUNT__", account_name)
    expected = [{**e, "counterparty": account_name} if e["counterparty"] == "__OWN_ACCOUNT__" else e for e in expected]
    p = csv_dir / f"{year}-{month:02d}.csv"
    p.write_text(csv_text, encoding="utf-8")
    t0 = time.perf_counter()
    r = client.post(
        "/api/statements/upload",
        files={"file": (p.name, csv_text.encode("utf-8"), "text/csv")},
        data={"account_id": str(aid), "mapping": json.dumps(COLUMN_MAPPING)},
    )
    upload_s = time.perf_counter() - t0
    r.raise_for_status()
    j = r.json()
    bid = j["batch"]["id"]
    t1 = time.perf_counter()
    rc = client.post(f"/api/statements/{bid}/confirm")
    confirm_s = time.perf_counter() - t1
    rc.raise_for_status()
    b = rc.json()
    assert b["status"] != "preview"
    return {
        "batch_id": bid,
        "upload_s": round(upload_s, 2),
        "confirm_s": round(confirm_s, 2),
        "parsed": j["parsed"],
        "errors_n": len(j["errors"]),
        "duplicates_skipped": j["duplicates_skipped"],
        "total_count": b["total_count"],
        "auto_count": b["auto_count"],
        "pending_count": b["pending_count"],
        "expected": len(expected),
        "status5xx": 0,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ledger 真实负载验证")
    p.add_argument("--months", type=int, default=24)
    p.add_argument("--quick", action="store_true")
    p.add_argument("--workdir", default="data/loadtest-tmp")
    p.add_argument("--out", default=None, help="JSON 报告输出路径")
    p.add_argument("--concurrency", type=int, default=0, help="并发探针并行上传路数，0=跳过")

    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return p


def main() -> int:
    args = build_parser().parse_args()
    months = 6 if args.quick else args.months
    workdir = ROOT / args.workdir
    csv_dir = workdir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    db_path = workdir / "ledger-loadtest.sqlite3"
    db_before = db_path.stat().st_size if db_path.exists() else 0
    started_at = datetime.now(UTC).isoformat()
    proc, port, log_path, log_file = start_server(db_path)
    failures: list[str] = []
    phases: list[dict] = []
    try:
        try:
            wait_for_health(port)
        except RuntimeError:
            print("uvicorn 健康检查超时，日志尾部：")
            tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
            print("\n".join(tail))
            raise
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=120, trust_env=False)
        aid, account_name = ensure_account(client)
        cat_map = get_category_map(client)
        n_rules = seed_rules(client, cat_map)
        print(f"账户: {account_name}  分类: {len(cat_map)}  规则: {n_rules}")
        y, m = 2024, 10
        for _ in range(months):
            try:
                rec = upload_month(client, aid, y, m, args.seed, account_name, csv_dir)
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                failures.append(f"{y}-{m:02d} 上传/确认 HTTP {code}")
                if code >= 500 and ZERO_HTTP_5XX:
                    failures.append(f"{y}-{m:02d} 出现 5xx")
                rec = {
                    "batch_id": None,
                    "upload_s": 0.0,
                    "confirm_s": 0.0,
                    "parsed": 0,
                    "errors_n": 0,
                    "duplicates_skipped": 0,
                    "total_count": 0,
                    "auto_count": 0,
                    "pending_count": 0,
                    "expected": 0,
                    "status5xx": 1,
                }
            rec["month"] = f"{y}-{m:02d}"
            if rec["parsed"] != rec["expected"]:
                failures.append(f"{rec['month']} parsed={rec['parsed']} expected={rec['expected']}")
            if rec["total_count"]:
                norm = rec["confirm_s"] / rec["total_count"] * 300
                if norm > CONFIRM_S_PER_300:
                    failures.append(f"{rec['month']} 确认折合 {norm:.1f}s/300条 超阈值 {CONFIRM_S_PER_300}s")
            phases.append(rec)
            m += 1
            if m > 12:
                m, y = 1, y + 1
        first_csv = csv_dir / "2024-10.csv"
        r = client.post(
            "/api/statements/upload",
            files={"file": (first_csv.name, first_csv.read_bytes(), "text/csv")},
            data={"account_id": str(aid), "mapping": json.dumps(COLUMN_MAPPING)},
        )
        r.raise_for_status()
        j = r.json()
        p0 = phases[0]["parsed"] if phases else 0
        dedup = {
            "parsed": j["parsed"],
            "duplicates_skipped": j["duplicates_skipped"],
            "original_parsed": p0,
            "new_batch_total": j["batch"]["total_count"],
            "exact": bool(j["duplicates_skipped"] == p0 and j["batch"]["total_count"] == 0),
        }
        if DEDUP_MUST_MATCH and not dedup["exact"]:
            failures.append(f"去重探针未精确命中: {dedup}")
        # 并发探针：用主循环之后的新月份生成全新 CSV，N 路并行只做上传
        from concurrent.futures import ThreadPoolExecutor

        concurrency_result: dict = {"enabled": False}
        if args.concurrency and args.concurrency > 0:
            n = args.concurrency
            jobs: list[tuple[str, bytes]] = []
            yy, mm = y, m
            for _ in range(n):
                ct, _ = generate_month_csv(yy, mm, args.seed)
                ct = ct.replace("__OWN_ACCOUNT__", account_name)
                jobs.append((f"probe-{yy}-{mm:02d}.csv", ct.encode("utf-8")))
                mm += 1
                if mm > 12:
                    mm, yy = 1, yy + 1

            def _one(job: tuple[str, bytes]) -> tuple[float, int]:
                fn, data = job
                t = time.perf_counter()
                rr = client.post(
                    "/api/statements/upload",
                    files={"file": (fn, data, "text/csv")},
                    data={"account_id": str(aid), "mapping": json.dumps(COLUMN_MAPPING)},
                )
                return round(time.perf_counter() - t, 2), rr.status_code

            per_s: list[float] = []
            codes: list[int] = []
            with ThreadPoolExecutor(max_workers=n) as ex:
                for s, c in ex.map(_one, jobs):
                    per_s.append(s)
                    codes.append(c)
            err5xx = sum(1 for c in codes if c >= 500)
            concurrency_result = {
                "enabled": True,
                "n": n,
                "per_upload_s": per_s,
                "status_codes": codes,
                "errors_5xx": err5xx,
            }
            if err5xx and ZERO_HTTP_5XX:
                failures.append(f"并发探针 {err5xx}/{n} 路 5xx")

        parsed_total = sum(p["parsed"] for p in phases)
        auto_total = sum(p["auto_count"] for p in phases)
        upload_s = round(sum(p["upload_s"] for p in phases), 2)
        confirm_s = round(sum(p["confirm_s"] for p in phases), 2)
        auto_rate = round(auto_total / parsed_total, 4) if parsed_total else 0.0
        db_after = db_path.stat().st_size if db_path.exists() else 0
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = Path(args.out) if args.out else ROOT / "docs" / f"load-test-{stamp}.json"
        report = {
            "meta": {"months": months, "seed": args.seed, "started_at": started_at, "rules_seeded": n_rules},
            "phases": phases,
            "totals": {
                "upload_s": upload_s,
                "confirm_s": confirm_s,
                "parsed_total": parsed_total,
                "auto_total": auto_total,
                "auto_rate": auto_rate,
            },
            "dedup": dedup,
            "concurrency": concurrency_result,
            "memory": {"peak_kb": peak_kb, "db_bytes_before": db_before, "db_bytes_after": db_after},
            "thresholds": {"passed": not failures, "failures": failures},
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"月份: {months}  总笔数: {parsed_total}  自动匹配率: {auto_rate:.1%}")
        print(f"上传总耗时: {upload_s}s  确认总耗时: {confirm_s}s  报告: {out_path}")
        print("阈值判定: " + ("通过" if not failures else "未通过"))
        for f in failures:
            print(" - " + f)
        return 0 if not failures else 2
    finally:
        stop_server(proc, log_file)


if __name__ == "__main__":
    sys.exit(main())
