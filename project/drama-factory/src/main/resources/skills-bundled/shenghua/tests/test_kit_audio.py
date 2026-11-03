"""Unit tests for a kit's audio block: validation in brand_kit.py, rendering in synth_audio.py."""

import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import brand_kit
import synth_audio
from brand_kit import KitError


def write_tone(path, seconds=0.2, amplitude=0.5):
    t = np.arange(int(synth_audio.SR * seconds)) / synth_audio.SR
    pcm = (np.sin(2 * np.pi * 440 * t) * amplitude * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(synth_audio.SR)
        handle.writeframes(pcm.tobytes())


def kit_with(audio):
    return {"version": 2, "colors": {"primary": "#ff0000", "bg": "#ffffff"},
            "fonts": {"display": {"google": "Inter"}}, "audio": audio}


class ValidateAudioTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        write_tone(self.root / "whoosh.wav")

    def test_should_accept_levels_gain_mute_and_file(self):
        brand_kit.validate(kit_with({"levels": {"music": 0.1, "sfx": 0.3},
                                     "sfx": {"whoosh": {"gain": 0.4, "file": "whoosh.wav"}, "type": {"mute": True}}}), self.root)

    def test_should_reject_unknown_cue(self):
        with self.assertRaises(KitError):
            brand_kit.validate(kit_with({"sfx": {"swoosh": {"gain": 0.5}}}), self.root)

    def test_should_reject_level_out_of_range(self):
        with self.assertRaises(KitError):
            brand_kit.validate(kit_with({"levels": {"music": 5}}), self.root)

    def test_should_reject_missing_sound_file(self):
        with self.assertRaises(KitError):
            brand_kit.validate(kit_with({"sfx": {"hit": {"file": "nope.wav"}}}), self.root)

    def test_should_reject_unknown_pack(self):
        with self.assertRaises(KitError):
            brand_kit.validate(kit_with({"pack": "nope"}), self.root)

    def test_should_accept_every_bundled_pack(self):
        for name in brand_kit.sound_packs():
            brand_kit.validate(kit_with({"pack": name}), self.root)


class PackCatalogueTest(unittest.TestCase):
    def test_should_map_only_known_cues_to_listed_archives(self):
        for name, pack in brand_kit.sound_packs().items():
            for cue, files in pack["cues"].items():
                self.assertIn(cue, brand_kit.CUE_TYPES, f"{name}: {cue}")
                for entry in files:
                    self.assertIn(entry.split("/")[0], pack["archives"], f"{name}: {entry}")


class MusicLibraryTest(unittest.TestCase):
    def test_should_accept_every_library_track_as_music(self):
        root = Path(tempfile.mkdtemp())
        for album, entry in brand_kit.music_library().items():
            for track in entry["tracks"]:
                brand_kit.validate(kit_with({"music": f"{album}/{track}"}), root)

    def test_should_treat_an_unknown_album_as_a_kit_file(self):
        self.assertIsNone(brand_kit.library_track("music/bed.mp3"))
        with self.assertRaises(KitError):
            brand_kit.validate(kit_with({"music": "music/bed.mp3"}), Path(tempfile.mkdtemp()))

    def test_should_list_a_checked_archive_and_audio_files_for_every_album(self):
        for album, entry in brand_kit.music_library().items():
            self.assertRegex(entry["archive"]["sha256"], r"^[0-9a-f]{64}$", album)
            self.assertTrue(entry["licence"] and entry["credit"], album)
            for file in entry["tracks"].values():
                self.assertIn(Path(file).suffix.lower(), brand_kit.AUDIO_EXTENSIONS, f"{album}: {file}")


class SynthAudioTest(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        write_tone(self.work / "beep.wav")
        self.samples = synth_audio.SR * 2

    def render(self, cues, settings):
        synth_audio.rng = np.random.default_rng(7)
        sfx, _ = synth_audio.build_sfx(cues, self.samples, synth_audio.Sounds(settings, self.work))
        return sfx

    def test_should_render_every_cue_type_brand_kit_validates(self):
        self.assertEqual(set(brand_kit.CUE_TYPES), set(synth_audio.REFERENCE))

    def test_should_render_silence_when_cue_is_muted(self):
        sfx = self.render([{"type": "whoosh", "t": 0.5}], {"whoosh": {"mute": True}})
        self.assertEqual(np.max(np.abs(sfx)), 0)

    def test_should_scale_cue_by_gain(self):
        loud = self.render([{"type": "pop", "t": 0.5}], {})
        quiet = self.render([{"type": "pop", "t": 0.5}], {"pop": {"gain": 0.5}})
        self.assertAlmostEqual(np.max(np.abs(quiet)), np.max(np.abs(loud)) * 0.5, places=6)

    def test_should_match_recorded_file_to_synth_peak(self):
        synth = self.render([{"type": "ding", "t": 0.5}], {})
        recorded = self.render([{"type": "ding", "t": 0.5}], {"ding": {"files": ["beep.wav"]}})
        self.assertAlmostEqual(np.max(np.abs(recorded)), np.max(np.abs(synth)), places=3)

    def test_should_end_recorded_riser_on_its_cue(self):
        sfx = self.render([{"type": "riser", "t": 0.5, "dur": 0.6}], {"riser": {"files": ["beep.wav"]}})
        last = np.nonzero(sfx)[0][-1] / synth_audio.SR
        self.assertAlmostEqual(last, 1.1, delta=0.01)

    def test_should_fall_back_to_defaults_without_kit(self):
        audio = synth_audio.kit_audio(self.work)
        self.assertEqual(audio["music"], "synth")
        self.assertEqual(audio["levels"], {"music": 0.22, "sfx": 0.5})


class InstallAudioTest(unittest.TestCase):
    def test_should_copy_kit_sounds_and_resolve_them_under_kit(self):
        root, target = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        write_tone(root / "boom.wav")
        write_tone(root / "bed.wav")
        kit = kit_with({"music": "bed.wav", "levels": {"sfx": 0.3}, "sfx": {"hit": {"file": "boom.wav", "gain": 0.8}}})
        manifest = brand_kit.install_audio(kit, root, Path(tempfile.mkdtemp()), target)
        self.assertEqual(manifest["music"], "kit/sounds/music.wav")
        self.assertEqual(manifest["levels"], {"music": 0.22, "sfx": 0.3})
        self.assertEqual(manifest["sfx"]["hit"], {"files": ["kit/sounds/hit-0.wav"], "gain": 0.8, "mute": False})
        self.assertTrue((target / "sounds" / "hit-0.wav").is_file())


if __name__ == "__main__":
    unittest.main()
