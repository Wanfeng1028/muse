"""R-29 剩余：Cursor 默认根路径不能写死成 macOS。

`registry._cursor_data_root` 已经按平台分了 darwin / win32 / XDG，但
`cursor.cursor_default_root` 仍硬返回
`~/Library/Application Support/Cursor/User`。这条路径在 Windows 上不存在，
谁调用它都会得到一个永远 detect 失败的根。

两处必须是同一份意见：fallback 逻辑只许有一份。
"""

from pathlib import Path

from one_memory.imports.sources.cursor import cursor_default_root
from one_memory.imports.sources.registry import _cursor_data_root


def test_cursor_default_root_on_windows_uses_appdata(tmp_path: Path) -> None:
    home = tmp_path / "home"
    app_data = tmp_path / "Roaming"

    assert (
        cursor_default_root(
            home,
            platform="win32",
            environment={"APPDATA": str(app_data)},
        )
        == app_data / "Cursor" / "User"
    )


def test_cursor_default_root_on_windows_falls_back_when_appdata_is_missing(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"

    assert (
        cursor_default_root(
            home,
            platform="win32",
            environment={},
        )
        == home / "AppData" / "Roaming" / "Cursor" / "User"
    )


def test_cursor_default_root_on_linux_uses_xdg(tmp_path: Path) -> None:
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"

    assert (
        cursor_default_root(
            home,
            platform="linux",
            environment={"XDG_CONFIG_HOME": str(xdg)},
        )
        == xdg / "Cursor" / "User"
    )


def test_cursor_default_root_on_darwin_keeps_the_library_path(tmp_path: Path) -> None:
    """绿对照：macOS 行为不许被顺手改掉。"""
    home = tmp_path / "home"

    assert cursor_default_root(home, platform="darwin", environment={}) == (
        home / "Library" / "Application Support" / "Cursor" / "User"
    )


def test_registry_fallback_and_cursor_default_root_are_the_same_opinion(
    tmp_path: Path,
) -> None:
    """两处曾各写一份；漂移过一次就会再漂。

    `~/.cursor` 不存在时，registry 的 fallback 必须就是 cursor_default_root
    给出的那条路径 —— 否则 Windows 上 catalog 指向一处、别处读另一处。
    """
    home = tmp_path / "home"
    app_data = tmp_path / "Roaming"
    environment = {"APPDATA": str(app_data)}

    from_registry = _cursor_data_root(
        home=home,
        environment=environment,
        platform="win32",
    )
    from_cursor = cursor_default_root(
        home,
        platform="win32",
        environment=environment,
    )
    assert from_registry == from_cursor
