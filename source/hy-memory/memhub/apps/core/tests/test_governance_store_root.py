"""生产代码里治理 store 只在 Core 启动的组合根建一次。

「人工写入口只能领一次」按 store 实例计；同一份库再建一个 store，就又能领一次。
所以别处要用治理 store，只能由启动时注入。扫描看不见运行时拼出的构造（getattr 之类），
这是补充，不是唯一防线。
"""

import ast
from pathlib import Path

import pytest

import one_memory

SOURCE = Path(one_memory.__file__).parent
CLASS = "MemoryGovernanceStore"
ROOT = ("api.py", "create_app.lifespan")


class _Scanner(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names = {CLASS}
        self.found: list[tuple[str, int]] = []
        self._scope: list[str] = []

    def _enter(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    visit_ClassDef = visit_FunctionDef = visit_AsyncFunctionDef = _enter

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (isinstance(func, ast.Name) and func.id in self.names) or (
            isinstance(func, ast.Attribute) and func.attr == CLASS
        ):
            self.found.append((".".join(self._scope) or "<module>", node.lineno))
        self.generic_visit(node)


def _constructions(text: str) -> list[tuple[str, int]]:
    tree = ast.parse(text)
    scanner = _Scanner()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            scanner.names.update(
                alias.asname for alias in node.names if alias.name == CLASS and alias.asname
            )
    scanner.visit(tree)
    return scanner.found


CONSTRUCTIONS = {
    "direct": "def f(p): MemoryGovernanceStore(p)\n",
    "through the module": (
        "from one_memory import memory_governance\n"
        "class A:\n    def f(self, p): memory_governance.MemoryGovernanceStore(p)\n"
    ),
    "renamed": (
        "from one_memory.memory_governance import MemoryGovernanceStore as G\ndef f(p): G(p)\n"
    ),
    "as an argument": "def f(p): run(governance=MemoryGovernanceStore(p))\n",
}


@pytest.mark.parametrize("sample", sorted(CONSTRUCTIONS))
def test_the_scan_sees_a_store_being_built(sample):
    assert _constructions(CONSTRUCTIONS[sample]) != []


def test_using_the_store_is_not_building_one():
    source = (
        "def f(db, rows, store: 'MemoryGovernanceStore') -> MemoryGovernanceStore:\n"
        "    isinstance(store, MemoryGovernanceStore)\n"
        "    return MemoryGovernanceStore.memories_from_rows(db, rows)\n"
    )
    assert _constructions(source) == []


def test_only_the_composition_root_builds_a_governance_store():
    built = [
        (path.relative_to(SOURCE).as_posix(), scope, line)
        for path in sorted(SOURCE.rglob("*.py"))
        for scope, line in _constructions(path.read_text(encoding="utf-8"))
    ]
    # 基数非零：组合根那一处扫得到，扫描本身在工作。
    assert [(file, scope) for file, scope, _ in built].count(ROOT) == 1
    assert [
        f"{file}:{line} in {scope}" for file, scope, line in built if (file, scope) != ROOT
    ] == []


SCRIPTS = SOURCE.parents[3] / "scripts"


def _discoveries_without_a_store(text: str) -> list[int]:
    """Lines building a MatterDiscovery with neither a processor nor a governance store."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", "")) == "MatterDiscovery"
        and len(node.args) < 3
        and not {"processor", "governance"} & {keyword.arg for keyword in node.keywords}
    ]


def test_the_discovery_scan_sees_a_discovery_left_to_build_its_own_store():
    source = (
        "a = MatterDiscovery(store, model)\n"
        "b = MatterDiscovery(store, model, processor)\n"
        "c = discovery.MatterDiscovery(store, model, governance=g)\n"
        "d = MatterDiscovery(store, model, importer=i)\n"
    )
    assert _discoveries_without_a_store(source) == [1, 4]


def test_every_matter_discovery_is_given_a_store():
    files = [*sorted(SOURCE.rglob("*.py")), *sorted(SCRIPTS.glob("*.py"))]
    scanned = [
        (path, _discoveries_without_a_store(path.read_text(encoding="utf-8")))
        for path in files
        if "MatterDiscovery(" in path.read_text(encoding="utf-8")
    ]
    # 基数非零：组合根和两个基线脚本都在扫描范围里。
    assert len(scanned) >= 3
    assert [f"{path.name}:{lines}" for path, lines in scanned if lines] == []


def test_matter_discovery_is_handed_the_store_rather_than_building_one():
    from one_memory.matters.discovery import MatterDiscovery

    with pytest.raises(ValueError, match="matter_discovery_needs_governance"):
        MatterDiscovery(object(), object())  # type: ignore[arg-type]
