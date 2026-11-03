"""Resolve a prompts-file entry plus CLI flags into one concrete generation job for gen_image.py."""
import argparse
import datetime
import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

import _gen_image_spec as spec_module
from _gen_image_spec import ImageSpec, PromptsFile, Reference

sys.dont_write_bytecode = True

PROVIDER_DEFAULT_MODELS = {
    "openai": spec_module.OPENAI_DEFAULT_MODEL,
    "gemini": "gemini-nano-banana-2.1",
    "bfl": "flux-2-pro",
    "recraft": "recraftv4_1",
}
MAX_REFERENCES = {"openai": 16, "gemini": 14, "bfl": 8, "recraft": 0}
EXTENSIONS = ("png", "webp", "jpg", "jpeg", "svg")
EDIT_ROLE = "the image to edit; keep everything this prompt does not change"
ROUGH_PRICE_PER_MEGAPIXEL = {"low": 0.006, "medium": 0.053, "high": 0.211, "auto": 0.211, "xhigh": 0.32, "max": 0.42}
ROUGH_REFERENCE_PRICE = 0.032


@dataclass
class ResolvedReference:
    name: str
    path: Path
    role: str | None


@dataclass
class Job:
    name: str
    provider: str
    model: str
    prompt: str
    size: str
    quality: str
    transparent: bool
    output_format: str
    output_compression: int | None
    n: int
    references: list[ResolvedReference]
    mask: Path | None
    composite_back: bool
    target_dir: Path
    style_hash: str
    moderation: str | None
    palette: list[str]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def extension(self) -> str:
        if self.provider == "recraft" and self.model.endswith("_vector"):
            return "svg"
        return "jpg" if self.output_format == "jpeg" else self.output_format

    def output_paths(self) -> list[Path]:
        if self.n == 1:
            return [self.target_dir / f"{self.name}.{self.extension}"]
        return [self.target_dir / f"{self.name}.{chr(97 + index)}.{self.extension}" for index in range(self.n)]


def style_hash(style: str) -> str:
    return hashlib.sha256(style.encode()).hexdigest()[:12]


def find_output(name: str, folders: list[Path]) -> Path | None:
    for folder in folders:
        for extension in EXTENSIONS:
            candidate = folder / f"{name}.{extension}"
            if candidate.is_file():
                return candidate
    return None


def resolve_reference(item: Reference, prompts: Path, folders: list[Path]) -> ResolvedReference:
    if spec_module.is_path_reference(item.ref):
        return ResolvedReference(item.ref, (prompts.parent / item.ref).resolve(), item.role)
    found = find_output(item.ref, folders)
    return ResolvedReference(item.ref, found or folders[0] / f"{item.ref}.png", item.role)


def ordered_references(name: str, spec: ImageSpec, prompts: Path, folders: list[Path]) -> list[ResolvedReference]:
    references = [resolve_reference(item, prompts, folders) for item in spec_module.references_of(spec)]
    if not (spec.mask and not spec.edit_of):
        references.sort(key=lambda reference: 0 if reference.role and "identity" in reference.role.lower() else 1)
    if spec.edit_of:
        found = find_output(spec.edit_of, folders)
        edited = ResolvedReference(spec.edit_of, found or folders[0] / f"{spec.edit_of}.png", EDIT_ROLE)
        references.insert(0, edited)
    return references


def image_lines(references: list[ResolvedReference]) -> str:
    if not any(reference.role for reference in references):
        return ""
    lines = [f"Image {index}: {reference.role or 'reference'} ({reference.name})." for index, reference in enumerate(references, 1)]
    return "\n".join(lines) + "\n\n"


def compose_prompt(spec: ImageSpec, config: PromptsFile, references: list[ResolvedReference], backdrop: str | None) -> str:
    ending = backdrop if backdrop is not None else spec_module.TRANSPARENT_LINE
    return f"{image_lines(references)}{spec.prompt}\n\nStyle: {config.style} {ending}".rstrip()


def resolve_provider_and_model(spec: ImageSpec, config: PromptsFile, args: argparse.Namespace) -> tuple[str, str]:
    provider = args.provider or spec.provider or config.provider or "openai"
    if provider not in PROVIDER_DEFAULT_MODELS:
        sys.exit(f"error: unknown provider {provider} ({', '.join(PROVIDER_DEFAULT_MODELS)})")
    if args.model:
        return provider, args.model
    if args.final and provider == "openai":
        return provider, spec_module.OPENAI_FINAL_MODEL
    if spec.model:
        return provider, spec.model
    if config.model and provider == (config.provider or "openai"):
        return provider, config.model
    return provider, PROVIDER_DEFAULT_MODELS[provider]


def resolve_quality(spec: ImageSpec, config: PromptsFile, args: argparse.Namespace) -> str:
    if args.quality:
        return args.quality
    if args.draft:
        return "low"
    if args.final:
        return "high"
    return spec.quality or config.quality


def resolve_job_size(spec: ImageSpec, config: PromptsFile, args: argparse.Namespace, job_warnings: list[str]) -> str:
    if args.aspect or spec.aspect:
        size = spec_module.resolve_size("", args.aspect or spec.aspect)
    elif spec.size:
        size = spec.size
    else:
        size = spec_module.resolve_size(config.size, config.aspect)
    overscan = args.overscan or spec.overscan or 1.0
    size, note = spec_module.apply_overscan(size, overscan)
    if note:
        job_warnings.append(note)
    return spec_module.draft_size(size) if args.draft else size


def resolve_format(spec: ImageSpec, config: PromptsFile, transparent: bool, job_warnings: list[str]) -> tuple[str, int | None]:
    output_format = spec.output_format or config.output_format
    compression = spec.output_compression if spec.output_compression is not None else config.output_compression
    if transparent and output_format == "jpeg":
        job_warnings.append("jpeg has no alpha: switched to png for the transparent background")
        output_format = "png"
    if compression is not None and output_format == "png":
        job_warnings.append("output_compression applies to jpeg/webp only: ignored for png")
        compression = None
    return output_format, compression


def validate(job: Job, spec: ImageSpec, today: datetime.date) -> None:
    if job.provider == "openai":
        policy = spec_module.model_policy(job.model, today)
        if policy:
            job.warnings.append(policy)
        errors, size_warnings = spec_module.size_problems(job.size)
        job.errors += errors
        job.warnings += size_warnings
    quality_problem = spec_module.check_quality(job.quality, job.model, job.provider)
    if quality_problem:
        job.errors.append(quality_problem)
    if job.transparent and not (job.provider == "openai" and spec_module.supports_transparency(job.model)):
        job.errors.append(f"transparent background is not supported on {job.provider}/{job.model}: use a gpt-image-2.5 "
                          "model, or generate on white/grey/green and run cutout.py")
    limit = MAX_REFERENCES[job.provider] if not job.model.startswith("flux-3") else 10
    if job.references and limit == 0:
        job.errors.append(f"{job.provider} takes no references in this script (text-to-image only)")
    elif len(job.references) > limit:
        job.errors.append(f"{len(job.references)} references; {job.provider}/{job.model} takes at most {limit}")
    if job.mask and job.provider != "openai":
        job.errors.append("masks are only implemented for the OpenAI provider")
    if job.mask and not job.references:
        job.errors.append("a mask needs an image to edit (references or edit_of): it applies to Image 1")
    if job.mask and job.references and job.mask.is_file() and job.references[0].path.is_file():
        mask_size, image_size = Image.open(job.mask).size, Image.open(job.references[0].path).size
        if mask_size != image_size:
            job.errors.append(f"mask is {mask_size[0]}x{mask_size[1]} but Image 1 ({job.references[0].name}) is "
                              f"{image_size[0]}x{image_size[1]}; they must match")
    if job.composite_back and not job.mask:
        job.warnings.append("--composite-back ignored: no mask on this image")
        job.composite_back = False
    if spec.edit_of and job.references and not job.references[0].path.is_file():
        job.warnings.append(f"edit_of {spec.edit_of}: {job.references[0].path} not on disk yet (pick a variant first if it has several)")


def build_job(name: str, config: PromptsFile, args: argparse.Namespace) -> Job:
    spec = config.images[name]
    provider, model = resolve_provider_and_model(spec, config, args)
    target_dir = args.out / "drafts" if args.draft else args.out
    folders = [target_dir, args.out] if args.draft else [args.out]
    warnings: list[str] = []
    backdrop = spec_module.backdrop_line(spec.background or config.background)
    references = ordered_references(name, spec, args.prompts, folders)
    output_format, compression = resolve_format(spec, config, backdrop is None, warnings)
    job = Job(
        name=name, provider=provider, model=model,
        prompt=compose_prompt(spec, config, references, backdrop),
        size=resolve_job_size(spec, config, args, warnings),
        quality=resolve_quality(spec, config, args),
        transparent=backdrop is None, output_format=output_format, output_compression=compression,
        n=spec.n or (4 if args.draft else 1), references=references,
        mask=(args.prompts.parent / spec.mask).resolve() if spec.mask else None,
        composite_back=args.composite_back, target_dir=target_dir, style_hash=style_hash(config.style),
        moderation=args.moderation, palette=config.palette, warnings=warnings,
    )
    validate(job, spec, datetime.date.today())
    return job


def estimate_cost(job: Job, batch: bool) -> float | None:
    if job.provider != "openai" or job.size == "auto":
        return None
    width, height = spec_module.parse_size(job.size)
    per_image = ROUGH_PRICE_PER_MEGAPIXEL.get(job.quality, 0.211) * width * height / 1_048_576
    total = per_image * job.n + ROUGH_REFERENCE_PRICE * len(job.references)
    return total * (0.5 if batch else 1.0)
