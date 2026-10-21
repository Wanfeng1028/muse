import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest

from one_memory import local_embedding
from one_memory.embedding_assets import AssetVerificationError, resolve_asset_dir
from one_memory.local_embedding import LocalEmbedder, TokenizedText


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refused(*args, **kwargs):
        pytest.fail("local tokenizer/encoder attempted network")

    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr(socket, "create_connection", refused)


@pytest.mark.parametrize(
    "text", ["中文😀e\u0301末尾", "👩‍💻链接", "e\u0301 cafe\u0301", "URL路径 /Case/末尾"]
)
def test_real_locked_tokenizer_offsets_are_unicode_codepoints(text):
    embedder = LocalEmbedder()
    tokenized = embedder.tokenize_with_offsets(text)
    assert isinstance(tokenized, TokenizedText)
    assert isinstance(tokenized.token_ids, tuple) and isinstance(tokenized.offsets, tuple)
    ordinary = [offset for offset in tokenized.offsets if not offset.special]
    assert ordinary
    for offset in ordinary:
        assert 0 <= offset.start_cp < offset.end_cp <= len(text)
        assert text[offset.start_cp : offset.end_cp]
    assert all(
        any(o.start_cp <= i < o.end_cp for o in ordinary)
        for i, character in enumerate(text)
        if not character.isspace()
    )
    assert embedder._session is None and embedder._tokenizer is None
    with pytest.raises(FrozenInstanceError):
        ordinary[0].start_cp = 10


def test_known_emoji_and_combining_offsets_are_not_utf8_or_utf16_units():
    value = LocalEmbedder().tokenize_with_offsets("中文😀e\u0301末尾")
    offsets = [(o.start_cp, o.end_cp) for o in value.offsets if not o.special]
    assert offsets == [(0, 1), (1, 2), (2, 5), (5, 6), (6, 7)]


def test_offsets_are_not_truncated_or_padded_and_do_not_create_onnx_session(monkeypatch):
    monkeypatch.setattr(local_embedding, "import_module", lambda *args: pytest.fail("ONNX load"))
    embedder = LocalEmbedder()
    long = embedder.tokenize_with_offsets("中" * 1600)
    short = embedder.tokenize_with_offsets("中")
    empty = embedder.tokenize_with_offsets("")
    assert len(long.token_ids) == 1602
    assert len(short.token_ids) == 3
    assert len(empty.token_ids) == 2
    assert all(o.special for o in empty.offsets)
    assert long.offsets[-2].end_cp == 1600
    assert embedder._session is None


def test_parallel_offset_calls_share_one_lazy_tokenizer_without_shared_encoder_mutation():
    embedder = LocalEmbedder()
    texts = ["中" * 700, "😀中e\u0301", "short"] * 8
    with ThreadPoolExecutor(max_workers=8) as pool:
        actual = list(pool.map(embedder.tokenize_with_offsets, texts))
    assert actual == [embedder.tokenize_with_offsets(text) for text in texts]
    assert embedder._session is None and embedder._tokenizer is None


def test_offset_tokenizer_does_not_modify_encode_state_or_vectors():
    embedder = LocalEmbedder()
    baseline = embedder.encode(["原有编码必须保持", "短句"])
    session, tokenizer = embedder._session, embedder._tokenizer
    truncation, padding = tokenizer.truncation.copy(), tokenizer.padding.copy()
    with ThreadPoolExecutor(max_workers=4) as pool:
        tokenized = pool.submit(embedder.tokenize_with_offsets, "中" * 1100)
        encoded = pool.submit(embedder.encode, ["原有编码必须保持", "短句"])
        assert len(tokenized.result().token_ids) == 1102
        assert encoded.result() == baseline
    assert embedder._session is session and embedder._tokenizer is tokenizer
    assert tokenizer.truncation == truncation and tokenizer.padding == padding
    assert len(tokenizer.encode("中" * 1100).ids) == 512


def test_offset_assets_reject_unlocked_tokenizer_without_loading_weights(tmp_path, monkeypatch):
    (tmp_path / "tokenizer.json").write_bytes(b'{"invalid":"not locked"}')
    monkeypatch.setattr(local_embedding, "resolve_asset_dir", lambda: tmp_path)
    with pytest.raises(AssetVerificationError):
        LocalEmbedder().tokenize_with_offsets("中")


def test_offset_tokenization_uses_only_tokenizer_asset(tmp_path, monkeypatch):
    # Tokenization must not require another ONNX session or even the weights file.
    (tmp_path / "tokenizer.json").write_bytes((resolve_asset_dir() / "tokenizer.json").read_bytes())
    monkeypatch.setattr(local_embedding, "resolve_asset_dir", lambda: tmp_path)
    assert len(LocalEmbedder().tokenize_with_offsets("中文").token_ids) == 4


def test_real_adjacent_wordpieces_and_long_ascii_unknown_keep_original_offsets():
    embedder = LocalEmbedder()
    word = "unaffordable"
    parts = [o for o in embedder.tokenize_with_offsets(word).offsets if not o.special]
    assert len(parts) > 1
    assert parts[0].start_cp == 0 and parts[-1].end_cp == len(word)
    assert all(a.end_cp == b.start_cp for a, b in zip(parts, parts[1:], strict=False))
    long_word = "x" * 6000
    unknown = embedder.tokenize_with_offsets(long_word)
    offsets = [o for o in unknown.offsets if not o.special]
    assert len(offsets) == 1 and unknown.token_ids[1] == 100  # locked BERT [UNK]
    assert (offsets[0].start_cp, offsets[0].end_cp) == (0, 6000)


def test_parallel_initial_load_constructs_one_offsets_tokenizer(monkeypatch):
    from tokenizers import Tokenizer

    calls = []
    original = Tokenizer.from_str

    def counted(value):
        calls.append(1)
        return original(value)

    monkeypatch.setattr(Tokenizer, "from_str", counted)
    embedder = LocalEmbedder()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(embedder.tokenize_with_offsets, ["中😀e\u0301"] * 16))
    assert len(calls) == 1
    assert all(value == results[0] for value in results)
    assert embedder._session is None
