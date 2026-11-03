"""Validate a schema_version=1 music timeline (Python 3.10+, stdlib only)."""

import argparse
import json
import math
from pathlib import Path
import sys


def _require(condition, path, message):
    if not condition:
        raise ValueError(f"{path}: {message}")


def _number(value, path):
    _require(type(value) in (int, float), path, "expected a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    _require(finite, path, "expected a finite number")
    return value


def _list(value, path):
    _require(isinstance(value, list), path, "expected an array")
    return value


def _object(value, path):
    _require(isinstance(value, dict), path, "expected an object")
    return value


def validate_timeline(data):
    """Raise ValueError with a field location on invalid timeline data."""
    _object(data, "$")
    _require(type(data.get("schema_version")) is int and data["schema_version"] == 1,
             "schema_version", "expected integer 1")
    duration = _number(data.get("duration"), "duration")
    _require(duration > 0, "duration", "must be positive")
    _require(type(data.get("fps")) is int and data["fps"] > 0,
             "fps", "expected a positive integer")

    previous = -1
    for i, beat in enumerate(_list(data.get("beats"), "beats")):
        path = f"beats[{i}]"
        beat = _number(beat, path)
        _require(0 <= beat < duration, path, "must satisfy 0 <= t < duration")
        _require(beat > previous, path, "must be strictly increasing")
        previous = beat

    sections = _list(data.get("sections"), "sections")
    _require(bool(sections), "sections", "must cover [0, duration]")
    ids = set()
    previous_end = 0
    for i, section in enumerate(sections):
        path = f"sections[{i}]"
        _object(section, path)
        section_id = section.get("id")
        _require(isinstance(section_id, str) and bool(section_id), path + ".id",
                 "expected a nonempty string")
        _require(section_id not in ids, path + ".id", "duplicate section id")
        ids.add(section_id)
        start = _number(section.get("start"), path + ".start")
        end = _number(section.get("end"), path + ".end")
        _require(0 <= start < end <= duration, path, "must satisfy 0 <= start < end <= duration")
        _require(start == previous_end, path + ".start", "must equal the preceding end (first start is 0)")
        previous_end = end
    _require(previous_end == duration, "sections[-1].end", "must equal duration")

    if "lyrics" in data:
        previous_end = 0
        for i, lyric in enumerate(_list(data["lyrics"], "lyrics")):
            path = f"lyrics[{i}]"
            _object(lyric, path)
            _require(isinstance(lyric.get("text"), str), path + ".text", "expected a string")
            start = _number(lyric.get("start"), path + ".start")
            end = _number(lyric.get("end"), path + ".end")
            _require(0 <= start < end <= duration, path, "must satisfy 0 <= start < end <= duration")
            _require(start >= previous_end, path + ".start", "lyrics must be ordered and nonoverlapping")
            previous_end = end

    if "energy" in data:
        energy = _object(data["energy"], "energy")
        for band, points in energy.items():
            path = f"energy.{band}"
            _require(band in ("low", "mid", "high"), path, "expected low, mid, or high")
            previous = -1
            for i, point in enumerate(_list(points, path)):
                point_path = f"{path}[{i}]"
                _object(point, point_path)
                t = _number(point.get("t"), point_path + ".t")
                value = _number(point.get("value"), point_path + ".value")
                _require(0 <= t < duration, point_path + ".t", "must satisfy 0 <= t < duration")
                _require(t > previous, point_path + ".t", "must be strictly increasing")
                _require(0 <= value <= 1, point_path + ".value", "must be between 0 and 1")
                previous = t


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="timeline JSON file")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.path.read_text(encoding="utf-8"))
        validate_timeline(data)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"{args.path}: {exc}", file=sys.stderr)
        return 1
    print(f"{args.path}: valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
