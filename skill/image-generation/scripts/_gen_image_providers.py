"""Gemini (Nano Banana), BFL FLUX and Recraft adapters for gen_image.py; request shapes from each vendor's docs."""
import base64
import math
import sys
import time

from _gen_image_http import ApiError, json_body, request_with_retries
from _gen_image_job import Job
from _gen_image_openai import MIME, Result
from _gen_image_spec import parse_size

sys.dont_write_bytecode = True

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_RATIOS = ["1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
GEMINI_TERMS = ("warning: Gemini API terms forbid use in an app 'directed towards or likely to be accessed by individuals "
                "under the age of 18'. For children's products prefer OpenAI or confirm with counsel.")
BFL_URL = "https://api.bfl.ai/v1"
FLUX3_RATIOS = ["21:9", "2:1", "16:9", "3:2", "7:5", "4:3", "5:4", "1:1", "4:5", "3:4", "5:7", "2:3", "9:16", "1:2", "9:21"]
FLUX2_MAX_PIXELS = 4 * 1024 * 1024
RECRAFT_URL = "https://external.api.recraft.ai/v1/images/generations"
RECRAFT_RATIOS = ["1:1", "16:9", "9:16", "3:2", "2:3"]
POSITIVE_ONLY = "note: {} has no negative prompts; 'no X' wording can summon X. Prefer positive descriptions."
OUTPUT_MIME = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}


def nearest_ratio(size: str, choices: list[str]) -> tuple[str, bool]:
    width, height = parse_size(size)
    target = math.log(width / height)

    def distance(choice: str) -> float:
        left, right = choice.split(":")
        return abs(math.log(int(left) / int(right)) - target)

    best = min(choices, key=distance)
    return best, distance(best) < 0.01


def long_edge(size: str) -> int:
    return max(parse_size(size))


def encoded(job: Job) -> list[tuple[str, str]]:
    return [(MIME.get(reference.path.suffix.lower(), "image/png"), base64.b64encode(reference.path.read_bytes()).decode())
            for reference in job.references]


def download(url: str) -> bytes:
    return request_with_retries("GET", url).content


def gemini_body(job: Job, images: list[tuple[str, str]]) -> dict:
    ratio, _ = nearest_ratio(job.size, GEMINI_RATIOS)
    edge = long_edge(job.size)
    image_size = "1K" if edge <= 1024 else "2K" if edge <= 2048 else "4K"
    parts = [{"type": "text", "text": job.prompt}] + [{"type": "image", "mime_type": mime, "data": data} for mime, data in images]
    response_format = {"type": "image", "mime_type": OUTPUT_MIME[job.output_format], "aspect_ratio": ratio, "image_size": image_size}
    return {"model": job.model, "input": parts, "response_format": response_format}


def collect_images(node: object, found: list[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        if node.get("type") == "image" and isinstance(node.get("data"), str):
            found.append((node.get("mime_type", "image/png"), node["data"]))
            return
        for key, value in node.items():
            if key != "input":
                collect_images(value, found)
    elif isinstance(node, list):
        for item in node:
            collect_images(item, found)


def gemini_output_images(body: dict) -> list[bytes]:
    steps = [step for step in body.get("steps", []) if "output" in str(step.get("type", ""))] or body.get("steps", []) or [body]
    found: list[tuple[str, str]] = []
    collect_images(steps, found)
    return [base64.b64decode(data) for _, data in found]


def gemini_run(job: Job, key: str) -> Result:
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    body = gemini_body(job, encoded(job))
    images: list[bytes] = []
    usage: list[dict] = []
    interaction_ids: list[str] = []
    for _ in range(job.n):
        response = request_with_retries("POST", GEMINI_URL, headers=headers, json=body)
        payload = json_body(response)
        found = gemini_output_images(payload)
        if not found:
            raise ApiError(f"no image in Gemini response: {str(payload)[:300]}")
        images += found[:1]
        usage.append(payload.get("usage", {}))
        interaction_ids.append(payload.get("id", ""))
    extra = {"interaction_ids": interaction_ids, "aspect_ratio": body["response_format"]["aspect_ratio"]}
    return Result(images, {"calls": usage}, None, None, extra)


def bfl_body(job: Job, images: list[tuple[str, str]]) -> dict:
    data = [value for _, value in images]
    if job.model.startswith("flux-3"):
        ratio, _ = nearest_ratio(job.size, FLUX3_RATIOS)
        edge = long_edge(job.size)
        resolution = "1k" if edge <= 1024 else "1.5k" if edge <= 1536 else "2k" if edge <= 2048 else "4k"
        body: dict = {"prompt": job.prompt, "aspect_ratio": ratio, "resolution": resolution}
        if data:
            body["images"] = data
        return body
    width, height = parse_size(job.size)
    scale = min(1.0, math.sqrt(FLUX2_MAX_PIXELS / (width * height)))
    body = {"prompt": job.prompt, "width": int(width * scale) // 16 * 16, "height": int(height * scale) // 16 * 16,
            "output_format": job.output_format, "disable_pup": True, "safety_tolerance": 2}
    for index, value in enumerate(data, 1):
        body["input_image" if index == 1 else f"input_image_{index}"] = value
    return body


def bfl_poll(polling_url: str, key: str) -> str:
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        payload = json_body(request_with_retries("GET", polling_url, headers={"x-key": key, "accept": "application/json"}))
        status = payload.get("status")
        if status == "Ready":
            return payload["result"]["sample"]
        if status not in ("Pending", "Processing", "Queued", None):
            raise ApiError(f"BFL task {status}: {str(payload)[:300]}")
        time.sleep(1.0)
    raise ApiError("BFL task did not finish within 10 minutes")


def bfl_run(job: Job, key: str) -> Result:
    headers = {"x-key": key, "accept": "application/json", "Content-Type": "application/json"}
    body = bfl_body(job, encoded(job))
    images: list[bytes] = []
    credits = 0.0
    for _ in range(job.n):
        task = json_body(request_with_retries("POST", f"{BFL_URL}/{job.model}", headers=headers, json=body))
        credits += task.get("cost") or 0.0
        images.append(download(bfl_poll(task["polling_url"], key)))
    return Result(images, None, None, None, {"bfl_credits": credits})


def recraft_body(job: Job) -> dict:
    ratio, _ = nearest_ratio(job.size, RECRAFT_RATIOS)
    body: dict = {"prompt": job.prompt, "model": job.model, "n": min(job.n, 6), "size": ratio, "response_format": "url"}
    if job.palette:
        body["controls"] = {"colors": [{"rgb": [int(hex_value.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]} for hex_value in job.palette]}
    return body


def recraft_run(job: Job, key: str) -> Result:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = json_body(request_with_retries("POST", RECRAFT_URL, headers=headers, json=recraft_body(job)))
    urls = [item["url"] for item in payload.get("data", []) if item.get("url")]
    if not urls:
        raise ApiError(f"no image URLs in Recraft response: {str(payload)[:300]}")
    return Result([download(url) for url in urls], None, None, None, {})


def summarize_images(body: object) -> object:
    if isinstance(body, dict):
        return {key: summarize_images(value) for key, value in body.items()}
    if isinstance(body, list):
        return [summarize_images(item) for item in body]
    if isinstance(body, str) and len(body) > 400 and " " not in body:
        return f"<base64 {len(body) * 3 // 4 // 1024} KB>"
    return body


def placeholder_images(job: Job) -> list[tuple[str, str]]:
    return [(MIME.get(reference.path.suffix.lower(), "image/png"),
             base64.b64encode(reference.path.read_bytes()).decode() if reference.path.is_file() else "A" * 1000)
            for reference in job.references]


def describe(job: Job) -> tuple[str, dict, list[str]]:
    notes = [f"reference #{index}: {reference.path} [{reference.role or 'no role'}]" for index, reference in enumerate(job.references, 1)]
    if job.provider == "gemini":
        ratio, exact = nearest_ratio(job.size, GEMINI_RATIOS)
        notes += [GEMINI_TERMS, POSITIVE_ONLY.format("Gemini")] + ([] if exact else [f"size {job.size} mapped to nearest ratio {ratio}"])
        return f"POST {GEMINI_URL} (json, x n={job.n} calls)", summarize_images(gemini_body(job, placeholder_images(job))), notes
    if job.provider == "bfl":
        notes.append(POSITIVE_ONLY.format("FLUX"))
        return f"POST {BFL_URL}/{job.model} (json, then poll polling_url, x n={job.n})", summarize_images(bfl_body(job, placeholder_images(job))), notes
    ratio, exact = nearest_ratio(job.size, RECRAFT_RATIOS)
    if not exact:
        notes.append(f"size {job.size} mapped to nearest ratio {ratio}")
    return f"POST {RECRAFT_URL} (json)", recraft_body(job), notes


RUNNERS = {"gemini": gemini_run, "bfl": bfl_run, "recraft": recraft_run}
