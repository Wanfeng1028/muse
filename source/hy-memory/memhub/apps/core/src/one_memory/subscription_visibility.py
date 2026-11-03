"""Whether a session may hear about another source's update."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VisibleUpdate:
    visible: bool
    title: str | None


def visible_update(
    *,
    granted_sources: tuple[str, ...],
    event_source: str,
    same_workspace: bool,
    title: str,
) -> VisibleUpdate:
    # A shared directory is only a relevance hint. It never reveals a source
    # the subscriber is not allowed to read, including that source's title.
    if event_source not in granted_sources:
        return VisibleUpdate(False, None)
    return VisibleUpdate(True, title)
