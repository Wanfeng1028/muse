#!/usr/bin/env python3
"""Build the machine camera index and hashes from bundled unchanged local sources."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    manifest = json.loads((ROOT / "references/sources/camera/manifest.json").read_text(encoding="utf-8-sig"))
    groups = [(8, "basic"), (20, "classic"), (36, "advanced_static_subject"), (48, "moving_subject"),
              (72, "film_grammar"), (84, "film_grammar_continued"), (100, "fast"), (132, "practical")]
    catalog = []
    for index, move in enumerate(manifest["moves"], 1):
        catalog.append({"id": f"{index:03d}", "key": move["key"], "name_zh": move["cn"], "name_en": move["en"],
                        "source_file": move["key"] + ".mp4", "category": next(name for end, name in groups if index <= end),
                        "source_fps": move["fps"], "source_frames": move["frames"], "source_duration": move["duration"],
                        "source_claim_not_local_media_verification": True})
    if len(catalog) != 132:
        raise ValueError("Expected exactly 132 source camera records")
    (ROOT / "data/camera-moves.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source_root = ROOT / "references/sources"
    sources = [{"file": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for path in sorted(source_root.rglob("*")) if path.is_file()]
    (ROOT / "data/source-hashes.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(catalog)} camera records and {len(sources)} source hashes")


if __name__ == "__main__":
    build()
