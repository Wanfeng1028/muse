#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import verify_zero_collection as gate


APPROVED_PATHS = (
    "packages/runtime-control/native/service-observer.m",
    "packages/runtime-control/src/system-service-observer.ts",
    "packages/runtime-control/src/system-service-observer.test.ts",
)


class ServiceStatusGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_actual_approved_status_sources_pass(self):
        product = Path(__file__).resolve().parents[1]
        for relative in APPROVED_PATHS:
            self.write(relative, (product / relative).read_text(encoding="utf-8"))
        self.assertEqual(gate.scan(self.root), [])

    def test_exact_native_path_still_scans_ax_and_screen_capture(self):
        relative = APPROVED_PATHS[0]
        for content, label in (
            ("AXUIElement *element;", "accessibility tree"),
            ("AXObserver *observer;", "accessibility tree"),
            ("SCStream *stream;", "macOS screen capture"),
            ("CGWindowListCreateImage();", "macOS screen capture"),
        ):
            with self.subTest(content=content):
                self.write(relative, content)
                self.assertEqual(gate.scan(self.root), [f"{label}: {relative}"])

    def test_all_approved_paths_retain_source_content_checks(self):
        for relative in APPROVED_PATHS:
            with self.subTest(relative=relative):
                self.write(relative, "desktopCapturer.getSources({});")
                self.assertIn(
                    f"electron screen capture: {relative}", gate.scan(self.root)
                )
                self.write(relative, "// safe status helper")

    def test_native_m_and_mm_are_scanned_without_observer_names(self):
        for suffix in (".m", ".mm"):
            relative = f"packages/runtime-control/native/status{suffix}"
            with self.subTest(suffix=suffix):
                self.write(relative, "SCShareableContent *content;")
                self.assertIn(
                    f"macOS screen capture: {relative}", gate.scan(self.root)
                )

    def test_similar_observer_paths_are_not_exempt(self):
        for relative in (
            "packages/runtime-control/native/service-observer.mm",
            "packages/runtime-control/native/service-observer-copy.m",
            "packages/runtime-control/src/system-service-observer-extra.ts",
            "packages/other/src/system-service-observer.ts",
            "packages/runtime-control/src/System-Service-Observer.ts",
            "packages/runtime-control/src/nested/system-service-observer.ts",
        ):
            with self.subTest(relative=relative):
                self.write(relative, "// status only")
                self.assertIn(f"forbidden path: {relative}", gate.scan(self.root))

    def test_arbitrary_collector_remains_forbidden(self):
        relative = "packages/runtime-control/src/collector.ts"
        self.write(relative, "export const safe = true;")
        self.assertEqual(gate.scan(self.root), [f"forbidden path: {relative}"])

    def test_exemption_only_suppresses_observer_rule(self):
        relative = APPROVED_PATHS[0]
        self.write(relative, "// status only")
        with patch.object(
            gate, "FORBIDDEN_PATH_PARTS", (*gate.FORBIDDEN_PATH_PARTS, "service-")
        ):
            self.assertEqual(gate.scan(self.root), [f"forbidden path: {relative}"])


if __name__ == "__main__":
    unittest.main()
