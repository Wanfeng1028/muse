"""Keep the public environment template aligned with runtime configuration."""

import ast
import base64
from collections import Counter
from pathlib import Path
import re
import warnings


ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"
ENV_REFERENCE = ROOT / "docs" / "env_reference.md"
RUNTIME_ROOT = ROOT / "hy_memory"


def _example_variables():
    pattern = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]+)\s*=", re.MULTILINE)
    return pattern.findall(ENV_EXAMPLE.read_text(encoding="utf-8"))


def _runtime_string_literals():
    """Collect executable string literals while ignoring Python docstrings."""
    values = set()

    class Visitor(ast.NodeVisitor):
        @staticmethod
        def _body_without_docstring(node):
            body = list(getattr(node, "body", []))
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                return body[1:]
            return body

        def _visit_scoped(self, node):
            for child in self._body_without_docstring(node):
                self.visit(child)

        def visit_Module(self, node):
            self._visit_scoped(node)

        def visit_ClassDef(self, node):
            self._visit_scoped(node)

        def visit_FunctionDef(self, node):
            self._visit_scoped(node)

        def visit_AsyncFunctionDef(self, node):
            self._visit_scoped(node)

        def visit_Constant(self, node):
            if isinstance(node.value, str):
                values.add(node.value)

    for path in RUNTIME_ROOT.rglob("*.py"):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        Visitor().visit(tree)
    return values


def test_env_example_has_no_duplicate_variables():
    counts = Counter(_example_variables())
    assert {name: count for name, count in counts.items() if count > 1} == {}


def test_every_example_variable_is_read_by_runtime_code():
    literals = _runtime_string_literals()
    missing = [name for name in _example_variables() if name not in literals]
    assert missing == []


def test_every_example_variable_is_documented_in_env_reference():
    reference = ENV_REFERENCE.read_text(encoding="utf-8")
    missing = [name for name in _example_variables() if name not in reference]
    assert missing == []


def test_removed_environment_variables_do_not_return():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    removed = {
        "MEMORY_CODING_WRITER_KIND",
        "MEMORY_ENABLE_SUMMARY",
        "MEMORY_SUMMARY_BUFFER_WINDOW",
        "MEMORY_READER_ENABLE_SUMMARY",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_PASSWORD",
    }
    assert [name for name in sorted(removed) if name in text] == []


def test_core_public_controls_are_documented():
    variables = set(_example_variables())
    required = {
        "MEMORY_EVOLING_SPECIFIC_SUPPLEMENT_ENABLED",
        "MEMORY_LOCAL_RERANK_ENABLED",
        "MEMORY_LOCAL_RERANK_MODEL",
        "MEMORY_CODING_VERBATIM_FALLBACK_ENABLED",
        "MEMORY_EXTRACT_HISTORY_TURNS",
        "MEMORY_MYSQL_HOST",
        "MEMORY_MYSQL_DATABASE",
    }
    assert required <= variables


def test_cache_backend_description_matches_supported_backends():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    line = next(
        value for value in text.splitlines()
        if "MEMORY_CACHE_BACKEND=" in value
    )
    assert "sqlite" in line and "mysql" in line
    assert "redis" not in line.lower()


def test_removed_vendor_modules_are_absent():
    encoded_paths = [
        "aHlfbWVtb3J5L2RhdGEvdmVjdG9yX3N0b3JlX3RlbmNlbnQucHk=",
        "aHlfbWVtb3J5L3BpcGVsaW5lcy9fcmV0cmlldmFsL2JtMjVfc3BhcnNlLnB5",
        "c2NyaXB0cy9jaGVja190ZW5jZW50X2NvbXBhdC5weQ==",
        "dGVzdHMvdGVzdF90ZW5jZW50X2Z1bGx0ZXh0LnB5",
    ]
    removed = [ROOT / base64.b64decode(value).decode() for value in encoded_paths]
    assert [str(path.relative_to(ROOT)) for path in removed if path.exists()] == []


def test_removed_vendor_markers_are_absent():
    encoded_markers = [
        "dGN2ZWN0b3JkYg==",
        "dGN2ZGJfdGV4dA==",
        "bWVtb3J5X3RlbmNlbnRfdmRi",
        "dmVjdG9yX3N0b3JlX3RlbmNlbnQ=",
        "dGVuY2VudHZlY3RvcnN0b3Jl",
        "dGVuY2VudCBjbG91ZCB2ZWN0b3JkYg==",
        "6IW+6K6v5LqR5ZCR6YeP5pWw5o2u5bqT",
        "dGVuY2VudCBjbG91ZCBteXNxbA==",
        "6IW+6K6v5LqRIG15c3Fs",
        "dHVyYm90a2U=",
        "dGtleA==",
        "dGtleF9jcHU=",
        "b3BlbmFpX2luZmVy",
        "cXdlbjMtZW1iZWRkaW5n",
        "LWZvci1vbmxpbmU=",
    ]
    markers = [base64.b64decode(value).decode().lower() for value in encoded_markers]
    roots = [ROOT / "hy_memory", ROOT / "docs", ROOT / "scripts", ROOT / "tests"]
    files = [ROOT / "pyproject.toml", ROOT / ".env.example"]
    for base in roots:
        files.extend(path for path in base.rglob("*") if path.is_file())

    violations = []
    for path in files:
        if path.suffix in {".pyc", ".whl"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for marker in markers:
            if marker in text:
                violations.append((str(path.relative_to(ROOT)), marker))
    assert violations == []
