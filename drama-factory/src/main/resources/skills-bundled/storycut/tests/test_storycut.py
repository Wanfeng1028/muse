import json
import tempfile
import unittest
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location


ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("storycut_cli", ROOT / "scripts" / "storycut.py")
mod = module_from_spec(spec)
spec.loader.exec_module(mod)


class StoryCutTests(unittest.TestCase):
    def test_parse_srt_and_export(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            path = mod.prepare(ROOT / "tests/fixtures/interview.srt", out, "base", None)
            transcript = json.loads(path.read_text())
            self.assertEqual(len(transcript["segments"]), 7)
            self.assertEqual(transcript["segments"][0]["id"], "s0001")
            result, warnings = mod.validate(path, ROOT / "tests/fixtures/cutlist_draft.json")
            self.assertEqual(len(result["clips"]), 3)
            self.assertEqual(result["clips"][0]["start"], "00:00:00.000")
            self.assertEqual(result["clips"][-1]["end"], "00:01:01.000")
            self.assertEqual(result["total_seconds"], 61)
            self.assertEqual(warnings, [])
            mod.export(result, out)
            self.assertTrue((out / "cutlist.md").exists())
            self.assertTrue((out / "cutlist.csv").exists())
            self.assertTrue((out / "cutlist.json").exists())

    def test_reject_fake_quote(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            transcript = mod.prepare(ROOT / "tests/fixtures/interview.srt", out, "base", None)
            draft = json.loads((ROOT / "tests/fixtures/cutlist_draft.json").read_text())
            draft["clips"][0]["quote"] = "The company became a unicorn."
            other = out / "bad.json"
            other.write_text(json.dumps(draft))
            with self.assertRaisesRegex(mod.StoryCutError, "quote"):
                mod.validate(transcript, other)

    def test_reject_nonconsecutive_segments(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            transcript = mod.prepare(ROOT / "tests/fixtures/interview.srt", out, "base", None)
            draft = json.loads((ROOT / "tests/fixtures/cutlist_draft.json").read_text())
            draft["clips"][0]["segment_ids"] = ["s0001", "s0003"]
            other = out / "bad.json"
            other.write_text(json.dumps(draft))
            with self.assertRaisesRegex(mod.StoryCutError, "consecutive"):
                mod.validate(transcript, other)

    def test_vtt_and_timed_txt(self):
        vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.500\n<v Interviewee>Hello there.</v>\n"
        cues = mod.parse_subtitles(vtt)
        self.assertEqual(cues[0]["text"], "Hello there.")
        txt = mod.parse_timed_txt("[00:00:04 - 00:00:07] That is the result.")
        self.assertEqual(txt[0]["end"], 7.0)

    def test_plain_text_has_no_fabricated_times(self):
        with self.assertRaises(mod.StoryCutError):
            mod.parse_timed_txt("We built a company and it was hard.")


if __name__ == "__main__":
    unittest.main()
