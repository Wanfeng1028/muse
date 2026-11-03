"""探测码在三处必须同时存在：python 枚举、TS 契约、界面文案表。

起因：新增 ProbeCode.MODEL_LIST_UNSUPPORTED 时只改了 python，
TS 契约的联合类型和 ModelSettings 的 probeLabel 表都没同步。
TS 那个联合类型是手写的，缺一个成员不会让构建失败；
probeLabel 用的是 Record<ProbeCode, string>，查不到就返回 undefined，
于是界面上那一栏渲染成空白 —— 看起来像坏了，但没有任何测试会红。
这个文件就是补上那道守卫。
"""

import re
from pathlib import Path

from one_memory.model_probe import ProbeCode

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "packages" / "contracts" / "src" / "index.ts"
MODEL_SETTINGS = REPO_ROOT / "apps" / "web" / "src" / "ModelSettings.tsx"


def _typescript_union_members() -> set[str]:
    source = CONTRACT.read_text(encoding="utf-8")
    match = re.search(r"export type ProbeCode =(.*?);", source, re.DOTALL)
    assert match, f"没在 {CONTRACT} 里找到 ProbeCode 联合类型"
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


def _probe_label_keys() -> set[str]:
    source = MODEL_SETTINGS.read_text(encoding="utf-8")
    match = re.search(
        r"const labels: Record<ProbeCode, string> = \{(.*?)\};",
        source,
        re.DOTALL,
    )
    assert match, f"没在 {MODEL_SETTINGS} 里找到 probeLabel 的文案表"
    return set(re.findall(r"^\s*([a-z_]+):", match.group(1), re.MULTILINE))


def test_every_probe_code_exists_in_the_typescript_contract() -> None:
    python_codes = {code.value for code in ProbeCode}
    missing = python_codes - _typescript_union_members()
    assert not missing, (
        f"这些探测码只有 python 有、TS 契约没有：{sorted(missing)}。"
        f"请同步 {CONTRACT.relative_to(REPO_ROOT)} 的 ProbeCode 联合类型。"
    )


def test_every_probe_code_has_a_label_in_the_settings_ui() -> None:
    python_codes = {code.value for code in ProbeCode}
    missing = python_codes - _probe_label_keys()
    assert not missing, (
        f"这些探测码在界面文案表里没有对应文案：{sorted(missing)}。"
        f"缺文案时 probeLabel 返回 undefined，界面会渲染成空白。"
        f"请补 {MODEL_SETTINGS.relative_to(REPO_ROOT)} 的 probeLabel。"
    )


def test_the_contract_does_not_carry_codes_python_no_longer_emits() -> None:
    """反向对照：TS 侧不该留着 python 已经删掉的码。

    没有这条，前两条可以被「往 TS 和文案表里塞一堆用不到的码」骗过。
    """
    python_codes = {code.value for code in ProbeCode}
    stale = _typescript_union_members() - python_codes
    assert not stale, f"TS 契约里有 python 不再产出的码：{sorted(stale)}"
