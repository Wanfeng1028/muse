#!/usr/bin/env python3
"""剧坊豆包邮件视频通道助手脚本。
Java 端 DoubaoEmailVideoProvider 经 ProcessBuilder 调用。
send: 发邮件派活 | poll: 查 Gmail 收回复
stdout 只输出一行 JSON，日志走 stderr。
"""
import argparse
import base64
import os
import re
import subprocess
import sys
import json

GMAIL_CLI = "/opt/hatch/bin/hatch_gws_cli"
DEFAULT_TO = "wanfeng6324@agent.qq.com"


def log(msg):
    print(msg, file=sys.stderr)


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def fail(error):
    emit({"ok": False, "error": str(error)})
    return 1


def run_gmail(args):
    log("running: " + " ".join(args))
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.stderr:
        log(proc.stderr.strip())
    if proc.returncode != 0:
        raise RuntimeError(
            "gmail cli failed rc=%s: %s" % (proc.returncode, (proc.stderr or proc.stdout or "").strip())
        )
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError("gmail cli returned empty stdout")
    return json.loads(out)


def build_body(prompt, seconds):
    return (
        f"豆包你好，这是剧坊分镜批量任务之一，请按以下要求一次完成（一小时查收一次邮件）：\n\n"
        f"任务：生成一段约{seconds}秒的短视频\n"
        f"内容：{prompt}\n"
        f"规格：16:9横屏，720p，mp4格式，画面无水印、无字幕\n"
        f"交付：请将生成的视频文件直接回复本邮件（附件），或在正文写\"视频链接：<链接>\"\n\n"
        f"——剧坊管线（自动发送）"
    )


def do_send(args):
    to = getattr(args, "to", None) or DEFAULT_TO
    prompt = getattr(args, "prompt", None)
    seconds = getattr(args, "seconds", None)
    if not prompt:
        return fail("missing --prompt")
    if seconds is None:
        return fail("missing --seconds")
    _sid = getattr(args, "shot_id", "?")
    subject = f"\u3010剧坊分镜#{_sid}\u3011请生成约{seconds}秒视频片段"
    body = build_body(prompt, seconds)
    try:
        res = run_gmail([
            GMAIL_CLI, "gmail", "+send",
            "--to", to,
            "--subject", subject,
            "--body", body,
            "--format", "json",
        ])
    except Exception as e:
        return fail(e)
    emit({
        "ok": True,
        "thread_id": res.get("threadId"),
        "message_id": res.get("id"),
    })
    return 0

def do_poll(args):
    try:
        params = {"userId": "me", "id": args.thread_id, "format": "full"}
        res = run_gmail([GMAIL_CLI, "gmail", "users", "threads", "get", "--params", json.dumps(params)])
    except Exception as e:
        return fail(str(e))

    out_dir = getattr(args, "out_dir", None) or "./doubao_downloads"
    os.makedirs(out_dir, exist_ok=True)

    def _b64d(data):
        if not data:
            return b""
        pad = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + pad)

    def _walk(parts, acc):
        for p in parts or []:
            if p.get("parts"):
                _walk(p["parts"], acc)
            else:
                acc.append(p)
        return acc

    def _headers(msg):
        return {h.get("name", "").lower(): h.get("value", "") for h in (msg.get("payload", {}).get("headers") or [])}

    try:
        for msg in res.get("messages", []):
            hdrs = _headers(msg)
            frm = hdrs.get("from", "")
            if "wanfeng6324@agent.qq.com" not in frm:
                continue
            mid = msg.get("id")
            parts = _walk(msg.get("payload", {}).get("parts"), [])
            if not parts and msg.get("payload"):
                parts = [msg["payload"]]

            for p in parts:
                mt = p.get("mimeType", "")
                body = p.get("body") or {}
                if mt.startswith("video/") and body.get("attachmentId"):
                    aparams = {"userId": "me", "messageId": mid, "id": body["attachmentId"]}
                    ares = run_gmail([GMAIL_CLI, "gmail", "users", "messages", "attachments", "get",
                                      "--params", json.dumps(aparams)])
                    raw = _b64d(ares.get("data", ""))
                    path = os.path.abspath(os.path.join(out_dir, f"{mid}.mp4"))
                    with open(path, "wb") as f:
                        f.write(raw)
                    emit({"ok": True, "status": "done", "video_url": "file://" + path})
                    return 0

            text = ""
            for p in parts:
                if p.get("mimeType") == "text/plain":
                    text += _b64d((p.get("body") or {}).get("data", "")).decode("utf-8", "ignore")
            if not text:
                text = _b64d((msg.get("payload", {}).get("body") or {}).get("data", "")).decode("utf-8", "ignore")

            m = re.search(r'视频链接[:：]\s*(https?://\S+)', text)
            if m:
                emit({"ok": True, "status": "done", "video_url": m.group(1)})
                return 0

            for kw in ("做不了", "无法生成", "拒绝", "不能生成"):
                if kw in text:
                    emit({"ok": True, "status": "failed", "error": text.strip()[:80]})
                    return 0

        emit({"ok": True, "status": "waiting"})
        return 0
    except Exception as e:
        return fail(str(e))

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("--shot-id", required=True)
    s.add_argument("--prompt", required=True)
    s.add_argument("--seconds", required=True)
    s.add_argument("--to", default=None)
    p = sub.add_parser("poll")
    p.add_argument("--thread-id", required=True)
    p.add_argument("--out-dir", default="./doubao_downloads")
    args = ap.parse_args()
    if args.cmd == "send":
        code = do_send(args)
    else:
        code = do_poll(args)
    sys.exit(code if isinstance(code, int) else 0)


if __name__ == "__main__":
    main()
