#!/usr/bin/env python3
"""Validate a story-video-director delivery package."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


MODEL_LIMITS = {
    "seedance-2.0": {"images": 9, "videos": 3, "audios": 3, "total": 12},
    # Public/product entry points may expose different 2.5 video, audio, and
    # combined-file ceilings. Only enforce the commonly stated image ceiling
    # unless the project manifest records provider-confirmed overrides.
    "seedance-2.5": {"images": 30, "videos": None, "audios": None, "total": None},
    "minimax-h3": {"images": 9, "videos": 0, "audios": 0, "total": 9},
    "metaso-minimax-h3": {"images": 9, "videos": 0, "audios": 0, "total": 9},
}


def read_json(path: Path, errors: list[str]) -> dict:
    if not path.is_file():
        errors.append(f"missing JSON file: {path.name}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON in {path.name}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.name} must contain a JSON object")
        return {}
    return value


def fenced_blocks(text: str) -> list[str]:
    return re.findall(r"```(?:text)?\s*\n(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)


def chinese_char_count(text: str) -> int:
    return len(re.findall(r"[\u3400-\u9fff]", text))


def normalize_dialogue(text: str) -> str:
    return re.sub(r"\s+", "", text).strip()


def validate_project(root: Path) -> tuple[list[str], list[str], dict]:
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict = {"project": str(root), "clips": 0, "duration": 0}

    if not root.is_dir():
        return [f"project directory does not exist: {root}"], warnings, summary

    manifest = read_json(root / "project-manifest.json", errors)
    jobs_doc = read_json(root / "api-jobs.json", errors)
    clips = manifest.get("clips", [])
    if not isinstance(clips, list) or not clips:
        errors.append("project-manifest.json must contain a non-empty clips array")
        clips = []

    recurring = manifest.get("recurring_identities", [])
    if recurring:
        if not isinstance(recurring, list):
            errors.append("recurring_identities must be an array")
            recurring = []
        for index, identity in enumerate(recurring, start=1):
            label = f"recurring identity #{index}"
            if not isinstance(identity, dict):
                errors.append(f"{label} must be an object")
                continue
            identity_id = str(identity.get("id", "")).strip()
            anchor = identity.get("identity_anchor")
            consumers = identity.get("clips", [])
            if not identity_id:
                errors.append(f"{label} is missing id")
            if not isinstance(anchor, str) or not anchor:
                errors.append(f"{label}: missing identity_anchor")
            elif not (root / anchor).is_file():
                errors.append(f"{label}: identity anchor does not exist: {anchor}")
            elif "/characters/" not in f"/{anchor}":
                warnings.append(f"{label}: identity anchor should normally live under assets/characters/")
            if not isinstance(consumers, list) or len(consumers) < 2:
                errors.append(f"{label}: clips must contain at least two consuming clip ids")

    target_model = str(manifest.get("target_model", "seedance-2.0")).lower()
    limits = MODEL_LIMITS.get(target_model)
    if limits is None:
        warnings.append(f"unknown target_model '{target_model}'; using Seedance 2.0 limits")
        limits = dict(MODEL_LIMITS["seedance-2.0"])
    else:
        limits = dict(limits)

    declared_limits = manifest.get("reference_limits", {})
    if declared_limits:
        if not isinstance(declared_limits, dict):
            errors.append("reference_limits must be an object when provided")
        else:
            for key in ("images", "videos", "audios", "total"):
                if key not in declared_limits:
                    continue
                value = declared_limits[key]
                if not isinstance(value, int) or value < 0:
                    errors.append(f"reference_limits.{key} must be a non-negative integer")
                else:
                    limits[key] = value

    max_clip = manifest.get("max_clip_seconds", 15)
    if max_clip != 15:
        warnings.append(f"max_clip_seconds is {max_clip}; this skill requires a 15-second ceiling")

    total = 0.0
    clip_ids: list[str] = []
    prompt_bodies: dict[str, str] = {}
    clip_durations: dict[str, float] = {}
    for index, clip in enumerate(clips, start=1):
        label = f"clip #{index}"
        if not isinstance(clip, dict):
            errors.append(f"{label} must be an object")
            continue

        clip_id = str(clip.get("id", "")).strip()
        if not clip_id:
            errors.append(f"{label} is missing id")
            clip_id = label
        elif clip_id in clip_ids:
            errors.append(f"duplicate clip id: {clip_id}")
        clip_ids.append(clip_id)
        label = clip_id

        duration = clip.get("duration_seconds")
        if not isinstance(duration, (int, float)) or duration <= 0:
            errors.append(f"{label}: duration_seconds must be positive")
            duration = 0
        elif duration > 15:
            errors.append(f"{label}: duration {duration}s exceeds 15s")
        total += float(duration)
        clip_durations[clip_id] = float(duration)

        prompt_rel = clip.get("prompt_file")
        if not isinstance(prompt_rel, str) or not prompt_rel:
            errors.append(f"{label}: missing prompt_file")
            prompt_path = None
            prompt_text = ""
            prompt_body = ""
        else:
            prompt_path = root / prompt_rel
            if not prompt_path.is_file():
                errors.append(f"{label}: prompt file does not exist: {prompt_rel}")
                prompt_text = ""
                prompt_body = ""
            else:
                prompt_text = prompt_path.read_text(encoding="utf-8")
                blocks = fenced_blocks(prompt_text)
                if len(blocks) != 1:
                    errors.append(f"{label}: prompt file must contain exactly one fenced prompt block")
                prompt_body = blocks[0].strip() if blocks else prompt_text.strip()
                prompt_bodies[clip_id] = prompt_body
                if len(prompt_body) > 5000:
                    warnings.append(f"{label}: prompt is {len(prompt_body)} characters; prefer <=5000")
                if not any(term in prompt_body for term in ("最终画面", "最后画面", "Last frame")):
                    errors.append(f"{label}: prompt lacks an explicit final frame")
                if not any(term in prompt_body for term in ("声音", "音效", "无声", "AUDIO")):
                    errors.append(f"{label}: prompt lacks an audio policy")
                if not any(term in prompt_body for term in ("负面提示词", "Negative Prompt")):
                    errors.append(f"{label}: prompt lacks a negative prompt")
                if any(term in prompt_body for term in ("打斗", "追逐", "舞蹈", "多镜头", "连续镜头", "重力", "撞击", "战斗")):
                    if not any(term in prompt_body for term in ("拍摄模式", "FORMAT MODE", "单一连续", "受控多镜头")):
                        warnings.append(f"{label}: complex motion may need an explicit format mode and cut policy")
                    if not any(term in prompt_body for term in ("物理", "PHYSICS", "惯性", "质量", "重力")):
                        warnings.append(f"{label}: complex motion may need explicit physics and material response")
                if "动态镜头" in prompt_body and not any(
                    term in prompt_body for term in ("机位", "路径", "推进", "跟拍", "环绕", "手持", "轨道", "摇臂")
                ):
                    warnings.append(f"{label}: '动态镜头' lacks an executable camera path or rig behavior")
                if not any(term in prompt_body for term in ("不要", "不得", "排除")):
                    warnings.append(f"{label}: no visible reference exclusion language found")
                if re.search(r"\b(?:fps|seed|resolution)\b|\d+\s*:\s*\d+", prompt_body, re.I):
                    warnings.append(f"{label}: generation parameters may be inside the model prompt")

                spoken = "".join(re.findall(r"\{([^{}]+)\}", prompt_body))
                spoken_chars = chinese_char_count(spoken)
                if duration and spoken_chars > float(duration) * 4.5:
                    warnings.append(
                        f"{label}: {spoken_chars} Chinese dialogue characters may exceed natural timing for {duration}s"
                    )
                dialogue_lines = [line.strip() for line in prompt_body.splitlines() if re.search(r"\{[^{}]+\}", line)]
                for dialogue_line in dialogue_lines:
                    canonical = re.search(
                        r"\[[A-Za-z0-9_-]+\].*说话人：[^；;，,]+[；;，,].*受话人：[^；;，,]+[；;，,].*\{[^{}]+\}",
                        dialogue_line,
                    )
                    if not canonical:
                        errors.append(f"{label}: non-canonical or unattributed dialogue line: {dialogue_line[:100]}")
                    elif not any(term in dialogue_line for term in ("嘴唇", "口型", "嘴部")):
                        errors.append(f"{label}: dialogue line lacks explicit speaker mouth/lip-sync state")
                    elif not any(term in dialogue_line for term in ("闭嘴", "不发声", "不说话", "离画", "画外无可见听者")):
                        errors.append(f"{label}: dialogue line lacks explicit listener silence/off-screen state")

        ref_groups = {
            "images": clip.get("image_refs", []),
            "videos": clip.get("video_refs", []),
            "audios": clip.get("audio_refs", []),
        }
        total_refs = 0
        for kind, refs in ref_groups.items():
            if not isinstance(refs, list):
                errors.append(f"{label}: {kind[:-1]}_refs must be an array")
                refs = []
            total_refs += len(refs)
            kind_limit = limits[kind]
            if kind_limit is not None and len(refs) > kind_limit:
                errors.append(f"{label}: {len(refs)} {kind} exceeds {target_model} limit {kind_limit}")
            elif kind_limit is None and len(refs) > 3:
                warnings.append(
                    f"{label}: {len(refs)} {kind}; confirm the current {target_model} provider ceiling"
                )
            for rel in refs:
                if not isinstance(rel, str) or not rel:
                    errors.append(f"{label}: invalid reference path in {kind[:-1]}_refs")
                    continue
                ref_path = root / rel
                if not ref_path.is_file():
                    errors.append(f"{label}: referenced file does not exist: {rel}")
                if prompt_text and f"@{Path(rel).name}" not in prompt_body:
                    errors.append(f"{label}: prompt does not contain inline reference @{Path(rel).name}")
        total_limit = limits["total"]
        if total_limit is not None and total_refs > total_limit:
            errors.append(f"{label}: {total_refs} total references exceeds {target_model} conservative limit {total_limit}")

    has_spoken_dialogue = any(re.search(r"\{[^{}]+\}", body) for body in prompt_bodies.values())
    ledger_path = root / "dialogue-ledger.json"
    ledger = read_json(ledger_path, errors) if ledger_path.is_file() else {}
    if has_spoken_dialogue and not ledger_path.is_file():
        errors.append("dialogue-led clips require dialogue-ledger.json")
    if has_spoken_dialogue and not (root / "00-screenplay.md").is_file():
        errors.append("dialogue-led clips require 00-screenplay.md")

    if ledger:
        ledger_characters = ledger.get("characters", [])
        if not isinstance(ledger_characters, list) or not ledger_characters:
            errors.append("dialogue-ledger.json must contain a non-empty characters array")
            ledger_characters = []
        character_ids: set[str] = set()
        character_names: dict[str, str] = {}
        for index, character in enumerate(ledger_characters, start=1):
            label = f"dialogue character #{index}"
            if not isinstance(character, dict):
                errors.append(f"{label} must be an object")
                continue
            character_id = str(character.get("id", "")).strip()
            character_name = str(character.get("name", "")).strip()
            if not character_id or not character_name:
                errors.append(f"{label} requires id and name")
                continue
            if character_id in character_ids:
                errors.append(f"duplicate dialogue character id: {character_id}")
            character_ids.add(character_id)
            character_names[character_id] = character_name

        ledger_clips = ledger.get("clips", [])
        if not isinstance(ledger_clips, list):
            errors.append("dialogue-ledger.json clips must be an array")
            ledger_clips = []
        ledger_clip_ids: set[str] = set()
        utterance_ids: set[str] = set()
        for index, ledger_clip in enumerate(ledger_clips, start=1):
            if not isinstance(ledger_clip, dict):
                errors.append(f"dialogue ledger clip #{index} must be an object")
                continue
            clip_id = str(ledger_clip.get("id", "")).strip()
            if clip_id not in clip_ids:
                errors.append(f"dialogue ledger references unknown clip: {clip_id or index}")
                continue
            if clip_id in ledger_clip_ids:
                errors.append(f"duplicate dialogue ledger clip: {clip_id}")
            ledger_clip_ids.add(clip_id)
            utterances = ledger_clip.get("utterances", [])
            if not isinstance(utterances, list):
                errors.append(f"{clip_id}: utterances must be an array")
                continue
            prompt_body = prompt_bodies.get(clip_id, "")
            prompt_lines = prompt_body.splitlines()
            ranges: list[tuple[float, float, str]] = []
            expected_texts: list[str] = []
            for utterance_index, utterance in enumerate(utterances, start=1):
                label = f"{clip_id} utterance #{utterance_index}"
                if not isinstance(utterance, dict):
                    errors.append(f"{label} must be an object")
                    continue
                utterance_id = str(utterance.get("id", "")).strip()
                speaker_id = str(utterance.get("speaker_id", "")).strip()
                speaker_name = str(utterance.get("speaker_name", "")).strip()
                addressee = str(utterance.get("addressee", "")).strip()
                utterance_text = str(utterance.get("text", "")).strip()
                start = utterance.get("start_seconds")
                end = utterance.get("end_seconds")
                if not utterance_id:
                    errors.append(f"{label}: missing id")
                elif utterance_id in utterance_ids:
                    errors.append(f"duplicate utterance id: {utterance_id}")
                utterance_ids.add(utterance_id)
                if speaker_id not in character_ids:
                    errors.append(f"{label}: unknown speaker_id '{speaker_id}'")
                elif character_names.get(speaker_id) != speaker_name:
                    errors.append(f"{label}: speaker_name does not match character '{speaker_id}'")
                if not addressee:
                    errors.append(f"{label}: missing addressee")
                if not utterance_text or "{" in utterance_text or "}" in utterance_text:
                    errors.append(f"{label}: text must contain spoken words only, without braces")
                if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or start >= end:
                    errors.append(f"{label}: invalid start_seconds/end_seconds")
                elif end > clip_durations.get(clip_id, 0):
                    errors.append(f"{label}: utterance ends after clip duration")
                else:
                    ranges.append((float(start), float(end), utterance_id))
                if utterance_text:
                    expected_texts.append(normalize_dialogue(utterance_text))
                matching_lines = [
                    line for line in prompt_lines
                    if f"[{utterance_id}]" in line and f"说话人：{speaker_name}" in line
                ]
                if len(matching_lines) != 1:
                    errors.append(f"{label}: prompt must contain exactly one canonical speaker line")
                elif f"{{{utterance_text}}}" not in matching_lines[0]:
                    errors.append(f"{label}: prompt dialogue does not exactly match ledger text")
                elif "受话人：" not in matching_lines[0]:
                    errors.append(f"{label}: canonical prompt line lacks addressee")

            ranges.sort()
            for previous, current in zip(ranges, ranges[1:]):
                if current[0] < previous[1]:
                    errors.append(f"{clip_id}: utterances {previous[2]} and {current[2]} overlap")

            actual_texts = [normalize_dialogue(value) for value in re.findall(r"\{([^{}]+)\}", prompt_body)]
            if actual_texts != expected_texts:
                errors.append(f"{clip_id}: prompt brace dialogue must match ledger once and in order")
            final_match = re.search(
                r"(?:最终画面|最后画面|Last frame)(.*?)(?:\n\s*(?:正向锁定|负面提示词|Positive|Negative)|\Z)",
                prompt_body,
                flags=re.DOTALL | re.IGNORECASE,
            )
            if final_match and re.search(r"\{[^{}]+\}", final_match.group(1)):
                errors.append(f"{clip_id}: final-frame section must not repeat dialogue braces")

        for clip_id, body in prompt_bodies.items():
            if re.search(r"\{[^{}]+\}", body) and clip_id not in ledger_clip_ids:
                errors.append(f"{clip_id}: spoken dialogue is missing from dialogue-ledger.json")

    declared_total = manifest.get("total_duration_seconds")
    if isinstance(declared_total, (int, float)):
        if abs(float(declared_total) - total) > 0.001:
            errors.append(f"declared total duration {declared_total}s does not equal clip sum {total:g}s")
    else:
        errors.append("project-manifest.json is missing numeric total_duration_seconds")

    jobs = jobs_doc.get("jobs", []) if isinstance(jobs_doc, dict) else []
    if not isinstance(jobs, list):
        errors.append("api-jobs.json jobs must be an array")
        jobs = []
    job_ids = [str(job.get("id", "")) for job in jobs if isinstance(job, dict)]
    if clip_ids and job_ids != clip_ids:
        errors.append("api-jobs.json job order or ids do not match project-manifest clips")

    if target_model in {"minimax-h3", "metaso-minimax-h3"}:
        for index, job in enumerate(jobs, start=1):
            if not isinstance(job, dict):
                continue
            label = str(job.get("id") or f"job #{index}")
            refs = job.get("references", [])
            refs = refs if isinstance(refs, list) else []
            roles = [str(ref.get("role", "")) for ref in refs if isinstance(ref, dict)]
            frame_mode = any(role in {"first_frame", "last_frame"} for role in roles)
            reference_mode = any(role in {"reference_image", "reference_video", "reference_audio"} for role in roles)
            if not refs:
                errors.append(f"{label}: MiniMax-H3 job requires at least one media reference")
            if frame_mode and reference_mode:
                errors.append(f"{label}: frame roles and multimodal reference roles are mutually exclusive")
            if frame_mode:
                if roles.count("first_frame") > 1 or roles.count("last_frame") > 1:
                    errors.append(f"{label}: at most one first_frame and one last_frame are allowed")
                if any(role not in {"first_frame", "last_frame"} for role in roles):
                    errors.append(f"{label}: invalid role in image-to-video mode")
            if reference_mode:
                if roles.count("reference_image") > 9:
                    errors.append(f"{label}: reference_image count exceeds 9")
                if roles.count("reference_video") > 3 or roles.count("reference_audio") > 3:
                    errors.append(f"{label}: reference video/audio count exceeds 3")
                if any(role not in {"reference_image", "reference_video", "reference_audio"} for role in roles):
                    errors.append(f"{label}: invalid role in multimodal reference mode")
                if len(clips) > 1 and roles.count("reference_image") < 2:
                    warnings.append(f"{label}: narrative multimodal job uses fewer than two reference images")
            slots = [ref.get("slot") for ref in refs if isinstance(ref, dict)]
            if slots != list(range(1, len(refs) + 1)):
                errors.append(f"{label}: reference slots must be contiguous and ordered from 1")
            for ref in refs:
                if not isinstance(ref, dict) or not isinstance(ref.get("path"), str) or not (root / ref["path"]).is_file():
                    errors.append(f"{label}: reference path does not exist")
            duration = job.get("duration_seconds")
            if not isinstance(duration, int) or isinstance(duration, bool) or not 4 <= duration <= 15:
                errors.append(f"{label}: MiniMax-H3 duration_seconds must be an integer in [4, 15]")

    summary.update({"clips": len(clips), "duration": total, "model": target_model})
    return errors, warnings, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    errors, warnings, summary = validate_project(args.project_dir.resolve())
    if args.as_json:
        print(json.dumps({"ok": not errors, "summary": summary, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    else:
        print(f"Project: {summary['project']}")
        print(f"Clips: {summary.get('clips', 0)}  Duration: {summary.get('duration', 0):g}s  Model: {summary.get('model', 'unknown')}")
        for message in warnings:
            print(f"WARNING: {message}")
        for message in errors:
            print(f"ERROR: {message}")
        print("PASS" if not errors else "FAIL")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
