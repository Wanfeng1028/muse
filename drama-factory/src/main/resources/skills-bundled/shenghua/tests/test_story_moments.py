"""Unit tests for the music moments in scripts/synth_audio.py: tape stop, muffle and stutter."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import synth_audio

SR = synth_audio.SR


def tone(seconds=4.0, frequency=3000.0):
    t = np.arange(int(SR * seconds)) / SR
    return np.sin(2 * np.pi * frequency * t) * 0.5


def rms(signal):
    return float(np.sqrt(np.mean(signal ** 2)))


class TapeStopTest(unittest.TestCase):
    def test_should_be_silent_after_the_wind_down(self):
        music = synth_audio.tape_stop(tone(), 1.0, 3.0)
        self.assertEqual(np.max(np.abs(music[int(1.7 * SR):int(3.0 * SR)])), 0)

    def test_should_resume_at_the_end_of_the_range(self):
        music = synth_audio.tape_stop(tone(), 1.0, 3.0)
        self.assertGreater(rms(music[int(3.1 * SR):int(3.5 * SR)]), 0.3)


class MuffleTest(unittest.TestCase):
    def test_should_cut_high_frequencies_inside_the_range(self):
        music = synth_audio.muffle(tone(), 1.0, 3.0)
        self.assertLess(rms(music[int(1.5 * SR):int(2.5 * SR)]), 0.05)

    def test_should_leave_the_music_after_the_range_untouched(self):
        original = tone()
        music = synth_audio.muffle(original.copy(), 1.0, 3.0)
        np.testing.assert_array_equal(music[int(3 * SR):], original[int(3 * SR):])


class StutterTest(unittest.TestCase):
    def test_should_repeat_one_beat_through_the_range(self):
        ramp = np.linspace(-1, 1, SR * 4)
        music = synth_audio.stutter(ramp.copy(), 1.0, 3.0, 0.5)
        beat = int(0.5 * SR)
        first, later = music[SR:SR + beat], music[SR + 2 * beat:SR + 3 * beat]
        np.testing.assert_allclose(first, later)

    def test_should_continue_the_music_from_the_end_of_the_range(self):
        ramp = np.linspace(-1, 1, SR * 4)
        music = synth_audio.stutter(ramp.copy(), 1.0, 3.0, 0.5)
        np.testing.assert_array_equal(music[3 * SR:], ramp[3 * SR:])


class ParseRangeTest(unittest.TestCase):
    def test_should_parse_a_range(self):
        self.assertEqual(synth_audio.parse_range("--stop", "1.5:2"), (1.5, 2.0))

    def test_should_reject_a_backwards_range(self):
        self.assertIsNone(synth_audio.parse_range("--stop", "3:2"))

    def test_should_reject_text(self):
        self.assertIsNone(synth_audio.parse_range("--muffle", "a:b"))


if __name__ == "__main__":
    unittest.main()
