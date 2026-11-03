#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "pydantic>=2", "pillow>=10.1", "numpy>=1.26"]
# ///
"""Generate or edit images from a prompts file with a locked style suffix, references with roles and a version archive.

Every prompt is sent as "[Image N: role lines]<prompt>\\n\\nStyle: <style> <backdrop line>", so only the subject varies.
An image with references or edit_of goes to /images/edits (Image 1 = edit_of, then identity refs); others to
/images/generations. Existing outputs are skipped unless --regenerate, which archives old files to <out>/raw/<name>.vN.<ext>.
Every output gets a <file>.json sidecar (prompt, model, size, refs with SHA-256, usage, request id, cost, style hash).

Models (OpenAI, checked 2026-10-06): default gpt-image-2.5-flare (drafts); --final = gpt-image-2.5-sunburst + high.
gpt-image-1 shuts down 2026-10-23 (refused after); 1.5, 1-mini, chatgpt-image-latest on 2026-12-01 (warned).
Transparent backgrounds only on gpt-image-2.5 (gpt-image-2's preview was withdrawn; edits reject it): the backdrop line
is dropped, png/webp forced, and the decoded file must have >1% fully transparent pixels or the image FAILs.
Sizes: WxH multiples of 16, ratio <= 3:1, edge <= 3840, 655,360-8,294,400 px; above 2560x1440 is experimental.

Subcommands (first argument instead of the prompts file):
  pick NAME LETTER [--dir DIR]          promote NAME.LETTER.* to NAME.*, archive the other variants
  contact-sheet IMAGES... --out PNG     labelled grid for review in one look
  check-alpha IMAGES...                 report alpha; exit 1 if any file lacks real transparency
  batch-fetch BATCH_ID --out DIR        download a finished --batch job and write files + sidecars

Keys from env or --env-file: OPENAI_API_KEY, GEMINI_API_KEY, BFL_API_KEY, RECRAFT_API_KEY.
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gen_image_cli import SUBCOMMANDS, add_generation_arguments  # noqa: E402
from _gen_image_http import CostMeter, RateLimiter, load_env_file, require_key  # noqa: E402
from _gen_image_job import Job, build_job  # noqa: E402
from _gen_image_output import existing_outputs, is_done, style_hash_warning  # noqa: E402
from _gen_image_run import print_dry_run, run_job  # noqa: E402
from _gen_image_spec import PromptsFile, order_names  # noqa: E402

EXAMPLES = """examples:
  gen_image.py image_prompts.json --out public/img --dry-run
  gen_image.py image_prompts.json cast --draft --contact-sheet out/review/cast-drafts.png
  gen_image.py pick cast b --dir public/img/drafts
  gen_image.py image_prompts.json shot-kitchen --final --aspect 16:9 --overscan 1.2 --budget 2
  gen_image.py image_prompts.json --batch --final            # half price, results within 24 h
  gen_image.py batch-fetch batch_abc123 --out public/img"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Image generation/edits (OpenAI default; Gemini, FLUX, Recraft via --provider) with a locked style.",
        epilog=__doc__.split("\n\n", 1)[1] + "\n" + EXAMPLES + "\n\nPrompts-file schema: see scripts/README.md.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("prompts", type=Path, help="prompts JSON (see assets/image_prompts.example.json)")
    parser.add_argument("names", nargs="*", help="images to generate (default: all, references first)")
    add_generation_arguments(parser)
    args = parser.parse_args()
    if args.draft and args.final:
        parser.error("--draft and --final are exclusive")
    if args.batch and (args.provider or "openai") != "openai":
        parser.error("--batch is OpenAI only")
    return args


def pending_jobs(wave: list[str], config: PromptsFile, args: argparse.Namespace) -> list[Job]:
    jobs = []
    for name in wave:
        job = build_job(name, config, args)
        if not args.regenerate and is_done(job):
            print(f"skip {name}: {job.output_paths()[0]} exists (use --regenerate)")
            continue
        jobs.append(job)
    return jobs


def report_problems(jobs: list[Job]) -> tuple[list[Job], int]:
    runnable, failures = [], 0
    for job in jobs:
        for warning in job.warnings:
            print(f"  {job.name}: {warning if warning.startswith('warning') else 'warning: ' + warning}")
        if job.errors:
            print(f"FAIL {job.name}: " + "; ".join(job.errors))
            failures += 1
            continue
        runnable.append(job)
    return runnable, failures


def run_wave(jobs: list[Job], args: argparse.Namespace, keys: dict[str, str], meter: CostMeter, limiter: RateLimiter) -> int:
    failures = 0
    workers = max(1, min(args.concurrency, args.ipm))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for messages in pool.map(lambda job: run_job(job, keys[job.provider], args, meter, limiter), jobs):
            for message in messages:
                print(message, flush=True)
                failures += message.startswith(("FAIL", "STOP"))
    return failures


def provider_keys(config: PromptsFile, args: argparse.Namespace) -> dict[str, str]:
    load_env_file(args.env_file)
    providers = {build_job(name, config, args).provider for name in (args.names or config.images)}
    return {provider: require_key(provider) for provider in sorted(providers)}


def submit_batch(jobs: list[Job], keys: dict[str, str], args: argparse.Namespace, more_waves: bool) -> int:
    from _gen_image_batch import submit
    from _gen_image_http import ApiError
    if more_waves:
        print("note: later waves reference this one; run --batch again after batch-fetch")
    if not jobs:
        return 0
    try:
        submit(jobs, keys["openai"], args.out)
    except ApiError as error:
        print(f"FAIL batch submit: {error}")
        return 1
    return 0


def finish(config: PromptsFile, args: argparse.Namespace, meter: CostMeter) -> None:
    names = args.names or list(config.images)
    folders = [args.out / "drafts", args.out] if args.draft else [args.out]
    warning = style_hash_warning(list(config.images), folders)
    if warning:
        print(warning)
    if args.contact_sheet:
        from _gen_image_review import contact_sheet
        contact_sheet([path for name in names for path in existing_outputs(name, folders[0])], args.contact_sheet)
    print(("estimated (rough) " if args.dry_run else "") + meter.summary())


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in SUBCOMMANDS:
        return SUBCOMMANDS[sys.argv[1]](sys.argv[2:])
    args = parse_args()
    config = PromptsFile.model_validate_json(args.prompts.read_text())
    waves = order_names(args.names, config)
    keys = {} if args.dry_run else provider_keys(config, args)
    meter, limiter = CostMeter(args.budget), RateLimiter(args.ipm)
    failures = 0
    for wave_index, wave in enumerate(waves):
        jobs, wave_failures = report_problems(pending_jobs(wave, config, args))
        failures += wave_failures
        if args.dry_run:
            print_dry_run(jobs, args, meter)
            continue
        if args.batch:
            failures += submit_batch(jobs, keys, args, wave_index < len(waves) - 1)
            break
        failures += run_wave(jobs, args, keys, meter, limiter)
    finish(config, args, meter)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
