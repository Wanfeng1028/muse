import json
import runpy
from pathlib import Path

import pytest

from one_memory.imports.access import SourceAccessError

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/run_hy_matter_baseline.py"


def test_first_import_replay_copies_raw_prefix_without_selecting_message_ids(tmp_path):
    script = SCRIPT.with_name("run_matter_first_import.py")
    source = tmp_path / "rollout-synthetic.jsonl"
    events = [
        {
            "type": "response_item",
            "timestamp": f"2026-09-11T0{index}:00:00Z",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": f"A short requirement {index}"}],
            },
        }
        for index in range(4)
    ]
    raw = [json.dumps(event) + "\n" for event in events]
    source.write_text("".join(raw))
    home = tmp_path / "isolated-home"
    records = runpy.run_path(str(script))["replay_source"](source, "2026-09-11T03:00:00Z", home)
    assert len(records) == 3
    assert (home / ".codex/sessions" / source.name).read_text() == "".join(raw[:3])
    assert source.read_text() == "".join(raw)


def test_frozen_transcript_keeps_middle_user_message_and_excludes_later_records(
    tmp_path, monkeypatch
):
    home = tmp_path / "isolated-home"
    root = home / ".codex/sessions"
    root.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    path = root / "rollout-example.jsonl"
    messages = [
        {
            "type": "response_item",
            "timestamp": f"2026-09-11T0{index}:00:00Z",
            "payload": {
                "type": "message",
                "role": "user" if index == 2 else "assistant",
                "content": [{"type": "input_text" if index == 2 else "output_text", "text": text}],
            },
        }
        for index, text in enumerate(
            ["Opening", "Reply", "Important middle user requirement", "Later"]
        )
    ]
    path.write_text("\n".join(json.dumps(m) for m in messages) + "\n")
    functions = runpy.run_path(str(SCRIPT))
    records = functions["transcript_records"](
        {"root_path": str(root)}, path, "2026-09-11T03:00:00+00:00"
    )
    assert len(records) == 3
    assert records[2].verbatim == "Important middle user requirement"
    assert records[2].written_by == "person"
    assert all(record.source_id == "codex" for record in records)
    with pytest.raises(SourceAccessError):
        functions["transcript_records"](
            {"root_path": str(root / "absent")}, path, "2026-09-11T03:00:00+00:00"
        )
