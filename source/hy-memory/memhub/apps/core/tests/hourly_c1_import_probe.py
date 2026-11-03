"""C1 hourly experiment: cold-start import into an isolated Home, then clean up.

This is C1's own evidence for the hourly package, not a package build (C0 owns
releases). It must never touch `~/.one-memory` or a real host source: it creates
its own marker-owned data directory, imports from a throwaway copy of real
transcripts, prints one JSON receipt, and removes exactly what it created.
"""

import argparse
import asyncio
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore
from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor

HOURLY_ROOT = Path.home() / "Library" / "Application Support" / "One Memory Hourly"
MARKER = ".one-memory-hourly-owned"


def _sample(origin: Path, target: Path, *, limit: int, cap: int) -> list[Path]:
    files = sorted(
        (path for path in origin.rglob("*.jsonl") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]
    copied = []
    for path in files:
        destination = target / path.relative_to(origin)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with path.open("rb") as handle:
            destination.write_bytes(handle.read(cap))
        copied.append(path)
    return copied


def _fingerprint(paths: list[Path]) -> dict[str, tuple[int, str]]:
    result = {}
    for path in paths:
        details = path.stat()
        with path.open("rb") as handle:
            result[path.as_posix()] = (
                details.st_size,
                hashlib.sha256(handle.read(8 * 1024 * 1024)).hexdigest(),
            )
    return result


async def run_import(data_dir: Path, root: Path, source: str) -> dict:
    database = data_dir / "one-memory.sqlite3"
    jobs = ImportJobStore(database)
    evidence = EvidenceStore(database)
    grants = SourceGrantStore(database, home=data_dir / "home")
    grants.grant(
        user_id="local",
        source_id=source,
        root=root,
        candidate_kind=RootCandidateKind.DEFAULT,
    )
    registration = build_source_catalog(home=data_dir / "home", environment={})[source]
    supervisor = ImportSupervisor(
        adapters={
            source: registration.create_adapter(
                grants.authorized_root(user_id="local", source_id=source)
            )
        },
        evidence_store=evidence,
        job_store=jobs,
    )
    job = supervisor.create_job(source)
    supervisor.enqueue(job.job_id)
    first = await supervisor.wait(job.job_id)
    again = supervisor.create_job(source)
    supervisor.enqueue(again.job_id)
    second = await supervisor.wait(again.job_id)
    return {
        "source": source,
        "first": {
            "status": str(first.status),
            "stored": first.stored,
            "merged": first.merged,
            "skipped": first.skipped,
            "errors": first.errors,
            "discovered_targets": first.discovered_targets,
        },
        "second": {
            "status": str(second.status),
            "stored": second.stored,
            "merged": second.merged,
            "emitted": second.emitted,
        },
        "evidence_rows": evidence.count(),
    }


async def run_append(data_dir: Path, root: Path, source: str) -> dict:
    """Append one record to the copy, then prove only that record arrives.

    Only a file copied whole is appended to: a capped copy ends in a half line,
    and appending after that half line would create one broken record instead of
    exercising append.
    """
    database = data_dir / "one-memory.sqlite3"
    jobs = ImportJobStore(database)
    evidence = EvidenceStore(database)
    grants = SourceGrantStore(database, home=data_dir / "home")
    registration = build_source_catalog(home=data_dir / "home", environment={})[source]

    candidates = sorted(root.rglob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    whole = [path for path in candidates if path.stat().st_size < 8 * 1024 * 1024] or candidates
    target = whole[0]
    if not target.read_bytes().endswith(b"\n"):
        with target.open("a", encoding="utf-8") as stream:
            stream.write("\n")
    record = (
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "appended on the copy"}],
            },
        }
        if source == "codex"
        else {
            "type": "user",
            "sessionId": "appended",
            "timestamp": "2026-09-28T11:00:00+08:00",
            "message": {"content": "appended on the copy"},
        }
    )
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")

    rows_before = evidence.count()
    supervisor = ImportSupervisor(
        adapters={
            source: registration.create_adapter(
                grants.authorized_root(user_id="local", source_id=source)
            )
        },
        evidence_store=evidence,
        job_store=jobs,
    )
    job = supervisor.create_job(source)
    supervisor.enqueue(job.job_id)
    final = await supervisor.wait(job.job_id)
    return {
        "status": str(final.status),
        "stored": final.stored,
        "errors": final.errors,
        "rows_before": rows_before,
        "rows_after": evidence.count(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--source", default="workbuddy")
    parser.add_argument("--origin", default="")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument(
        "--append",
        action="store_true",
        help="append one record to the copy after the first import, then import again",
    )
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    build_dir = HOURLY_ROOT / args.build_id
    if build_dir.exists():
        raise SystemExit(f"refusing to reuse an existing build directory: {build_dir}")
    build_dir.mkdir(parents=True)
    (build_dir / MARKER).write_text(args.build_id, encoding="utf-8")

    origin = (
        Path(args.origin).expanduser() if args.origin else Path.home() / ".codebuddy" / "projects"
    )
    receipt = {
        "build_id": args.build_id,
        "started_at": datetime.now(UTC).isoformat(),
        "data_dir": str(build_dir),
        "origin": str(origin),
        "source": args.source,
    }
    try:
        if not origin.is_dir():
            receipt["import"] = {"skipped": "origin not present"}
        else:
            root = build_dir / "sources"
            root.mkdir()
            sampled = _sample(origin, root, limit=args.limit, cap=8 * 1024 * 1024)
            before = _fingerprint(sampled)
            result = asyncio.run(run_import(build_dir, root, args.source))
            if args.append:
                result["append"] = asyncio.run(run_append(build_dir, root, args.source))
            receipt["import"] = result
            after = _fingerprint(sampled)
            changing = {key for key in before if before[key][0] != after[key][0]}
            for key in changing:
                del before[key], after[key]
            receipt["originals_unchanged"] = before == after
            receipt["sampled_files"] = len(sampled)
        receipt["finished_at"] = datetime.now(UTC).isoformat()
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    finally:
        if not args.keep:
            shutil.rmtree(build_dir, ignore_errors=True)
            print(f"cleaned {build_dir}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
