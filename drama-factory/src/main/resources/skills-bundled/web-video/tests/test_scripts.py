"""Unit tests for the pure parts of the web-video scripts. Run: python3 -m unittest discover -s tests"""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import edl  # noqa: E402
import overlay  # noqa: E402
from common import FPS, snap, validate_storyboard  # noqa: E402
from record import is_secret, parse_action, step_actions  # noqa: E402
from redact import MASK, Redactor, literal_pass  # noqa: E402
import theme  # noqa: E402


def on_grid(x):
    return abs(x * FPS - round(x * FPS)) < 1e-4   # snap() keeps 6 decimals


class TimeMapping(unittest.TestCase):
    def setUp(self):
        self.segs = edl.build_ranges(1.0, 10.0, windows=[(1.0, 3.0), (6.0, 7.0)], cuts=[], idle_speed=6.0)

    def test_classifies_keep_and_idle(self):
        self.assertEqual([s["speed"] == 1.0 for s in self.segs], [True, False, True, False])
        idle = self.segs[1]
        self.assertGreaterEqual(idle["speed"], 6.0)
        self.assertLessEqual((idle["b"] - idle["a"]) / idle["speed"], edl.MAX_IDLE_OUT + 1e-6)

    def test_boundaries_snap_to_frame_grid(self):
        segs = edl.build_ranges(0.513, 4.271, [(0.9, 2.017)], [], 6.0)
        self.assertTrue(all(on_grid(s["a"]) and on_grid(s["b"]) for s in segs))

    def test_cuts_are_removed(self):
        segs = edl.build_ranges(0.0, 6.0, [(0.0, 6.0)], cuts=[(2.0, 4.0)], idle_speed=6.0)
        self.assertEqual([(s["a"], s["b"]) for s in segs], [(0.0, 2.0), (4.0, 6.0)])
        self.assertAlmostEqual(edl.newt(segs, 3.0), 2.0)      # inside a cut maps to the next kept frame
        self.assertAlmostEqual(edl.body_duration(segs), 4.0)

    def test_short_idle_gap_stays_1x(self):
        segs = edl.build_ranges(0.0, 3.0, [(0.0, 1.4), (1.5, 3.0)], [], 6.0)
        self.assertEqual(len(segs), 1)

    def test_newt_monotonic_and_rawt_inverse(self):
        segs = edl.insert_freeze(self.segs, 2.0, 1.0)
        prev = -1
        for k in range(0, 101):
            t = 1.0 + k * 0.09
            nt = edl.newt(segs, t)
            self.assertGreaterEqual(nt, prev - 1e-9)
            prev = nt
        for t in (1.2, 2.5, 6.5):                         # 1x regions round-trip exactly
            self.assertAlmostEqual(edl.rawt(segs, edl.newt(segs, t)), t, places=6)

    def test_freeze_adds_duration_once(self):
        before = edl.body_duration(self.segs)
        segs = edl.insert_freeze(self.segs, 2.0, 1.0)
        self.assertAlmostEqual(edl.body_duration(segs), before + 1.0, places=6)
        self.assertEqual(sum(1 for s in segs if "freeze" in s), 1)
        self.assertAlmostEqual(edl.newt(segs, 2.0 + 1 / FPS) - edl.newt(segs, 2.0), 1.0 + 1 / FPS, places=6)


def fake_doc(off=0.1):
    ev = [{"t": 0.5, "kind": "flash"}, {"t": 1.0, "kind": "flash_end"},
          {"t": 1.0, "kind": "step", "i": 0, "caption": "Login", "hidden": True, "bug": False},
          {"t": 3.0, "kind": "step_end", "i": 0},
          {"t": 3.0, "kind": "step", "i": 1, "caption": "Open the list", "hidden": False, "bug": False},
          {"t": 5.0, "kind": "step_end", "i": 1},
          {"t": 5.0, "kind": "step", "i": 2, "caption": "Click save", "hidden": False, "bug": True},
          {"t": 6.0, "kind": "click", "x": 640, "y": 650, "w": 1280, "h": 720, "target": "#save",
           "bbox": {"x": 600, "y": 630, "width": 80, "height": 40}},
          {"t": 6.1, "kind": "error", "source": "http", "status": 500, "method": "POST", "url": "http://x/api"},
          {"t": 9.0, "kind": "bug", "i": 2, "bbox": {"x": 600, "y": 630, "width": 80, "height": 40}},
          {"t": 9.0, "kind": "step_end", "i": 2}, {"t": 9.0, "kind": "end"}]
    return {"viewport": [1280, 720], "video_offset": off, "events": ev}


SB = {"mode": "bug-report", "url": "http://x", "title": "t",
      "bug": {"expected": "saved", "actual": "spins"},
      "steps": [{"do": "goto /login", "hidden": True}, {"do": "expect h1", "caption": "Open the list"},
                {"do": "click #save", "caption": "Click save", "bug": True}]}


class Plan(unittest.TestCase):
    def test_bug_report_plan(self):
        plan = edl.make_plan(fake_doc(), SB, raw_dur=14.0, narration=None, zoom=1.5)
        self.assertGreaterEqual(plan["start"], 3.1 - 1e-6)            # hidden login and flash are cut
        self.assertEqual(sum(1 for s in plan["segments"] if "freeze" in s and s["dur"] == edl.BUG_FREEZE), 1)
        self.assertEqual(plan["zooms"], [])                            # no zoom in bug-report
        self.assertAlmostEqual(plan["stop"], 9.1 + edl.TAIL["bug-report"], places=6)
        self.assertEqual([c["text"] for c in plan["captions"]], ["Open the list", "Click save"])
        self.assertEqual(len(plan["errors"]), 1)

    def test_feature_demo_caption_goes_opposite_click(self):
        sb = dict(SB, mode="feature-demo")
        plan = edl.make_plan(fake_doc(), sb, raw_dur=14.0, narration=None, zoom=1.5)
        self.assertEqual(plan["captions"][1]["pos"], "top")           # click at y=650 of 720
        self.assertEqual(len(plan["zooms"]), 1)
        self.assertIsNone(next((s for s in plan["segments"] if s.get("dur") == edl.BUG_FREEZE), None))

    def test_offset_applied_once(self):
        a = edl.make_plan(fake_doc(0.0), SB, 14.0, None, 1.5)
        b = edl.make_plan(fake_doc(0.3), SB, 14.0, None, 1.5)
        self.assertAlmostEqual(b["start"] - a["start"], 0.3, delta=1 / FPS)
        self.assertAlmostEqual(b["clicks"][0]["raw_t"] - a["clicks"][0]["raw_t"], 0.3, places=6)

    def test_narration_holds_step(self):
        sb = dict(SB, mode="feature-demo")
        narr = {"clips": [{"i": 1, "duration": 5.0, "file": "x"}]}
        plan = edl.make_plan(fake_doc(), sb, 14.0, narr, 1.5)
        cap = plan["captions"][0]
        self.assertGreaterEqual(cap["b"] - cap["a"], 5.0 + 0.35 - 1 / FPS)

    def test_first_visible_goto_skips_page_load(self):
        doc = fake_doc(0.0)
        doc["events"] = [e for e in doc["events"] if e.get("i") != 0 or e["kind"] not in ("step", "step_end")]
        doc["events"].insert(2, {"t": 1.0, "kind": "step", "i": 0, "caption": "Open", "hidden": False, "bug": False})
        doc["events"].insert(3, {"t": 2.6, "kind": "nav", "url": "http://x/"})
        doc["events"].insert(4, {"t": 3.0, "kind": "step_end", "i": 0})
        sb = dict(SB, mode="feature-demo", steps=[{"do": "goto /", "caption": "Open"}] + SB["steps"][1:])
        plan = edl.make_plan(doc, sb, 14.0, None, 1.5)
        self.assertGreaterEqual(plan["start"], 2.6)

    def test_zoom_expression_has_all_windows(self):
        z = [{"a": 1.0, "b": 2.5, "cx": 0.2, "cy": 0.3}, {"a": 3.0, "b": 4.0, "cx": 0.8, "cy": 0.6}]
        f = edl.zoom_filter(z, 1280, 720, 1.5, 2)
        self.assertIn("2560:1440", f)
        self.assertEqual(f.count("clip(min("), 2)
        self.assertIn("0.8", f)


class Storyboard(unittest.TestCase):
    def test_parse_actions(self):
        self.assertEqual(parse_action("fill #email | a@b.c"), ("fill", ["#email", "a@b.c"]))
        self.assertEqual(parse_action("click text=New invoice"), ("click", ["text=New invoice"]))
        self.assertEqual(step_actions({"do": ["goto /", "wait 300"]}), [("goto", ["/"]), ("wait", ["300"])])

    def test_yaml_comment_trap_has_hint(self):
        with self.assertRaisesRegex(ValueError, "quote the whole line"):
            parse_action("fill")

    def test_bad_actions(self):
        for s in ("tap #x", "type #x", "goto"):
            with self.assertRaises(ValueError):
                parse_action(s)

    def test_validate(self):
        self.assertEqual(validate_storyboard(SB), [])
        bad = dict(SB, steps=[{"do": "click #a"}])
        self.assertTrue(any("caption" in e for e in validate_storyboard(bad)))
        self.assertTrue(any("bug" in e for e in validate_storyboard(dict(SB, bug={}))))

    def test_is_secret(self):
        self.assertTrue(is_secret("#password", None))
        self.assertTrue(is_secret("#pw", "password"))
        self.assertFalse(is_secret("#email", "email"))


class Redaction(unittest.TestCase):
    def test_har_entry(self):
        r = Redactor(literals=["hunter22"])
        entry = {"request": {"url": "http://x/api?token=abc&page=2", "headers": [
            {"name": "Authorization", "value": "Bearer abcdefghijkl"}, {"name": "Accept", "value": "json"}],
            "cookies": [{"name": "sid", "value": "s3cr3t"}],
            "postData": {"mimeType": "application/json", "text": '{"email":"a@b.c","password":"hunter22"}'}}}
        out = r.walk(entry)
        req = out["request"]
        self.assertIn(f"token={MASK.replace('[', '%5B').replace(']', '%5D')}", req["url"])
        self.assertIn("page=2", req["url"])
        self.assertEqual(req["headers"][0]["value"], MASK)
        self.assertEqual(req["headers"][1]["value"], "json")
        self.assertEqual(req["cookies"][0]["value"], MASK)
        self.assertNotIn("hunter22", req["postData"]["text"])
        self.assertIn("a@b.c", req["postData"]["text"])

    def test_literal_pass_catches_trace_params(self):
        r = Redactor(literals=["demo-pass"])
        line = json.dumps({"method": "fill", "params": {"selector": "#pw", "value": "demo-pass"}}).encode()
        self.assertNotIn(b"demo-pass", literal_pass(r, line))


class VietnameseNumbers(unittest.TestCase):
    def test_num_to_vi(self):
        from tts import num_to_vi
        cases = {0: "không", 15: "mười lăm", 21: "hai mươi mốt", 105: "một trăm linh năm",
                 1005: "một nghìn không trăm linh năm", 1500: "một nghìn năm trăm",
                 1200300: "một triệu hai trăm nghìn ba trăm", 2000000000: "hai tỷ"}
        for n, w in cases.items():
            self.assertEqual(num_to_vi(n), w)

    def test_normalize_vi(self):
        from tts import normalize_vi
        self.assertEqual(normalize_vi("Tổng 1.500 USD, giảm 10%"),
                         "Tổng một nghìn năm trăm đô la, giảm mười phần trăm")
        self.assertEqual(normalize_vi("Giá $25"), "Giá hai mươi lăm đô la")
        self.assertEqual(normalize_vi("tăng 2,5 lần"), "tăng hai phẩy năm lần")
        self.assertEqual(normalize_vi("Bấm New invoice"), "Bấm New invoice")


class FfmpegCompat(unittest.TestCase):
    def test_filter_script_flag_by_version(self):
        import common
        old = common._FF_MAJOR
        try:
            for major, flag in ((6, "-filter_complex_script"), (7, "-/filter_complex"), (8, "-/filter_complex"),
                                (0, "-/filter_complex")):
                common._FF_MAJOR = major
                self.assertEqual(common.filter_script_args("f.txt"), [flag, "f.txt"])
        finally:
            common._FF_MAJOR = old


class TextFiles(unittest.TestCase):
    def test_textfile_uses_lf_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            t = overlay.Texts(pathlib.Path(td))
            rel = t.file("dòng 1\ndòng 2")
            self.assertNotIn(b"\r", (pathlib.Path(td) / rel).read_bytes())


class BrowserProfile(unittest.TestCase):
    """browser_profile.py without a browser: naming, launch flags, import filtering, delete safety."""

    def setUp(self):
        import importlib
        import os
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.root = self.base / "profiles"
        self._env = os.environ.get("WEB_VIDEO_PROFILE_ROOT")
        os.environ["WEB_VIDEO_PROFILE_ROOT"] = str(self.root)
        import browser_profile
        self.bp = importlib.reload(browser_profile)
        self.chrome = self.base / "Chrome"
        self.bp.chrome_user_data_dir = lambda: self.chrome

    def tearDown(self):
        import os
        if self._env is None:
            os.environ.pop("WEB_VIDEO_PROFILE_ROOT", None)
        else:
            os.environ["WEB_VIDEO_PROFILE_ROOT"] = self._env
        self.tmp.cleanup()

    def fake_chrome(self):
        prof = self.chrome / "Profile 1"
        prof.mkdir(parents=True)
        (self.chrome / "Local State").write_text(json.dumps({"profile": {"info_cache": {
            "Profile 1": {"name": "Work", "user_name": "qa@example.com"}}}}), encoding="utf-8")
        for f in ("Preferences", "Cookies", "Login Data", "Web Data", "History"):
            (prof / f).write_text("x", encoding="utf-8")
        (prof / "Local Storage").mkdir()
        (prof / "Local Storage" / "leveldb").write_text("x", encoding="utf-8")

    def run_import(self, name, src="Profile 1", replace=False):
        import argparse
        return self.bp.cmd_import(argparse.Namespace(name=name, from_chrome=src, replace=replace))

    def test_resolve_names_and_paths(self):
        self.assertEqual(self.bp.resolve("demo_1"), self.root / "demo_1")
        for bad in ("..", ".", "a b", "a;b"):
            with self.assertRaises(SystemExit):
                self.bp.resolve(bad)
        self.assertEqual(self.bp.resolve(str(self.base / "x")), (self.base / "x").resolve())

    def test_launch_flags_by_keychain(self):
        real = self.bp.launch_options("chrome", interactive=False)
        self.assertIn("--use-mock-keychain", real["ignore_default_args"])
        self.assertEqual(real["channel"], "chrome")
        self.assertNotIn("--enable-automation", real["ignore_default_args"])
        mock = self.bp.launch_options("chromium", interactive=False, keychain="mock")
        self.assertEqual(mock["ignore_default_args"], [])
        self.assertNotIn("channel", mock)
        login = self.bp.launch_options(None, interactive=True)
        self.assertIn("--enable-automation", login["ignore_default_args"])

    def test_chrome_profiles_listing(self):
        self.fake_chrome()
        self.assertEqual(self.bp.chrome_profiles(), [("Profile 1", "Work", "qa@example.com")])

    def test_import_copies_only_session_state(self):
        self.fake_chrome()
        self.run_import("work")
        d = self.root / "work" / "Default"
        self.assertTrue((d / "Cookies").exists() and (d / "Local Storage" / "leveldb").exists())
        for kept_out in ("Login Data", "Web Data", "History"):
            self.assertFalse((d / kept_out).exists(), kept_out)
        self.assertTrue((self.root / "work" / "Local State").exists())
        self.assertEqual(self.bp.read_marker(self.root / "work")["source"], "chrome:Profile 1")
        with self.assertRaises(SystemExit):                 # exists, no --replace
            self.run_import("work")
        self.run_import("work", replace=True)

    def test_import_rejects_traversal(self):
        self.fake_chrome()
        for bad in ("../Chrome", "..", "a/b"):
            with self.assertRaises(SystemExit):
                self.run_import("x", src=bad)

    def test_delete_refuses_foreign_folders(self):
        import argparse
        foreign = self.base / "important"
        foreign.mkdir()
        (foreign / "keep.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.bp.cmd_delete(argparse.Namespace(name=str(foreign)))
        self.assertTrue((foreign / "keep.txt").exists())
        self.assertFalse(self.bp.safe_to_remove(pathlib.Path.home()))
        marked = self.bp.init_profile(self.base / "elsewhere", "test", "mock")
        self.bp.cmd_delete(argparse.Namespace(name=str(marked)))
        self.assertFalse(marked.exists())
        self.bp.init_profile(self.root / "inroot", "login")
        self.bp.cmd_delete(argparse.Namespace(name="inroot"))
        self.assertFalse((self.root / "inroot").exists())

    def test_restore_state_adds_only_missing_cookies(self):
        prof = self.bp.init_profile(self.root / "p", "test", "mock")
        (prof / self.bp.STATE).write_text(json.dumps({"cookies": [
            {"name": "session", "value": "s1", "domain": "localhost", "path": "/"},
            {"name": "theme", "value": "dark", "domain": "localhost", "path": "/"}]}), encoding="utf-8")

        class Ctx:
            added = []
            def cookies(self):
                return [{"name": "theme", "value": "light", "domain": "localhost", "path": "/"}]
            def add_cookies(self, cs):
                self.added.extend(cs)
        ctx = Ctx()
        self.assertEqual(self.bp.restore_state(ctx, prof), 1)
        self.assertEqual([c["name"] for c in ctx.added], ["session"])     # live value wins for existing ones

    def test_list_tolerates_legacy_and_unknown(self):
        import contextlib
        import io
        (self.root / "legacy").mkdir(parents=True)
        (self.root / "legacy" / "web-video-source.json").write_text('{"chrome_profile": "Default"}', encoding="utf-8")
        (self.root / "bare").mkdir()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.bp.cmd_list(None)
        self.assertIn("chrome:Default", out.getvalue())
        self.assertIn("bare", out.getvalue())


class Theme(unittest.TestCase):
    """theme.py: loading, validation, layout, layers. Rendering tests skip when no usable font exists."""

    def setUp(self):
        import importlib
        import os
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self._env = os.environ.get("WEB_VIDEO_THEME_DIR")
        os.environ["WEB_VIDEO_THEME_DIR"] = str(self.base / "personal")
        self.th = importlib.reload(theme)

    def tearDown(self):
        import os
        if self._env is None:
            os.environ.pop("WEB_VIDEO_THEME_DIR", None)
        else:
            os.environ["WEB_VIDEO_THEME_DIR"] = self._env
        self.tmp.cleanup()

    def write(self, name, text, folder=None):
        d = folder or self.base
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        p.write_text(text, encoding="utf-8")
        return p

    def fonts_or_skip(self, t):
        try:
            self.th.font_file(t, "display")
        except SystemExit:
            self.skipTest("no display font on this machine")

    def test_builtin_base_is_neutral(self):
        t = self.th.load_theme("clean")
        for k in ("brand", "seal_glyph", "watermark_glyph", "vertical_note"):
            self.assertEqual(t[k], "", k)
        self.assertEqual(t["numerals"], "arabic")
        self.assertEqual([n for n, origin in self.th.theme_names() if origin == "built-in"], ["clean"])

    def test_extends_overrides_only_given_keys(self):
        p = self.write("brand.yaml", "extends: clean\nbrand: ACME\ncolors:\n  seal: '#004488'\n")
        t = self.th.load_theme(str(p))
        self.assertEqual((t["brand"], t["colors"]["seal"]), ("ACME", "#004488"))
        self.assertEqual(t["colors"]["paper"], "#F7F7F5")      # inherited from the base
        self.assertEqual(t["name"], "brand")

    def test_personal_theme_dir_wins_over_builtin_and_is_listed(self):
        self.write("clean.yaml", "extends: " + str(self.th.THEMES / "clean.yaml") + "\nbrand: MINE\n",
                   self.base / "personal")
        self.assertEqual(self.th.load_theme("clean")["brand"], "MINE")
        self.assertIn(("clean", f"personal ({self.base / 'personal'})"), self.th.theme_names())

    def test_validation_reports_every_problem(self):
        p = self.write("bad.yaml", "extends: clean\ncanvas: [1921, 1080]\ncolors:\n  seal: red\n"
                                   "numerals: roman\n")
        with self.assertRaises(SystemExit) as cm:
            self.th.load_theme(str(p))
        msg = str(cm.exception)
        for part in ("canvas must be", "colors.seal must be", "numerals must be"):
            self.assertIn(part, msg)

    def test_extends_cycle_stops(self):
        self.write("a.yaml", "extends: b.yaml\n")
        self.write("b.yaml", "extends: a.yaml\n")
        with self.assertRaises(SystemExit):
            self.th.load_theme(str(self.base / "a.yaml"))

    def test_hanzi_numerals_need_a_hanzi_font(self):
        p = self.write("h.yaml", "extends: clean\nnumerals: hanzi\n")
        with self.assertRaisesRegex(SystemExit, "fonts.hanzi"):
            self.th.load_theme(str(p))

    def test_layout_keeps_aspect_and_leaves_a_caption_band(self):
        t = self.th.load_theme("clean")
        for vp in ((1280, 720), (1440, 900), (1280, 800)):
            fx, fy, fw, fh = self.th.layout(t, vp)["frame"]
            self.assertAlmostEqual(fw / fh, vp[0] / vp[1], places=2)
            self.assertTrue(fw % 2 == 0 and fh % 2 == 0 and fx % 2 == 0)
            self.assertLess(self.th.layout(t, vp)["band_top"] + t["caption"]["size"], t["canvas"][1])

    def test_layout_shrinks_wide_frames_and_rejects_impossible_ones(self):
        t = self.th.load_theme(str(self.write("wide.yaml", "extends: clean\nframe:\n  width: 1900\n  top: 60\n")))
        for vp in ((1280, 720), (1024, 768)):
            lay = self.th.layout(t, vp)
            fx, fy, fw, fh = lay["frame"]
            self.assertLessEqual(lay["band_top"] + t["caption"]["size"], t["canvas"][1])
            self.assertAlmostEqual(fw / fh, vp[0] / vp[1], places=2)
        low = self.th.load_theme(str(self.write("low.yaml", "extends: clean\nframe:\n  top: 800\n")))
        with self.assertRaisesRegex(SystemExit, "caption band"):
            self.th.layout(low, (1280, 720))

    def test_numerals(self):
        self.assertEqual([self.th.numeral(n, "hanzi") for n in (1, 8, 10, 12, 20)], ["一", "八", "十", "十二", "二十"])
        self.assertEqual(self.th.numeral(3, "arabic"), "03")
        self.assertEqual(self.th.numeral(120, "hanzi"), "120")

    def test_layers_render_and_captions_are_cropped(self):
        t = self.th.load_theme("clean")
        self.fonts_or_skip(t)
        res = self.th.render_layers(t, (1280, 720), self.base / "out" / "theme", title="Tạo hoá đơn mới",
                                    subtitle="Hướng dẫn", outro="Xong!", label="v2.3",
                                    captions=[(1, "Bấm Lưu"), (2, "Nhập khách hàng và số tiền " * 3)])
        from PIL import Image
        cw, ch = t["canvas"]
        for key in ("background", "intro", "outro"):
            with Image.open(self.base / "out" / res["files"][key]) as im:
                self.assertEqual(im.size, (cw, ch))
        for cap in res["files"]["captions"].values():
            with Image.open(self.base / "out" / cap["file"]) as f:
                im = f.copy()
            self.assertLess(im.height, ch // 4)                       # cropped to the caption band
            self.assertTrue(0 <= cap["x"] and cap["x"] + im.width <= cw and cap["y"] + im.height <= ch)
            self.assertTrue(im.width % 2 == 0 and im.height % 2 == 0)

    def test_long_caption_shrinks_to_fit(self):
        t = self.th.load_theme("clean")
        self.fonts_or_skip(t)
        lay = self.th.layout(t, (1280, 720))
        img = self.th.caption(t, lay, 7, "Một chú thích rất dài để kiểm tra việc thu nhỏ chữ cho vừa khung " * 2)
        x0, _, x1, _ = img.getbbox()
        self.assertGreaterEqual(x0, int(t["canvas"][0] * 0.04))
        self.assertLessEqual(x1, int(t["canvas"][0] * 0.96))

    def test_vietnamese_glyphs_in_base_font(self):
        t = self.th.load_theme("clean")
        self.fonts_or_skip(t)
        f = self.th.Fonts(t)("display", 40)
        self.assertTrue(all(self.th.has_glyph(f, c) for c in "ạảấầẩẫậắằẳẵặđơưộợ"))

    def test_storyboard_rules(self):
        base = {"mode": "feature-demo", "url": "http://x", "steps": [{"caption": "a", "do": "wait 1"}]}
        self.assertEqual(validate_storyboard({**base, "theme": "clean"}), [])
        bug = {**base, "mode": "bug-report", "theme": "clean", "bug": {"expected": "e", "actual": "a"},
               "steps": [{"caption": "a", "do": "wait 1", "bug": True}]}
        self.assertIn("'theme' applies to feature-demo only", validate_storyboard(bug))


class ThemeInit(unittest.TestCase):
    """theme_init: a project's design becomes the video theme (colours, fonts, brand, sources)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name)
        import theme_init
        self.ti = theme_init

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, rel, text):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def test_parse_color_forms(self):
        pc = self.ti.parse_color
        self.assertEqual(pc("#abc"), "#AABBCC")
        self.assertEqual(pc("#11223344"), "#112233")
        self.assertEqual(pc("rgb(37, 99, 235)"), "#2563EB")
        self.assertEqual(pc("0 0% 100%"), "#FFFFFF")                  # shadcn HSL triplet
        self.assertEqual(pc("hsl(0, 100%, 50%)"), "#FF0000")
        self.assertIsNone(pc("var(--primary)"))

    def test_canvas_is_one_step_from_the_app_background(self):
        light, dark = self.ti.canvas_from("#FFFFFF"), self.ti.canvas_from("#0B0F14")
        self.assertTrue(1.05 < self.ti.contrast("#FFFFFF", light) < 1.3)
        self.assertTrue(1.05 < self.ti.contrast("#0B0F14", dark) < 1.6)

    def test_shadcn_css_variables_and_brand(self):
        self.put("package.json", json.dumps({"name": "@acme/billing-portal", "dependencies": {"@fontsource/inter": "5"}}))
        self.put("src/globals.css", """:root { --background: 0 0% 100%; --foreground: 222.2 84% 4.9%;
            --primary: 221.2 83.2% 53.3%; --muted: 210 40% 96.1%; --border: 214.3 31.8% 91.4%; }
            .dark { --background: 222.2 84% 4.9%; --foreground: 210 40% 98%; }""")
        self.put("node_modules/x/evil.css", ":root { --primary: #FF00FF; }")   # never scanned
        t, sources, notes = self.ti.build_theme(self.repo)
        self.assertEqual(t["extends"], "clean")
        self.assertEqual(t["colors"]["paper"], self.ti.canvas_from("#FFFFFF"))   # light palette, not .dark
        self.assertTrue(self.ti.luminance(t["colors"]["ink"]) < 0.05)
        self.assertNotEqual(t["colors"]["seal"], "#FF00FF")
        self.assertGreater(self.ti.saturation(t["colors"]["seal"]), 0.5)
        self.assertEqual(t["brand"], "BILLING PORTAL")
        self.assertTrue(any("--primary" in s for s in sources))
        self.assertTrue(any("Inter" in s for s in sources))

    def test_tailwind_and_design_doc(self):
        self.put("tailwind.config.js", "module.exports = { theme: { extend: { colors: { brand: '#0F766E', "
                                       "surface: '#FAFAF7', ink: '#1F2937' }, fontFamily: { sans: ['Manrope', 'sans-serif'], "
                                       "mono: ['JetBrains Mono'] } } } }")
        self.put("docs/DESIGN.md", "# Design\nPrimary accent: brand #0F766E\n")
        t, sources, notes = self.ti.build_theme(self.repo)
        self.assertEqual(t["colors"]["seal"], "#0F766E")
        self.assertEqual(t["colors"]["paper"], self.ti.canvas_from("#FAFAF7"))
        self.assertEqual(t["colors"]["ink"], "#1F2937")
        self.assertTrue(any("DESIGN.md" in s for s in sources))
        self.assertTrue(any("Manrope" in s for s in sources))

    def test_dark_app_keeps_dark_ground_and_checks_contrast(self):
        self.put("app.css", ":root { --bg: #0B0F14; --text: #E6EDF3; --accent: #F59E0B; }")
        t, _, notes = self.ti.build_theme(self.repo)
        self.assertEqual(t["colors"]["paper"], self.ti.canvas_from("#0B0F14"))
        self.assertGreater(self.ti.luminance(t["colors"]["paper"]), self.ti.luminance("#0B0F14"))
        self.assertEqual(t["colors"]["seal_text"], "#111111")          # dark text on amber reads better
        self.assertFalse(any("contrast" in n for n in notes))

    def test_title_brand_and_unnamed_palette(self):
        self.put("index.html", "<title>Invoices · Invoicer</title><style>body{background:#f9fafb;color:#111827}"
                               ".btn{background:#2563eb}.btn2{background:#2563eb}</style>")
        self.put("login.html", "<title>Sign in · Invoicer</title>")
        t, sources, _ = self.ti.build_theme(self.repo)
        self.assertEqual(t["brand"], "INVOICER")
        self.assertEqual(t["colors"]["seal"], "#2563EB")
        self.assertTrue(any("most used saturated" in s for s in sources))

    def test_empty_repo_says_so(self):
        t, sources, notes = self.ti.build_theme(self.repo)
        self.assertNotIn("colors", t)
        self.assertTrue(any("no design signals" in n for n in notes))

    def test_init_cli_writes_a_valid_theme_and_refuses_overwrite(self):
        import subprocess
        import sys
        self.put("styles.css", ":root { --primary: #7C3AED; --background: #FFFFFF; --foreground: #111111; }")
        out = self.repo / "theme.yaml"
        script = str(pathlib.Path(__file__).resolve().parent.parent / "scripts" / "theme.py")
        r = subprocess.run([sys.executable, script, "init", "--repo", str(self.repo), "--out", str(out)],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = out.read_text(encoding="utf-8")
        self.assertIn("# Sources:", text)
        self.assertEqual(theme.load_theme(str(out))["colors"]["seal"], "#7C3AED")
        r2 = subprocess.run([sys.executable, script, "init", "--repo", str(self.repo), "--out", str(out)],
                            capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(r2.returncode, 0)

class Srt(unittest.TestCase):
    def test_srt_format(self):
        s = overlay.srt([{"a": 1.5, "b": 62.25, "text": "Xin chào"}])
        self.assertIn("00:00:01,500 --> 00:01:02,250", s)
        self.assertIn("Xin chào", s)


if __name__ == "__main__":
    unittest.main()
