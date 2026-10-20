"""Behavior checks using only temporary, self-generated media.

Run with: python3 -m unittest discover -s tests -v
Media checks skip when their existing local dependencies are unavailable.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
spec = importlib.util.spec_from_file_location("compile_cues", SCRIPTS / "compile_cues.py")
assert spec and spec.loader
compile_cues = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compile_cues)


def dependencies(*modules: str) -> list[str]:
    missing = [binary for binary in ("ffmpeg", "ffprobe") if not shutil.which(binary)]
    missing.extend(name for name in modules if importlib.util.find_spec(name) is None)
    return missing


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_cli(script: str, *args: object, env: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *(str(arg) for arg in args)],
        capture_output=True, encoding="utf-8", errors="replace", env=env, timeout=30,
    )


def make_media(path: Path, *args: str):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *args, str(path)],
        check=True, capture_output=True, timeout=30,
    )


class CueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cue-tests-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    @staticmethod
    def sheet(verification="designed"):
        return {
            "fps": 30, "duration_s": 4, "asset_status": "planned",
            "cues": [{
                "id": "landing", "asset": "audio/landing.wav",
                "verification": verification, "target_s": 2,
                "source_in_s": 0.4, "source_anchor_s": 0.9,
                "source_out_s": 1.6, "playback_rate": 2,
                "note": "自己设计的落定声，素材待提供",
            }],
        }

    def write_sheet(self, sheet):
        path = self.directory / "input.json"
        path.write_text(json.dumps(sheet, ensure_ascii=False), encoding="utf-8")
        return path

    def test_anchor_trim_and_rate_are_compiled_without_double_scaling(self):
        result = compile_cues.compile_sheet(self.sheet())
        cue = result["cues"][0]
        self.assertEqual(result["composition_duration_frames"], 120)
        self.assertEqual(cue["target_frame"], 60)
        self.assertEqual(cue["clip_start_frame"], 53)  # 52.5 rounds half up.
        self.assertEqual(cue["source_trim_before_frame"], 12)
        self.assertEqual(cue["source_duration_frames"], 36)
        self.assertEqual(cue["output_duration_frames"], 18)
        self.assertAlmostEqual(cue["continuous_clip_start_s"], 1.75)
        self.assertAlmostEqual(cue["continuous_clip_end_s"], 2.35)
        self.assertAlmostEqual(cue["quantized_anchor_time_s"], 53 / 30 + 0.5 / 2)
        self.assertAlmostEqual(cue["anchor_quantization_error_ms"], 1000 / 60)
        self.assertEqual(cue["asset_status"], "planned")
        self.assertFalse(result["asset_files_checked"])

    def test_candidate_requires_explicit_option_and_keeps_its_identity(self):
        source = self.write_sheet(self.sheet("measured_candidate"))
        output = self.directory / "compiled.json"
        refused = run_cli("compile_cues.py", "--input", source, "--out", output)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("measured_candidate remains unverified", refused.stderr)
        self.assertFalse(output.exists())
        accepted = run_cli(
            "compile_cues.py", "--input", source, "--out", output, "--include-candidates",
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "candidate_draft")
        self.assertEqual(result["cues"][0]["verification"], "measured_candidate")
        self.assertEqual(result["cues"][0]["id"], "landing")

    def test_input_and_existing_output_are_preserved(self):
        source = self.write_sheet(self.sheet())
        original = source.read_bytes()
        refused = run_cli(
            "compile_cues.py", "--input", source, "--out", source, "--overwrite",
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("cannot replace the input", refused.stderr)
        self.assertEqual(source.read_bytes(), original)
        output = self.directory / "existing.json"
        output.write_bytes(b"existing derived output")
        refused = run_cli("compile_cues.py", "--input", source, "--out", output)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("already exists", refused.stderr)
        self.assertEqual(output.read_bytes(), b"existing derived output")
        self.assertEqual(source.read_bytes(), original)

    def test_chinese_cue_is_utf8_even_with_ascii_locale(self):
        sheet = self.sheet()
        source = self.write_sheet(sheet)
        output = self.directory / "compiled.json"
        env = os.environ.copy()
        env.update(LC_ALL="C", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0")
        result = run_cli("compile_cues.py", "--input", source, "--out", output, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = output.read_text(encoding="utf-8")
        self.assertIn(sheet["cues"][0]["note"], text)
        self.assertEqual(json.loads(text)["cues"][0]["note"], sheet["cues"][0]["note"])


class FrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = dependencies("PIL")
        if missing:
            raise unittest.SkipTest("Frame media checks need existing dependencies: " + ", ".join(missing))
        cls.temp = tempfile.TemporaryDirectory(prefix="frame-tests-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.source = cls.directory / "irregular-pts.mkv"
        # Self-generated VFR frames at source PTS 2.0, 2.1, 2.4, 2.8 seconds.
        make_media(
            cls.source, "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=10:duration=1",
            "-vf", "select=eq(n\\,0)+eq(n\\,1)+eq(n\\,4)+eq(n\\,8),setpts=PTS+2/TB",
            "-fps_mode", "vfr", "-an", "-c:v", "ffv1",
        )
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames", "-show_format",
             "-show_entries", "frame=best_effort_timestamp_time:format=start_time,duration",
             "-of", "json", str(cls.source)],
            check=True, capture_output=True, encoding="utf-8", timeout=30,
        )
        data = json.loads(probe.stdout)
        cls.pts = [float(frame["best_effort_timestamp_time"]) for frame in data["frames"]]
        cls.origin = float(data["format"]["start_time"])
        cls.source_digest = sha256(cls.source)

    def sample(self, output, times):
        return run_cli(
            "sample_frames.py", "--input", self.source, "--out", output,
            "--times", times, "--frame-width", 96, "--thumb-width", 120, "--thumb-height", 80,
        )

    def test_actual_pts_and_reused_frame_keep_source_unchanged(self):
        self.assertEqual(len(self.pts), 4)
        self.assertGreater(self.origin, 0)
        self.assertNotAlmostEqual(self.pts[1] - self.pts[0], self.pts[2] - self.pts[1])
        targets = [0, 0.04, 0.31, 0.79]
        output = self.directory / "sampled"
        result = self.sample(output, ",".join(map(str, targets)))
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["timeline_origin_pts_s"], self.origin)
        self.assertEqual(manifest["sample_count"], 4)
        self.assertEqual(manifest["unique_frame_count"], 3)
        self.assertEqual(manifest["samples"][0]["image"], manifest["samples"][1]["image"])
        for target, sample in zip(targets, manifest["samples"]):
            expected_index = min(range(len(self.pts)), key=lambda i: (abs(self.pts[i] - self.origin - target), i))
            self.assertEqual(sample["frame_index_0"], expected_index)
            self.assertAlmostEqual(sample["actual_pts_s"], self.pts[expected_index])
            self.assertAlmostEqual(sample["actual_time_s"], self.pts[expected_index] - self.origin)
            self.assertAlmostEqual(sample["error_s"], self.pts[expected_index] - self.origin - target)
            self.assertTrue((output / sample["image"]).is_file())
        self.assertEqual(len(list((output / "frames").glob("*.jpg"))), 3)
        self.assertTrue(all((output / path).is_file() for path in manifest["contact_sheets"]))
        self.assertEqual(sha256(self.source), self.source_digest)

    def test_request_after_final_decoded_frame_fails_without_output(self):
        output = self.directory / "past-end"
        result = self.sample(output, str(self.pts[-1] - self.origin + 0.02))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the decoded video frame span", result.stderr)
        self.assertFalse(output.exists())
        self.assertEqual(sha256(self.source), self.source_digest)

    def test_existing_output_is_preserved(self):
        output = self.directory / "existing-frames"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_bytes(b"existing frame evidence")
        result = self.sample(output, "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("output already exists", result.stderr.lower())
        self.assertEqual(marker.read_bytes(), b"existing frame evidence")
        self.assertEqual(list(output.iterdir()), [marker])
        self.assertEqual(sha256(self.source), self.source_digest)


class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = dependencies("numpy", "scipy")
        if missing:
            raise unittest.SkipTest("Audio media checks need existing dependencies: " + ", ".join(missing))
        cls.temp = tempfile.TemporaryDirectory(prefix="audio-tests-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.sources = {}
        for name, lavfi, codec in (
            ("silence", "anullsrc=r=22050:cl=mono", "pcm_s16le"),
            ("tone", "sine=frequency=440:sample_rate=22050", "pcm_s16le"),
            ("opposites", "aevalsrc=0.2*sin(2*PI*440*t)|-0.2*sin(2*PI*440*t):s=22050", "pcm_f32le"),
        ):
            source = cls.directory / f"{name}.wav"
            make_media(source, "-f", "lavfi", "-i", lavfi, "-t", "0.35", "-c:a", codec)
            cls.sources[name] = source
        cls.sources["no-audio"] = cls.directory / "no-audio.mkv"
        make_media(
            cls.sources["no-audio"], "-f", "lavfi", "-i", "color=size=64x64:rate=10:duration=0.3",
            "-an", "-c:v", "ffv1",
        )

    def analyze(self, name, output):
        return run_cli("analyze_audio.py", "--input", self.sources[name], "--out", output)

    def test_source_audio_states_are_distinct_and_source_hashes_stay_valid(self):
        for name, expected in (
            ("silence", "digital_silence"), ("tone", "measured"),
            ("no-audio", "no_audio_stream"), ("opposites", "mono_downmix_cancellation"),
        ):
            with self.subTest(source=name):
                source = self.sources[name]
                original = sha256(source)
                output = self.directory / f"analysis-{name}"
                result = self.analyze(name, output)
                self.assertEqual(result.returncode, 0, result.stderr)
                analysis = json.loads((output / "analysis.json").read_text(encoding="utf-8"))
                self.assertEqual(analysis["status"], expected)
                self.assertEqual(analysis["source"]["sha256"], original)
                self.assertEqual(sha256(source), original)
                if name == "no-audio":
                    self.assertEqual(analysis["audio_stream_count"], 0)
                    self.assertNotIn("original_channels", analysis)
                else:
                    self.assertEqual(analysis["audio_stream_count"], 1)
                    channels = analysis["original_channels"]
                    self.assertEqual(channels["all_channels_exactly_zero"], name == "silence")
                    if name == "silence":
                        self.assertIsNone(channels["channels"][0]["rms_dbfs"])
                        self.assertEqual(analysis["onset_candidates"], [])
                    else:
                        self.assertGreater(channels["channels"][0]["rms_linear"], 0)
                    if name == "opposites":
                        self.assertTrue(channels["stereo_channels_exact_opposites"])
                        self.assertIn("cancellation_note", analysis["analysis_levels"])
                        self.assertEqual(analysis["onset_candidates"], [])
                        self.assertEqual(analysis["global_repetition_candidates"], [])
                if name == "tone":
                    self.assertEqual(analysis["global_repetition_candidates"], [])  # < 5 seconds.
                    self.assertTrue(all(cue["review_status"] == "unreviewed" for cue in analysis["onset_candidates"]))

    def test_existing_output_is_preserved(self):
        output = self.directory / "existing-audio"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_bytes(b"existing audio evidence")
        original = sha256(self.sources["tone"])
        result = self.analyze("tone", output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("output already exists", result.stderr.lower())
        self.assertEqual(marker.read_bytes(), b"existing audio evidence")
        self.assertEqual(list(output.iterdir()), [marker])
        self.assertEqual(sha256(self.sources["tone"]), original)


if __name__ == "__main__":
    unittest.main()
