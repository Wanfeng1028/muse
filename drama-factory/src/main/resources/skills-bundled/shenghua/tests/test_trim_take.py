"""Unit tests for scripts/trim_take.py: frame-snapped cut points and excerpt word filtering.

main() is driven with probe_duration and ffmpeg mocked out, so no media tools run.
"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import trim_take


def word(t, s, e):
    return {"t": t, "s": s, "e": e}


class EdgeTest(unittest.TestCase):
    def test_auto_returns_default(self):
        self.assertEqual(trim_take.edge("auto", 1.25), 1.25)

    def test_number_returns_float(self):
        self.assertEqual(trim_take.edge("2.5", 1.25), 2.5)


class TrimTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.source = root / "take.mp4"
        self.source.write_bytes(b"not really a video")
        self.work = root / "work"
        self.work.mkdir()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def tearDown(self):
        self.tmp.cleanup()

    def write_words(self, words):
        (self.work / "words.json").write_text(json.dumps(words), encoding="utf-8")
        (self.work / "transcript.txt").write_text("transcript\n", encoding="utf-8")

    def run_main(self, *extra, words=None, length=60.0):
        if words is not None:
            self.write_words(words)
        argv = ["trim_take.py", str(self.source), str(self.work), *extra]
        ffmpeg = mock.Mock(return_value=mock.Mock(returncode=0, stderr=""))
        with mock.patch.object(sys, "argv", argv), \
             mock.patch("trim_take.probe_duration", return_value=length), \
             mock.patch("trim_take.subprocess.run", ffmpeg), \
             contextlib.redirect_stdout(self.stdout), \
             contextlib.redirect_stderr(self.stderr):
            code = trim_take.main()
        return code, ffmpeg

    def take_json(self):
        return json.loads((self.work / "take.json").read_text(encoding="utf-8"))

    def out_words(self):
        return json.loads((self.work / "words.json").read_text(encoding="utf-8"))

    def test_auto_cut_points_snap_outward_to_frame_boundaries(self):
        words = [word("hello", 1.234, 1.5), word("world", 2.0, 2.678)]
        code, ffmpeg = self.run_main(words=words)
        self.assertEqual(code, 0, self.stderr.getvalue())
        # in: floor((1.234 - 0.5) * 30) = 22 → 22/30; out: ceil((2.678 + 2.5) * 30) = 156 → 156/30
        take = self.take_json()
        self.assertEqual(take["firstFrame"], 22)
        self.assertAlmostEqual(take["in"], 22 / 30, places=6)
        self.assertAlmostEqual(take["out"], 156 / 30, places=6)
        self.assertAlmostEqual(take["duration"], 156 / 30 - 22 / 30, places=6)
        self.assertEqual(take["fps"], 30)
        # ffmpeg is asked to cut exactly those seconds
        atrim = ffmpeg.call_args[0][0][ffmpeg.call_args[0][0].index("-af") + 1]
        self.assertIn(f"start={22 / 30:.6f}", atrim)
        self.assertIn(f"end={156 / 30:.6f}", atrim)

    def test_words_are_shifted_so_the_cut_start_is_zero(self):
        words = [word("hello", 1.234, 1.5), word("world", 2.0, 2.678)]
        self.run_main(words=words)
        shifted = self.out_words()
        self.assertAlmostEqual(shifted[0]["s"], round(1.234 - 22 / 30, 2), places=2)
        self.assertAlmostEqual(shifted[1]["e"], round(2.678 - 22 / 30, 2), places=2)

    def test_cut_inside_the_speech_drops_words_outside_it(self):
        words = [word("before", 1.0, 1.4), word("kept", 1.7, 2.0), word("after", 3.0, 3.5)]
        code, _ = self.run_main("--in", "1.5", "--out", "2.5", words=words)
        self.assertEqual(code, 0, self.stderr.getvalue())
        kept = self.out_words()
        self.assertEqual([w["t"] for w in kept], ["kept"])
        self.assertEqual(kept[0]["s"], 0.2)
        self.assertEqual(kept[0]["e"], 0.5)
        self.assertIn("2 words outside the cut dropped", self.stdout.getvalue())

    def test_word_straddling_a_cut_point_is_dropped(self):
        # starts before the cut-in / ends after the cut-out: only the fully inside word stays
        words = [word("halfin", 1.4, 1.8), word("inside", 1.9, 2.1), word("halfout", 2.2, 2.6)]
        code, _ = self.run_main("--in", "1.5", "--out", "2.5", words=words)
        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual([w["t"] for w in self.out_words()], ["inside"])

    def test_cut_with_no_words_fails_loud(self):
        words = [word("hello", 1.0, 1.4)]
        code, ffmpeg = self.run_main("--in", "5", "--out", "6", words=words)
        self.assertEqual(code, 1)
        self.assertIn("No words between", self.stderr.getvalue())
        self.assertIn("Next:", self.stderr.getvalue())
        ffmpeg.assert_not_called()

    def test_cut_out_is_capped_at_the_source_length(self):
        words = [word("hello", 1.0, 1.4), word("end", 8.9, 9.0)]
        code, _ = self.run_main(words=words, length=9.2)
        self.assertEqual(code, 0, self.stderr.getvalue())
        # 9.0 + 2.5 tail = 11.5 > 9.2 s of source: clamped, and re-snapped to a whole frame
        take = self.take_json()
        self.assertLessEqual(take["out"], 9.2)
        self.assertAlmostEqual(take["out"] * 30, round(take["out"] * 30), places=4)

    def test_rerun_trims_from_the_raw_transcript(self):
        words = [word("before", 1.0, 1.4), word("kept", 1.7, 2.0), word("after", 3.0, 3.5)]
        self.run_main("--in", "1.5", "--out", "2.5", words=words)
        self.assertEqual([w["t"] for w in self.out_words()], ["kept"])
        # A second run with no cut arguments starts from words.raw.json, not the excerpt
        code, _ = self.run_main()
        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual([w["t"] for w in self.out_words()], ["before", "kept", "after"])

    def test_missing_words_json_fails_loud(self):
        code, _ = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("No words.json", self.stderr.getvalue())
        self.assertIn("Next:", self.stderr.getvalue())

    def test_missing_source_fails_loud(self):
        self.source.unlink()
        code, _ = self.run_main(words=[word("a", 1.0, 1.2)])
        self.assertEqual(code, 1)
        self.assertIn("No such recording", self.stderr.getvalue())

    def test_ffmpeg_failure_fails_loud(self):
        argv = ["trim_take.py", str(self.source), str(self.work)]
        self.write_words([word("a", 1.0, 1.2)])
        with mock.patch.object(sys, "argv", argv), \
             mock.patch("trim_take.probe_duration", return_value=60.0), \
             mock.patch("trim_take.subprocess.run",
                        return_value=mock.Mock(returncode=1, stderr="boom")), \
             contextlib.redirect_stdout(self.stdout), \
             contextlib.redirect_stderr(self.stderr):
            code = trim_take.main()
        self.assertEqual(code, 1)
        self.assertIn("could not cut", self.stderr.getvalue())
        self.assertIn("Next:", self.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
