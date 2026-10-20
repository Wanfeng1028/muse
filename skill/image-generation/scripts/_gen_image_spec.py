"""Prompts-file schema, model policy, size/aspect validation and backdrop lines for gen_image.py."""
import datetime
import math
import re
import sys

from pydantic import BaseModel, ConfigDict, Field

sys.dont_write_bytecode = True

WHITE = "Plain flat solid pure white (#FFFFFF) background with nothing on it, no floor shadow."
TRANSPARENT_LINE = "Transparent background."
BACKDROP_PRESETS = {"white": "#FFFFFF", "grey": "#808080", "gray": "#808080", "green": "#00B140"}
ASPECT_PRESETS = {"16:9": "2048x1152", "9:16": "1152x2048", "1:1": "1536x1536", "4:5": "1280x1600"}
OPENAI_DEFAULT_MODEL = "gpt-image-2.5-flare"
OPENAI_FINAL_MODEL = "gpt-image-2.5-sunburst"
BASE_QUALITIES = {"low", "medium", "high", "auto"}
EXTENDED_QUALITIES = {"xhigh", "max"}
SHUTDOWNS = {
    "dall-e-2": datetime.date(2026, 5, 12),
    "dall-e-3": datetime.date(2026, 5, 12),
    "gpt-image-1": datetime.date(2026, 10, 23),
    "gpt-image-1.5": datetime.date(2026, 12, 1),
    "gpt-image-1-mini": datetime.date(2026, 12, 1),
    "chatgpt-image-latest": datetime.date(2026, 12, 1),
}
MIN_PIXELS = 655_360
MAX_PIXELS = 8_294_400
MAX_EDGE = 3840
EXPERIMENTAL_PIXELS = 2560 * 1440
DRAFT_PIXELS = 1024 * 1024


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    role: str | None = None


class ImageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str
    notes: str | None = None
    size: str | None = None
    aspect: str | None = None
    overscan: float | None = Field(default=None, ge=1.0, le=3.0)
    quality: str | None = None
    references: list[str | Reference] = []
    edit_of: str | None = None
    mask: str | None = None
    background: str | None = None
    n: int | None = Field(default=None, ge=1, le=10)
    output_format: str | None = Field(default=None, pattern="^(png|webp|jpeg)$")
    output_compression: int | None = Field(default=None, ge=0, le=100)
    provider: str | None = None
    model: str | None = None


class PromptsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style: str
    notes: str | None = None
    background: str = WHITE
    size: str = "1536x1024"
    aspect: str | None = None
    quality: str = "high"
    provider: str | None = None
    model: str | None = None
    output_format: str = Field(default="png", pattern="^(png|webp|jpeg)$")
    output_compression: int | None = Field(default=None, ge=0, le=100)
    palette: list[str] = []
    images: dict[str, ImageSpec]


def references_of(spec: ImageSpec) -> list[Reference]:
    return [Reference(ref=item) if isinstance(item, str) else item for item in spec.references]


def is_path_reference(reference: str) -> bool:
    return "/" in reference or bool(re.search(r"\.(png|webp|jpe?g)$", reference, re.IGNORECASE))


def dependencies_of(name: str, spec: ImageSpec) -> set[str]:
    names = {item.ref for item in references_of(spec) if not is_path_reference(item.ref)}
    if spec.edit_of and spec.edit_of != name:
        names.add(spec.edit_of)
    return names


def order_names(requested: list[str], config: PromptsFile) -> list[list[str]]:
    unknown = [name for name in requested if name not in config.images]
    if unknown:
        sys.exit(f"error: not in prompts file: {', '.join(unknown)}")
    pending = list(requested or config.images)
    waves: list[list[str]] = []
    while pending:
        wave = [name for name in pending if not dependencies_of(name, config.images[name]) & set(pending)]
        if not wave:
            sys.exit(f"error: circular references among {', '.join(pending)}")
        waves.append(wave)
        pending = [name for name in pending if name not in wave]
    return waves


def backdrop_line(background: str) -> str | None:
    value = background.strip()
    if value.lower() == "transparent":
        return None
    if value.lower() == "none":
        return ""
    hex_value = BACKDROP_PRESETS.get(value.lower())
    if value.lower().startswith("color:"):
        hex_value = value.split(":", 1)[1].strip()
    if hex_value is None:
        return value
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", hex_value):
        sys.exit(f"error: background colour must be #RRGGBB, got {hex_value}")
    if hex_value.upper() == "#FFFFFF":
        return WHITE
    return f"Plain flat solid {hex_value.upper()} colour background with nothing on it, no floor shadow."


def parse_size(size: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)x(\d+)", size.strip())
    if not match:
        raise ValueError(f"size must be WIDTHxHEIGHT or auto, got {size!r}")
    return int(match.group(1)), int(match.group(2))


def size_problems(size: str) -> tuple[list[str], list[str]]:
    if size == "auto":
        return [], []
    width, height = parse_size(size)
    errors: list[str] = []
    warnings: list[str] = []
    if width % 16 or height % 16:
        errors.append(f"{size}: both edges must be multiples of 16")
    if max(width, height) > MAX_EDGE:
        errors.append(f"{size}: longest edge above {MAX_EDGE}")
    if max(width, height) / min(width, height) > 3:
        errors.append(f"{size}: aspect ratio beyond 3:1")
    if not MIN_PIXELS <= width * height <= MAX_PIXELS:
        errors.append(f"{size}: {width * height:,} px outside {MIN_PIXELS:,}-{MAX_PIXELS:,}")
    if width * height > EXPERIMENTAL_PIXELS:
        warnings.append(f"{size}: above 2560x1440 is experimental on GPT Image")
    return errors, warnings


def round16(value: float) -> int:
    return max(16, int(round(value / 16)) * 16)


def fit_pixels(width: int, height: int, target_pixels: float) -> tuple[int, int]:
    scale = math.sqrt(target_pixels / (width * height))
    new_width, new_height = round16(width * scale), round16(height * scale)
    while new_width * new_height > MAX_PIXELS or max(new_width, new_height) > MAX_EDGE:
        new_width, new_height = round16(new_width * 0.99), round16(new_height * 0.99)
    while new_width * new_height < MIN_PIXELS:
        new_width, new_height = new_width + 16, round16((new_width + 16) * height / width)
    return new_width, new_height


def within_limits(width: int, height: int) -> bool:
    return width * height <= MAX_PIXELS and max(width, height) <= MAX_EDGE


def exact_ratio_scale(width: int, height: int, overscan: float) -> tuple[int, int] | None:
    if width % 16 or height % 16:
        return None
    divisor = math.gcd(width // 16, height // 16)
    step_width, step_height = width // divisor, height // divisor
    multiple = math.ceil(divisor * overscan - 1e-9)
    while multiple > divisor and not within_limits(step_width * multiple, step_height * multiple):
        multiple -= 1
    if multiple <= divisor or step_width * multiple > width * overscan * 1.15:
        return None
    return step_width * multiple, step_height * multiple


def apply_overscan(size: str, overscan: float) -> tuple[str, str | None]:
    if size == "auto" or overscan == 1.0:
        return size, None
    width, height = parse_size(size)
    exact = exact_ratio_scale(width, height, overscan)
    new_width, new_height = exact or fit_pixels(width, height, width * overscan * height * overscan)
    if new_width * new_height <= width * height:
        return size, f"no room for overscan {overscan}: {size} is already at the size limit"
    reached = new_width / width
    note = None if reached >= overscan - 0.01 else f"overscan capped at {reached:.2f}x by the size limits"
    return f"{new_width}x{new_height}", note


def draft_size(size: str) -> str:
    if size == "auto":
        return size
    width, height = parse_size(size)
    if width * height <= DRAFT_PIXELS:
        return size
    if width % 16 == 0 and height % 16 == 0:
        divisor = math.gcd(width // 16, height // 16)
        step_width, step_height = width // divisor, height // divisor
        multiple = math.isqrt(DRAFT_PIXELS // (step_width * step_height))
        if multiple >= 1 and step_width * step_height * multiple * multiple >= MIN_PIXELS:
            return f"{step_width * multiple}x{step_height * multiple}"
    new_width, new_height = fit_pixels(width, height, DRAFT_PIXELS)
    return f"{new_width}x{new_height}"


def resolve_size(size: str, aspect: str | None) -> str:
    if not aspect:
        return size
    if aspect not in ASPECT_PRESETS:
        sys.exit(f"error: aspect must be one of {', '.join(ASPECT_PRESETS)}, got {aspect}")
    return ASPECT_PRESETS[aspect]


def is_extended_model(model: str) -> bool:
    return model.startswith("gpt-image-2.5")


def supports_transparency(model: str) -> bool:
    return is_extended_model(model)


def model_policy(model: str, today: datetime.date) -> str | None:
    base = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model)
    shutdown = SHUTDOWNS.get(base)
    if shutdown is None:
        return None
    if today >= shutdown:
        sys.exit(f"error: {model} was shut down on {shutdown}; use {OPENAI_DEFAULT_MODEL} or {OPENAI_FINAL_MODEL}")
    return f"warning: {model} shuts down on {shutdown}; migrate to {OPENAI_DEFAULT_MODEL} or {OPENAI_FINAL_MODEL}"


def check_quality(quality: str, model: str, provider: str) -> str | None:
    if provider != "openai":
        return None
    if quality in BASE_QUALITIES:
        return None
    if quality in EXTENDED_QUALITIES and is_extended_model(model):
        return None
    if quality in EXTENDED_QUALITIES:
        return f"quality {quality} needs a gpt-image-2.5 model, not {model}"
    return f"unknown quality {quality!r} (low, medium, high, auto; xhigh, max on 2.5)"
