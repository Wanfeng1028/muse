"""月度报告导出 HTML 的移动端适配存在性测试。

如实说明：导出 HTML 由浏览器端 JS 函数 buildExportHtml() 拼接生成，
服务端没有渲染入口，因此本文件做模板文件的静态存在性断言
（与 tests/test_mobile.py 的"断点 CSS 存在性冒烟"同类）。
"""

from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "ledger"
    / "templates"
    / "report.html"
)


def _export_region():
    text = TEMPLATE.read_text(encoding="utf-8")
    start = text.index("function buildExportHtml")
    end = text.index("exportBtn.addEventListener")
    return text[start:end]


def test_export_has_viewport_meta():
    region = _export_region()
    assert (
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        in region
    ), "导出的自包含 HTML 缺少 viewport meta，移动端会按桌面宽度缩放"


def test_export_has_mobile_breakpoint():
    region = _export_region()
    assert "@media (max-width:768px)" in region, "导出 CSS 缺少 768px 移动端断点"


def test_export_mobile_rules_cover_key_layouts():
    region = _export_region()
    assert ".summary{flex-wrap:wrap" in region, "汇总卡在窄屏下不会换行"
    assert "overflow-x:auto" in region, "表格在窄屏下没有横向滚动兜底"
