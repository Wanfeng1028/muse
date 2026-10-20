"""Unit tests for scripts/assemble.py: caption shifting and the YouTube chapter list."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import assemble

SRT = "1\n00:00:00,500 --> 00:00:02,000\nfirst line\n\n2\n00:00:03,000 --> 00:00:04,250\nsecond\nwrapped\n"


class ShiftCuesTest(unittest.TestCase):
    def test_should_move_every_cue_by_the_chapter_start(self):
        cues = assemble.shift_cues(SRT, 60.0)
        self.assertEqual([(start, end) for start, end, _ in cues], [(60.5, 62.0), (63.0, 64.25)])

    def test_should_keep_multi_line_cue_text(self):
        self.assertEqual(assemble.shift_cues(SRT, 0)[1][2], "second\nwrapped")

    def test_should_ignore_blocks_without_a_timing_line(self):
        self.assertEqual(assemble.shift_cues("WEBVTT\n\nnote only\n", 0), [])


class ChapterListTest(unittest.TestCase):
    def test_should_start_at_zero_and_use_minutes_under_an_hour(self):
        text, _ = assemble.chapter_list(["A", "B", "C"], [0, 75.4, 600], 900)
        self.assertEqual(text, "0:00 A\n1:15 B\n10:00 C\n")

    def test_should_add_hours_past_an_hour(self):
        self.assertEqual(assemble.youtube_stamp(3725), "1:02:05")

    def test_should_flag_fewer_than_three_chapters(self):
        _, problems = assemble.chapter_list(["A", "B"], [0, 60], 120)
        self.assertTrue(any("at least 3" in p for p in problems))

    def test_should_flag_a_chapter_shorter_than_ten_seconds(self):
        _, problems = assemble.chapter_list(["A", "B", "C"], [0, 60, 65], 120)
        self.assertEqual(len(problems), 1)
        self.assertIn('"B"', problems[0])


class ClockTest(unittest.TestCase):
    def test_should_round_to_milliseconds(self):
        self.assertEqual(assemble.clock(3661.0004, ","), "01:01:01,000")


if __name__ == "__main__":
    unittest.main()
