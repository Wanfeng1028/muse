"""Single-Evidence identity chunking; no reads, persistence, normalization or grants.

Callers must first establish eligibility/sanitization/permission. This module
does not strip wrappers or secrets and must not be used as a content safety gate.
"""

from dataclasses import dataclass
from typing import Protocol

from one_memory.embedding_assets import BUILTIN_EMBEDDING_MAX_TOKENS
from one_memory.local_embedding import TokenizedText, TokenOffset


class OffsetTokenizer(Protocol):
    def tokenize_with_offsets(self, text: str) -> TokenizedText: ...


class ChunkingError(ValueError):
    """Invalid offsets, uncovered text or insufficient encoding budget; never truncate."""


@dataclass(frozen=True)
class TextChunk:
    ordinal: int
    start_cp: int
    end_cp: int
    token_count: int
    text: str


@dataclass(frozen=True)
class _Span:
    start: int
    end: int
    tokens: int


def _spans(text: str, encoded: TokenizedText) -> tuple[_Span, ...]:
    if not isinstance(encoded, TokenizedText) or len(encoded.token_ids) != len(encoded.offsets):
        raise ChunkingError("chunk_token_offset_count_mismatch")
    spans: list[_Span] = []
    previous_start = previous_end = 0
    for token_id, offset in zip(encoded.token_ids, encoded.offsets, strict=True):
        if type(token_id) is not int or token_id < 0 or not isinstance(offset, TokenOffset):
            raise ChunkingError("chunk_invalid_token_offset")
        if (
            type(offset.start_cp) is not int
            or type(offset.end_cp) is not int
            or type(offset.special) is not bool
        ):
            raise ChunkingError("chunk_invalid_token_offset")
        start, end = offset.start_cp, offset.end_cp
        if offset.special:
            if start != 0 or end != 0:
                raise ChunkingError("chunk_invalid_special_offset")
            continue
        if not 0 <= start < end <= len(text) or start < previous_start or end < previous_end:
            raise ChunkingError("chunk_invalid_offset_order_or_bounds")
        if start > previous_end and not text[previous_end:start].isspace():
            raise ChunkingError("chunk_uncovered_nonwhitespace")
        # Overlapping subpieces (including several pieces for one code point)
        # form an indivisible interval; slicing inside it loses token identity.
        if spans and start < spans[-1].end:
            prior = spans[-1]
            spans[-1] = _Span(prior.start, end, prior.tokens + 1)
        else:
            spans.append(_Span(start, end, 1))
        previous_start, previous_end = start, end
    if text[previous_end:] and not text[previous_end:].isspace():
        raise ChunkingError("chunk_uncovered_nonwhitespace")
    return tuple(spans)


def _encoding(text: str, tokenizer: OffsetTokenizer) -> tuple[TokenizedText, tuple[_Span, ...]]:
    try:
        result = tokenizer.tokenize_with_offsets(text)
    except Exception as error:
        raise ChunkingError("chunk_tokenization_failed") from error
    return result, _spans(text, result)


def chunk_evidence(
    text: str,
    tokenizer: OffsetTokenizer,
    *,
    prefix: str = "",
    target_tokens: int = 384,
    overlap_tokens: int = 64,
    max_tokens: int = BUILTIN_EMBEDDING_MAX_TOKENS,
) -> tuple[TextChunk, ...]:
    """Chunk one original with code point [start,end), preserving exact slices.

    target/overlap count original non-special tokens. Overlap is up to the
    requested token count at indivisible offset boundaries; forward progress is
    mandatory. token_count is re-tokenized prefix + chunk.text INCLUDING specials,
    never an additive estimate. Prefix is caller-provided, unchanged, and omitted
    from chunk.text/offsets. Empty/whitespace-only inputs have no index chunks.
    """
    if not isinstance(text, str) or not isinstance(prefix, str):
        raise ChunkingError("chunk_requires_text")
    if (
        any(type(value) is not int for value in (target_tokens, overlap_tokens, max_tokens))
        or not 0 <= overlap_tokens < target_tokens
        or not 1 <= max_tokens <= BUILTIN_EMBEDDING_MAX_TOKENS
        or target_tokens > max_tokens
    ):
        raise ChunkingError("chunk_invalid_token_budget")
    if not text or text.isspace():
        return ()
    _, spans = _encoding(text, tokenizer)
    if not spans:
        raise ChunkingError("chunk_uncovered_nonwhitespace")
    chunks: list[TextChunk] = []
    start_index = 0
    previous_end_cp = 0
    while start_index < len(spans):
        end_index = start_index
        body_tokens = 0
        while end_index < len(spans):
            candidate = body_tokens + spans[end_index].tokens
            if end_index > start_index and candidate > target_tokens:
                break
            body_tokens = candidate
            end_index += 1
        # Prefer the last paragraph boundary in the latter half of the target.
        # Never trade away an entire overlap window or split a token interval.
        if end_index < len(spans):
            count = 0
            preferred = None
            for boundary in range(start_index + 1, end_index + 1):
                count += spans[boundary - 1].tokens
                if count >= max(target_tokens // 2, overlap_tokens + 1):
                    left, right = spans[boundary - 1].end, spans[boundary].start
                    if "\n" in text[max(spans[boundary - 1].start, left - 1) : right]:
                        preferred = boundary
            if preferred is not None:
                end_index = preferred
        start_cp = 0 if start_index == 0 else spans[start_index].start
        while end_index > start_index:
            # Include gaps verbatim, including whitespace and combining marks;
            # source coverage is never reconstructed by joining decoded tokens.
            end_cp = spans[end_index].start if end_index < len(spans) else len(text)
            encoded, _ = _encoding(prefix + text[start_cp:end_cp], tokenizer)
            token_count = len(encoded.token_ids)
            if token_count <= max_tokens:
                break
            end_index -= 1
        else:
            raise ChunkingError("chunk_indivisible_span_exceeds_token_budget")
        if end_cp <= previous_end_cp or start_cp > previous_end_cp:
            raise ChunkingError("chunk_coverage_cannot_progress")
        chunks.append(TextChunk(len(chunks), start_cp, end_cp, token_count, text[start_cp:end_cp]))
        previous_end_cp = end_cp
        if end_index == len(spans):
            break
        next_start = end_index
        overlap = 0
        while next_start > start_index + 1:
            candidate = overlap + spans[next_start - 1].tokens
            if candidate > overlap_tokens:
                break
            next_start -= 1
            overlap = candidate
        start_index = next_start
    if previous_end_cp != len(text):
        raise ChunkingError("chunk_incomplete_coverage")
    return tuple(chunks)
