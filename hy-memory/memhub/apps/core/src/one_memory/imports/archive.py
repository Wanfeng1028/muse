"""What an uploaded export is, decided before anything parses it.

Two jobs, deliberately kept apart.

**Safety.** Accepting an archive from a person and unpacking it is the one
genuinely dangerous thing this feature does, and it has to hold before any
vendor parser exists. An entry named `../../.ssh/authorized_keys` writes
outside the destination; a 40KB archive can expand to gigabytes; a stored
symlink can point anywhere on the disk. None of these is hypothetical and
none is the parser's problem, so they are refused here, from the declared
metadata, before a single byte is read out.

**Recognition, by entry name only.** Nothing in this module reads a payload's
schema, because the schemas are exactly what we do not have real samples of.
Structure we can be certain of from the vendors' own documented file names;
content we cannot. So this module refuses to guess: it reports `UNKNOWN` when
no signature matches and `AMBIGUOUS` when more than one does.

That refusal is the point. An honest `UNKNOWN` sends someone to fetch a real
sample. A confident wrong guess sends the wrong parser at real data and
silently produces wrong memories, which is the failure this whole import path
exists to avoid.

Deliberately dependency-free: stdlib only, and no imports from elsewhere in
`one_memory`. Wiring the result to `StorageKind` and the source registry is a
separate, later step, and keeping it out of here means this module can be
tested on its own.
"""

import shutil
import stat
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath

#: Read size while unpacking. Small enough that an over-budget archive is
#: stopped within a chunk of the limit rather than after a whole entry.
_CHUNK_BYTES = 64 * 1024

#: Room for a real export with attachments, and no room for a bomb.
#: A ChatGPT archive with images runs to a few GB in the worst case seen
#: documented, so the ceiling is generous; the point is that it exists and is
#: checked against the declared sizes rather than discovered by filling a disk.
DEFAULT_MAX_TOTAL_BYTES = 4 * 1024**3

#: A real export is thousands of entries. Millions is someone probing us.
DEFAULT_MAX_ENTRIES = 200_000


class ArchiveRejection(Exception):
    """The upload will not be unpacked, and why.

    Carries a message meant to reach the user: a refusal they cannot read is
    indistinguishable from the feature being broken.
    """


class ExportKind(StrEnum):
    CHATGPT = "chatgpt"
    CLAUDE = "claude"
    DEEPSEEK = "deepseek"
    ALMA = "alma"
    RAYCAST = "raycast"
    GOOGLE_TAKEOUT = "google_takeout"
    MARKDOWN = "markdown"
    #: More than one vendor signature matched. Not a kind, a refusal to pick.
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


#: The kinds this release intends to import.
#:
#: Reported separately from recognition on purpose. "We know what your file is
#: and this version cannot read it yet" and "we do not know what this is" are
#: different messages, and only the first one stops the person hunting for a
#: mistake they did not make.
IN_SCOPE = frozenset(
    {
        ExportKind.CHATGPT,
        ExportKind.CLAUDE,
        ExportKind.DEEPSEEK,
        ExportKind.MARKDOWN,
    }
)


@dataclass(frozen=True, slots=True)
class DetectedExport:
    kind: ExportKind
    #: The entry to hand the parser, as named inside the archive. `None`
    #: whenever we are not prepared to say, which includes AMBIGUOUS: naming
    #: one payload there would be the choice we are declining to make.
    payload: str | None = None
    candidates: tuple[ExportKind, ...] = field(default_factory=tuple)

    @property
    def supported(self) -> bool:
        return self.kind in IN_SCOPE


def safe_entry_names(
    path: Path,
    *,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_entries: int = DEFAULT_MAX_ENTRIES,
) -> list[str]:
    """Every entry name, or a refusal naming the first thing that was wrong.

    Reads only the central directory. Nothing is extracted and nothing is
    written, so a refused archive costs a listing rather than a disk.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, OSError) as error:
        raise ArchiveRejection(f"{path.name} is not a readable archive") from error

    if len(entries) > max_entries:
        raise ArchiveRejection(
            f"{path.name} declares {len(entries)} entries, over the {max_entries} budget"
        )

    total = 0
    names: list[str] = []
    for entry in entries:
        _refuse_unsafe_name(path, entry.filename)
        if stat.S_ISLNK(entry.external_attr >> 16):
            raise ArchiveRejection(
                f"{path.name} contains a symbolic link ({entry.filename}), "
                "which could point anywhere on this machine"
            )
        total += entry.file_size
        if total > max_total_bytes:
            raise ArchiveRejection(f"{path.name} expands past the {max_total_bytes} byte budget")
        if not entry.is_dir():
            names.append(entry.filename)
    return names


def extract_safely(
    path: Path,
    into: Path,
    *,
    select: Sequence[str] | None = None,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_entries: int = DEFAULT_MAX_ENTRIES,
) -> list[Path]:
    """Unpack under `into`, or refuse and leave the disk as it was found.

    `safe_entry_names` runs first and covers the declared shape: escapes,
    links, entry count, declared total. That check happens before anything is
    written, so an archive that fails it costs a listing.

    There is deliberately no second byte count during the write. The intent
    was to re-count against bytes actually written, on the grounds that a
    zip's central directory is written by whoever built the file and verified
    by nobody. Measuring it showed the recount is unreachable: CPython's
    `zipfile` caps each read at the declared size, so an entry cannot write
    past what it declared -- it fails its CRC instead, and lands here as a
    refusal. An unreachable check is worse than no check, because it reads
    like protection while never having run.

    There is also no second path check inside the write loop. One was written
    and then removed for the same reason: every name reaching the loop has
    already been through `_refuse_unsafe_name`, which rejects absolute paths
    and any `..` component before a join is ever performed, so the re-check
    could not be made to fail. Mutating it away changed no test, which is the
    signature of a guard that guards nothing.

    On any refusal the files this call created are removed, but `into` itself
    is left in place if it already existed. Deleting a directory the caller
    handed us, because their archive turned out to be bad, is a worse outcome
    than the bad archive.
    """
    names = safe_entry_names(path, max_total_bytes=max_total_bytes, max_entries=max_entries)

    wanted = list(names)
    if select is not None:
        available = set(names)
        missing = [name for name in select if name not in available]
        if missing:
            raise ArchiveRejection(f"{path.name} does not contain {', '.join(missing)}")
        wanted = list(select)

    existed = into.exists()
    written: list[Path] = []
    try:
        into.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path) as archive:
            for name in wanted:
                target = into / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open("wb") as sink:
                    written.append(target)
                    while chunk := source.read(_CHUNK_BYTES):
                        sink.write(chunk)
    except (ArchiveRejection, zipfile.BadZipFile, OSError) as error:
        _undo(written, into, existed=existed)
        if isinstance(error, ArchiveRejection):
            raise
        raise ArchiveRejection(f"{path.name} could not be unpacked") from error
    return written


def _undo(written: Sequence[Path], into: Path, *, existed: bool) -> None:
    for target in written:
        target.unlink(missing_ok=True)
    if existed:
        # Only the directories this call added are worth reclaiming, and only
        # while they are empty; anything else belongs to the caller.
        for target in written:
            parent = target.parent
            while parent != into and parent.is_relative_to(into):
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        return
    shutil.rmtree(into, ignore_errors=True)


def _refuse_unsafe_name(path: Path, name: str) -> None:
    # Checked on the declared name, before any join, because the join is what
    # we are trying not to perform with a hostile value.
    if name.startswith("/") or name.startswith("\\"):
        raise ArchiveRejection(f"{path.name} contains an absolute path ({name})")
    if ".." in PurePosixPath(name).parts:
        raise ArchiveRejection(
            f"{path.name} contains an entry that points outside the archive ({name})"
        )


def detect_export(path: Path, **limits: int) -> DetectedExport:
    """What kind of export this is, or an honest admission that we cannot say."""
    if zipfile.is_zipfile(path):
        return _detect_in_archive(path, safe_entry_names(path, **limits))
    if path.suffix.lower() == ".zip":
        # Named like an archive and unreadable as one. Saying UNKNOWN here
        # would send the person looking at their content when the problem is
        # the file itself, most often a truncated download.
        raise ArchiveRejection(f"{path.name} is not a readable archive")
    return _detect_bare_file(path)


def _detect_in_archive(path: Path, names: list[str]) -> DetectedExport:
    del path
    #: First occurrence wins. Vendors nest their payload under a top-level
    #: folder often enough that matching the basename anywhere is what makes
    #: the common case work.
    by_base: dict[str, str] = {}
    for name in names:
        by_base.setdefault(PurePosixPath(name).name, name)

    matched: list[tuple[ExportKind, str]] = []

    # Both vendors ship `conversations.json`; the companion file decides.
    if "conversations.json" in by_base:
        if "memories.json" in by_base:
            matched.append((ExportKind.CLAUDE, by_base["conversations.json"]))
        if "chat.html" in by_base or "user.json" in by_base:
            matched.append((ExportKind.CHATGPT, by_base["conversations.json"]))
    if "threads.json" in by_base:
        matched.append((ExportKind.ALMA, by_base["threads.json"]))
    for name in names:
        if "My Activity/" in name and name.endswith("MyActivity.html"):
            matched.append((ExportKind.GOOGLE_TAKEOUT, name))
            break

    if not matched:
        return DetectedExport(ExportKind.UNKNOWN)
    if len(matched) > 1:
        return DetectedExport(
            ExportKind.AMBIGUOUS,
            candidates=tuple(kind for kind, _ in matched),
        )
    kind, payload = matched[0]
    return DetectedExport(kind, payload=payload)


def _detect_bare_file(path: Path) -> DetectedExport:
    name = path.name
    # Matched on the vendors' documented default names only. A `.json` of
    # some other name could be anybody's, and calling it Raycast's because it
    # is the only bare-JSON kind we know would be the guess this module exists
    # to avoid.
    if name == "deepseek_conversations.json":
        return DetectedExport(ExportKind.DEEPSEEK, payload=name)
    if name == "raycast_ai_chats.json":
        return DetectedExport(ExportKind.RAYCAST, payload=name)
    if path.suffix.lower() in {".md", ".txt", ".markdown"}:
        return DetectedExport(ExportKind.MARKDOWN, payload=name)
    return DetectedExport(ExportKind.UNKNOWN)
