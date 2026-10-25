"""版本一致性测试：__init__、pyproject.toml 与 CHANGELOG.md 三处版本应一致。"""

import re
from pathlib import Path

import pytest

EXPECTED_VERSION = "2.17.16"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _version_from_init() -> str:
    init_py = PROJECT_ROOT / "src" / "ledger" / "__init__.py"
    content = init_py.read_text(encoding="utf-8")
    match = re.search(
        r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", content, re.MULTILINE
    )
    if match is None:
        pytest.fail(f"{init_py} 中未找到 __version__ 定义")
    return match.group(1)


def _version_from_pyproject() -> str:
    pyproject = PROJECT_ROOT / "pyproject.toml"
    try:
        import tomllib
    except ModuleNotFoundError:
        content = pyproject.read_text(encoding="utf-8")
        match = re.search(
            r"^\[project\].*?^version\s*=\s*['\"]([^'\"]+)['\"]",
            content,
            re.MULTILINE | re.DOTALL,
        )
        if match is None:
            pytest.fail(f"{pyproject} 中未找到 [project] version")
        return match.group(1)
    with pyproject.open("rb") as file:
        data = tomllib.load(file)
    return str(data["project"]["version"])


def _version_from_changelog() -> str:
    changelog = PROJECT_ROOT / "CHANGELOG.md"
    content = changelog.read_text(encoding="utf-8")
    match = re.search(r"^##\s+v(\d+\.\d+\.\d+)(?=\s|$)", content, re.MULTILINE)
    if match is None:
        pytest.fail(f"{changelog} 中未找到 ## vX.Y.Z 标题")
    return match.group(1)


def test_version_consistency_across_files() -> None:
    assert _version_from_init() == EXPECTED_VERSION
    assert _version_from_pyproject() == EXPECTED_VERSION
    assert _version_from_changelog() == EXPECTED_VERSION
