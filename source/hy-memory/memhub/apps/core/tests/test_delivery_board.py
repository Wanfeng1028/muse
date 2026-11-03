import json
import runpy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "render_delivery_board.py"


def load_functions():
    return runpy.run_path(str(SCRIPT))


def board():
    return {
        "title": "Delivery",
        "updated_at": "2026-09-11T12:00:00+08:00",
        "target_at": "2026-09-11T17:30:00+08:00",
        "execution": "active",
        "summary": "A real trial",
        "boundary": "Not release validation",
        "branch": "feat/demo",
        "stages": [{"id": "S1", "name": "Trial", "status": "active"}],
        "tasks": [
            {
                "id": "D1",
                "title": "Trial",
                "stage": "S1",
                "status": "active",
                "owner": "Agent",
                "eta": "2026-09-11T14:00:00+08:00",
                "confidence": "medium",
                "done": "",
                "remaining": "Run tests",
                "acceptance": "Evidence exists",
                "evidence": [],
                "depends_on": [],
            }
        ],
        "risks": [],
        "scope": [],
    }


def test_parses_only_the_marked_structured_record():
    functions = load_functions()
    data = board()
    text = "Old status\n<!-- one-memory-delivery-board:start -->\n```json\n"
    text += json.dumps(data) + "\n```\n<!-- one-memory-delivery-board:end -->\nOther notes"
    assert functions["read_board"](text) == data


def test_verified_requires_evidence_with_a_positive_control():
    functions = load_functions()
    data = board()
    data["tasks"][0]["status"] = "verified"
    with pytest.raises(ValueError, match="evidence"):
        functions["validate_board"](data)
    data["tasks"][0]["evidence"] = ["test report"]
    functions["validate_board"](data)


def test_rejects_unknown_dependency():
    functions = load_functions()
    data = board()
    data["tasks"][0]["depends_on"] = ["does-not-exist"]
    with pytest.raises(ValueError, match="dependency"):
        functions["validate_board"](data)


def test_board_escapes_embedded_script_and_has_no_external_requests():
    data = board()
    data["title"] = "</script><script>alert(1)</script>"
    rendered = load_functions()["render_board"](data)
    assert data["title"] not in rendered
    assert "\\u003c/script>" in rendered
    assert "fetch(" not in rendered
    assert "https://" not in rendered
    assert 'id="board-data"' in rendered


def test_eta_requires_explicit_timezone():
    data = board()
    data["tasks"][0]["eta"] = "2026-09-11T14:00:00"
    with pytest.raises(ValueError, match="timezone"):
        load_functions()["validate_board"](data)
