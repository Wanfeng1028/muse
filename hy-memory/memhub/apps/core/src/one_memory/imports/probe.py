"""Describe the shape of an export without handing over what is inside it.

Every source adapter in this repository was written by reading a real file
from a real machine. That is the only way to get the format right, and it is
also the reason the archives keep having to change hands: to write a parser
for a chat export, someone has to send us their chat export.

This module is the way out of that trade. It walks a decoded export and
reports what is there -- key names, nesting, types, how many of each, and the
exact spelling of small enumerations like ``role`` -- while never emitting a
message body. The output is meant to be pasted into a chat by the person
holding the file, who then keeps the file.

The line it draws:

* **Structure goes out.** Key names, paths, types, counts, list lengths.
  A parser cannot be written without them and none of them is about a person.
* **Content stays.** Message text, titles, anything free-form.
* **Small enumerations count as structure.** ``user`` / ``assistant`` /
  ``system`` decides whose sentence a memory gets attributed to; getting the
  spelling wrong misfiles every memory in the import. Three short values that
  repeat across a whole file are a vocabulary, not someone's writing.

The enumeration rule is deliberately about behaviour across the file rather
than appearance in one record. Titles are short and look enumerable in the
first three rows; across thirty they are obviously content. Judging by
looking is how a redactor leaks.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: A field with no more than this many distinct values, all of them short, is
#: a vocabulary rather than someone's words.
MAX_ENUM_VALUES = 8

#: Above this length a value is prose regardless of how rarely it varies.
MAX_ENUM_LENGTH = 32

#: A mapping with more keys than this is being used as a dictionary keyed by
#: id, not as a record with named fields. Its keys are data; they collapse to
#: ``{}`` so the report stays about the shape.
MAX_LITERAL_KEYS = 12

#: Short names are field names. An identifier long enough to be unique across
#: someone's whole history is not.
MIN_ID_LENGTH = 8

#: A vocabulary proves itself by repeating. Below this many sightings of a
#: field there is no evidence either way, and guessing costs a leak.
MIN_ENUM_OCCURRENCES = 4

#: And each value has to appear more than once on average. Without this, a
#: four-message sample of four different short sentences reads as a
#: four-value enumeration and the whole sample goes out in the report.
MAX_ENUM_VALUE_RATIO = 2

#: Report at most this many values for an enumeration, in case the threshold
#: is ever raised without this being revisited.
MAX_REPORTED_VALUES = 8


@dataclass
class PathFacts:
    """What was seen at one place in the structure, across the whole file."""

    types: set[str] = field(default_factory=set)
    occurrences: int = 0
    #: Collected until the enum threshold is passed, then abandoned: past that
    #: point the values are content and there is no reason to hold them.
    values: set[str] | None = field(default_factory=set)
    longest_value: int = 0
    list_lengths: list[int] = field(default_factory=list)
    #: Sizes of the id-keyed maps seen here. How many messages hang off a
    #: conversation decides the import's batching, and it is not in a schema.
    map_sizes: list[int] = field(default_factory=list)

    def note_map(self, size: int) -> None:
        self.map_sizes.append(size)

    def note_string(self, value: str) -> None:
        self.longest_value = max(self.longest_value, len(value))
        if self.values is None:
            return
        if len(value) > MAX_ENUM_LENGTH:
            self.values = None
            return
        self.values.add(value)
        if len(self.values) > MAX_ENUM_VALUES:
            self.values = None

    @property
    def enumeration(self) -> list[str] | None:
        """The values, if this field has proven itself to be a vocabulary.

        Three tests, and the first two are what stop a leak:

        1. Seen enough times that repetition means something. A field
           encountered once or twice tells us nothing about whether its value
           is a label or a sentence, and a short sentence is short.
        2. Repeating. Distinct values have to be outnumbered by sightings,
           or every field in a four-message sample looks like a four-value
           enumeration -- which is to say, the sample goes out verbatim.

        Length is not tested here. It is enforced earlier, in `note_string`,
        which drops the whole value set the moment a long value arrives; by
        the time this runs, `self.values` is already `None`. A second length
        test was written here and removed after mutation showed it could not
        be made to fail. Dropping early is the better of the two places
        anyway: the long text is never held in memory at all.
        """
        if self.values is None or not self.values:
            return None
        if self.occurrences < MIN_ENUM_OCCURRENCES:
            return None
        if len(self.values) * MAX_ENUM_VALUE_RATIO > self.occurrences:
            return None
        return sorted(self.values)[:MAX_REPORTED_VALUES]


def describe_json(value: Any) -> dict[str, PathFacts]:
    """Walk a decoded export and collect facts per path.

    Two passes are not needed: the enum decision is made from facts that
    accumulate as the walk proceeds, and a field only ever loses its
    enumeration status, never regains it.
    """
    facts: dict[str, PathFacts] = defaultdict(PathFacts)
    _walk(value, "$", facts)
    return dict(facts)


def _walk(value: Any, path: str, facts: dict[str, PathFacts]) -> None:
    here = facts[path]
    here.occurrences += 1

    if value is None:
        here.types.add("null")
        return
    if isinstance(value, bool):
        here.types.add("bool")
        return
    if isinstance(value, int):
        here.types.add("int")
        return
    if isinstance(value, float):
        here.types.add("float")
        return
    if isinstance(value, str):
        here.types.add("str")
        here.note_string(value)
        return
    if isinstance(value, list):
        here.types.add("list")
        here.list_lengths.append(len(value))
        for item in value:
            _walk(item, f"{path}[]", facts)
        return
    if isinstance(value, dict):
        here.types.add("object")
        collapse = _is_keyed_by_id(value.keys())
        if collapse:
            here.note_map(len(value))
        for key, item in value.items():
            _walk(item, f"{path}.{'{}' if collapse else key}", facts)
        return
    here.types.add(type(value).__name__)


def _is_keyed_by_id(keys: Any) -> bool:
    """Is this a dictionary of records, rather than a record with fields?

    Judged over the whole dictionary at once, not key by key as the walk
    proceeds. Deciding incrementally produced the worst of both: the first
    dozen uuids went into the report as literal paths and only the remainder
    collapsed, so the output was both longer and leakier than either rule
    alone.

    Two signals, either sufficient:

    * More keys than any record has fields.
    * Keys that look like identifiers -- long, and carrying digits or hex.
      This catches the common case of a map with only a handful of entries,
      which a count alone cannot distinguish from a wide record.
    """
    names = list(keys)
    if len(names) > MAX_LITERAL_KEYS:
        return True
    if len(names) < 2:
        # One key is not a pattern. A literal name is more informative here
        # and, being a single value, is not the kind of bulk that matters.
        return False
    return sum(1 for name in names if _looks_like_id(name)) * 2 > len(names)


def _looks_like_id(name: str) -> bool:
    if len(name) < MIN_ID_LENGTH:
        return False
    if not any(character.isdigit() for character in name):
        return False
    return "-" in name or "_" in name or all(c in "0123456789abcdefABCDEF" for c in name)


def render_report(facts: dict[str, PathFacts]) -> str:
    """One line per path, ordered so the report reads like the file."""
    lines = ["path | type | seen | detail"]
    for path in sorted(facts):
        entry = facts[path]
        detail: list[str] = []
        if entry.list_lengths:
            low, high = min(entry.list_lengths), max(entry.list_lengths)
            detail.append(f"len {low}" if low == high else f"len {low}..{high}")
        if entry.map_sizes:
            low, high = min(entry.map_sizes), max(entry.map_sizes)
            detail.append(
                f"id-keyed, {low} entries" if low == high else f"id-keyed, {low}..{high} entries"
            )
        values = entry.enumeration
        if values is not None and "str" in entry.types:
            detail.append("values " + ", ".join(values))
        elif "str" in entry.types:
            # Length is shape: it separates an id from a paragraph, and it is
            # the one thing about the text that is safe to say.
            detail.append(f"free text, longest {entry.longest_value}")
        lines.append(
            f"{path} | {'/'.join(sorted(entry.types)) or '-'} | {entry.occurrences}"
            f" | {'; '.join(detail)}"
        )
    return "\n".join(lines)


def describe_file(path: Path) -> str:
    """Convenience for the CLI: read one JSON file and report on it."""
    with path.open(encoding="utf-8") as handle:
        return render_report(describe_json(json.load(handle)))
