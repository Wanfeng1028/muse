"""--screen-voices mode for voice_qa.py: fetch library candidates, record probes, rank voices by worst noise floor."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

import _voice_eleven as eleven
from _voice_qa_checks import TakeReport

LIBRARY_PAGE_SIZE = 100
HARD_MAX_IN_FLIGHT = 3


@dataclass
class Candidate:
    id: str
    name: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class ProbeJob:
    voice: Candidate
    probe: int
    text: str
    path: Path
    body: dict


def _candidate(entry: object) -> Candidate:
    if isinstance(entry, str):
        return Candidate(entry.strip())
    if isinstance(entry, dict) and (entry.get("voice_id") or entry.get("id")):
        voice_id = str(entry.get("voice_id") or entry.get("id"))
        keep = ("accent", "gender", "age", "description", "category", "cloned_by_count", "use_case", "language")
        return Candidate(voice_id, str(entry.get("name", "")), {key: entry[key] for key in keep if key in entry})
    raise SystemExit(f"error: cannot read a voice id from {entry!r}")


def parse_voice_input(value: str) -> list[Candidate]:
    path = Path(value)
    if not path.is_file():
        return [Candidate(part.strip()) for part in value.split(",") if part.strip()]
    raw = path.read_text().strip()
    if raw.startswith(("[", "{")):
        data = json.loads(raw)
        entries = data.get("voices", data) if isinstance(data, dict) else data
        return [_candidate(entry) for entry in entries]
    return [Candidate(line.split()[0]) for line in raw.splitlines() if line.strip() and not line.startswith("#")]


def library_url(query: str, page: int) -> str:
    params = dict(parse_qsl(query.lstrip("?")))
    params.setdefault("sort", "cloned_by_count")
    params.update(page_size=str(LIBRARY_PAGE_SIZE), page=str(page))
    return f"{eleven.API_ROOT}/shared-voices?{urlencode(params)}"


def fetch_library(key: str, query: str, max_voices: int) -> list[Candidate]:
    found: list[Candidate] = []
    page = 0
    while len(found) < max_voices:
        reply = eleven.send("GET", library_url(query, page), key)
        if not reply.ok:
            raise SystemExit(f"error: shared-voices HTTP {reply.status}: {reply.error}")
        body = reply.json()
        found += [_candidate(entry) for entry in body.get("voices", [])]
        if not body.get("has_more") or not body.get("voices"):
            break
        page += 1
    return found[:max_voices]


def probe_file(out: Path, voice_id: str, probe: int, take: int) -> Path:
    suffix = "" if take == 0 else f"-{take + 1}"
    return out / f"{re.sub(r'[^A-Za-z0-9_-]', '_', voice_id)}-{probe}{suffix}.mp3"


def plan_probes(candidates: list[Candidate], probes: list[str], takes: int, out: Path, base_body: dict) -> list[ProbeJob]:
    jobs = []
    for voice in candidates:
        for probe_index, text in enumerate(probes, start=1):
            for take in range(takes):
                body = {**base_body, "text": text}
                jobs.append(ProbeJob(voice, probe_index, text, probe_file(out, voice.id, probe_index, take), body))
    return jobs


def probe_url(voice_id: str, output_format: str) -> str:
    return f"{eleven.API_ROOT}/text-to-speech/{voice_id}?output_format={output_format}"


def record_probe(job: ProbeJob, key: str, output_format: str) -> tuple[str, float]:
    reply = eleven.send("POST", probe_url(job.voice.id, output_format), key, f"  {job.path.name}: ", json=job.body)
    if not reply.ok:
        return f"FAIL {job.path.name}: HTTP {reply.status} {reply.error}", 0.0
    job.path.write_bytes(reply.content)
    return f"ok   {job.path}", float(reply.usage()["character_cost"] or 0)


def record_all(jobs: list[ProbeJob], key: str, max_in_flight: int, output_format: str) -> tuple[int, float]:
    failures, cost = 0, 0.0
    with ThreadPoolExecutor(max_workers=max(1, min(HARD_MAX_IN_FLIGHT, max_in_flight))) as pool:
        for message, spent in pool.map(lambda job: record_probe(job, key, output_format), jobs):
            print(message, flush=True)
            failures += message.startswith("FAIL")
            cost += spent
    return failures, cost


def summarize(candidates: list[Candidate], reports: dict[str, list[TakeReport]], max_floor_db: float) -> list[dict]:
    rows = []
    for voice in candidates:
        takes = reports.get(voice.id, [])
        floors = [take.checks["noise_floor_db"]["value"] for take in takes]
        measurable = [floor for floor in floors if floor is not None]
        worst = max(measurable) if measurable else None
        loudness = [take.checks["lufs"]["value"] for take in takes if take.checks["lufs"]["value"] is not None]
        problems = sorted({reason for take in takes for reason in take.failures})
        static = worst is not None and worst > max_floor_db
        verdict = "missing" if not takes else "static" if static else "fail" if problems else "pass"
        rows.append({
            "voice_id": voice.id,
            "name": voice.name,
            "details": voice.details,
            "worst_floor_db": worst,
            "lufs": round(sum(loudness) / len(loudness), 1) if loudness else None,
            "seconds": [take.checks["seconds"]["value"] for take in takes],
            "verdict": verdict,
            "problems": problems,
            "takes": [take.as_dict() for take in takes],
        })
    rows.sort(key=lambda row: (row["verdict"] != "pass", row["worst_floor_db"] if row["worst_floor_db"] is not None else 0))
    return rows


def print_table(rows: list[dict]) -> None:
    print(f"\n{'voice':<24}{'name':<22}{'worst floor':>12}{'LUFS':>8}  {'seconds':<16}verdict")
    for row in rows:
        floor = f"{row['worst_floor_db']:.1f}" if row["worst_floor_db"] is not None else "n/a"
        lufs = f"{row['lufs']:.1f}" if row["lufs"] is not None else "-"
        seconds = " ".join(f"{value:.2f}" for value in row["seconds"])
        extra = f"  ({'; '.join(row['problems'])})" if row["problems"] and row["verdict"] != "pass" else ""
        print(f"{row['voice_id']:<24}{row['name'][:21]:<22}{floor:>12}{lufs:>8}  {seconds:<16}{row['verdict']}{extra}")
