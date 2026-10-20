"""Unit tests for scripts/build_captions.py: fixes.json matching and the captions.srt/vtt writers."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_captions as bc


def word(t, s, e):
    return {"t": t, "s": s, "e": e}


WORDS = [
    word("Hello", 0.0, 0.3),
    word("world,", 0.4, 0.7),
    word("San", 1.0, 1.3),
    word("that", 2.0, 2.2),
    word("drop", 3.0, 3.2),
    word("that", 5.0, 5.2),
    word("Java", 5.3, 5.6),
]


class ParseKeyTest(unittest.TestCase):
    def test_plain_token(self):
        self.assertEqual(bc.parse_key("San"), ("San", None))

    def test_timed_token(self):
        self.assertEqual(bc.parse_key("that@50.22"), ("that", 50.22))

    def test_non_numeric_time_is_a_plain_token(self):
        self.assertEqual(bc.parse_key("word@ noon"), ("word@ noon", None))

    def test_empty_token_is_not_a_timed_key(self):
        self.assertEqual(bc.parse_key("@12.0"), ("@12.0", None))

    def test_last_at_sign_wins(self):
        self.assertEqual(bc.parse_key("a@b@1.5"), ("a@b", 1.5))


class StartsAtTest(unittest.TestCase):
    def test_untimed_key_matches_everywhere(self):
        self.assertTrue(bc.starts_at(word("x", 99.0, 99.2), None))

    def test_within_the_tolerance(self):
        # transcript.txt prints two decimals, so a typed time can sit 5ms off
        self.assertTrue(bc.starts_at(word("x", 5.0, 5.2), 5.005))
        self.assertTrue(bc.starts_at(word("x", 5.0, 5.2), 4.996))

    def test_outside_the_tolerance(self):
        self.assertFalse(bc.starts_at(word("x", 5.0, 5.2), 5.01))


class BareTest(unittest.TestCase):
    def test_strips_punctuation_and_case(self):
        self.assertEqual(bc.bare('"Java",'), "java")


class SplitPhrasesTest(unittest.TestCase):
    def test_breaks_after_terminal_punctuation(self):
        phrases = bc.split_phrases([word("hi.", 0, 0.2), word("there", 0.3, 0.5)])
        self.assertEqual([[w["t"] for w in p] for p in phrases], [["hi."], ["there"]])

    def test_breaks_at_five_words(self):
        words = [word(f"w{i}", i * 0.5, i * 0.5 + 0.3) for i in range(7)]
        phrases = bc.split_phrases(words)
        self.assertEqual([len(p) for p in phrases], [5, 2])

    def test_empty_input(self):
        self.assertEqual(bc.split_phrases([]), [])


class ClockTest(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(bc.clock(0, ","), "00:00:00,000")

    def test_hours_minutes_millis(self):
        self.assertEqual(bc.clock(3661.5, "."), "01:01:01.500")

    def test_separator(self):
        self.assertIn(",", bc.clock(1.25, ","))
        self.assertIn(".", bc.clock(1.25, "."))


class CaptionCuesTest(unittest.TestCase):
    def test_cue_times_and_text_come_from_the_words(self):
        phrases = bc.split_phrases(WORDS[:2]) + bc.split_phrases(WORDS[2:])
        cues = bc.caption_cues(phrases)
        self.assertEqual(cues[0], (0.0, 1.0, "Hello world,"))  # capped at the next phrase's start
        self.assertEqual(cues[1][0], 1.0)
        self.assertAlmostEqual(cues[1][1], 5.6 + 0.6)
        self.assertEqual(cues[1][2], "San that drop that Java")

    def test_last_cue_stays_up_past_the_last_word(self):
        cues = bc.caption_cues([[word("only", 2.0, 2.4)]])
        self.assertEqual(cues, [(2.0, 3.0, "only")])

    def test_a_cue_lasts_at_least_a_tenth_of_a_second(self):
        phrases = [[word("a", 1.0, 1.02)], [word("b", 1.05, 1.2)]]
        cues = bc.caption_cues(phrases)
        self.assertAlmostEqual(cues[0][1], 1.1)


class WriteCaptionFilesTest(unittest.TestCase):
    def test_srt_and_vtt_match_the_phrases(self):
        tmp = tempfile.TemporaryDirectory()
        work = Path(tmp.name)
        phrases = bc.split_phrases(WORDS)
        count = bc.write_caption_files(work, phrases)
        self.assertEqual(count, 2)
        srt = (work / "captions.srt").read_text(encoding="utf-8")
        vtt = (work / "captions.vtt").read_text(encoding="utf-8")
        self.assertEqual(
            srt,
            "1\n00:00:00,000 --> 00:00:01,000\nHello world,\n\n"
            "2\n00:00:01,000 --> 00:00:06,200\nSan that drop that Java\n\n")
        self.assertEqual(
            vtt,
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\nHello world,\n\n"
            "00:00:01.000 --> 00:00:06.200\nSan that drop that Java\n\n")
        tmp.cleanup()


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, words=WORDS, fixes=None, keywords=None):
        (self.work / "words.json").write_text(json.dumps(words), encoding="utf-8")
        if fixes is not None:
            (self.work / "fixes.json").write_text(json.dumps(fixes), encoding="utf-8")
        if keywords is not None:
            (self.work / "keywords.json").write_text(json.dumps(keywords), encoding="utf-8")
        with mock.patch.object(sys, "argv", ["build_captions.py", str(self.work)]), \
             contextlib.redirect_stdout(self.stdout), \
             contextlib.redirect_stderr(self.stderr):
            return bc.main()

    def phrases(self):
        text = (self.work / "words.js").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("window.PHRASES="))
        return json.loads(text[len("window.PHRASES="):-1])

    def flat_words(self):
        return [w for phrase in self.phrases() for w in phrase]

    def test_plain_fixes_rename_and_drop_tokens(self):
        code = self.run_main(fixes={"San": "Sun", "drop": ""})
        self.assertEqual(code, 0, self.stderr.getvalue())
        tokens = [w["t"] for w in self.flat_words()]
        self.assertEqual(tokens, ["Hello", "world,", "Sun", "that", "that", "Java"])
        self.assertIn("2 fixes applied", self.stdout.getvalue())

    def test_timed_fix_hits_only_the_one_occurrence(self):
        code = self.run_main(fixes={"that@5.00": "data"})
        self.assertEqual(code, 0, self.stderr.getvalue())
        tokens = [w["t"] for w in self.flat_words()]
        self.assertEqual(tokens, ["Hello", "world,", "San", "that", "drop", "data", "Java"])

    def test_timed_key_wins_over_a_plain_key_for_the_same_token(self):
        code = self.run_main(fixes={"that": "this", "that@5.00": "data"})
        self.assertEqual(code, 0, self.stderr.getvalue())
        tokens = [w["t"] for w in self.flat_words()]
        self.assertEqual(tokens, ["Hello", "world,", "San", "this", "drop", "data", "Java"])

    def test_timestamps_are_never_touched(self):
        self.run_main(fixes={"San": "Sun"})
        for original, fixed in zip(WORDS, self.flat_words()):
            self.assertEqual((fixed["s"], fixed["e"]), (original["s"], original["e"]))

    def test_keywords_match_case_and_punctuation_blind(self):
        code = self.run_main(keywords=["java"])
        self.assertEqual(code, 0, self.stderr.getvalue())
        flagged = [w["t"] for w in self.flat_words() if w.get("k")]
        self.assertEqual(flagged, ["Java"])

    def test_timed_keyword_flags_only_the_one_occurrence(self):
        code = self.run_main(keywords=["that@2.00"])
        self.assertEqual(code, 0, self.stderr.getvalue())
        flagged = [(w["t"], w["s"]) for w in self.flat_words() if w.get("k")]
        self.assertEqual(flagged, [("that", 2.0)])

    def test_unused_fixes_and_keywords_are_reported(self):
        code = self.run_main(fixes={"Nope": "nada"}, keywords=["missing"])
        self.assertEqual(code, 0, self.stderr.getvalue())
        out = self.stdout.getvalue()
        self.assertIn("unmatched fixes: Nope", out)
        self.assertIn("unmatched keywords: missing", out)

    def test_caption_files_match_words_js(self):
        self.run_main(fixes={"San": "Sun", "drop": ""})
        phrases = self.phrases()
        cues = bc.caption_cues(phrases)
        srt = (self.work / "captions.srt").read_text(encoding="utf-8")
        vtt = (self.work / "captions.vtt").read_text(encoding="utf-8")
        for i, (start, end, text) in enumerate(cues, 1):
            self.assertIn(f"{bc.clock(start, ',')} --> {bc.clock(end, ',')}\n{text}", srt)
            self.assertIn(f"{bc.clock(start, '.')} --> {bc.clock(end, '.')}\n{text}", vtt)
        self.assertEqual(srt.count("-->"), len(cues))
        self.assertTrue(vtt.startswith("WEBVTT"))

    def test_missing_words_json_fails_loud(self):
        (self.work / "words.json").unlink(missing_ok=True)
        with mock.patch.object(sys, "argv", ["build_captions.py", str(self.work)]), \
             contextlib.redirect_stdout(self.stdout), \
             contextlib.redirect_stderr(self.stderr):
            code = bc.main()
        self.assertEqual(code, 1)
        self.assertIn("No words.json", self.stderr.getvalue())
        self.assertIn("Next:", self.stderr.getvalue())

    def test_wrong_shaped_fixes_json_fails_loud(self):
        (self.work / "words.json").write_text(json.dumps(WORDS), encoding="utf-8")
        (self.work / "fixes.json").write_text('["not", "a", "dict"]', encoding="utf-8")
        with mock.patch.object(sys, "argv", ["build_captions.py", str(self.work)]), \
             contextlib.redirect_stdout(self.stdout), \
             contextlib.redirect_stderr(self.stderr):
            code = bc.main()
        self.assertEqual(code, 1)
        self.assertIn("Next:", self.stderr.getvalue())

    def test_broken_fixes_json_fails_loud(self):
        (self.work / "words.json").write_text(json.dumps(WORDS), encoding="utf-8")
        (self.work / "fixes.json").write_text("{oops", encoding="utf-8")
        with mock.patch.object(sys, "argv", ["build_captions.py", str(self.work)]), \
             contextlib.redirect_stdout(self.stdout), \
             contextlib.redirect_stderr(self.stderr):
            code = bc.main()
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", self.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
