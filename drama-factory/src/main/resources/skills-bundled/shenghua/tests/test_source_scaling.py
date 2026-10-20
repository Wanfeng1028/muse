"""Unit tests for source-faithful scaling: the probe block, HDR detection, render scale for
--resolution source, and the bitrate cap that scales with the canvas.

Only the pure functions run — no ffprobe, no ffmpeg.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fill_template
import trim_take


def probe_json(streams, fmt=None):
    return {"streams": streams, "format": fmt or {}}


def video_stream(**overrides):
    stream = {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
              "avg_frame_rate": "30/1", "bit_rate": "8000000", "duration": "12.000000"}
    stream.update(overrides)
    return stream


class HdrFlagTest(unittest.TestCase):
    def test_pq_transfer_is_hdr(self):
        self.assertTrue(trim_take.is_hdr(video_stream(color_transfer="smpte2084")))

    def test_hlg_transfer_is_hdr(self):
        self.assertTrue(trim_take.is_hdr(video_stream(color_transfer="hlg")))

    def test_arib_transfer_is_hdr(self):
        self.assertTrue(trim_take.is_hdr(video_stream(color_transfer="arib-std-b67")))

    def test_bt2020_primaries_are_hdr(self):
        self.assertTrue(trim_take.is_hdr(video_stream(color_primaries="bt2020")))

    def test_bt2020_colour_space_is_hdr(self):
        self.assertTrue(trim_take.is_hdr(video_stream(color_space="bt2020nc")))

    def test_bt709_is_sdr(self):
        stream = video_stream(color_transfer="bt709", color_primaries="bt709", color_space="bt709")
        self.assertFalse(trim_take.is_hdr(stream))

    def test_untagged_is_sdr(self):
        self.assertFalse(trim_take.is_hdr(video_stream()))


class SourceFromProbeTest(unittest.TestCase):
    def test_video_fields(self):
        probe = trim_take.source_from_probe(probe_json([video_stream()]))
        self.assertEqual(probe["width"], 1920)
        self.assertEqual(probe["height"], 1080)
        self.assertEqual(probe["fps"], 30.0)
        self.assertEqual(probe["codec"], "h264")
        self.assertEqual(probe["bitrate_kbps"], 8000)
        self.assertFalse(probe["hdr"])
        self.assertEqual(probe["duration"], 12.0)

    def test_fractional_fps(self):
        probe = trim_take.source_from_probe(probe_json([video_stream(avg_frame_rate="30000/1001")]))
        self.assertAlmostEqual(probe["fps"], 29.97, places=2)

    def test_bitrate_falls_back_to_the_format(self):
        stream = video_stream()
        del stream["bit_rate"]
        probe = trim_take.source_from_probe(probe_json([stream], fmt={"bit_rate": "5200000"}))
        self.assertEqual(probe["bitrate_kbps"], 5200)

    def test_missing_bitrate_is_null(self):
        stream = video_stream()
        del stream["bit_rate"]
        probe = trim_take.source_from_probe(probe_json([stream]))
        self.assertIsNone(probe["bitrate_kbps"])

    def test_pure_audio_has_no_probe_block(self):
        audio = {"codec_type": "audio", "codec_name": "pcm_s16le"}
        self.assertIsNone(trim_take.source_from_probe(probe_json([audio])))


class SourceScaleTest(unittest.TestCase):
    def test_4k_vertical_source_scales_2x(self):
        self.assertEqual(fill_template.source_scale(2160, 3840, 1080, 1920), 2)

    def test_1080p_vertical_source_scales_1x(self):
        self.assertEqual(fill_template.source_scale(1080, 1920, 1080, 1920), 1)

    def test_small_source_scales_1x(self):
        self.assertEqual(fill_template.source_scale(640, 360, 1920, 1080), 1)

    def test_landscape_4k_source_scales_2x(self):
        self.assertEqual(fill_template.source_scale(3840, 2160, 1920, 1080), 2)

    def test_between_1x_and_2x_picks_the_nearer(self):
        # 1440x2560 is 1.78x the vertical canvas: nearer to 1x than to 4x the pixels
        self.assertEqual(fill_template.source_scale(1440, 2560, 1080, 1920), 1)


class MaxrateTest(unittest.TestCase):
    def test_1080x1920_at_1x_is_16m(self):
        self.assertEqual(fill_template.maxrate_kbps(1080, 1920, 1), 16000)

    def test_2160x3840_at_2x_is_64m(self):
        self.assertEqual(fill_template.maxrate_kbps(1080, 1920, 2), 64000)

    def test_landscape_4k_is_64m(self):
        self.assertEqual(fill_template.maxrate_kbps(1920, 1080, 2), 64000)

    def test_small_canvas_clamps_to_the_floor(self):
        self.assertEqual(fill_template.maxrate_kbps(1080, 1080, 1), 16000)

    def test_oversized_canvas_clamps_to_the_ceiling(self):
        self.assertEqual(fill_template.maxrate_kbps(1920, 1080, 3), 68000)


if __name__ == "__main__":
    unittest.main()
