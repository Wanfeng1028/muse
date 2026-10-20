"""Unit tests for the pure helpers in scripts/brand_kit.py."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import brand_kit
from brand_kit import KitError


def minimal_kit():
    return {
        "version": 2,
        "name": "Test Brand",
        "colors": {"primary": "#ff0000", "bg": "#ffffff"},
        "fonts": {"display": {"google": "Inter"}},
    }


class ColourMathTest(unittest.TestCase):
    def test_contrast_black_white_is_21(self):
        self.assertAlmostEqual(brand_kit.contrast("#000000", "#ffffff"), 21.0, places=2)

    def test_contrast_same_colour_is_1(self):
        self.assertAlmostEqual(brand_kit.contrast("#3ddc84", "#3ddc84"), 1.0, places=6)

    def test_contrast_is_symmetric(self):
        self.assertAlmostEqual(brand_kit.contrast("#123456", "#fedcba"),
                               brand_kit.contrast("#fedcba", "#123456"), places=9)

    def test_mix_endpoints(self):
        self.assertEqual(brand_kit.mix("#102030", "#ffffff", 0.0), "#102030")
        self.assertEqual(brand_kit.mix("#102030", "#ffffff", 1.0), "#ffffff")

    def test_mix_midpoint(self):
        self.assertEqual(brand_kit.mix("#000000", "#ffffff", 0.5), "#808080")

    def test_luminance_extremes(self):
        self.assertAlmostEqual(brand_kit.luminance("#ffffff"), 1.0, places=6)
        self.assertAlmostEqual(brand_kit.luminance("#000000"), 0.0, places=6)

    def test_is_dark(self):
        self.assertTrue(brand_kit.is_dark("#101014"))
        self.assertFalse(brand_kit.is_dark("#f7f7f4"))


class InkTest(unittest.TestCase):
    def test_already_legible_colour_is_returned_unchanged(self):
        self.assertEqual(brand_kit.ink("#770000", "#ffffff"), "#770000")

    def test_lightens_on_dark_background(self):
        result = brand_kit.ink("#330000", "#101014")
        self.assertNotEqual(result, "#330000")
        self.assertGreaterEqual(brand_kit.contrast(result, "#101014"), 4.5)

    def test_darkens_on_light_background(self):
        result = brand_kit.ink("#ff6666", "#f7f7f4")
        self.assertNotEqual(result, "#ff6666")
        self.assertGreaterEqual(brand_kit.contrast(result, "#f7f7f4"), 4.5)

    def test_unreachable_minimum_falls_back_to_the_pure_shade(self):
        # no colour reaches 25:1, so the loop exhausts to the light/dark extreme
        self.assertEqual(brand_kit.ink("#808080", "#ffffff", minimum=25), "#000000")
        self.assertEqual(brand_kit.ink("#808080", "#101014", minimum=25), "#ffffff")


class PaletteTest(unittest.TestCase):
    def test_minimal_dark_kit_derives_every_token(self):
        kit = minimal_kit()
        kit["colors"]["bg"] = "#101014"
        colors = brand_kit.palette(kit)
        expected = {"scheme", "primary", "primary-ink", "secondary", "bg", "text", "muted",
                    "surface1", "surface2", "border", "on-primary",
                    "success", "on-success", "error", "on-error"}
        self.assertEqual(set(colors), expected)
        self.assertEqual(colors["scheme"], "dark")
        self.assertEqual(colors["bg"], "#101014")
        self.assertEqual(colors["success"], brand_kit.DEFAULT_SUCCESS)
        self.assertEqual(colors["error"], brand_kit.DEFAULT_ERROR)

    def test_muted_is_text_mixed_toward_bg(self):
        kit = minimal_kit()
        colors = brand_kit.palette(kit)
        self.assertEqual(colors["muted"], brand_kit.mix(colors["text"], colors["bg"], 0.42))

    def test_secondary_derived_from_primary_when_absent(self):
        kit = minimal_kit()  # light bg → secondary mixes primary toward black
        colors = brand_kit.palette(kit)
        self.assertEqual(colors["secondary"], brand_kit.mix("#ff0000", "#000000", 0.35))

    def test_explicit_secondary_and_status_colours_win(self):
        kit = minimal_kit()
        kit["colors"].update({"secondary": "#00ff00", "success": "#123456", "error": "#654321"})
        colors = brand_kit.palette(kit)
        self.assertEqual(colors["secondary"], "#00ff00")
        self.assertEqual(colors["success"], "#123456")
        self.assertEqual(colors["error"], "#654321")

    def test_scheme_switch_to_light_uses_bgalt(self):
        kit = minimal_kit()
        kit["colors"].update({"bg": "#101014", "bgAlt": "#f0f0ee", "textAlt": "#222222"})
        colors = brand_kit.palette(kit, "light")
        self.assertEqual(colors["scheme"], "light")
        self.assertEqual(colors["bg"], "#f0f0ee")
        self.assertEqual(colors["text"], "#222222")

    def test_scheme_switch_without_bgalt_derives_a_tinted_canvas(self):
        kit = minimal_kit()
        kit["colors"]["bg"] = "#101014"
        colors = brand_kit.palette(kit, "light")
        self.assertEqual(colors["bg"], brand_kit.mix("#f7f7f4", "#ff0000", 0.04))
        self.assertEqual(colors["scheme"], "light")

    def test_matching_scheme_keeps_the_kit_canvas(self):
        kit = minimal_kit()
        kit["colors"]["bg"] = "#101014"
        colors = brand_kit.palette(kit, "dark")
        self.assertEqual(colors["bg"], "#101014")

    def test_text_defaults_to_canvas_pair(self):
        kit = minimal_kit()
        self.assertEqual(brand_kit.palette(kit)["text"], "#14161a")  # light canvas
        kit["colors"]["bg"] = "#101014"
        self.assertEqual(brand_kit.palette(kit)["text"], "#eef0f2")  # dark canvas


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_minimal_kit_passes(self):
        brand_kit.validate(minimal_kit(), self.root)

    def test_missing_primary_and_bg_fail(self):
        for missing in ("primary", "bg"):
            kit = minimal_kit()
            del kit["colors"][missing]
            with self.assertRaises(KitError) as ctx:
                brand_kit.validate(kit, self.root)
            self.assertIn(f"colors.{missing}", ctx.exception.problem)

    def test_bad_hex_fails(self):
        kit = minimal_kit()
        kit["colors"]["primary"] = "red"
        with self.assertRaises(KitError) as ctx:
            brand_kit.validate(kit, self.root)
        self.assertIn("#rrggbb", ctx.exception.problem)

    def test_missing_display_font_fails(self):
        kit = minimal_kit()
        del kit["fonts"]["display"]
        with self.assertRaises(KitError) as ctx:
            brand_kit.validate(kit, self.root)
        self.assertIn("fonts.display", ctx.exception.problem)

    def test_font_file_must_exist_and_be_a_web_font(self):
        kit = minimal_kit()
        kit["fonts"]["display"] = {"file": "fonts/Display.woff2"}
        with self.assertRaises(KitError) as ctx:
            brand_kit.validate(kit, self.root)
        self.assertIn("does not exist", ctx.exception.problem)
        (self.root / "fonts").mkdir()
        (self.root / "fonts" / "Display.txt").write_text("x")
        kit["fonts"]["display"] = {"file": "fonts/Display.txt"}
        with self.assertRaises(KitError) as ctx:
            brand_kit.validate(kit, self.root)
        self.assertIn("not a web font", ctx.exception.problem)
        (self.root / "fonts" / "Display.woff2").write_bytes(b"wOF2")
        kit["fonts"]["display"] = {"file": "fonts/Display.woff2"}
        brand_kit.validate(kit, self.root)

    def test_font_with_neither_file_nor_google_fails(self):
        kit = minimal_kit()
        kit["fonts"]["display"] = {"family": "Inter"}
        with self.assertRaises(KitError):
            brand_kit.validate(kit, self.root)

    def test_nested_logos_must_exist(self):
        kit = minimal_kit()
        kit["logos"] = {"wordmark": {"onDark": "logos/mark.svg"}}
        with self.assertRaises(KitError) as ctx:
            brand_kit.validate(kit, self.root)
        self.assertIn("wordmark.onDark", ctx.exception.problem)
        (self.root / "logos").mkdir()
        (self.root / "logos" / "mark.svg").write_text("<svg/>")
        brand_kit.validate(kit, self.root)

    def test_logo_extension_checked(self):
        kit = minimal_kit()
        (self.root / "mark.gif").write_bytes(b"GIF89a")
        kit["logos"] = {"mark": "mark.gif"}
        with self.assertRaises(KitError):
            brand_kit.validate(kit, self.root)

    def test_unknown_background_style_fails(self):
        kit = minimal_kit()
        kit["background"] = {"style": "plaid"}
        with self.assertRaises(KitError) as ctx:
            brand_kit.validate(kit, self.root)
        self.assertIn("plaid", ctx.exception.problem)

    def test_image_background_needs_its_file(self):
        kit = minimal_kit()
        kit["background"] = {"style": "image", "image": "bg.jpg"}
        with self.assertRaises(KitError):
            brand_kit.validate(kit, self.root)
        (self.root / "bg.jpg").write_bytes(b"\xff\xd8")
        brand_kit.validate(kit, self.root)

    def test_flatten_logos_unnests(self):
        flat = dict(brand_kit.flatten_logos({"a": {"b": "x.svg"}, "c": "y.svg"}))
        self.assertEqual(flat, {"a.b": "x.svg", "c": "y.svg"})


class ResolveTest(unittest.TestCase):
    """resolve() against a temp HOME: named kits, config.json defaultKit, legacy file, example."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.config_dir = root / "config"
        self.kits_dir = self.config_dir / "kits"
        self.kits_dir.mkdir(parents=True)
        self.patcher = mock.patch.multiple(
            brand_kit,
            CONFIG_DIR=self.config_dir,
            KITS_DIR=self.kits_dir,
            CONFIG_FILE=self.config_dir / "config.json",
            LEGACY_KIT=self.config_dir / "brand.json",
        )
        self.patcher.start()
        self.cwd = os.getcwd()
        os.chdir(root)  # resolve() probes ./brand.json; the temp cwd must not have one

    def tearDown(self):
        os.chdir(self.cwd)
        self.patcher.stop()
        self.tmp.cleanup()

    def make_kit(self, folder, name):
        path = Path(folder)
        path.mkdir(parents=True, exist_ok=True)
        kit = minimal_kit()
        kit["name"] = name
        (path / "brand.json").write_text(json.dumps(kit), encoding="utf-8")
        return path

    def set_default(self, name):
        (self.config_dir / "config.json").write_text(json.dumps({"defaultKit": name}), encoding="utf-8")

    def test_explicit_folder_resolves(self):
        kit_dir = self.make_kit(Path(self.tmp.name) / "elsewhere", "Elsewhere")
        self.assertEqual(brand_kit.resolve(str(kit_dir)), kit_dir)

    def test_explicit_brand_json_path_resolves(self):
        kit_dir = self.make_kit(Path(self.tmp.name) / "elsewhere", "Elsewhere")
        self.assertEqual(brand_kit.resolve(str(kit_dir / "brand.json")), kit_dir / "brand.json")

    def test_name_resolves_to_kits_folder_entry(self):
        folder = self.make_kit(self.kits_dir / "acme", "Acme")
        self.assertEqual(brand_kit.resolve("acme"), folder)

    def test_name_matches_the_brand_name_not_just_the_folder(self):
        folder = self.make_kit(self.kits_dir / "random-slug", "Acme Health")
        self.assertEqual(brand_kit.resolve("Acme Health"), folder)

    def test_mistyped_name_fails_loud(self):
        self.make_kit(self.kits_dir / "acme", "Acme")
        with self.assertRaises(KitError) as ctx:
            brand_kit.resolve("acm")
        self.assertIn("No kit named", ctx.exception.problem)

    def test_configured_default_is_used_without_an_argument(self):
        folder = self.make_kit(self.kits_dir / "acme", "Acme")
        self.set_default("acme")
        self.assertEqual(brand_kit.resolve(), folder)

    def test_default_pointing_at_a_missing_kit_fails(self):
        self.set_default("ghost")
        with self.assertRaises(KitError) as ctx:
            brand_kit.resolve()
        self.assertIn("ghost", ctx.exception.problem)

    def test_legacy_single_kit_is_the_next_fallback(self):
        legacy = self.config_dir / "brand.json"
        legacy.write_text(json.dumps(minimal_kit()), encoding="utf-8")
        self.assertEqual(brand_kit.resolve(), legacy)

    def test_bundled_example_is_the_last_resort(self):
        self.assertEqual(brand_kit.resolve(), brand_kit.SKILL_DIR / "brand.example.json")

    def test_explicit_path_beats_the_default(self):
        self.make_kit(self.kits_dir / "acme", "Acme")
        self.set_default("acme")
        other = self.make_kit(Path(self.tmp.name) / "other", "Other")
        self.assertEqual(brand_kit.resolve(str(other)), other)

    def test_slug(self):
        self.assertEqual(brand_kit.slug("Acme Health"), "acme-health")
        self.assertEqual(brand_kit.slug("!!!"), "kit")

    def test_google_font_name_old_shape(self):
        url = "https://fonts.gstatic.com/s/anton/v27-1Ptgg87LROyAm3K8-C8.woff2"
        self.assertEqual(brand_kit.google_font_name(url), "s-anton-v27-1Ptgg87LROyAm3K8-C8.woff2")

    def test_google_font_name_kit_shape_has_no_query_chars(self):
        # /l/font?kit=… URLs kept ? and &, which become a query string inside CSS url() and 404 the file
        url = "https://fonts.gstatic.com/l/font?kit=tDbv2o-flEEny0FZhsfKu5WU4zr3E_BX0PnT8RD8yKwBNntkaToggR7BYXHKPx3cwg&skey=48ad01c60053c2ae&v=v24"
        name = brand_kit.google_font_name(url)
        self.assertNotIn("?", name)
        self.assertNotIn("&", name)
        self.assertTrue(name.endswith(".woff2"))
        self.assertRegex(name, r"^[A-Za-z0-9._-]+$")


if __name__ == "__main__":
    unittest.main()
