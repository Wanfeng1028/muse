from types import SimpleNamespace

from one_memory.imports.sources.common import rotate_history_files


def test_history_listing_alternates_started_and_untouched_files() -> None:
    files = [SimpleNamespace(safe_id=f"started-{index}", size=100) for index in range(10)] + [
        SimpleNamespace(safe_id=f"new-{index}", size=100) for index in range(10)
    ]
    cursors = {f"started-{index}": SimpleNamespace(checkpoint="byte:50") for index in range(10)}

    rotated = rotate_history_files(files, cursors)  # type: ignore[arg-type]

    assert [item.safe_id for item in rotated[:10]] == [
        "new-0",
        "started-0",
        "new-1",
        "started-1",
        "new-2",
        "started-2",
        "new-3",
        "started-3",
        "new-4",
        "started-4",
    ]


def test_history_listing_drains_whichever_cohort_is_longer() -> None:
    files = [SimpleNamespace(safe_id="started", size=100)] + [
        SimpleNamespace(safe_id=f"new-{index}", size=100) for index in range(3)
    ]

    rotated = rotate_history_files(files, {"started": SimpleNamespace(checkpoint="byte:50")})  # type: ignore[arg-type]

    assert [item.safe_id for item in rotated] == ["new-0", "started", "new-1", "new-2"]
