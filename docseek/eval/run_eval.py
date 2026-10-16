
#!/usr/bin/env python3
"""DocSeek v0.7 评测执行脚本。

用法（必须在仓库根目录运行）:
    python3 eval/run_eval.py --binary ./build/docseek --dict /path/to/dict
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="DocSeek v0.7 evaluation runner")
    p.add_argument("--binary", required=True, help="docseek binary path")
    p.add_argument("--dict", required=True, help="cppjieba dict dir")
    p.add_argument("--workdir", default="./eval/work_v07")
    p.add_argument("--pairs", default="eval/eval_pairs_v07.json")
    p.add_argument("--corpus-script", default="eval/gen_corpus_v07.py")
    p.add_argument("--expand-script", default="eval/expand_corpus_v07.py")
    return p.parse_args()



def run(cmd, cwd=None, env=None, timeout=60, check=True):
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        timeout=timeout,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def main():
    args = parse_args()

    repo_root = Path.cwd()
    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    corpus_src = repo_root / "eval" / "corpus_v07"
    corpus_script = repo_root / args.corpus_script

    # ① 生成语料
    if not corpus_script.exists():
        raise FileNotFoundError(f"corpus script not found: {corpus_script}")

    print(f"[1/4] generate corpus via {corpus_script}", flush=True)
    run([sys.executable, str(corpus_script)], cwd=str(repo_root), timeout=600)
    expand_script = repo_root / args.expand_script
    if expand_script.exists():
        print(f"[1/4] expand short docs via {expand_script}", flush=True)
        run([sys.executable, str(expand_script)], cwd=str(repo_root), timeout=600)
    else:
        print(f"[1/4] expand script not found, skip: {expand_script}", flush=True)


    if not corpus_src.exists():
        raise FileNotFoundError(f"corpus dir not found after generation: {corpus_src}")

    corpus_dst = workdir / "corpus"
    if corpus_dst.exists():
        shutil.rmtree(corpus_dst)
    shutil.copytree(corpus_src, corpus_dst)
    print(f"      copied corpus -> {corpus_dst}", flush=True)

    # ② 建索引
    db_path = workdir / "eval.db"
    if db_path.exists():
        db_path.unlink()

    env = os.environ.copy()
    env["DOCSEEK_DICT_DIR"] = args.dict

    binary = str(Path(args.binary).resolve())
    print(f"[2/4] build index -> {db_path}", flush=True)
    run(
        [binary, "--db", str(db_path), "index", str(corpus_dst) + os.sep],
        env=env,
        timeout=600,
    )

    # ③ 逐条跑 pair
    pairs_path = Path(args.pairs)
    with open(pairs_path, "r", encoding="utf-8") as f:
        pairs = json.load(f)

    print(f"[3/4] running {len(pairs)} pairs", flush=True)

    results = []  # (pair, got, ok)
    for pair in pairs:
        pid = pair["id"]
        query = pair["query"]
        expected = pair["expected"]
        ptype = pair["type"]
        category = pair["category"]

        cmd = [binary, "--db", str(db_path), "--json", ptype, query]
        proc = run(cmd, env=env, timeout=60, check=False)

        got = None
        ok = False

        if proc.returncode != 0:
            print(f"FAIL {pid} {query} -> subprocess rc={proc.returncode} "
                  f"stderr={proc.stderr.strip()!r}", flush=True)
            results.append((pair, None, False))
            continue

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            print(f"FAIL {pid} {query} -> bad JSON: {e}; stdout={proc.stdout[:200]!r}",
                  flush=True)
            results.append((pair, None, False))
            continue

        if ptype == "search":
            hits = data.get("hits") or []
            if hits:
                got = os.path.basename(hits[0]["path"])
            else:
                got = None
            if expected is None:
                ok = len(hits) == 0
            else:
                ok = (got == expected)
        elif ptype == "locate":
            anchors = data.get("anchors") or []
            if anchors:
                got = os.path.basename(anchors[0]["path"])
            else:
                got = None
            if expected is None:
                ok = len(anchors) == 0
            else:
                ok = (got == expected)
        else:
            raise ValueError(f"unknown type {ptype!r} in pair {pid}")

        status = "PASS" if ok else "FAIL"
        print(f"{status} {pid} {query} -> {got}", flush=True)
        results.append((pair, got, ok))

    # ④ 汇总
    total = len(results)
    correct = sum(1 for _, _, ok in results if ok)
    acc = correct / total if total else 0.0

    print(f"Top-1 accuracy: {correct}/{total} ({acc * 100:.1f}%)", flush=True)

    by_cat = {}
    for pair, _, ok in results:
        c = pair["category"]
        n, k = by_cat.get(c, (0, 0))
        by_cat[c] = (n + 1, k + (1 if ok else 0))

    for c in sorted(by_cat):
        n, k = by_cat[c]
        pct = k / n * 100 if n else 0.0
        print(f"  category {c}: {k}/{n} ({pct:.1f}%)", flush=True)

    # ⑤ 退出码
    if acc < 0.80:
        print("FAILED: accuracy below 80%", flush=True)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
