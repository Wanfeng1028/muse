#!/usr/bin/env python3

import argparse
import re
import tempfile
from pathlib import Path


SOURCE_ROOTS = ("apps", "packages", "plugins")
SOURCE_SUFFIXES = {".cjs", ".js", ".jsx", ".m", ".mjs", ".mm", ".py", ".ts", ".tsx"}
IGNORED_DIRECTORY_NAMES = {
    ".venv",
    "build",
    "dist",
    "node_modules",
    "release",
    "release-preview",
    "__pycache__",
}
ARTIFACT_ROOTS = (
    "apps/web/dist",
    "apps/desktop/release",
    "apps/desktop/release-preview",
)
SCANNABLE_ARTIFACT_SUFFIXES = {
    ".asar",
    ".cjs",
    ".css",
    ".html",
    ".js",
    ".json",
    ".mjs",
    ".plist",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
FORBIDDEN_PATH_PARTS = (
    "collector",
    "screen-recorder",
    "screen_recorder",
    "screen-capture",
    "screen_capture",
    "visionocr",
    "observer",
    "activity-tracker",
    "ax-tree",
    "axtree",
)
# These reviewed files only query SMAppService eligibility. Exempt their names
# from the observer rule, never other path rules or source-content scanning.
SERVICE_STATUS_OBSERVER_PATHS = frozenset({
    "packages/runtime-control/native/service-observer.m",
    "packages/runtime-control/src/system-service-observer.ts",
    "packages/runtime-control/src/system-service-observer.test.ts",
})
FORBIDDEN_SOURCE = {
    "electron screen capture": re.compile(r"\bdesktopCapturer\b"),
    "macOS screen capture": re.compile(
        r"\bSCStream\b|\bSCShareableContent\b|\bCGWindowListCreateImage\b"
        r"|screencapture\s+-",
    ),
    "accessibility tree": re.compile(
        r"\bAXUIElement\b|\bAXTree\b|\bAXObserver\b|\bkAX[A-Z]"
    ),
    "OCR engine": re.compile(
        r"\b(VisionOCR|tesseract|pytesseract|easyocr)\b",
        re.IGNORECASE,
    ),
    "keyboard listener": re.compile(
        r"\b(global-key-listener|iohook|uiohook|CGEventTap|pynput)\b",
        re.IGNORECASE,
    ),
    "background audio capture": re.compile(
        r"\b(getUserMedia|MediaRecorder|AVAudioEngine|AudioQueueNewInput)\b"
    ),
    "clipboard capture": re.compile(
        r"\bNSPasteboard\b|\bclipboard\.(read|readText)\b"
        r"|\bnavigator\.clipboard\.read"
    ),
    "window activity capture": re.compile(
        r"\bCGWindowListCopyWindowInfo\b"
        r"|\bNSWorkspaceDidActivateApplicationNotification\b"
        r"|\bgetActiveWindow\b"
    ),
}
FORBIDDEN_DEPENDENCIES = {
    "active-win",
    "clipboard-event",
    "easyocr",
    "iohook",
    "node-global-key-listener",
    "pynput",
    "pytesseract",
    "screenshot-desktop",
    "tesseract.js",
    "uiohook-napi",
}
FORBIDDEN_IMPORT_IMPLEMENTATION = {
    "implicit real home access": re.compile(r"\bPath\.home\(\)"),
    "unbounded recursive glob": re.compile(r"\.rglob\("),
    "conversation body logging": re.compile(
        r"\b(print|logger\.\w+|logging\.\w+)\s*\([^)]*\b"
        r"(verbatim|content|message|raw_meta)\b",
        re.IGNORECASE,
    ),
}
FORBIDDEN_PERMISSIONS = {
    "camera permission": re.compile(r"NSCameraUsageDescription|device\.camera"),
    "microphone permission": re.compile(r"NSMicrophoneUsageDescription|device\.audio-input"),
    "screen permission": re.compile(
        r"CGPreflightScreenCaptureAccess|CGRequestScreenCaptureAccess"
    ),
    "accessibility permission": re.compile(r"AXIsProcessTrusted|uiAccess"),
}


def scan(root: Path) -> list[str]:
    failures: list[str] = []
    for source_root in SOURCE_ROOTS:
        directory = root / source_root
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            relative = path.relative_to(root)
            if any(part in IGNORED_DIRECTORY_NAMES for part in relative.parts):
                continue
            normalized = relative.as_posix().lower()
            if any(
                part in normalized
                and not (
                    part == "observer"
                    and relative.as_posix() in SERVICE_STATUS_OBSERVER_PATHS
                )
                for part in FORBIDDEN_PATH_PARTS
            ):
                failures.append(f"forbidden path: {relative}")
            if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            for label, pattern in FORBIDDEN_SOURCE.items():
                if pattern.search(content):
                    failures.append(f"{label}: {relative}")
            if relative.as_posix().startswith("apps/core/src/one_memory/imports/"):
                for label, pattern in FORBIDDEN_IMPORT_IMPLEMENTATION.items():
                    if pattern.search(content):
                        failures.append(f"{label}: {relative}")

    for manifest in root.rglob("package.json"):
        if "node_modules" in manifest.parts:
            continue
        content = manifest.read_text(encoding="utf-8").lower()
        for dependency in FORBIDDEN_DEPENDENCIES:
            if f'"{dependency.lower()}"' in content:
                failures.append(f"forbidden dependency {dependency}: {manifest.relative_to(root)}")
    for manifest_name in ("pyproject.toml", "uv.lock"):
        for manifest in root.rglob(manifest_name):
            if any(part in IGNORED_DIRECTORY_NAMES for part in manifest.parts):
                continue
            content = manifest.read_text(encoding="utf-8", errors="replace").lower()
            for dependency in FORBIDDEN_DEPENDENCIES:
                if re.search(rf"(?<![a-z0-9_-]){re.escape(dependency)}(?![a-z0-9_-])", content):
                    failures.append(
                        f"forbidden dependency {dependency}: {manifest.relative_to(root)}"
                    )
    return sorted(set(failures))


def scan_permissions(root: Path) -> list[str]:
    failures: list[str] = []
    desktop = root / "apps" / "desktop"
    for path in desktop.rglob("*"):
        if not path.is_file() or any(
            part in IGNORED_DIRECTORY_NAMES for part in path.relative_to(root).parts
        ):
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in FORBIDDEN_PERMISSIONS.items():
            if pattern.search(content):
                failures.append(f"{label}: {path.relative_to(root)}")
    return sorted(set(failures))


def scan_artifacts(root: Path) -> list[str]:
    failures: list[str] = []
    scanned_files = 0
    patterns = {**FORBIDDEN_SOURCE, **FORBIDDEN_PERMISSIONS}
    for relative_root in ARTIFACT_ROOTS:
        directory = root / relative_root
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if (
                not path.is_file()
                or path.suffix.lower() not in SCANNABLE_ARTIFACT_SUFFIXES
            ):
                continue
            scanned_files += 1
            normalized = path.relative_to(root).as_posix().lower()
            if any(part in normalized for part in FORBIDDEN_PATH_PARTS):
                failures.append(f"forbidden artifact path: {path.relative_to(root)}")
            content = path.read_text(encoding="utf-8", errors="replace")
            for label, pattern in patterns.items():
                if pattern.search(content):
                    failures.append(f"{label} in artifact: {path.relative_to(root)}")
    if scanned_files == 0:
        failures.append("artifact coverage: no build artifact files were scanned")
    return sorted(set(failures))


def self_test() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "apps" / "desktop"
        source.mkdir(parents=True)
        safe_file = source / "main.ts"
        safe_file.write_text("export const safe = true\n", encoding="utf-8")
        if scan(root):
            raise AssertionError("safe fixture failed")

        safe_file.write_text("desktopCapturer.getSources({})\n", encoding="utf-8")
        if not scan(root):
            raise AssertionError("source mutation did not fail")

        safe_file.write_text("export const safe = true\n", encoding="utf-8")
        (source / "package.json").write_text(
            '{"dependencies":{"screenshot-desktop":"1.0.0"}}',
            encoding="utf-8",
        )
        if not scan(root):
            raise AssertionError("dependency mutation did not fail")

        (source / "package.json").unlink()
        core_import = root / "apps" / "core" / "src" / "one_memory" / "imports"
        core_import.mkdir(parents=True)
        unsafe_import = core_import / "source.py"
        unsafe_import.write_text("for path in Path.home().rglob('*'): pass\n")
        if not scan(root):
            raise AssertionError("implicit home scan mutation did not fail")
        unsafe_import.unlink()

        (root / "pyproject.toml").write_text(
            'dependencies = ["pynput"]\n',
            encoding="utf-8",
        )
        if not scan(root):
            raise AssertionError("Python dependency mutation did not fail")
        (root / "pyproject.toml").unlink()

        permission_file = source / "entitlements.plist"
        permission_file.write_text(
            "<key>NSMicrophoneUsageDescription</key>",
            encoding="utf-8",
        )
        if not scan_permissions(root):
            raise AssertionError("permission mutation did not fail")

        permission_file.unlink()
        artifact = source / "dist" / "main.js"
        artifact.parent.mkdir()
        artifact.write_text("desktopCapturer.getSources({})\n", encoding="utf-8")
        if not scan_artifacts(root):
            raise AssertionError("artifact mutation did not fail")

        preview = source / "release-preview" / "mac-arm64" / "Preview.app" / "Contents"
        bundle = preview / "Resources" / "web" / "index.js"
        bundle.parent.mkdir(parents=True)
        bundle.write_text("desktopCapturer.getSources({})\n", encoding="utf-8")
        if not any("electron screen capture in artifact" in failure
                   and "release-preview" in failure for failure in scan_artifacts(root)):
            raise AssertionError("preview artifact mutation was not scanned")
        bundle.write_text("export const safe = true\n", encoding="utf-8")
        framework = preview / "Frameworks" / "Electron Framework"
        framework.parent.mkdir()
        framework.write_bytes(b"\x00CGRequestScreenCaptureAccess\x00")
        # Electron contains OS integration symbols; the source gate must not
        # mistake its binary for application code. JS and plist remain scanned.
        if scan_permissions(root):
            raise AssertionError("preview runtime binary treated as application source")
        permission = preview / "Info.plist"
        permission.write_text("<key>NSCameraUsageDescription</key>", encoding="utf-8")
        if not any("camera permission in artifact" in failure
                   and "release-preview" in failure for failure in scan_artifacts(root)):
            raise AssertionError("preview permission mutation was not scanned")

    print("zero-collection mutation tests passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--artifacts", action="store_true")
    arguments = parser.parse_args()
    if arguments.self_test:
        self_test()
        return

    root = Path(__file__).resolve().parents[1]
    failures = scan_artifacts(root) if arguments.artifacts else scan(root) + scan_permissions(root)
    if failures:
        for failure in failures:
            print(failure)
        raise SystemExit(1)
    layer = "artifact" if arguments.artifacts else "source/package/permission"
    print(f"zero-collection {layer} gate passed")


if __name__ == "__main__":
    main()
