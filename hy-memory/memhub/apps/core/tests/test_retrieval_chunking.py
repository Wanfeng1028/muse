from dataclasses import FrozenInstanceError

import pytest

from one_memory.local_embedding import LocalEmbedder, TokenizedText, TokenOffset
from one_memory.retrieval.chunking import ChunkingError, chunk_evidence


class Characters:
    def tokenize_with_offsets(self, text):
        offsets = (
            TokenOffset(0, 0, True),
            *(TokenOffset(i, i + 1) for i in range(len(text))),
            TokenOffset(0, 0, True),
        )
        return TokenizedText(tuple(range(len(offsets))), offsets)


def assert_coverage(text, chunks, tokenizer, prefix=""):
    assert chunks
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    covered = bytearray(len(text))
    previous_start = -1
    for chunk in chunks:
        assert 0 <= chunk.start_cp < chunk.end_cp <= len(text)
        assert chunk.start_cp > previous_start
        previous_start = chunk.start_cp
        assert chunk.text == text[chunk.start_cp : chunk.end_cp]
        assert chunk.token_count == len(
            tokenizer.tokenize_with_offsets(prefix + chunk.text).token_ids
        )
        assert chunk.token_count <= 512
        covered[chunk.start_cp : chunk.end_cp] = b"\x01" * (chunk.end_cp - chunk.start_cp)
    assert all(covered[i] for i, c in enumerate(text) if not c.isspace())
    assert chunks[-1].end_cp == len(text)


def test_default_384_body_64_overlap_and_exact_source_slices():
    text = "中" * 1000
    chunks = chunk_evidence(text, Characters())
    assert [(c.start_cp, c.end_cp) for c in chunks] == [(0, 384), (320, 704), (640, 1000)]
    assert chunks[0].token_count == 386
    assert_coverage(text, chunks, Characters())
    with pytest.raises(FrozenInstanceError):
        chunks[0].text = "replacement"


def test_all_prefix_and_special_tokens_count_toward_strict_512_budget():
    prefix = "P" * 200
    text = "中" * 900
    chunks = chunk_evidence(text, Characters(), prefix=prefix)
    assert chunks[0].end_cp == 310
    assert chunks[0].token_count == 512
    assert_coverage(text, chunks, Characters(), prefix)
    with pytest.raises(ChunkingError, match="budget"):
        chunk_evidence("中", Characters(), prefix="P" * 510)


def test_real_tokenizer_covers_long_chinese_middle_and_tail_object_locations():
    middle = "https://example.test/Middle?Key=Value#Anchor"
    tail = "/CaseSensitive/路径/final.txt"
    text = "中文😀e\u0301\n" + "中" * 740 + "\n" + middle + "\n" + "尾" * 800 + "\n" + tail
    tokenizer = LocalEmbedder()
    chunks = chunk_evidence(text, tokenizer)
    assert len(chunks) > 3
    assert_coverage(text, chunks, tokenizer)
    for value in (middle, tail):
        location = text.index(value)
        assert any(c.start_cp <= location and c.end_cp >= location + len(value) for c in chunks)
    assert chunks[0].text.startswith("中文😀e\u0301\n")


def test_prefers_paragraph_boundary_near_target_without_losing_text():
    text = "中" * 300 + "\n\n" + "尾" * 500
    chunks = chunk_evidence(text, Characters())
    assert chunks[0].end_cp == 302
    assert_coverage(text, chunks, Characters())


@pytest.mark.parametrize("text", ["", " \n\t\r "])
def test_empty_or_whitespace_has_no_index_chunks(text):
    assert chunk_evidence(text, Characters()) == ()


@pytest.mark.parametrize(
    "text", ["😀" * 300, "e\u0301" * 400, "甲\n乙\t丙", "原样 <user_query>原文</user_query>"]
)
def test_unicode_and_wrapper_text_identity_is_preserved(text):
    chunks = chunk_evidence(text, Characters())
    assert_coverage(text, chunks, Characters())


@pytest.mark.parametrize(
    "offsets,ids",
    [
        ((TokenOffset(0, 4),), (1,)),
        ((TokenOffset(-1, 1),), (1,)),
        ((TokenOffset(1, 2), TokenOffset(0, 1)), (1, 2)),
        ((TokenOffset(0, 1), TokenOffset(2, 3)), (1, 2)),
        ((TokenOffset(0, 0),), (1,)),
        ((TokenOffset(0, 1, True),), (1,)),
        ((TokenOffset(0, 3),), (1, 2)),
        ((), ()),
    ],
)
def test_bad_or_incomplete_offsets_fail_explicitly(offsets, ids):
    class Broken:
        def tokenize_with_offsets(self, text):
            return TokenizedText(ids, offsets)

    with pytest.raises(ChunkingError):
        chunk_evidence("abc", Broken())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_tokens": 64},
        {"overlap_tokens": -1},
        {"max_tokens": 513},
        {"max_tokens": True},
        {"target_tokens": 0},
        {"overlap_tokens": 384},
    ],
)
def test_invalid_budgets_fail_before_tokenizing(kwargs):
    with pytest.raises(ChunkingError):
        chunk_evidence("content", Characters(), **kwargs)


def test_retokenizes_actual_prefix_plus_slice_instead_of_assuming_additive_counts():
    class ContextSensitive(Characters):
        def tokenize_with_offsets(self, text):
            result = super().tokenize_with_offsets(text)
            if text.startswith("P"):
                # Same valid offsets may carry multiple pieces. Budget must include them all.
                return TokenizedText(
                    result.token_ids * 2,
                    tuple(o for o in result.offsets if o.special)
                    + tuple(o for o in result.offsets if o.special)
                    + tuple(o for o in result.offsets if not o.special for _ in range(2)),
                )
            return result

    tokenizer = ContextSensitive()
    chunks = chunk_evidence("中" * 600, tokenizer, prefix="P")
    assert_coverage("中" * 600, chunks, tokenizer, "P")


def test_overlapping_token_offsets_are_not_split_inside_a_character():
    class Repeated(Characters):
        def tokenize_with_offsets(self, text):
            return TokenizedText(
                tuple(range(2 * len(text))),
                tuple(TokenOffset(i, i + 1) for i in range(len(text)) for _ in range(2)),
            )

    tokenizer = Repeated()
    text = "😀" * 500
    chunks = chunk_evidence(text, tokenizer)
    assert_coverage(text, chunks, tokenizer)


def test_single_indivisible_offset_over_budget_is_not_truncated():
    class Indivisible:
        def tokenize_with_offsets(self, text):
            return TokenizedText(
                tuple(range(600)), tuple(TokenOffset(0, len(text)) for _ in range(600))
            )

    with pytest.raises(ChunkingError, match="budget"):
        chunk_evidence("😀", Indivisible())


def test_real_long_continuous_ascii_unknown_preserves_all_6000_characters():
    tokenizer = LocalEmbedder()
    text = " \t" + "x" * 6000 + "\n末尾链接 https://example.test/Case?A=B#C\t"
    chunks = chunk_evidence(text, tokenizer)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert_coverage(text, chunks, tokenizer)


def test_real_subword_and_whitespace_boundaries_have_no_gaps():
    tokenizer = LocalEmbedder()
    text = " \t\n" + ("unaffordable embeddings\t中\u0301文  a\u0301b\n\n" * 180) + "\t\n "
    prefix = "本段用于检索："
    chunks = chunk_evidence(text, tokenizer, prefix=prefix)
    assert len(chunks) > 3
    assert chunks[0].start_cp == 0 and chunks[-1].end_cp == len(text)
    assert_coverage(text, chunks, tokenizer, prefix)
    for first, second in zip(chunks, chunks[1:], strict=False):
        assert second.start_cp <= first.end_cp


def test_partially_overlapping_offsets_for_combining_cluster_are_indivisible():
    class Combining(Characters):
        def tokenize_with_offsets(self, text):
            offsets = []
            i = 0
            while i < len(text):
                if text.startswith("e\u0301", i):
                    offsets.extend((TokenOffset(i, i + 2), TokenOffset(i + 1, i + 2)))
                    i += 2
                else:
                    offsets.append(TokenOffset(i, i + 1))
                    i += 1
            return TokenizedText(tuple(range(len(offsets))), tuple(offsets))

    text = "中" * 383 + "e\u0301" + "尾" * 500
    tokenizer = Combining()
    chunks = chunk_evidence(text, tokenizer)
    assert_coverage(text, chunks, tokenizer)
    assert all(c.start_cp != 384 and c.end_cp != 384 for c in chunks)


def test_sparse_whitespace_gaps_are_retained_not_rebuilt_from_tokens():
    tokenizer = LocalEmbedder()
    text = " \n" + "中" * 380 + "\n \t\n" + "尾" * 380 + " \t\r\n"
    chunks = chunk_evidence(text, tokenizer)
    assert_coverage(text, chunks, tokenizer)
    assert chunks[0].text.startswith(" \n")
    assert chunks[-1].text.endswith(" \t\r\n")


def test_real_prefix_retokenization_never_exceeds_encoder_window():
    tokenizer = LocalEmbedder()
    prefix = "检索前缀" * 50
    text = ("中文tokenization😀e\u0301\n" * 120) + "https://example.test/Tail"
    chunks = chunk_evidence(text, tokenizer, prefix=prefix)
    assert len(chunks) > 1
    assert_coverage(text, chunks, tokenizer, prefix)


def test_tokenizer_failure_is_explicit_not_partial_output():
    class Broken:
        def tokenize_with_offsets(self, text):
            raise RuntimeError("tokenizer unavailable")

    with pytest.raises(ChunkingError, match="tokenization_failed"):
        chunk_evidence("中", Broken())


@pytest.mark.parametrize(
    "text", ["e\u0301", "\u0301", "中\u0301文", "\n\r\t中\n尾\n", "👩‍💻", "👩‍👩‍👧‍👦", "✈️"]
)
def test_locked_normalizer_supported_unicode_examples_cover_original(text):
    tokenizer = LocalEmbedder()
    assert_coverage(text, chunk_evidence(text, tokenizer), tokenizer)


@pytest.mark.parametrize("text", ["中\u200d文", "\u200d", "中\u200b文", "中\x00文", "\x00"])
def test_locked_normalizer_dropped_nonwhitespace_is_explicitly_unsupported(text):
    tokenizer = LocalEmbedder()
    offsets = tokenizer.tokenize_with_offsets(text).offsets
    assert any(
        not character.isspace()
        and not any(
            not offset.special and offset.start_cp <= i < offset.end_cp for offset in offsets
        )
        for i, character in enumerate(text)
    )
    with pytest.raises(ChunkingError, match="uncovered_nonwhitespace"):
        chunk_evidence(text, tokenizer)


def test_another_normalizer_dropping_trailing_combining_mark_is_not_reported_complete():
    class NormalizesAccent:
        def tokenize_with_offsets(self, text):
            return TokenizedText((1,), (TokenOffset(0, 1),))

    with pytest.raises(ChunkingError, match="uncovered_nonwhitespace"):
        chunk_evidence("e\u0301", NormalizesAccent())
