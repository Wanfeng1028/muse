"""A shared directory is not a read grant."""

from one_memory.subscription_visibility import visible_update


def test_same_directory_does_not_reveal_an_unauthorized_source() -> None:
    result = visible_update(
        granted_sources=("cursor",),
        event_source="workbuddy",
        same_workspace=True,
        title="SECRET_DECISION",
    )
    assert result.visible is False
    assert result.title is None


def test_an_authorized_source_stays_visible() -> None:
    result = visible_update(
        granted_sources=("workbuddy",),
        event_source="workbuddy",
        same_workspace=False,
        title="kept",
    )
    assert result.visible is True
    assert result.title == "kept"
