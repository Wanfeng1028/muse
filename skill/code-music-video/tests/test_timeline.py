"""Run with: python -m unittest discover -s tests -v"""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_timeline import validate_timeline


class TimelineTest(unittest.TestCase):
    def setUp(self):
        self.timeline = json.loads((ROOT / "examples" / "timeline.json").read_text(encoding="utf-8"))

    def test_valid_and_optional_data(self):
        validate_timeline(self.timeline)
        del self.timeline["lyrics"]
        del self.timeline["energy"]
        validate_timeline(self.timeline)

    def test_invalid_fields(self):
        cases = [
            ("duration", float("nan")), ("duration", float("inf")),
            ("duration", True), ("duration", 0), ("fps", True), ("fps", 1.5),
            ("schema_version", True), ("sections", []),
            ("beats", [0, 6]), ("beats", [1, 0]), ("beats", [0, 0]),
            ("beats", [True]), ("beats", [float("nan")]),
            ("sections", [{"id": "a", "start": 0, "end": 2}, {"id": "b", "start": 3, "end": 6}]),
            ("sections", [{"id": "a", "start": 0, "end": 0}, {"id": "b", "start": 0, "end": 6}]),
            ("sections", [{"id": "a", "start": 0, "end": 3}, {"id": "a", "start": 3, "end": 6}]),
            ("lyrics", [{"text": "a", "start": 0, "end": 2}, {"text": "b", "start": 1, "end": 3}]),
            ("lyrics", [{"text": "a", "start": 3, "end": 4}, {"text": "b", "start": 0, "end": 1}]),
            ("lyrics", [{"text": "a", "start": 5, "end": 7}]),
            ("energy", {"low": [{"t": 0, "value": 1.1}]}),
            ("energy", {"mid": [{"t": 6, "value": 0.5}]}),
            ("energy", {"high": [{"t": 2, "value": 0.5}, {"t": 1, "value": 0.4}]}),
            ("energy", {"low": [{"t": 0, "value": True}]}),
            ("energy", {"mid": [{"t": float("nan"), "value": 0.5}]}),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                data = deepcopy(self.timeline)
                data[field] = value
                with self.assertRaisesRegex(ValueError, field):
                    validate_timeline(data)

    def test_cli(self):
        command = [sys.executable, str(ROOT / "scripts" / "validate_timeline.py")]
        result = subprocess.run(command + [str(ROOT / "examples" / "timeline.json")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            data = deepcopy(self.timeline)
            data["beats"] = [6]
            path.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run(command + [str(path)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("beats[0]", result.stderr)


if __name__ == "__main__":
    unittest.main()
