"""OpenAI Images API adapter for gen_image.py: request fields, multipart edits with roles and masks, usage cost."""
import base64
import io
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

from _gen_image_http import ApiError, json_body, request_with_retries
from _gen_image_job import Job

sys.dont_write_bytecode = True

API = "https://api.openai.com/v1"
PRICE_IMAGE_OUTPUT = 30 / 1_000_000
PRICE_IMAGE_INPUT = 8 / 1_000_000
PRICE_TEXT_INPUT = 5 / 1_000_000
MIME = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


@dataclass
class Result:
    images: list[bytes]
    usage: dict | None = None
    request_id: str | None = None
    cost: float | None = None
    extra: dict = field(default_factory=dict)


def request_fields(job: Job) -> dict:
    fields: dict = {
        "model": job.model,
        "prompt": job.prompt,
        "size": job.size,
        "quality": job.quality,
        "background": "transparent" if job.transparent else "opaque",
        "output_format": job.output_format,
        "n": job.n,
    }
    if job.output_compression is not None:
        fields["output_compression"] = job.output_compression
    if job.moderation:
        fields["moderation"] = job.moderation
    return fields


def endpoint(job: Job) -> str:
    return "images/edits" if job.references else "images/generations"


def mask_alpha(mask_path: Path, first_image: Path) -> tuple[Image.Image, str]:
    mask = Image.open(mask_path)
    base_size = Image.open(first_image).size
    if mask.size != base_size:
        raise ApiError(f"mask {mask.size[0]}x{mask.size[1]} differs from Image 1 {base_size[0]}x{base_size[1]} ({first_image.name})")
    if mask.mode in ("RGBA", "LA") or (mask.mode == "P" and "transparency" in mask.info):
        return mask.convert("RGBA").getchannel("A"), "alpha channel (transparent = edit)"
    return ImageOps.invert(mask.convert("L")), "black/white converted to alpha (white = edit)"


def mask_png(mask_path: Path, first_image: Path) -> tuple[bytes, str]:
    alpha, source = mask_alpha(mask_path, first_image)
    rgba = Image.new("RGBA", alpha.size, (0, 0, 0, 255))
    rgba.putalpha(alpha)
    buffer = io.BytesIO()
    rgba.save(buffer, format="PNG")
    edit_share = sum(alpha.histogram()[:128]) / (alpha.width * alpha.height)
    return buffer.getvalue(), f"{source}; edit area {edit_share:.0%} of Image 1"


def as_png(path: Path) -> bytes:
    buffer = io.BytesIO()
    Image.open(path).save(buffer, format="PNG")
    return buffer.getvalue()


def reference_files(job: Job) -> list[tuple[str, tuple[str, bytes, str]]]:
    files = []
    for index, reference in enumerate(job.references):
        path = reference.path
        if index == 0 and job.mask and path.suffix.lower() != ".png":
            files.append(("image[]", (f"{path.stem}.png", as_png(path), "image/png")))
            continue
        files.append(("image[]", (path.name, path.read_bytes(), MIME.get(path.suffix.lower(), "image/png"))))
    if job.mask:
        mask_bytes, _ = mask_png(job.mask, job.references[0].path)
        files.append(("mask", ("mask.png", mask_bytes, "image/png")))
    return files


def usage_cost(usage: dict | None, batch: bool = False) -> float | None:
    if not usage:
        return None
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    image_in = input_details.get("image_tokens", 0)
    text_in = input_details.get("text_tokens", max(0, usage.get("input_tokens", 0) - image_in))
    image_out = output_details.get("image_tokens", usage.get("output_tokens", 0))
    cost = image_out * PRICE_IMAGE_OUTPUT + image_in * PRICE_IMAGE_INPUT + text_in * PRICE_TEXT_INPUT
    return cost * (0.5 if batch else 1.0)


def result_from_body(body: dict, request_id: str | None, batch: bool = False) -> Result:
    items = body.get("data") or []
    images = [base64.b64decode(item["b64_json"]) for item in items if item.get("b64_json")]
    if not images:
        raise ApiError(f"no b64_json images in response: {str(body)[:300]}")
    revised = [item.get("revised_prompt") for item in items if item.get("revised_prompt")]
    extra = {key: body[key] for key in ("size", "quality", "background", "output_format") if key in body}
    if revised:
        extra["revised_prompt"] = revised
    usage = body.get("usage")
    return Result(images, usage, request_id, usage_cost(usage, batch), extra)


def run(job: Job, key: str) -> Result:
    headers = {"Authorization": f"Bearer {key}"}
    fields = request_fields(job)
    if job.references:
        data = {name: str(value) for name, value in fields.items()}
        response = request_with_retries("POST", f"{API}/images/edits", headers=headers, data=data, files=reference_files(job))
    else:
        response = request_with_retries("POST", f"{API}/images/generations", headers=headers, json=fields)
    return result_from_body(json_body(response), response.headers.get("x-request-id"))


def describe_file(path: Path) -> str:
    if not path.is_file():
        return "not on disk yet (made in an earlier wave)"
    with Image.open(path) as image:
        return f"{image.width}x{image.height} {image.mode}, {path.stat().st_size // 1024} KB"


def describe(job: Job) -> tuple[str, dict, list[str]]:
    kind = "multipart" if job.references else "json"
    fields = {name: value for name, value in request_fields(job).items() if name != "prompt"}
    lines = [f"image[] #{index}: {reference.path} [{reference.role or 'no role'}] ({describe_file(reference.path)})"
             for index, reference in enumerate(job.references, 1)]
    if job.mask:
        first = job.references[0].path if job.references else None
        if first and first.is_file() and job.mask.is_file():
            try:
                _, summary = mask_png(job.mask, first)
                converted = "" if first.suffix.lower() == ".png" else "; Image 1 sent as PNG to match the mask"
                lines.append(f"mask: {job.mask} -> applies to Image 1 ({first.name}); {summary}{converted}")
            except ApiError as error:
                lines.append(f"mask: {job.mask} ERROR {error}")
        else:
            lines.append(f"mask: {job.mask} (checked at send time; Image 1 or mask not on disk yet)")
        if job.composite_back:
            lines.append("composite-back: output pasted over Image 1 only inside the mask (feathered)")
    return f"POST {API}/{endpoint(job)} ({kind})", fields, lines
