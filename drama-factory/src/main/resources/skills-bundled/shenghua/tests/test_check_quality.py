"""Unit tests for scripts/check_quality.py: score parsing, threshold, scaling decision.

Pure logic only — ffmpeg and ffprobe are never invoked.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_quality

SAMPLE_LOG = """[Parsed_libvmaf_4 @ 0x55f1a2b3] VMAF score: 96.444379
frame=  120 fps= 12 q=-0.0 Lsize=N/A time=00:00:04.00 bitrate=N/A speed=1.2x
"""

MULTI_PASS_LOG = """[Parsed_libvmaf_0 @ 0x1] VMAF score: 88.100000
[Parsed_libvmaf_0 @ 0x2] VMAF score: 91.250000
"""


def meta(width, height):
    return {"width": width, "height": height, "fps": 30.0, "duration": 10.0}


class ParseScoreTest(unittest.TestCase):
    def test_score_parsed_from_ffmpeg_stderr(self):
        self.assertAlmostEqual(check_quality.parse_vmaf_score(SAMPLE_LOG), 96.444379)

    def test_last_score_wins(self):
        self.assertAlmostEqual(check_quality.parse_vmaf_score(MULTI_PASS_LOG), 91.25)

    def test_integer_score(self):
        self.assertEqual(check_quality.parse_vmaf_score("VMAF score: 100"), 100.0)

    def test_no_score_returns_none(self):
        self.assertIsNone(check_quality.parse_vmaf_score("frame= 10 fps= 5"))
        self.assertIsNone(check_quality.parse_vmaf_score(""))


class ThresholdTest(unittest.TestCase):
    def test_score_at_the_minimum_passes(self):
        self.assertTrue(check_quality.passes(95.0, 95))

    def test_score_below_the_minimum_fails(self):
        self.assertFalse(check_quality.passes(94.9, 95))

    def test_score_above_the_minimum_passes(self):
        self.assertTrue(check_quality.passes(99.9, 95))


class ScalingTest(unittest.TestCase):
    def test_same_resolution_needs_no_scaling(self):
        self.assertFalse(check_quality.needs_scaling(meta(1920, 1080), meta(1920, 1080)))

    def test_larger_reference_is_scaled_down(self):
        self.assertTrue(check_quality.needs_scaling(meta(3840, 2160), meta(1080, 1920)))

    def test_same_area_different_shape_still_scales(self):
        self.assertTrue(check_quality.needs_scaling(meta(1920, 1080), meta(1080, 1920)))

    def test_filter_scales_reference_to_output_size(self):
        graph = check_quality.build_filter(meta(3840, 2160), meta(1080, 1920), 10)
        self.assertIn("scale=1080:1920", graph)
        self.assertIn("select=not(mod(n\\,10))", graph)
        self.assertTrue(graph.endswith("[dist][ref]libvmaf"))

    def test_filter_without_mismatch_has_no_scale(self):
        graph = check_quality.build_filter(meta(1080, 1920), meta(1080, 1920), 10)
        self.assertNotIn("scale=", graph)

    def test_sample_every_one_drops_the_select(self):
        graph = check_quality.build_filter(meta(1080, 1920), meta(1080, 1920), 1)
        self.assertNotIn("select=", graph)


class DescribeTest(unittest.TestCase):
    def test_integer_fps_prints_without_decimals(self):
        self.assertEqual(check_quality.describe(meta(1080, 1920)), "1080x1920@30")

    def test_fractional_fps_keeps_decimals(self):
        m = meta(1080, 1920)
        m["fps"] = 29.97
        self.assertEqual(check_quality.describe(m), "1080x1920@29.97")


if __name__ == "__main__":
    unittest.main()
