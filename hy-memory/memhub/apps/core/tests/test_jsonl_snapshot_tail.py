"""Bounded EOF handling on synthetic files only, never original host history."""

import hashlib
import io

import pytest
import zstandard

from one_memory.imports.readers import (
    RawReadFailure,
    RawReadFailureCode,
    RawRecord,
    read_jsonl,
    read_zstd_jsonl,
    verify_jsonl_checkpoint,
)
from tests.test_source_readers import authorized


@pytest.fixture(params=["jsonl", "zstd"])
def source_reader(tmp_path, request):
    compressed = request.param == "zstd"
    path = tmp_path / ("history.jsonl.zstd" if compressed else "history.jsonl")

    def write(content):
        data = zstandard.ZstdCompressor().compress(content) if compressed else content
        path.write_bytes(data)
        return authorized(path)

    def checkpoint(content, records):
        return f"record:{records}" if compressed else f"byte:{len(content)}"

    return read_zstd_jsonl if compressed else read_jsonl, write, checkpoint


def test_immutable_valid_eof_is_emitted_once_and_resumes(source_reader):
    reader, write, checkpoint = source_reader
    prefix, tail = b'{"id":1}\n', b'{"id":2}'
    source_file = write(prefix + tail)

    events = list(reader(source_file, immutable=True))

    assert [event.value for event in events] == [{"id": 1}, {"id": 2}]
    assert events[-1].checkpoint == checkpoint(prefix + tail, 2)
    assert events[-1].checkpoint_anchor == hashlib.sha256(tail).hexdigest()
    assert list(reader(source_file, checkpoint=events[-1].checkpoint, immutable=True)) == []
    assert list(reader(source_file, checkpoint=events[0].checkpoint, immutable=True)) == events[1:]


def test_immutable_zstd_eof_after_concatenated_frames_resumes_by_record(tmp_path):
    path = tmp_path / "history.jsonl.zstd"
    compressor = zstandard.ZstdCompressor(write_checksum=True)
    path.write_bytes(compressor.compress(b'{"id":1}\n') + compressor.compress(b'{"id":2}'))
    events = list(read_zstd_jsonl(authorized(path), immutable=True, checkpoint="record:1"))
    assert [event.value for event in events] == [{"id": 2}]
    assert events[0].checkpoint == "record:2"
    assert list(read_zstd_jsonl(authorized(path), immutable=True, checkpoint="record:2")) == []


def test_live_zstd_partial_record_can_finish_in_a_later_frame(tmp_path):
    path = tmp_path / "history.jsonl.zstd"
    compressor = zstandard.ZstdCompressor(write_checksum=True)
    path.write_bytes(compressor.compress(b'{"id":1}\n{"id":'))
    first = list(read_zstd_jsonl(authorized(path)))
    assert len(first) == 1
    with path.open("ab") as stream:
        stream.write(compressor.compress(b"2}\n"))
    resumed = list(read_zstd_jsonl(authorized(path), checkpoint=first[0].checkpoint))
    assert [event.value for event in resumed] == [{"id": 2}]


@pytest.mark.parametrize(
    ("tail", "reason"),
    [
        (b"\0" * 13_738, RawReadFailureCode.INVALID_JSON),
        (b'{"id":', RawReadFailureCode.INVALID_JSON),
        (b'{"text":"\xff"}', RawReadFailureCode.INVALID_JSON),
        (b'{"text":"\xe4\xb8', RawReadFailureCode.INVALID_JSON),
        (b"  \t\r", RawReadFailureCode.INVALID_JSON),
        (b"[]", RawReadFailureCode.RECORD_NOT_OBJECT),
        (b"null", RawReadFailureCode.RECORD_NOT_OBJECT),
    ],
    ids=["f06-nul", "partial-json", "invalid-utf8", "partial-utf8", "whitespace", "array", "null"],
)
def test_nonempty_immutable_invalid_tail_reports_existing_failure(source_reader, tail, reason):
    reader, write, checkpoint = source_reader
    prefix = b'{"id":1}\n'
    source_file = write(prefix + tail)

    events = list(reader(source_file, immutable=True))

    assert len(events) == 2
    assert events[0].value == {"id": 1}
    assert events[1] == RawReadFailure(
        checkpoint(prefix + tail, 2), reason, hashlib.sha256(tail).hexdigest()
    )
    assert list(reader(source_file, checkpoint=events[-1].checkpoint, immutable=True)) == []


@pytest.mark.parametrize("immutable", [False, True])
def test_empty_file_has_no_records_or_failures(source_reader, immutable):
    reader, write, _ = source_reader
    assert list(reader(write(b""), immutable=immutable)) == []


@pytest.mark.parametrize("tail", [b'{"id":2}', b'{"id":', b"\0" * 13_738, b'{"text":"\xff"}'])
def test_live_unterminated_tail_is_deferred_without_checkpoint(source_reader, tail):
    reader, write, checkpoint = source_reader
    prefix = b'{"id":1}\n'
    events = list(reader(write(prefix + tail)))

    assert len(events) == 1
    assert events[0].value == {"id": 1}
    assert events[0].checkpoint == checkpoint(prefix, 1)


@pytest.mark.parametrize("limit", [16, 64])
def test_oversized_live_partial_tail_is_deferred_until_newline(source_reader, limit):
    reader, write, checkpoint = source_reader
    prefix = b'{"id":1}\n'
    partial = b'{"text":"' + b"x" * (limit * 3)
    events = list(reader(write(prefix + partial), max_record_bytes=limit))

    assert len(events) == 1, "An unterminated live extent must not advance the cursor"
    assert events[0].checkpoint == checkpoint(prefix, 1)
    complete = prefix + partial + b'"}\n'
    resumed = list(
        reader(
            write(complete + b'{"id":3}\n'), checkpoint=events[0].checkpoint, max_record_bytes=limit
        )
    )
    assert len(resumed) == 2
    assert resumed[0] == RawReadFailure(
        checkpoint(complete, 2), RawReadFailureCode.RECORD_TOO_LARGE
    )
    assert resumed[1].value == {"id": 3}


@pytest.mark.parametrize("newline", [b"", b"\n"])
def test_immutable_oversized_extent_is_one_failure_and_resumes(source_reader, newline):
    reader, write, checkpoint = source_reader
    content = b'{"text":"' + b"x" * 1024 + b'"}' + newline
    source_file = write(content)
    events = list(reader(source_file, immutable=True, max_record_bytes=64))

    assert events == [RawReadFailure(checkpoint(content, 1), RawReadFailureCode.RECORD_TOO_LARGE)]
    assert (
        list(
            reader(
                source_file, checkpoint=events[0].checkpoint, immutable=True, max_record_bytes=64
            )
        )
        == []
    )


@pytest.mark.parametrize("newline", [b"", b"\n", b"\r\n"])
def test_exact_record_limit_is_not_oversized(source_reader, newline):
    reader, write, _ = source_reader
    content = b'{"id":1}' + newline
    events = list(reader(write(content), immutable=True, max_record_bytes=len(content)))

    assert len(events) == 1
    assert isinstance(events[0], RawRecord)
    assert events[0].value == {"id": 1}


@pytest.mark.parametrize("immutable", [False, True])
def test_newline_records_and_failures_keep_existing_checkpoints(source_reader, immutable):
    reader, write, checkpoint = source_reader
    lines = [b'{"id":1}\n', b"bad-json\n", b'{"text":"\xff"}\r\n', b"[]\n", b'{"id":2}\r\n']
    source_file = write(b"".join(lines))
    events = list(reader(source_file, immutable=immutable))

    assert len(events) == len(lines)
    assert events[0].value == {"id": 1}
    assert events[-1].value == {"id": 2}
    assert [event.reason_code for event in events[1:-1]] == [
        RawReadFailureCode.INVALID_JSON,
        RawReadFailureCode.INVALID_JSON,
        RawReadFailureCode.RECORD_NOT_OBJECT,
    ]
    for index, (line, event) in enumerate(zip(lines, events, strict=True), 1):
        assert event.checkpoint == checkpoint(b"".join(lines[:index]), index)
        assert event.checkpoint_anchor == hashlib.sha256(line).hexdigest()
    assert (
        list(reader(source_file, immutable=immutable, checkpoint=events[1].checkpoint))
        == events[2:]
    )


@pytest.mark.parametrize("prefix", [b"", b'{"id":0}\n', b'{"padding":"' + b"x" * 100 + b'"}\n'])
def test_immutable_eof_anchor_verifies_and_detects_same_size_rewrite(tmp_path, prefix):
    path = tmp_path / "history.jsonl"
    tail = b'{"id":1}'
    path.write_bytes(prefix + tail)
    checkpoint, anchor = f"byte:{len(prefix + tail)}", hashlib.sha256(tail).hexdigest()

    assert verify_jsonl_checkpoint(authorized(path), checkpoint=checkpoint, anchor=anchor)
    path.write_bytes(prefix + b'{"id":2}')
    assert not verify_jsonl_checkpoint(authorized(path), checkpoint=checkpoint, anchor=anchor)


@pytest.mark.parametrize("newline", [b"", b"\n"])
def test_anchor_uses_the_full_bounded_record_not_an_arbitrary_suffix(tmp_path, newline):
    path = tmp_path / "history.jsonl"
    prefix = b'{"padding":"' + b"x" * 128 + b'"}\n'
    tail = b'{"id":1}' + newline
    path.write_bytes(prefix + tail)
    assert verify_jsonl_checkpoint(
        authorized(path),
        checkpoint=f"byte:{len(prefix + tail)}",
        anchor=hashlib.sha256(tail).hexdigest(),
        max_record_bytes=len(tail),
    )
    path.write_bytes(b"x" * 256 + tail)
    assert not verify_jsonl_checkpoint(
        authorized(path),
        checkpoint=f"byte:{path.stat().st_size}",
        anchor=hashlib.sha256(tail).hexdigest(),
        max_record_bytes=len(tail),
    )


@pytest.mark.parametrize("suffix", [b"\n", b'\n{"id":2}\n', b'\r\n{"id":2}\r\n'])
def test_completed_eof_checkpoint_still_verifies_after_separator_is_appended(tmp_path, suffix):
    path = tmp_path / "history.jsonl"
    tail = b'{"id":1}'
    path.write_bytes(tail + suffix)
    assert verify_jsonl_checkpoint(
        authorized(path), checkpoint=f"byte:{len(tail)}", anchor=hashlib.sha256(tail).hexdigest()
    )


@pytest.mark.parametrize("suffix", [b"2}\n", b"x\n", b' {"id":2}\n'])
def test_eof_checkpoint_does_not_skip_a_live_continuation(tmp_path, suffix):
    path = tmp_path / "history.jsonl"
    partial = b'{"id":'
    path.write_bytes(partial + suffix)
    assert not verify_jsonl_checkpoint(
        authorized(path),
        checkpoint=f"byte:{len(partial)}",
        anchor=hashlib.sha256(partial).hexdigest(),
    )


def test_eof_resume_consumes_only_the_late_separator_not_a_blank_record(tmp_path):
    path = tmp_path / "history.jsonl"
    tail = b'{"id":1}'
    path.write_bytes(tail)
    first = list(read_jsonl(authorized(path), immutable=True))[0]
    with path.open("ab") as stream:
        stream.write(b'\r\n{"id":2}\n')
    resumed = list(read_jsonl(authorized(path), checkpoint=first.checkpoint))

    assert len(resumed) == 1
    assert resumed[0].value == {"id": 2}
    assert resumed[0].checkpoint == f"byte:{path.stat().st_size}"
    assert list(read_jsonl(authorized(path), checkpoint=resumed[0].checkpoint)) == []


def test_normal_checkpoint_does_not_hide_a_genuine_blank_line(tmp_path):
    path = tmp_path / "history.jsonl"
    first = b'{"id":1}\n'
    path.write_bytes(first + b'\n{"id":2}\n')

    resumed = list(read_jsonl(authorized(path), checkpoint=f"byte:{len(first)}"))

    assert len(resumed) == 2
    assert resumed[0].reason_code is RawReadFailureCode.INVALID_JSON
    assert resumed[1].value == {"id": 2}


def test_oversized_frozen_eof_resume_does_not_invent_record_from_live_continuation(tmp_path):
    path = tmp_path / "history.jsonl"
    prefix = b'{"id":1}\n'
    path.write_bytes(prefix + b"x" * 256)
    events = list(read_jsonl(authorized(path), immutable=True, max_record_bytes=32))
    assert len(events) == 2
    assert events[-1].reason_code is RawReadFailureCode.RECORD_TOO_LARGE
    assert events[-1].checkpoint_anchor is None

    with path.open("ab") as stream:
        stream.write(b'{"id":99}\n{"id":2}\n')
    resumed = list(
        read_jsonl(authorized(path), checkpoint=events[-1].checkpoint, max_record_bytes=32)
    )

    assert len(resumed) == 2
    assert isinstance(resumed[0], RawReadFailure), "A continuation is not a new message"
    assert resumed[0].reason_code is RawReadFailureCode.RECORD_TOO_LARGE
    assert resumed[1].value == {"id": 2}


@pytest.mark.parametrize("limit", [0, -1])
def test_invalid_record_limit_is_rejected(source_reader, limit):
    reader, write, _ = source_reader
    with pytest.raises(ValueError, match="max_record_bytes must be positive"):
        list(reader(write(b"{}\n"), max_record_bytes=limit))


@pytest.mark.parametrize("immutable", [False, True])
def test_oversized_plain_reader_uses_only_bounded_reads(immutable):
    class BoundedStream(io.BytesIO):
        def readline(self, size=-1):
            assert 0 < size <= 65
            return super().readline(size)

        def read(self, size=-1):
            assert 0 <= size <= 65
            return super().read(size)

    class Source:
        def open_binary(self):
            return BoundedStream(b"x" * 4096)

    events = list(read_jsonl(Source(), immutable=immutable, max_record_bytes=64))
    assert len(events) == (1 if immutable else 0)
