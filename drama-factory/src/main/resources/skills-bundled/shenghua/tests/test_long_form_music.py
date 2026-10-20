"""Unit tests for long-form music: chapter slices of one continuous bed, chapter offsets and stale-music checks."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import assemble
import fill_template
import synth_audio

SR = synth_audio.SR
PROFILE = next(t["music"] for t in json.loads(synth_audio.TEMPLATES_JSON.read_text())["templates"] if t["id"] == "kinetic")


def bed(duration, offset=0.0, fades=(True, True), drums_from=None):
    return synth_audio.build_music(duration, int(SR * duration), drums_from, None, [], PROFILE,
                                   np.random.default_rng(42), offset, fades)


class ContinuousBedTest(unittest.TestCase):
    def test_should_join_two_slices_into_the_whole_bed(self):
        whole = bed(11.0, fades=(True, False))
        joined = np.concatenate([bed(6.0, fades=(True, False)), bed(5.0, 6.0, (False, False))])
        self.assertTrue(np.allclose(joined, whole, atol=1e-9))

    def test_should_carry_the_drums_across_a_join(self):
        whole = bed(11.0, fades=(True, False), drums_from=0)
        joined = np.concatenate([bed(6.0, fades=(True, False), drums_from=0), bed(5.0, 6.0, (False, False), drums_from=0)])
        self.assertTrue(np.allclose(joined, whole, atol=1e-9))

    def test_should_not_fade_a_middle_chapter(self):
        middle = bed(5.0, 30.0, (False, False))
        self.assertGreater(np.max(np.abs(middle[: SR // 10])), 0.01)
        self.assertGreater(np.max(np.abs(middle[-SR // 10:])), 0.01)

    def test_should_join_kit_track_slices_into_one_loop(self):
        track = np.random.default_rng(3).standard_normal(SR * 2)
        play = lambda seconds, offset: synth_audio.track_music(track, seconds, int(SR * seconds), [], None, offset, (False, False))
        self.assertTrue(np.allclose(np.concatenate([play(2.0, 0.0), play(3.0, 2.0)]), play(5.0, 0.0)))

    def test_should_start_a_kit_track_clean(self):
        track = np.random.default_rng(3).standard_normal(SR * 2)
        music = synth_audio.track_music(track, 1.0, SR, [], None, 0.0, (False, False))
        self.assertTrue(np.array_equal(music, track[:SR]))


class ChapterPositionTest(unittest.TestCase):
    def setUp(self):
        self.project = Path(tempfile.mkdtemp())
        (self.project / "chapters.json").write_text(json.dumps({"chapters": [
            {"dir": "01-a", "title": "A"}, {"dir": "02-b", "title": "B"}, {"dir": "03-c", "title": "C"}]}))
        for name in ("01-a", "02-b", "03-c"):
            (self.project / name / "work").mkdir(parents=True)

    def duration(self, name, seconds):
        (self.project / name / "work" / "render.json").write_text(json.dumps({"duration": seconds}))

    def test_should_offset_by_the_earlier_chapters(self):
        self.duration("01-a", 60.5)
        self.duration("02-b", 30.0)
        chapter = synth_audio.chapter_position(self.project / "03-c" / "work")
        self.assertEqual((chapter["offset"], chapter["number"], chapter["of"]), (90.5, 3, 3))

    def test_should_refuse_when_an_earlier_chapter_has_no_duration(self):
        self.duration("01-a", 60.5)
        with self.assertRaises(SystemExit):
            synth_audio.chapter_position(self.project / "03-c" / "work")

    def test_should_ignore_a_work_dir_outside_any_project(self):
        self.assertIsNone(synth_audio.chapter_position(Path(tempfile.mkdtemp()) / "work"))


class StaleMusicTest(unittest.TestCase):
    def test_should_name_a_chapter_whose_music_was_made_for_another_start(self):
        work = Path(tempfile.mkdtemp())
        (work / "mix.json").write_text(json.dumps({"music_offset": 61.0}))
        stale = assemble.stale_music([{"title": "B", "work": work}], [62.5])
        self.assertEqual(len(stale), 1)
        self.assertIn('"B"', stale[0])

    def test_should_accept_music_within_rounding(self):
        work = Path(tempfile.mkdtemp())
        (work / "mix.json").write_text(json.dumps({"music_offset": 10.0333}))
        self.assertEqual(assemble.stale_music([{"title": "B", "work": work}], [301 / 30]), [])


class WholeFramesTest(unittest.TestCase):
    def test_should_round_up_to_the_next_frame(self):
        self.assertEqual(fill_template.whole_frames(10.02), 10.0333)

    def test_should_give_render_chunks_the_same_frame_count(self):
        import math
        for frames in range(1, 20000):
            seconds = fill_template.whole_frames(frames / 30)
            self.assertEqual(math.ceil(seconds * 30), frames)


if __name__ == "__main__":
    unittest.main()
