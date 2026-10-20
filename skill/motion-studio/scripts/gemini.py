"""Gemini (Nano Banana) image route: draw panels from a prompt and role-labelled references, edit a panel with one
instruction and a keep-list, in batch (half price, 24 h target) or interactively, with a hard spend cap.

Google's budgets only send alerts, so the cap lives here: every image is priced before it is sent, the price goes into
a ledger, and a run (or a month) that would pass its cap is refused whole. Prices are Google's list prices as of
2026-10-19 and can be replaced in ~/.motion-studio.json. Each output gets a sidecar <image>.gemini.json with the model,
the exact text sent, the references with sha256, settings, price and time.

The key comes from $GEMINI_API_KEY or the macOS Keychain (service motion-studio-gemini) and is never printed or written.
The SDK is google-genai (Apache-2.0, pip install google-genai), imported only when a call is made. Outputs carry
Google's SynthID watermark; the paid API terms let them be used commercially, with no express licence, and Google
does not train on paid-tier data. That is recorded in each sidecar as the asset's licence note.

  draw(film, jobs, batch=True)     new panels -> the panel paths (an existing panel moves to history/ first)
  collect(film)                    fetch finished batches, write panels, retry unchanged outputs once
  edit(film, image, instruction, keep, refs)   one edit -> a candidate in repairs/<image>/rNN/, for `accept`
  totals(run)                      a run's and this month's spend from the ledger
"""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

MODELS = {"flash": "gemini-nano-banana-2.1", "pro": "gemini-3-pro-image"}
DEFAULT_MODEL = "flash"
# USD per output image (standard, batch), and per million input tokens (standard, batch); Google's list, 2026-10-19
PRICES = {
    "gemini-nano-banana-2.1": {"1K": (0.0336, 0.0168), "2K": (0.0504, 0.0252), "4K": (0.113, 0.0567), "input": (1.50, 0.75)},
    "gemini-3.1-flash-image": {"1K": (0.067, 0.034), "2K": (0.101, 0.050), "4K": (0.151, 0.076), "input": (0.50, 0.25)},
    "gemini-3-pro-image": {"1K": (0.134, 0.067), "2K": (0.134, 0.067), "4K": (0.24, 0.12), "input": (2.00, 1.00)},
}
TOKENS_PER_IMAGE = 560      # Google's figure for an input image
MAX_REFS = 14               # the API's limit; Nano Banana 2.1 takes up to 4 character references among them
CAP_USD = 15.0              # per run, unless "gemini": {"cap_usd": N} in ~/.motion-studio.json
MONTH_CAP_USD = 80.0        # per calendar month, unless "month_cap_usd" (null turns it off)
SIZE = "1K"                 # 16:9 at 1K is 1376x768; `upscale` takes it to the frame. "size": "2K" per panel for the exceptions
UNCHANGED = 0.005           # an output with under 0.5% of pixels moved from an input counts as handed back unchanged
FILE_TTL = 24 * 3600        # uploaded references are reused for 24 h (the Files API keeps them 48 h; a batch can take 24 h)
LICENCE = "Gemini API output (paid tier): usable commercially under Google's API terms, no ownership claimed, SynthID watermark"
DONE = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}

_CLIENT = None              # tests put a stand-in here


# ---- config, key, client ----

def config():
    path = Path.home() / ".motion-studio.json"
    return (json.loads(path.read_text()).get("gemini") or {}) if path.exists() else {}


def model_id(name):
    return MODELS.get(name, name)


def price(model, size, batch):
    table = {**PRICES, **(config().get("prices") or {})}
    if model not in table or size not in table[model]:
        raise SystemExit(f"no price for {model} at {size}: add it under \"gemini\": {{\"prices\": {{...}}}} in ~/.motion-studio.json")
    return table[model][size][1 if batch else 0], table[model]["input"][1 if batch else 0]


def api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key and shutil.which("security"):
        r = subprocess.run(["security", "find-generic-password", "-s", "motion-studio-gemini", "-w"], capture_output=True, text=True)
        key = r.stdout.strip() if r.returncode == 0 else None
    if not key:
        raise SystemExit("no Gemini key: set $GEMINI_API_KEY, or store it in the Keychain with "
                         "`security add-generic-password -s motion-studio-gemini -a gemini -w` (it prompts for the key)")
    return key


def client():
    global _CLIENT
    if _CLIENT is None:
        try:
            from google import genai
        except ImportError:
            raise SystemExit("the Gemini route needs google-genai (Apache-2.0): pip install google-genai")
        _CLIENT = genai.Client(api_key=api_key())
    return _CLIENT


# ---- requests ----

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mime(path):
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(Path(path).suffix.lower(), "image/png")


def ref_list(refs, plate=None):
    """References as [{"path", "role"}]. A bare path gets a role from its file name; the plate is the room behind the
    people. Roles are written into the prompt ("image 2 is ..."), which is what keeps Gemini from mixing them up."""
    out = []
    for r in refs or []:
        r = {"path": r} if isinstance(r, str) else dict(r)
        r.setdefault("role", f"a reference image ({Path(r['path']).stem.replace('_', ' ')})")
        out.append(r)
    if plate:
        out.append({"path": plate, "role": "the room plate (the room behind the people only)"})
    if len(out) > MAX_REFS:
        raise SystemExit(f"{len(out)} reference images; the API takes at most {MAX_REFS}")
    return out


def prompt_text(job, retry=False):
    """The text sent: the image roles first, then the scene or the edit, as K-factory's template orders them."""
    imgs = ([{"role": "the panel to edit"}] if job.get("base") else []) + job["refs"]
    roles = ", ".join(f"image {i} is {r['role']}" for i, r in enumerate(imgs, 1))
    head = f"Using the attached images: {roles}.\n" if imgs else ""
    if job.get("base"):
        body = job["instruction"].rstrip(".") + "."
        if job.get("keep"):
            k = job["keep"]
            body += f" Keep {', '.join(k[:-1]) + ' and ' + k[-1] if len(k) > 1 else k[0]} exactly the same."
    else:
        body = job["prompt"]
    return ("Generate a new image. " if retry else "") + head + body


def request(job, film, retry=False, uploads=None):
    """One generateContent request in the REST shape (what a batch JSONL line holds). With `uploads` the images go by
    Files API reference instead of inline, so a batch file carries each character sheet once, not once per panel."""
    parts = []
    for p in ([job["base"]] if job.get("base") else []) + [r["path"] for r in job["refs"]]:
        path = film / p
        if uploads is not None:
            parts.append({"fileData": {"fileUri": uploads[sha256(path)]["uri"], "mimeType": mime(path)}})
        else:
            parts.append({"inlineData": {"mimeType": mime(path), "data": base64.b64encode(path.read_bytes()).decode()}})
    parts.append({"text": prompt_text(job, retry)})
    return {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": job["aspect"], "imageSize": job["size"]}}}


def estimate(job, batch):
    per_image, per_mtok = price(job["model"], job["size"], batch)
    n_in = len(job["refs"]) + (1 if job.get("base") else 0)
    tokens = n_in * TOKENS_PER_IMAGE + len(prompt_text(job)) / 4
    return round(per_image + tokens * per_mtok / 1e6, 5)


def actual(job, batch, usage):
    """The price from the usage the API reported: input tokens at the input rate, plus the per-image output price."""
    per_image, per_mtok = price(job["model"], job["size"], batch)
    return round(per_image + (usage or {}).get("promptTokenCount", 0) * per_mtok / 1e6, 5)


def image_from(response):
    """(bytes, mime, usage, why-not) from a REST-shaped response."""
    usage = response.get("usageMetadata") or {}
    for c in response.get("candidates") or []:
        for p in (c.get("content") or {}).get("parts") or []:
            d = p.get("inlineData")
            if d and d.get("data"):
                return base64.b64decode(d["data"]), d.get("mimeType", "image/png"), usage, None
    c = (response.get("candidates") or [{}])[0]
    text = " ".join(p.get("text", "") for p in (c.get("content") or {}).get("parts") or [] if p.get("text"))
    why = c.get("finishReason") or (response.get("promptFeedback") or {}).get("blockReason") or "no image returned"
    return None, None, usage, f"{why}{': ' + text[:200] if text else ''}"


def call(job, film, retry=False):
    """One interactive call; returns (bytes, mime, usage, why-not)."""
    from google.genai import types
    req = request(job, film, retry)
    resp = client().models.generate_content(
        model=job["model"], contents=[types.Content.model_validate(c) for c in req["contents"]],
        config=types.GenerateContentConfig(response_modalities=["IMAGE"], image_config=types.ImageConfig(
            aspect_ratio=job["aspect"], image_size=job["size"])))
    return image_from(resp.model_dump(mode="json", by_alias=True, exclude_none=True))


# ---- the unchanged-output check ----

def thumb(path_or_bytes, w=256, h=None):
    src = ["-i", str(path_or_bytes)] if not isinstance(path_or_bytes, bytes) else ["-i", "-"]
    h = h or w * 9 // 16
    raw = subprocess.run(["ffmpeg", "-v", "error", *src, "-vf", f"scale={w}:{h}:flags=area", "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], input=path_or_bytes if isinstance(path_or_bytes, bytes) else None,
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3).astype(np.float32)


def size_of(path_or_bytes):
    src = ["-i", str(path_or_bytes)] if not isinstance(path_or_bytes, bytes) else ["-i", "-"]
    out = subprocess.run(["ffprobe", "-v", "error", *src, "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0"], input=path_or_bytes if isinstance(path_or_bytes, bytes) else None,
                         capture_output=True, check=True).stdout
    w, h = out.decode().strip().split(",")[:2]
    return int(w), int(h)


def unchanged(data, inputs):
    """The input the output is a copy of, if any: identical bytes, or under 0.5% of pixels moved by more than 24 levels
    in any channel on a 256-wide thumbnail (colour, not grey: a recoloured panel is a change). Inputs of another shape (a portrait character sheet against a 16:9 panel) are skipped,
    since a copy keeps the shape."""
    digest = hashlib.sha256(data).hexdigest()
    W, H = size_of(data)
    for p in inputs:
        if sha256(p) == digest:
            return str(p)
        w, h = size_of(p)
        if abs(w / h - W / H) > 0.05:
            continue
        a, b = thumb(data, 256, max(1, round(256 * H / W))), thumb(p, 256, max(1, round(256 * H / W)))
        if (np.abs(a - b).max(-1) > 24).mean() < UNCHANGED:
            return str(p)
    return None


# ---- ledger ----

def ledger_path():
    return Path.home() / ".motion-studio" / "gemini-ledger.jsonl"


def ledger():
    p = ledger_path()
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def record(**row):
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), **row}) + "\n")


def totals(run=None):
    """USD committed for a run and for this calendar month: the reported price where a call has settled, else its
    estimate."""
    rows, month = ledger(), time.strftime("%Y-%m")
    settled = {(r["run"], r["key"]): r["usd"] for r in rows if r.get("kind") == "actual"}
    committed = [(r, settled.get((r["run"], r["key"]), r["usd"])) for r in rows if r.get("kind") == "estimate"]
    return (round(sum(u for r, u in committed if r["run"] == run), 4),
            round(sum(u for r, u in committed if r["at"].startswith(month)), 4))


def check_cap(run, extra):
    cfg = config()
    cap, month_cap = float(cfg.get("cap_usd", CAP_USD)), cfg.get("month_cap_usd", MONTH_CAP_USD)
    spent, month = totals(run)
    if spent + extra > cap + 1e-9:
        return f"this run would reach ${spent + extra:.2f}, over its ${cap:.2f} cap (\"gemini\": {{\"cap_usd\"}} in ~/.motion-studio.json)"
    if month_cap is not None and month + extra > float(month_cap) + 1e-9:
        return f"this month would reach ${month + extra:.2f}, over its ${float(month_cap):.2f} cap (\"month_cap_usd\")"
    return None


# ---- jobs ----

def make_jobs(film, items, model=None, size=None, aspect="16:9"):
    """Jobs from panel records ({"image", "prompt", "refs", "plate"}, as `longform.py panels` writes them, or a jobs
    file with "refs": [{"path", "role"}] and an optional per-panel "model": "pro")."""
    jobs = []
    for it in items:
        if not it.get("prompt"):
            raise SystemExit(f"{it.get('image')}: no prompt")
        refs = ref_list(it.get("refs"), it.get("plate"))
        for r in refs:
            if not (film / r["path"]).exists():
                raise SystemExit(f"{it['image']}: no reference image {r['path']}")
        jobs.append({"key": it["image"], "image": it["image"], "prompt": it["prompt"], "refs": refs,
                     "model": model_id(it.get("model") or model or config().get("model") or DEFAULT_MODEL),
                     "size": it.get("size") or size or SIZE, "aspect": it.get("aspect") or aspect, "beats": it.get("beats", [])})
    return jobs


def run_id():
    return time.strftime("%Y%m%d-%H%M%S")


def state_dir(film):
    d = film / "out" / "gemini"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ext_for(mime_type):
    return {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime_type, ".png")


def save_panel(film, job, data, mime_type, meta):
    """Write an output to the panel's path (in the panel's own format). A panel already there moves to
    history/<path>/<time><ext> first, so nothing drawn before is lost."""
    dest = film / job["image"]
    if dest.exists():
        old = film / "history" / Path(job["image"]).with_suffix("") / (time.strftime("%Y%m%d-%H%M%S") + dest.suffix)
        old.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), old)
        meta["replaced"] = str(old.relative_to(film))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if ext_for(mime_type) == dest.suffix.lower() or (dest.suffix.lower() == ".jpeg" and mime_type == "image/jpeg"):
        dest.write_bytes(data)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "-", "-frames:v", "1", str(dest)], input=data, check=True)
    sidecar(film, job, dest, meta)
    return dest


def sidecar(film, job, dest, meta):
    side = dest.with_name(dest.stem + ".gemini.json")
    side.write_text(json.dumps({
        "image": str(dest.relative_to(film)), "model": job["model"], "mode": "edit" if job.get("base") else "generate",
        "prompt": meta.pop("prompt"), "refs": [{**r, "sha256": sha256(film / r["path"])} for r in job["refs"]],
        **({"base": {"path": job["base"], "sha256": meta.pop("base_sha")}} if job.get("base") else {}),
        "settings": {"aspect_ratio": job["aspect"], "image_size": job["size"]}, "licence": LICENCE,
        "made_at": time.strftime("%Y-%m-%d %H:%M:%S"), **meta}, indent=1, ensure_ascii=False) + "\n")


def finish(film, run, job, data, mime_type, usage, why, batch, prompt):
    """Shared by interactive calls and batch results: price it, check for a handed-back copy (one fresh retry, which is
    always interactive and priced as such), then save or report."""
    usd = actual(job, batch, usage) if data or usage else 0.0
    record(kind="actual", run=run, key=job["key"], usd=usd)
    inputs = [film / job["base"]] if job.get("base") else [film / r["path"] for r in job["refs"]]
    meta = {"prompt": prompt, "batch": batch, "run": run, "usd": usd, "tries": 1}
    if job.get("base"):
        meta["base_sha"] = sha256(film / job["base"])
    if data is None:
        return None, f"{job['image']}: {why}"
    copy = unchanged(data, inputs)
    if copy:
        note = check_cap(run, estimate(job, False))
        if note:
            return None, f"{job['image']}: handed back {Path(copy).name} unchanged; no retry, {note}"
        rkey = job["key"] + "#retry"
        record(kind="estimate", run=run, key=rkey, film=str(film), image=job["image"], model=job["model"], size=job["size"],
               batch=False, usd=estimate(job, False))
        data2, mime2, usage2, why2 = call(job, film, retry=True)
        usd2 = actual(job, False, usage2) if data2 or usage2 else 0.0
        record(kind="actual", run=run, key=rkey, usd=usd2)
        meta.update(tries=2, usd=round(usd + usd2, 5), prompt=prompt_text(job, retry=True), first_try="unchanged copy of " + Path(copy).name)
        if data2 is None:
            return None, f"{job['image']}: retry failed: {why2}"
        copy2 = unchanged(data2, inputs)
        data, mime_type = data2, mime2
        if copy2:
            meta["flag"] = "unchanged twice"
            return None, f"{job['image']}: handed back {Path(copy2).name} unchanged twice; flagged, nothing saved"
    return (data, mime_type, meta), None


# ---- draw, collect, edit ----

def upload_refs(film, jobs):
    """Upload each distinct reference once (reusing uploads under 24 h old) and return {sha256: {"uri", "name", "at"}}."""
    cache_path = state_dir(film) / "files.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    for job in jobs:
        for r in job["refs"]:
            path = film / r["path"]
            h = sha256(path)
            if h in cache and time.time() - cache[h]["at"] < FILE_TTL:
                continue
            f = client().files.upload(file=str(path), config={"mime_type": mime(path), "display_name": path.name})
            cache[h] = {"uri": f.uri, "name": f.name, "at": time.time()}
    cache_path.write_text(json.dumps(cache, indent=1) + "\n")
    return cache


def draw(film, jobs, batch=True):
    """Draw new panels. The whole run is priced first and refused if it would pass a cap; with batch=True the jobs go
    to the Batch API (one job per model) and `collect` fetches them; otherwise each is drawn now."""
    run = run_id()
    cost = round(sum(estimate(j, batch) for j in jobs), 4)
    note = check_cap(run, cost)
    if note:
        raise SystemExit(f"refused: {len(jobs)} images at about ${cost:.2f}; {note}")
    for j in jobs:
        record(kind="estimate", run=run, key=j["key"], film=str(film), image=j["image"], model=j["model"], size=j["size"],
               batch=batch, usd=estimate(j, batch))
    if not batch:
        done, problems = [], []
        for j in jobs:
            data, mime_type, usage, why = call(j, film)
            ok, problem = finish(film, run, j, data, mime_type, usage, why, False, prompt_text(j))
            if ok:
                done.append(save_panel(film, j, *ok))
            else:
                problems.append(problem)
        return run, cost, done, problems
    uploads = upload_refs(film, jobs)
    sdir = state_dir(film)
    submitted = []
    for model in sorted({j["model"] for j in jobs}):
        mine = [j for j in jobs if j["model"] == model]
        src = sdir / f"batch-{run}-{model}.jsonl"
        with src.open("w") as f:
            for j in mine:
                f.write(json.dumps({"key": j["key"], "request": request(j, film, uploads=uploads)}) + "\n")
        up = client().files.upload(file=str(src), config={"mime_type": "jsonl", "display_name": src.name})
        bj = client().batches.create(model=model, src=up.name, config={"display_name": f"motion-studio {film.name} {run}"})
        state = {"run": run, "model": model, "name": bj.name, "film": str(film), "submitted": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "jobs": mine, "prompts": {j["key"]: prompt_text(j) for j in mine}, "status": "submitted"}
        (sdir / f"batch-{run}-{model}.json").write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n")
        submitted.append(bj.name)
    return run, cost, submitted, []


def collect(film):
    """Fetch every submitted batch of this film that has finished; returns (written, problems, still_running)."""
    written, problems, running = [], [], []
    for sp in sorted(state_dir(film).glob("batch-*.json")):
        st = json.loads(sp.read_text())
        if st["status"] != "submitted":
            continue
        bj = client().batches.get(name=st["name"])
        state = bj.state.name if hasattr(bj.state, "name") else str(bj.state)
        if state not in DONE:
            running.append(f"{st['name']} ({state}, submitted {st['submitted']})")
            continue
        if state != "JOB_STATE_SUCCEEDED":
            for j in st["jobs"]:
                record(kind="actual", run=st["run"], key=j["key"], usd=0.0)
            problems.append(f"batch {st['name']} ended {state}; nothing was charged for it as far as the ledger knows")
        else:
            lines = client().files.download(file=bj.dest.file_name).decode().splitlines()
            by_key = {j["key"]: j for j in st["jobs"]}
            seen = set()
            for line in filter(None, lines):
                row = json.loads(line)
                j = by_key.get(row.get("key"))
                if not j:
                    continue
                seen.add(j["key"])
                if row.get("error") or not row.get("response"):
                    record(kind="actual", run=st["run"], key=j["key"], usd=0.0)
                    problems.append(f"{j['image']}: {row.get('error') or 'no response'}")
                    continue
                data, mime_type, usage, why = image_from(row["response"])
                ok, problem = finish(film, st["run"], j, data, mime_type, usage, why, True, st["prompts"][j["key"]])
                if ok:
                    ok[2]["batch_job"] = st["name"]
                    written.append(save_panel(film, j, *ok))
                else:
                    problems.append(problem)
            for k in set(by_key) - seen:
                record(kind="actual", run=st["run"], key=k, usd=0.0)
                problems.append(f"{by_key[k]['image']}: missing from the batch output")
        st.update(status=state.removeprefix("JOB_STATE_").lower(), collected=time.strftime("%Y-%m-%d %H:%M:%S"))
        sp.write_text(json.dumps(st, indent=1, ensure_ascii=False) + "\n")
    return written, problems, running


def edit(film, image, instruction, keep=(), refs=(), model=None, size=None, aspect="16:9", beats=()):
    """One interactive edit of a whole panel. The result is a repair candidate (repairs/<image>/rNN/candidate_1.<ext>),
    logged like a crop repair, so the review sheet, `accept` and `revert` work the same way."""
    src = film / image
    if not src.exists():
        raise SystemExit(f"no panel image {image}")
    job = {"key": image + "#edit", "image": image, "base": image, "instruction": instruction, "keep": list(keep),
           "refs": ref_list(refs), "model": model_id(model or config().get("model") or DEFAULT_MODEL), "size": size or SIZE, "aspect": aspect}
    run = run_id()
    cost = estimate(job, False)
    note = check_cap(run, cost)
    if note:
        raise SystemExit(f"refused: about ${cost:.3f}; {note}")
    record(kind="estimate", run=run, key=job["key"], film=str(film), image=image, model=job["model"], size=job["size"], batch=False, usd=cost)
    t0 = time.time()
    data, mime_type, usage, why = call(job, film)
    ok, problem = finish(film, run, job, data, mime_type, usage, why, False, prompt_text(job))
    key = Path(image).with_suffix("").as_posix()
    root = film / "repairs" / key
    n = 1 + max([int(p.name[1:]) for p in root.glob("r[0-9]*") if p.name[1:].isdigit()] or [0])
    rdir = root / f"r{n:02d}"
    rdir.mkdir(parents=True)
    entry = {"id": f"{key}/r{n:02d}", "image": image, "beats": list(beats), "route": "gemini", "whole": True,
             "prompt": prompt_text(job), "model": job["model"], "ref": [r["path"] for r in job["refs"]] or None, "seeds": [1],
             "candidates": [], "seconds": round(time.time() - t0, 1), "at": time.strftime("%Y-%m-%d %H:%M"), "status": "failed"}
    if ok:
        data, mime_type, meta = ok
        out = rdir / ("out_1" + ext_for(mime_type))
        out.write_bytes(data)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-i", str(out), "-filter_complex",
                        "[0]scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:-1:-1[a];"
                        "[1]scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:-1:-1[b];[a][b]hstack", "-frames:v", "1", str(rdir / "compare_1.png")], check=True)
        sidecar(film, job, out, meta)
        entry.update(candidates=[1], status="candidate", usd=meta["usd"], tries=meta["tries"])
    else:
        entry["problem"] = problem
    log_path = film / "repairs" / "log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else []
    log.append(entry)
    log_path.write_text(json.dumps(log, indent=1, ensure_ascii=False) + "\n")
    return rdir, entry, problem
