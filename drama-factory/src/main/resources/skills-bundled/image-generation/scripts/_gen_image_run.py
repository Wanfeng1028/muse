"""Run one job against its provider, or print it as a dry run with the budget meter, for gen_image.py."""
import argparse
import json
import sys

import _gen_image_openai as openai_adapter
from _gen_image_http import ApiError, CostMeter, RateLimiter
from _gen_image_job import Job, estimate_cost
from _gen_image_output import write_results
from _gen_image_providers import RUNNERS, describe as describe_other

sys.dont_write_bytecode = True


def money(value: float | None) -> str:
    return "unknown" if value is None else f"${value:.4f}"


def missing_references(job: Job) -> list[str]:
    paths = [reference.path for reference in job.references] + ([job.mask] if job.mask else [])
    return [str(path) for path in paths if not path.is_file()]


def run_job(job: Job, key: str, args: argparse.Namespace, meter: CostMeter, limiter: RateLimiter) -> list[str]:
    missing = missing_references(job)
    if missing:
        return [f"FAIL {job.name}: missing {', '.join(missing)}"]
    estimate = estimate_cost(job, batch=False)
    if not meter.allows(estimate):
        return [f"STOP {job.name}: budget ${args.budget:.2f} reached ({meter.summary()}; next ~{money(estimate)})"]
    limiter.acquire(job.n)
    runner = openai_adapter.run if job.provider == "openai" else RUNNERS[job.provider]
    try:
        result = runner(job, key)
        messages = write_results(job, result, args.feather)
    except ApiError as error:
        return [f"FAIL {job.name}: {error}"]
    except (KeyError, ValueError, OSError) as error:
        return [f"FAIL {job.name}: unexpected response or file error: {type(error).__name__}: {error}"]
    spent = meter.add(result.cost)
    extra = f"  credits {result.extra['bfl_credits']}" if "bfl_credits" in result.extra else ""
    return messages + [f"     {job.name}: cost {money(result.cost)}, running {money(spent)}{extra}"]


def print_job(job: Job) -> None:
    describe = openai_adapter.describe if job.provider == "openai" else describe_other
    request, payload, notes = describe(job)
    targets = ", ".join(str(path) for path in job.output_paths())
    print(f"== {job.name}  [{job.provider}/{job.model}]  -> {targets}")
    print(request)
    print(json.dumps({key: value for key, value in payload.items() if key not in ("prompt", "input")}, indent=2, ensure_ascii=False))
    if "input" in payload:
        print(f"input parts: {json.dumps(payload['input'][1:], ensure_ascii=False)}")
    print(f"size: {job.size} OK" + (" (provider maps it, see notes)" if job.provider != "openai" else ""))
    for line in notes:
        print(line)
    print(f"prompt ({len(job.prompt)} chars):\n{job.prompt}")


def print_dry_run(jobs: list[Job], args: argparse.Namespace, meter: CostMeter) -> None:
    for job in jobs:
        print_job(job)
        estimate = estimate_cost(job, batch=args.batch)
        verdict = ""
        if not meter.allows(estimate):
            verdict = f"  -> STOP: --budget ${args.budget:.2f} would stop before this request"
        running = meter.add(estimate)
        basis = "rough: gpt-image-2 per-MP table + ~$0.03/reference; 2.5 differs" if estimate is not None else "no price table for this provider"
        print(f"estimate: ~{money(estimate)} ({basis}), running ~{money(running)}{verdict}\n")
    if args.batch and jobs:
        from _gen_image_batch import print_dry_run as print_batch
        print_batch([job for job in jobs if job.provider == "openai"])
