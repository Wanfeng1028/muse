import json
import runpy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "render_matter_trial.py"


def test_rejects_a_result_without_readonly_boundary():
    render = runpy.run_path(str(SCRIPT))["render_trial"]
    with pytest.raises(ValueError, match="read-only"):
        render({"production_write": True})


def test_checks_group_members_and_escapes_script_endings():
    render = runpy.run_path(str(SCRIPT))["render_trial"]
    data = {
        "production_write": False,
        "proposals": [{"id": "p1"}],
        "groups": [
            {"title": "A", "proposal_ids": ["missing"]},
        ],
    }
    with pytest.raises(ValueError, match="unknown proposal"):
        render(data)
    data["groups"][0]["proposal_ids"] = ["p1"]
    data["payload"] = "</script><img src=x onerror=alert(1)>"
    page = render(data)
    assert data["payload"] not in page
    encoded = page.split('<script id="trial-data" type="application/json">', 1)[1].split(
        "</script>", 1
    )[0]
    assert json.loads(encoded) == data
