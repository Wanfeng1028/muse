#!/usr/bin/env python3
"""DocSeek v0.9 评测：corpus_v09 + eval_pairs_v09.json。用法：在仓库根运行 python3 eval/run_eval_v09.py --binary ./build/docseek"""
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path

def run(cmd, env, timeout=60):
    return subprocess.run(cmd, timeout=timeout, capture_output=True, text=True, env=env)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--workdir", default="./eval/work_v09")
    ap.add_argument("--pairs", default="eval/eval_pairs_v09.json")
    a = ap.parse_args()
    repo = Path.cwd()
    workdir = Path(a.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    corpus_src = repo / "eval" / "corpus_v09"
    assert corpus_src.is_dir(), "corpus_v09 missing, run merge_v09.py first"
    corpus_dst = workdir / "corpus"
    if corpus_dst.exists(): shutil.rmtree(corpus_dst)
    shutil.copytree(corpus_src, corpus_dst)
    db_path = workdir / "eval.db"
    if db_path.exists(): db_path.unlink()
    env = os.environ.copy()
    env["DOCSEEK_DICT_DIR"] = str((repo / "build" / "dict").resolve())
    binary = str(Path(a.binary).resolve())
    print("[1/3] index", flush=True)
    r = run([binary, "--db", str(db_path), "index", str(corpus_dst) + os.sep], env, 900)
    assert r.returncode == 0, r.stderr[-2000:]
    pairs = json.load(open(repo / a.pairs, encoding="utf-8"))
    print("[2/3] run %d pairs" % len(pairs), flush=True)
    ok = fail = 0
    fails = []
    for pr in pairs:
        cmd = [binary, "--db", str(db_path), "--json", pr["type"], pr["query"]]
        r = run(cmd, env, 60)
        good = False
        if r.returncode == 0:
            try:
                data = json.loads(r.stdout)
                if pr["type"] == "search":
                    hits = data.get("hits") or []
                    good = bool(hits) and os.path.basename(hits[0]["path"]) == pr["expected"]
                else:
                    anchors = data.get("anchors") or []
                    good = bool(anchors) and os.path.basename(anchors[0].get("path", "")) == pr["expected"]
            except Exception:
                pass
        if good: ok += 1
        else:
            fail += 1
            if len(fails) < 20: fails.append((pr["id"], pr["query"], pr["expected"]))
    print("[3/3] v09: %d/%d passed (%.1f%%)" % (ok, len(pairs), 100.0 * ok / len(pairs)), flush=True)
    json.dump({"total": len(pairs), "passed": ok, "failed": fail, "sample_fails": fails},
              open(workdir / "result_v09.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
