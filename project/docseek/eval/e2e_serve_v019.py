#!/usr/bin/env python3
"""E2E test for the `serve` subcommand of docseek (文溯) v0.19.0.

Verifies search highlightability and natural-language locate against a real
binary, real HTTP server and a real index built from four Chinese documents.

Usage:
    python3 eval/e2e_serve_v019.py --bin <path-to-docseek> [--keep]
"""

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Test documents
# ---------------------------------------------------------------------------

DOCS = {
    "install.txt": (
        "软件安装步骤说明\n"
        "\n"
        "本文档介绍本软件的完整安装步骤。请按照下面的安装步骤依次操作，"
        "不要跳过任何一个安装步骤。\n"
        "\n"
        "第一步下载安装包。请从官方网站下载最新版本的安装包，"
        "下载完成后请校验文件的完整性，确认没有损坏。\n"
        "\n"
        "第二步运行安装程序。双击安装包，按照向导提示选择安装目录，"
        "建议使用默认目录以避免权限问题。\n"
        "\n"
        "第三步配置环境变量。安装完成后需要把可执行文件所在目录加入 PATH，"
        "然后重新打开终端使配置生效。\n"
        "\n"
        "如果安装步骤中出现错误，请先查看日志文件，"
        "再根据错误码到官方文档查询解决办法。\n"
    ),
    "backup.md": (
        "# 数据备份与恢复\n"
        "\n"
        "本文档说明数据备份与恢复的标准流程。备份是保障数据安全最重要的手段。\n"
        "\n"
        "## 自动备份\n"
        "\n"
        "系统每天凌晨 3 点自动备份一次全部业务数据，"
        "备份文件会加密后写入对象存储。\n"
        "\n"
        "## 备份保留策略\n"
        "\n"
        "备份保留 30 天，超过保留期的备份会被自动清理，"
        "如需长期保存请手动导出。\n"
        "\n"
        "## 恢复流程\n"
        "\n"
        "恢复时请先停止写入服务，选择最近一次可用的备份，"
        "校验通过后再执行恢复操作。\n"
        "\n"
        "备份任务失败会触发告警，值班人员需要在当天内处理。\n"
    ),
    "network.txt": (
        "WiFi 网络故障排查\n"
        "\n"
        "当无线网络无法连接时，可以按照下面的顺序逐项排查。\n"
        "\n"
        "首先重启路由器。拔掉电源等待三十秒再插回，"
        "等指示灯稳定后再尝试连接。\n"
        "\n"
        "其次检查网线是否松动。确认光猫到路由器的网线两端都插紧，"
        "接口指示灯应当常亮或闪烁。\n"
        "\n"
        "然后确认无线信道是否拥挤，可以切换到 5GHz 频段减少干扰。\n"
        "\n"
        "如果问题依旧，请记录错误信息并联系网络管理员。\n"
    ),
    "irrelevant.txt": (
        "周末的天气与散步\n"
        "\n"
        "今天天气晴朗，气温适宜，非常适合出门散步。\n"
        "\n"
        "公园里的树叶已经变黄，风一吹就落下来，铺满了小路。\n"
        "\n"
        "沿着湖边慢慢走一圈，大约需要四十分钟，"
        "途中可以看到很多水鸟。\n"
        "\n"
        "傍晚回家时天色渐暗，路灯依次亮起，空气里有一点凉意。\n"
        "\n"
        "这样平常的一天，也让人觉得心情舒畅。\n"
    ),
}

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


class Fail(Exception):
    pass


def http_get(url, timeout=10.0):
    """Return (status, body_bytes, headers). Never raises on HTTP errors."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, body, dict(e.headers or {})
    except Exception as e:
        raise Fail("request failed for %s: %s" % (url, e))


def get_json(url, timeout=10.0):
    status, body, _ = http_get(url, timeout=timeout)
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception as e:
        raise Fail("invalid JSON from %s (status %s): %s" % (url, status, e))
    return status, data


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def strip_ws(s):
    return "".join(s.split())


# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

class Env(object):
    def __init__(self, bin_path, keep):
        self.bin_path = os.path.abspath(bin_path)
        self.keep = keep
        self.workdir = None
        self.docs_dir = None
        self.db_dir = None
        self.stderr_path = None
        self.proc = None
        self.port = None
        self.base = None

    def setup(self):
        if not os.path.isfile(self.bin_path):
            raise Fail("binary not found: %s" % self.bin_path)
        root = repo_root()
        base = os.path.join(root, "docseek", "test-tmp")
        os.makedirs(base, exist_ok=True)
        self.workdir = os.path.join(base, "e2e_serve_v019_%d" % os.getpid())
        if os.path.exists(self.workdir):
            shutil.rmtree(self.workdir, ignore_errors=True)
        os.makedirs(self.workdir)
        self.docs_dir = os.path.join(self.workdir, "docs")
        os.makedirs(self.docs_dir)
        self.db_dir = os.path.join(self.workdir, "db")
        for name, content in DOCS.items():
            with open(os.path.join(self.docs_dir, name), "w", encoding="utf-8") as f:
                f.write(content)

    def build_index(self):
        cmd = [self.bin_path, "index", "--db", self.db_dir, self.docs_dir]
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        if proc.returncode != 0:
            sys.stderr.write("index command failed (rc=%d)\n" % proc.returncode)
            sys.stderr.write(proc.stdout.decode("utf-8", "replace")[-2000:] + "\n")
            sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-2000:] + "\n")
            raise Fail("index build failed")

    def start_server(self):
        self.port = free_port()
        self.base = "http://127.0.0.1:%d" % self.port
        self.stderr_path = os.path.join(self.workdir, "serve.stderr.log")
        err_f = open(self.stderr_path, "wb")
        cmd = [self.bin_path, "--db", self.db_dir, "serve", "--port", str(self.port)]
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=err_f, cwd=self.workdir
        )
        # err_f is closed by the child on exec; keep reference out of scope.
        err_f.close()

    def wait_ready(self, timeout=15.0):
        deadline = time.time() + timeout
        last_err = None
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise Fail("serve process exited early with code %s" % self.proc.returncode)
            try:
                status, body, _ = http_get(self.base + "/api/health", timeout=2.0)
                if status == 200:
                    return
                last_err = "health status %s" % status
            except Fail as e:
                last_err = str(e)
            time.sleep(0.3)
        self.dump_stderr()
        raise Fail("server not ready within %.1fs (last: %s)" % (timeout, last_err))

    def dump_stderr(self):
        if not self.stderr_path or not os.path.exists(self.stderr_path):
            return
        try:
            with open(self.stderr_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            return
        tail = lines[-20:]
        if tail:
            sys.stderr.write("--- serve stderr (last %d lines) ---\n" % len(tail))
            for ln in tail:
                sys.stderr.write(ln if ln.endswith("\n") else ln + "\n")
            sys.stderr.write("--- end serve stderr ---\n")

    def stop_server(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            try:
                self.proc.send_signal(signal.SIGTERM)
            except Exception:
                pass
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    self.proc.kill()
                except Exception:
                    pass
                try:
                    self.proc.wait(timeout=5)
                except Exception:
                    pass

    def cleanup(self):
        if self.keep:
            print("keeping workdir: %s" % self.workdir)
            return
        if self.workdir and os.path.exists(self.workdir):
            shutil.rmtree(self.workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def q(url_path):
    return ENV.base + url_path


@check("health")
def check_health():
    status, data = get_json(ENV.base + "/api/health")
    if status != 200:
        raise Fail("expected 200, got %s" % status)
    if not isinstance(data, dict):
        raise Fail("health payload is not a JSON object: %r" % (data,))
    if data.get("ok") is not True:
        raise Fail('expected "ok":true, got %r' % (data.get("ok"),))
    version = data.get("version")
    if version != "0.19.0":
        raise Fail('expected version "0.19.0", got %r' % (version,))


@check("search_basic")
def check_search_basic():
    url = ENV.base + "/api/search?" + urllib.parse.urlencode(
        {"q": "安装步骤", "limit": "5"}
    )
    status, data = get_json(url)
    if status != 200:
        raise Fail("expected 200, got %s" % status)
    hits = data.get("hits") if isinstance(data, dict) else None
    if not hits:
        raise Fail("hits is empty: %r" % (data,))
    top = hits[0]
    path = top.get("path", "")
    if not path.endswith("install.txt"):
        raise Fail("Top-1 path does not end with install.txt: %r" % (path,))
    required = ["doc_id", "path", "title", "snippet", "score", "file_type"]
    for i, h in enumerate(hits):
        missing = [k for k in required if k not in h]
        if missing:
            raise Fail("hit #%d missing keys %s: %r" % (i, missing, h))


@check("search_snippet_highlightable")
def check_search_snippet_highlightable():
    url = ENV.base + "/api/search?" + urllib.parse.urlencode(
        {"q": "安装步骤", "limit": "5"}
    )
    status, data = get_json(url)
    if status != 200:
        raise Fail("expected 200, got %s" % status)
    hits = data.get("hits") if isinstance(data, dict) else None
    if not hits:
        raise Fail("hits is empty")
    for i, h in enumerate(hits):
        snippet = h.get("snippet", "")
        if not isinstance(snippet, str):
            raise Fail("hit #%d snippet is not a string: %r" % (i, snippet))
        if ("安装" not in snippet) and ("步骤" not in snippet):
            raise Fail(
                "hit #%d snippet has no query term (cannot be highlighted): %r"
                % (i, snippet)
            )


@check("search_explain_api")
def check_search_explain_api():
    url = ENV.base + "/api/search?" + urllib.parse.urlencode(
        {"q": "安装步骤", "explain": "true"}
    )
    status, data = get_json(url)
    if status != 200:
        raise Fail("expected 200, got %s" % status)
    hits = data.get("hits") if isinstance(data, dict) else None
    if not hits:
        raise Fail("hits is empty")
    parts = ["base_bm25", "title_bonus", "phrase_bonus", "structural_bonus"]
    for i, h in enumerate(hits):
        ex = h.get("explain")
        if not isinstance(ex, dict):
            raise Fail("hit #%d has no explain object: %r" % (i, h.get("explain")))
        missing = [k for k in parts + ["final"] if k not in ex]
        if missing:
            raise Fail("hit #%d explain missing keys %s: %r" % (i, missing, ex))
        total = 0.0
        for k in parts:
            v = ex[k]
            if not isinstance(v, (int, float)):
                raise Fail("hit #%d explain[%s] not numeric: %r" % (i, k, v))
            total += float(v)
        score = h.get("score")
        if not isinstance(score, (int, float)):
            raise Fail("hit #%d score not numeric: %r" % (i, score))
        if abs(total - float(score)) >= 1e-6:
            raise Fail(
                "hit #%d explain sum %.10f != score %.10f (delta %.3g)"
                % (i, total, float(score), abs(total - float(score)))
            )


@check("search_explain_off")
def check_search_explain_off():
    url = ENV.base + "/api/search?" + urllib.parse.urlencode(
        {"q": "安装步骤", "explain": "0"}
    )
    status, data = get_json(url)
    if status != 200:
        raise Fail("expected 200, got %s" % status)
    hits = data.get("hits") if isinstance(data, dict) else None
    if not hits:
        raise Fail("hits is empty")
    for i, h in enumerate(hits):
        if "explain" in h:
            raise Fail(
                'hit #%d contains "explain" although explain=0: %r'
                % (i, h.get("explain"))
            )


@check("search_no_q")
def check_search_no_q():
    status, body, _ = http_get(ENV.base + "/api/search")
    if status != 400:
        raise Fail("expected 400 for missing q, got %s (body: %r)" % (status, body[:200]))


def _locate_passages(data):
    """Tolerant extraction of the passages array from a locate response."""
    if isinstance(data, dict):
        for key in ("passages", "anchors", "results", "items", "hits"):
            v = data.get(key)
            if isinstance(v, list):
                return v
        # Some servers nest under "data".
        inner = data.get("data")
        if isinstance(inner, dict):
            for key in ("passages", "anchors", "results", "items", "hits"):
                v = inner.get(key)
                if isinstance(v, list):
                    return v
    if isinstance(data, list):
        return data
    return None


def _passage_text(p):
    if isinstance(p, str):
        return p
    if isinstance(p, dict):
        for key in ("text", "content", "snippet", "passage", "body"):
            v = p.get(key)
            if isinstance(v, str):
                return v
    return None


def _passage_lines(p):
    """Return a list of (label, value) integer line numbers found on a passage."""
    out = []
    if not isinstance(p, dict):
        return out
    for key in ("line_start", "line_no", "start_line", "start", "line",
                "line_end", "end_line", "end"):
        v = p.get(key)
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            out.append((key, v))
        elif isinstance(v, float) and v.is_integer():
            out.append((key, int(v)))
        elif isinstance(v, str):
            try:
                out.append((key, int(v.strip())))
            except Exception:
                pass
    return out


@check("locate_natural")
def check_locate_natural():
    url = ENV.base + "/api/locate?" + urllib.parse.urlencode(
        {"q": "备份要保留多少天"}
    )
    status, body, _ = http_get(url)
    if status != 200:
        raise Fail("expected 200, got %s (body: %r)" % (status, body[:300]))
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception as e:
        raise Fail("invalid JSON from /api/locate: %s (body: %r)" % (e, body[:300]))

    # Debug: dump the full locate response once so the schema is visible.
    print("[debug] /api/locate raw response:")
    try:
        print(json.dumps(data, ensure_ascii=False, indent=2)[:4000])
    except Exception:
        print(repr(data)[:4000])

    passages = _locate_passages(data)
    if not passages:
        raise Fail("no passages array / empty passages in locate response")

    first = passages[0]
    text = _passage_text(first)
    if text is None:
        raise Fail("first passage has no recognizable text field: %r" % (first,))

    backup_path = os.path.join(ENV.docs_dir, "backup.md")
    with open(backup_path, "r", encoding="utf-8") as f:
        backup_content = f.read()
    backup_lines = backup_content.splitlines()
    total_lines = len(backup_lines)

    if strip_ws(text) not in strip_ws(backup_content):
        raise Fail(
            "first passage text is not a substring of backup.md content: %r" % (text,)
        )

    lines = _passage_lines(first)
    if not lines:
        raise Fail("first passage has no recognizable line-number field: %r" % (first,))
    for label, value in lines:
        if value < 1 or value > total_lines:
            raise Fail(
                "first passage line field %s=%d out of range 1..%d"
                % (label, value, total_lines)
            )


@check("web_ui")
def check_web_ui():
    status, body, _ = http_get(ENV.base + "/")
    if status != 200:
        raise Fail("expected 200, got %s" % status)
    html = body.decode("utf-8", "replace")
    if "buildSnippet" not in html:
        raise Fail("index page does not contain buildSnippet (highlight function)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ENV = None


def main():
    global ENV
    ap = argparse.ArgumentParser(description="E2E test for docseek serve (v0.19.0)")
    ap.add_argument("--bin", required=True, help="path to the docseek binary")
    ap.add_argument("--keep", action="store_true", help="keep the work directory")
    args = ap.parse_args()

    ENV = Env(args.bin, args.keep)
    setup_failed = None
    results = []
    try:
        try:
            ENV.setup()
            ENV.build_index()
            ENV.start_server()
            ENV.wait_ready()
        except Fail as e:
            setup_failed = str(e)

        if setup_failed is None:
            for name, fn in CHECKS:
                try:
                    fn()
                    results.append((name, True, ""))
                except Fail as e:
                    results.append((name, False, str(e)))
                except Exception as e:
                    results.append((name, False, "unexpected error: %r" % (e,)))
        else:
            for name, _ in CHECKS:
                results.append((name, False, "skipped: setup failed"))
            sys.stderr.write("setup failed: %s\n" % setup_failed)
            ENV.dump_stderr()
    finally:
        ENV.stop_server()
        ENV.cleanup()

    print("")
    print("===== e2e_serve_v019 results =====")
    failed = 0
    for name, ok, reason in results:
        if ok:
            print("PASS  %s" % name)
        else:
            failed += 1
            print("FAIL  %s  -- %s" % (name, reason))
    print("----------------------------------")
    print("%d/%d passed" % (len(results) - failed, len(results)))

    if failed:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
