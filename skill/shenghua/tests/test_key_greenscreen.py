"""Unit tests for the pure helpers in scripts/key_greenscreen.py.

The matte is exercised on synthetic numpy frames (screen, skin, green logo, spill);
no ffmpeg, video file or worker process is involved.
"""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import key_greenscreen as kg

SCREEN = (0, 200, 40)
SKIN = (200, 150, 130)


def make_matte(**overrides):
    pixels = np.array([SCREEN], np.float32)
    r, g = kg.chromaticity(pixels)
    matte = {"screen": list(SCREEN), "low": 8, "high": 30,
             "centre": (float(r[0]), float(g[0])), "near": 0.05, "far": 0.10, "masks": []}
    matte.update(overrides)
    return matte


class FrameRateTest(unittest.TestCase):
    def test_fraction(self):
        self.assertAlmostEqual(kg.frame_rate("30000/1001"), 29.97, places=2)
        self.assertEqual(kg.frame_rate("30/1"), 30.0)

    def test_plain_number(self):
        self.assertEqual(kg.frame_rate("25"), 25.0)

    def test_garbage_and_zero_division_return_zero(self):
        self.assertEqual(kg.frame_rate("garbage"), 0.0)
        self.assertEqual(kg.frame_rate("0/0"), 0.0)
        self.assertEqual(kg.frame_rate(""), 0.0)


class ScaledSizeTest(unittest.TestCase):
    def test_small_source_is_untouched(self):
        self.assertEqual(kg.scaled_size(1920, 1080, 3840), (1920, 1080))

    def test_tall_source_is_downscaled_to_the_limit(self):
        self.assertEqual(kg.scaled_size(3840, 2160, 1080), (1920, 1080))

    def test_results_stay_even_for_420_chroma(self):
        width, height = kg.scaled_size(999, 2000, 1000)
        self.assertEqual((width % 2, height % 2), (0, 0))
        # an odd --max-height is rounded down to even, never exceeded
        width, height = kg.scaled_size(1000, 2000, 1001)
        self.assertEqual(height, 1000)
        self.assertEqual(width % 2, 0)

    def test_never_shrinks_below_two_pixels(self):
        width, height = kg.scaled_size(3, 10000, 4)
        self.assertGreaterEqual(min(width, height), 2)


class BoxMeanTest(unittest.TestCase):
    def test_constant_plane_is_unchanged(self):
        plane = np.full((9, 11), 3.5, np.float32)
        np.testing.assert_allclose(kg.box_mean(plane, 2), 3.5, atol=1e-5)

    def test_impulse_spreads_over_the_window(self):
        plane = np.zeros((7, 7), np.float32)
        plane[3, 3] = 9.0
        result = kg.box_mean(plane, 1)
        self.assertAlmostEqual(float(result[3, 3]), 1.0, places=5)
        self.assertAlmostEqual(float(result.sum()), 9.0, places=4)

    def test_matches_a_naive_window_mean(self):
        rng = np.random.default_rng(42)
        plane = rng.random((20, 30)).astype(np.float32)
        padded = np.pad(plane, 3, mode="edge")  # box_mean replicates the edge at the borders
        expected = np.array([[padded[y:y + 7, x:x + 7].mean()
                              for x in range(30)] for y in range(20)], np.float32)
        np.testing.assert_allclose(kg.box_mean(plane, 3), expected, atol=1e-4)


class ChromaticityTest(unittest.TestCase):
    def test_pure_green(self):
        r, g = kg.chromaticity(np.array([[[0, 255, 0]]], np.float32))
        self.assertAlmostEqual(float(r[0, 0]), 0.0, places=5)
        self.assertAlmostEqual(float(g[0, 0]), 1.0, places=5)

    def test_brightness_divides_out(self):
        dim, _ = kg.chromaticity(np.array([[[10, 20, 30]]], np.float32))
        bright, _ = kg.chromaticity(np.array([[[100, 200, 300]]], np.float32))
        self.assertAlmostEqual(float(dim[0, 0]), float(bright[0, 0]), places=5)


class CompleteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "f00000.webp"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, payload_size=20, declared=None):
        declared = payload_size + 4 if declared is None else declared
        self.path.write_bytes(b"RIFF" + declared.to_bytes(4, "little") + b"WEBP" + b"x" * payload_size)

    def test_whole_file_is_complete(self):
        self.write()
        self.assertTrue(kg.complete(self.path))

    def test_truncated_file_is_incomplete(self):
        self.write(declared=10_000)
        self.assertFalse(kg.complete(self.path))

    def test_short_header_is_incomplete(self):
        self.path.write_bytes(b"RIFF")
        self.assertFalse(kg.complete(self.path))

    def test_wrong_magic_is_incomplete(self):
        self.path.write_bytes(b"NOPE" + (24).to_bytes(4, "little") + b"WEBP" + b"x" * 20)
        self.assertFalse(kg.complete(self.path))
        self.path.write_bytes(b"RIFF" + (24).to_bytes(4, "little") + b"AVIF" + b"x" * 20)
        self.assertFalse(kg.complete(self.path))

    def test_missing_file_is_incomplete(self):
        self.assertFalse(kg.complete(self.path))


class RunsTest(unittest.TestCase):
    def flatten(self, jobs):
        return [n for start, count in jobs for n in range(start, start + count)]

    def test_empty_input(self):
        self.assertEqual(kg.runs([], 4), [])

    def test_contiguous_frames_make_one_job(self):
        self.assertEqual(kg.runs([0, 1, 2], 1), [(0, 3)])

    def test_a_gap_starts_a_new_job(self):
        self.assertEqual(kg.runs([0, 1, 2, 10, 11], 1), [(0, 3), (10, 2)])

    def test_long_runs_split_at_the_chunk_size(self):
        jobs = kg.runs(list(range(100)), 4)  # size = max(30, min(450, 25)) = 30
        self.assertEqual(jobs, [(0, 30), (30, 30), (60, 30), (90, 10)])

    def test_jobs_cover_exactly_the_missing_frames_in_order(self):
        missing = [1, 2, 3, 5, 6, 9, 40, 41, 42, 43]
        jobs = kg.runs(missing, 3)
        self.assertEqual(self.flatten(jobs), missing)
        for start, count in jobs:
            self.assertGreater(count, 0)
            self.assertEqual(missing.index(start + count - 1), missing.index(start) + count - 1)

    def test_every_worker_gets_a_share_of_a_short_take(self):
        jobs = kg.runs(list(range(8)), 4)  # ceil(8/4)=2 < 30 → size 30, still one run
        self.assertEqual(self.flatten(jobs), list(range(8)))

    def test_huge_take_splits_at_the_chunk_cap(self):
        jobs = kg.runs(list(range(2000)), 2)  # ceil(2000/2)=1000 > CHUNK → capped at 450
        self.assertTrue(all(count <= kg.CHUNK for _, count in jobs))
        self.assertEqual(self.flatten(jobs), list(range(2000)))


class ParseMaskTest(unittest.TestCase):
    def test_valid_mask(self):
        self.assertEqual(kg.parse_mask("10,20,300,200"), (10, 20, 300, 200))

    def test_invalid_mask_fails_loud(self):
        import argparse
        with self.assertRaises(argparse.ArgumentTypeError):
            kg.parse_mask("10,20,30")
        with self.assertRaises(argparse.ArgumentTypeError):
            kg.parse_mask("a,b,c,d")


class KeyTest(unittest.TestCase):
    def test_screen_keys_out_and_skin_stays(self):
        frame = np.zeros((80, 80, 3), np.uint8)
        frame[:, :40] = SCREEN
        frame[:, 40:] = SKIN
        out = kg.key(frame, make_matte())
        self.assertEqual(int(out[40, 10, 3]), 0)    # screen interior is transparent
        self.assertEqual(int(out[40, 70, 3]), 255)  # skin interior is opaque

    def test_green_logo_inside_the_subject_stays_opaque(self):
        # green but not the screen's green: the chromaticity rescue fills the hole
        frame = np.full((120, 120, 3), SKIN, np.uint8)
        frame[50:70, 50:70] = (30, 180, 60)
        out = kg.key(frame, make_matte())
        self.assertEqual(int(out[60, 60, 3]), 255)

    def test_screen_coloured_region_away_from_screen_keys_out(self):
        frame = np.full((60, 60, 3), SCREEN, np.uint8)
        out = kg.key(frame, make_matte())
        self.assertEqual(int(out[..., 3].max()), 0)

    def test_spill_is_clamped_near_the_screen_colour(self):
        frame = np.full((40, 40, 3), (30, 200, 35), np.uint8)
        matte = make_matte(far=0.3)  # the cast sits inside the spill radius
        out = kg.key(frame, matte)
        r, g, b = (int(out[20, 20, c]) for c in range(3))
        self.assertLessEqual(g, max(r, b) + 4)

    def test_unspilled_colours_keep_their_green(self):
        # the logo is green but far from the screen's chromaticity: no spill clamp may touch it
        frame = np.full((120, 120, 3), SKIN, np.uint8)
        frame[50:70, 50:70] = (30, 180, 60)
        out = kg.key(frame, make_matte())
        self.assertEqual(int(out[60, 60, 1]), 180)

    def test_mask_forces_transparency(self):
        frame = np.full((60, 60, 3), SKIN, np.uint8)
        matte = make_matte(masks=[(10, 10, 20, 20)])
        out = kg.key(frame, matte)
        self.assertEqual(int(out[20, 20, 3]), 0)
        self.assertEqual(int(out[55, 55, 3]), 255)

    def test_output_is_rgba_uint8_same_size(self):
        frame = np.full((24, 32, 3), SKIN, np.uint8)
        out = kg.key(frame, make_matte())
        self.assertEqual(out.shape, (24, 32, 4))
        self.assertEqual(out.dtype, np.uint8)


class NeighbourhoodTest(unittest.TestCase):
    def test_minimum_erodes(self):
        plane = np.ones((5, 5), np.float32)
        plane[2, 2] = 0.0
        result = kg.neighbourhood(plane, np.minimum)
        self.assertEqual(float(result[2, 1]), 0.0)
        self.assertEqual(float(result[0, 0]), 1.0)

    def test_edges_use_edge_padding(self):
        plane = np.ones((3, 3), np.float32)
        plane[0, 0] = 5.0
        result = kg.neighbourhood(plane, np.maximum)
        self.assertEqual(float(result[0, 0]), 5.0)
        self.assertEqual(float(result[1, 1]), 5.0)
        self.assertEqual(float(result[2, 2]), 1.0)


class AliveTest(unittest.TestCase):
    def test_current_process_is_alive(self):
        import os
        self.assertTrue(kg.alive(os.getpid()))

    def test_reaped_child_is_dead(self):
        import os
        import subprocess
        child = subprocess.Popen(["true"])
        child.wait()
        for _ in range(100):  # the pid may take a moment to disappear
            if not kg.alive(child.pid):
                return
        self.skipTest("pid still reports alive")


if __name__ == "__main__":
    unittest.main()
