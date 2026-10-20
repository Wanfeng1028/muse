#!/usr/bin/env python3
"""Regression checks for dialogue ownership validation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from validate_project import validate_project


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def build_project(root: Path, prompt_line: str) -> None:
    (root / "prompts").mkdir(parents=True)
    (root / "assets" / "characters").mkdir(parents=True)
    (root / "assets" / "characters" / "guard.png").write_bytes(b"test")
    (root / "00-screenplay.md").write_text("# Test\n\n**何师傅**：卡过期了。\n", encoding="utf-8")
    (root / "prompts" / "clip-01.md").write_text(
        """时长：8秒

```text
写实对话测试。
本段引用素材：何师傅@guard.png。只提取人物身份；不要使用设定图背景。
对白与声源锁定：c01-u01只属于何师傅；陈默闭嘴。
"""
        + prompt_line
        + """
声音：普通话同期声，无旁白，无字幕。
最终画面：何师傅说完后嘴唇闭合，镜头静止。不得出现文字。
负面提示词：身份漂移、台词交换、字幕、水印。
```
""",
        encoding="utf-8",
    )
    write_json(
        root / "project-manifest.json",
        {
            "version": 1,
            "title": "Test",
            "target_model": "seedance-2.0",
            "total_duration_seconds": 8,
            "max_clip_seconds": 15,
            "clips": [
                {
                    "id": "clip-01",
                    "duration_seconds": 8,
                    "prompt_file": "prompts/clip-01.md",
                    "image_refs": ["assets/characters/guard.png"],
                    "video_refs": [],
                    "audio_refs": [],
                    "depends_on": [],
                }
            ],
        },
    )
    write_json(
        root / "api-jobs.json",
        {
            "jobs": [
                {
                    "id": "clip-01",
                    "model": "seedance-2.0",
                    "duration_seconds": 8,
                    "prompt_file": "prompts/clip-01.md",
                    "references": [],
                }
            ]
        },
    )
    write_json(
        root / "dialogue-ledger.json",
        {
            "version": 1,
            "language": "zh-CN",
            "characters": [
                {"id": "guard", "name": "何师傅", "voice": "57岁男声"},
                {"id": "chen", "name": "陈默", "voice": "31岁男声"},
            ],
            "clips": [
                {
                    "id": "clip-01",
                    "utterances": [
                        {
                            "id": "c01-u01",
                            "speaker_id": "guard",
                            "speaker_name": "何师傅",
                            "addressee": "陈默",
                            "text": "卡过期了。",
                            "start_seconds": 2.0,
                            "end_seconds": 3.2,
                            "delivery": "平静",
                            "visibility": "on_screen",
                        }
                    ],
                }
            ],
        },
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="story-video-dialogue-test-") as temp_dir:
        valid_root = Path(temp_dir) / "valid"
        valid_root.mkdir()
        build_project(
            valid_root,
            "2.0—3.2秒｜[c01-u01] 说话人：何师傅；受话人：陈默；何师傅单人近景，嘴唇同步说：{卡过期了。} 陈默离画、闭嘴。\n",
        )
        valid_errors, _, _ = validate_project(valid_root)
        assert not valid_errors, valid_errors

        invalid_root = Path(temp_dir) / "invalid"
        invalid_root.mkdir()
        build_project(
            invalid_root,
            "2.0—3.2秒：陈默回头说：{卡过期了。}\n",
        )
        invalid_errors, _, _ = validate_project(invalid_root)
        assert any("non-canonical" in error for error in invalid_errors), invalid_errors
        assert any("canonical speaker line" in error for error in invalid_errors), invalid_errors

    print("dialogue validation regression tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
