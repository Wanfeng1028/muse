"""OpenAI Batch API (half price, up to 24 h) for gen_image.py: submit JSONL, then fetch and write results."""
import base64
import dataclasses
import datetime
import json
import sys
from pathlib import Path

from _gen_image_http import ApiError, json_body, request_with_retries
from _gen_image_job import Job, ResolvedReference
from _gen_image_openai import API, MIME, as_png, mask_png, request_fields, result_from_body
from _gen_image_output import write_results

sys.dont_write_bytecode = True


def data_url(path: Path) -> str:
    mime = MIME.get(path.suffix.lower(), "image/png")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def batch_body(job: Job, placeholder: bool) -> dict:
    body = request_fields(job)
    if not job.references:
        return body
    body["images"] = [{"image_url": "<data url of " + str(ref.path) + ">" if placeholder else data_url(ref.path)}
                      for ref in job.references]
    if job.mask and not placeholder and job.references[0].path.suffix.lower() != ".png":
        body["images"][0] = {"image_url": "data:image/png;base64," + base64.b64encode(as_png(job.references[0].path)).decode()}
    if job.mask:
        mask = "<data url of mask>" if placeholder else "data:image/png;base64," + base64.b64encode(mask_png(job.mask, job.references[0].path)[0]).decode()
        body["mask"] = {"image_url": mask}
    return body


def batch_line(job: Job, placeholder: bool = False) -> dict:
    url = "/v1/images/edits" if job.references else "/v1/images/generations"
    return {"custom_id": job.name, "method": "POST", "url": url, "body": batch_body(job, placeholder)}


def job_record(job: Job) -> dict:
    record = dataclasses.asdict(job)
    return json.loads(json.dumps(record, default=str))


def job_from_record(record: dict) -> Job:
    record = dict(record)
    record["references"] = [ResolvedReference(item["name"], Path(item["path"]), item["role"]) for item in record["references"]]
    record["mask"] = Path(record["mask"]) if record["mask"] else None
    record["target_dir"] = Path(record["target_dir"])
    return Job(**record)


def group_by_endpoint(jobs: list[Job]) -> dict[str, list[Job]]:
    groups: dict[str, list[Job]] = {}
    for job in jobs:
        groups.setdefault("/v1/images/edits" if job.references else "/v1/images/generations", []).append(job)
    return groups


def print_dry_run(jobs: list[Job]) -> None:
    for endpoint, group in group_by_endpoint(jobs).items():
        print(f"BATCH {endpoint}: POST {API}/files (purpose=batch, {len(group)} JSONL lines), then POST {API}/batches")
        print(json.dumps({"input_file_id": "<file id>", "endpoint": endpoint, "completion_window": "24h"}))
        for job in group:
            line = batch_line(job, placeholder=True)
            line["body"]["prompt"] = line["body"]["prompt"][:80] + "..."
            print("  " + json.dumps(line, ensure_ascii=False))
        print()


def submit(jobs: list[Job], key: str, out: Path) -> list[str]:
    headers = {"Authorization": f"Bearer {key}"}
    manifests: list[str] = []
    for endpoint, group in group_by_endpoint(jobs).items():
        jsonl = "\n".join(json.dumps(batch_line(job)) for job in group).encode()
        upload = request_with_retries("POST", f"{API}/files", headers=headers, data={"purpose": "batch"},
                                      files={"file": ("batch.jsonl", jsonl, "application/jsonl")})
        file_id = json_body(upload)["id"]
        created = json_body(request_with_retries("POST", f"{API}/batches", headers=headers,
                                                 json={"input_file_id": file_id, "endpoint": endpoint, "completion_window": "24h"}))
        manifest = out / "batches" / f"{created['id']}.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        record = {"batch_id": created["id"], "endpoint": endpoint, "submitted": datetime.datetime.now().isoformat(timespec="seconds"),
                  "jobs": {job.name: job_record(job) for job in group}}
        manifest.write_text(json.dumps(record, indent=2, ensure_ascii=False))
        print(f"submitted batch {created['id']} ({len(group)} requests, {endpoint}); manifest {manifest}")
        manifests.append(created["id"])
    return manifests


def fetch(batch_id: str, out: Path, key: str) -> int:
    manifest = out / "batches" / f"{batch_id}.json"
    if not manifest.is_file():
        print(f"error: no manifest {manifest} (fetch with the same --out used to submit)", file=sys.stderr)
        return 1
    record = json.loads(manifest.read_text())
    headers = {"Authorization": f"Bearer {key}"}
    batch = json_body(request_with_retries("GET", f"{API}/batches/{batch_id}", headers=headers))
    print(f"batch {batch_id}: {batch.get('status')} {json.dumps(batch.get('request_counts', {}))}")
    if batch.get("status") != "completed":
        return 0 if batch.get("status") in ("validating", "in_progress", "finalizing") else 1
    failures = 0
    if batch.get("error_file_id"):
        errors = request_with_retries("GET", f"{API}/files/{batch['error_file_id']}/content", headers=headers).text
        for line in errors.splitlines():
            print(f"FAIL {line[:400]}")
            failures += 1
    if not batch.get("output_file_id"):
        return 1
    content = request_with_retries("GET", f"{API}/files/{batch['output_file_id']}/content", headers=headers).text
    for line in content.splitlines():
        item = json.loads(line)
        job = job_from_record(record["jobs"][item["custom_id"]])
        response = item.get("response") or {}
        try:
            if response.get("status_code") != 200:
                raise ApiError(f"status {response.get('status_code')}: {json.dumps(response.get('body'))[:300]}")
            messages = write_results(job, result_from_body(response["body"], response.get("request_id"), batch=True))
        except ApiError as error:
            messages = [f"FAIL {job.name}: {error}"]
        for message in messages:
            print(message)
            failures += message.startswith("FAIL")
    return 1 if failures else 0
