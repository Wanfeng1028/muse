"""Output handling for gen_image.py: versioned archive, decode checks, alpha check, composite-back and sidecars."""
import datetime
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from _gen_image_http import ApiError
from _gen_image_job import Job
from _gen_image_openai import Result, mask_alpha

sys.dont_write_bytecode = True

MIN_TRANSPARENT_SHARE = 0.01
PIL_FORMATS = {"png": "PNG", "webp": "WEBP", "jpg": "JPEG"}
COST_NOTE = "OpenAI usage x $30/M image out, $8/M image in, $5/M text in (Batch half); other providers: see extra"


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def archive_existing(current: Path) -> Path | None:
    if not current.exists():
        return None
    archive = current.parent / "raw"
    archive.mkdir(parents=True, exist_ok=True)
    stem, extension = current.name.rsplit(".", 1)
    version = 1
    while (archive / f"{stem}.v{version}.{extension}").exists():
        version += 1
    target = archive / f"{stem}.v{version}.{extension}"
    current.rename(target)
    sidecar = current.with_name(current.name + ".json")
    if sidecar.exists():
        sidecar.rename(target.with_name(target.name + ".json"))
    print(f"  archived {current} -> {target}")
    return target


def existing_outputs(name: str, folder: Path) -> list[Path]:
    exact = [path for path in folder.glob(f"{name}.*") if path.suffix != ".json" and path.stem == name]
    variants = [path for path in folder.glob(f"{name}.?.*") if path.suffix != ".json" and len(path.stem) == len(name) + 2]
    return sorted(exact + variants)


def is_done(job: Job) -> bool:
    return any(path.exists() for path in [job.output_paths()[0], job.target_dir / f"{job.name}.{job.extension}"])


def normalize(data: bytes, extension: str) -> bytes:
    if extension == "svg":
        head = data[:200].lstrip().lower()
        if not (head.startswith(b"<svg") or head.startswith(b"<?xml")):
            raise ApiError(f"expected SVG, got {data[:60]!r}")
        return data
    if len(data) < 1000:
        raise ApiError(f"only {len(data)} bytes returned (probably an error body, not an image)")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as error:
        raise ApiError(f"returned bytes do not decode as an image: {error}") from error
    wanted = PIL_FORMATS[extension]
    if image.format == wanted:
        return data
    buffer = io.BytesIO()
    (image.convert("RGB") if wanted == "JPEG" else image).save(buffer, format=wanted)
    return buffer.getvalue()


def alpha_report(path: Path) -> dict:
    with Image.open(path) as image:
        has_alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
        if not has_alpha:
            return {"has_alpha": False, "transparent_share": 0.0, "size": f"{image.width}x{image.height}"}
        alpha = np.asarray(image.convert("RGBA").getchannel("A"))
        return {"has_alpha": True, "transparent_share": round(float((alpha == 0).mean()), 4), "size": f"{image.width}x{image.height}"}


def alpha_failure(report: dict) -> str | None:
    if not report["has_alpha"]:
        return "no alpha channel in the output"
    if report["transparent_share"] <= MIN_TRANSPARENT_SHARE:
        return f"only {report['transparent_share']:.2%} fully transparent pixels"
    return None


def composite_back(original_path: Path, edited: bytes, mask_path: Path, feather: float) -> bytes:
    original = Image.open(original_path).convert("RGBA")
    output = Image.open(io.BytesIO(edited)).convert("RGBA")
    if output.size != original.size:
        output = output.resize(original.size, Image.LANCZOS)
    alpha, _ = mask_alpha(mask_path, original_path)
    weight = Image.eval(alpha, lambda value: 255 - value).filter(ImageFilter.GaussianBlur(feather))
    result = Image.composite(output, original, weight)
    buffer = io.BytesIO()
    result.save(buffer, format="PNG")
    return buffer.getvalue()


def sidecar_payload(job: Job, path: Path, result: Result, index: int, report: dict | None) -> dict:
    share = 1 / len(result.images)
    return {
        "name": job.name,
        "file": path.name,
        "variant": chr(97 + index) if job.n > 1 else None,
        "provider": job.provider,
        "model": job.model,
        "prompt": job.prompt,
        "size_requested": job.size,
        "size_written": report["size"] if report else None,
        "quality": job.quality,
        "background": "transparent" if job.transparent else "opaque",
        "output_format": job.output_format,
        "output_compression": job.output_compression,
        "references": [{"name": reference.name, "path": str(reference.path), "role": reference.role,
                        "sha256": sha256(reference.path)} for reference in job.references],
        "mask": {"path": str(job.mask), "sha256": sha256(job.mask), "composited_back": job.composite_back} if job.mask else None,
        "alpha": report if job.transparent else None,
        "usage": result.usage,
        "request_id": result.request_id,
        "estimated_cost_usd": round(result.cost * share, 5) if result.cost is not None else None,
        "cost_note": COST_NOTE,
        "style_hash": job.style_hash,
        "extra": result.extra,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }


def final_bytes(job: Job, data: bytes, feather: float) -> bytes:
    normalized = normalize(data, job.extension)
    if job.composite_back and job.mask and job.references:
        return normalize(composite_back(job.references[0].path, normalized, job.mask, feather), job.extension)
    return normalized


def write_results(job: Job, result: Result, feather: float = 1.0) -> list[str]:
    job.target_dir.mkdir(parents=True, exist_ok=True)
    prepared = [final_bytes(job, data, feather) for data in result.images[: job.n]]
    paths = job.output_paths()[: len(prepared)]
    for stale in existing_outputs(job.name, job.target_dir):
        archive_existing(stale)
    messages: list[str] = []
    for index, (path, data) in enumerate(zip(paths, prepared, strict=True)):
        path.write_bytes(data)
        report = alpha_report(path) if job.extension != "svg" else None
        sidecar = path.with_name(path.name + ".json")
        sidecar.write_text(json.dumps(sidecar_payload(job, path, result, index, report), indent=2, ensure_ascii=False))
        failure = alpha_failure(report) if job.transparent and report else None
        if failure:
            messages.append(f"FAIL {job.name}: wrote {path} but {failure}; regenerate on white/grey/green and run cutout.py")
        else:
            messages.append(f"ok   {job.name}: wrote {path} (+ .json)")
    return messages


def style_hash_warning(names: list[str], folders: list[Path]) -> str | None:
    hashes: dict[str, list[str]] = {}
    for name in names:
        for folder in folders:
            for path in existing_outputs(name, folder):
                sidecar = path.with_name(path.name + ".json")
                if sidecar.is_file():
                    value = json.loads(sidecar.read_text()).get("style_hash", "?")
                    hashes.setdefault(value, []).append(path.name)
    if len(hashes) <= 1:
        return None
    groups = "; ".join(f"{value}: {', '.join(sorted(set(files))[:6])}" for value, files in hashes.items())
    return f"warning: images in this set were made with different style suffixes ({groups})"
