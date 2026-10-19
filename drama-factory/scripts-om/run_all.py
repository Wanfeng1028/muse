import json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

man = json.load(open("scripts-om/manifest.json", encoding="utf-8"))
allb = [b["batch"] for b in man["batches"]]
done_file = "scripts-om/work/done.log"
try:
    done = set(l.strip() for l in open(done_file, encoding="utf-8") if l.strip())
except FileNotFoundError:
    done = set()
todo = [b for b in allb if b not in done]
print(f"total={len(allb)} done={len(done)} todo={len(todo)}", flush=True)

def one(b):
    r = subprocess.run(["./scripts-om/run_batch.sh", b], capture_output=True, text=True, timeout=900)
    tail = (r.stdout + r.stderr)[-1500:]
    ok = r.returncode == 0
    with open("scripts-om/work/run-all.log", "a", encoding="utf-8") as f:
        f.write(f"\n===== {b} rc={r.returncode} =====\n{tail}\n")
    if ok:
        with open(done_file, "a", encoding="utf-8") as f:
            f.write(b + "\n")
    return (b, ok)

failed = []
with ThreadPoolExecutor(max_workers=4) as ex:
    for b, ok in ex.map(one, todo):
        print(("OK " if ok else "FAIL ") + b, flush=True)
        if not ok:
            failed.append(b)
print("FAILED:", failed)
