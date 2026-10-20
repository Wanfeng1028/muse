#!/usr/bin/env python3
"""Verify all 132 upstream MP4s against the camera catalog; no model inference."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

from audit_storyboard_quality import ROOT, read_data, require


def verify(archive, output):
    archive, output = Path(archive), Path(output).resolve()
    require(archive.is_file(), "Upstream ZIP is missing")
    require(not output.exists(), "Extraction directory already exists; use a new revision")
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            resolved = (output / member.filename).resolve()
            require(resolved == output or output in resolved.parents, "Unsafe ZIP path")
            require(not ((member.external_attr >> 16) & 0o170000) == 0o120000, "ZIP symlinks are not accepted")
        bundle.extractall(output)
    catalog = read_data(ROOT / "data/camera-moves.json")
    media = list(output.rglob("*.mp4"))
    require(len(media) == 132, f"Expected 132 MP4s, found {len(media)}")
    by_name = {p.name: p for p in media}
    require(len(by_name) == 132, "Duplicate MP4 basename")
    def probe(record):
        path = by_name.get(record["source_file"])
        require(path is not None, f"Missing source MP4: {record['source_file']}")
        result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames:format=duration", "-of", "json", str(path)], capture_output=True, text=True, check=True, timeout=60)
        metadata = json.loads(result.stdout)
        stream = metadata["streams"][0]
        require(stream["width"] == 1920 and stream["height"] == 1080, f"{path.name}: resolution mismatch")
        require(stream["r_frame_rate"] == "24/1" and int(stream["nb_read_frames"]) == 96, f"{path.name}: frame contract mismatch")
        require(abs(float(metadata["format"]["duration"]) - 4.0) < 0.001, f"{path.name}: duration mismatch")
        return {"id": record["id"], "file": path.relative_to(output).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "width": 1920, "height": 1080, "fps": 24, "frames": 96, "duration": 4.0}
    with ThreadPoolExecutor(max_workers=4) as executor:
        checked = list(executor.map(probe, catalog))
    report = {"status": "PASS", "source": "https://github.com/q2522879285-source/camera-moves-whitebox/releases",
              "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "count": len(checked), "files": checked,
              "scope": "Decoded frame counts and technical metadata, not an aesthetic review of camera motion"}
    return report


def verify_directory(media_root):
    media_root = Path(media_root).resolve()
    require(media_root.is_dir(), "Media directory is missing")
    catalog = read_data(ROOT / "data/camera-moves.json")
    media = list(media_root.rglob("*.mp4"))
    require(len(media) == 132, f"Expected 132 MP4s, found {len(media)}")
    by_name = {p.name: p for p in media}
    require(len(by_name) == 132, "Duplicate MP4 basename")
    checked = []
    for record in catalog:
        path = by_name.get(record["source_file"])
        require(path is not None, f"Missing source MP4: {record['source_file']}")
        result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames:format=duration", "-of", "json", str(path)], capture_output=True, text=True, check=True, timeout=60)
        metadata = json.loads(result.stdout)
        stream = metadata["streams"][0]
        require(stream["width"] == 1920 and stream["height"] == 1080, f"{path.name}: resolution mismatch")
        require(stream["r_frame_rate"] == "24/1" and int(stream["nb_read_frames"]) == 96, f"{path.name}: frame contract mismatch")
        require(abs(float(metadata["format"]["duration"]) - 4.0) < 0.001, f"{path.name}: duration mismatch")
        checked.append({"id": record["id"], "file": path.relative_to(media_root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "width": 1920, "height": 1080, "fps": 24, "frames": 96, "duration": 4.0})
    return {"status": "PASS", "source": "camera-moves-whitebox-132", "count": len(checked), "files": checked, "scope": "Decoded frame counts and technical metadata, not an aesthetic review of camera motion"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path, nargs="?")
    parser.add_argument("--media-dir", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        require(bool(args.zip) ^ bool(args.media_dir), "Provide exactly one of ZIP path or --media-dir")
        report = verify(args.zip, args.out) if args.zip else verify_directory(args.media_dir)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"PASS: {report['count']} MP4s verified at 1920x1080, 24fps, 96 frames, 4.00s")
        return 0
    except (ValueError, OSError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
