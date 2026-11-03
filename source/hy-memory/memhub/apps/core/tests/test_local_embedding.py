"""Guards for the built-in embedding model.

The point of building this in is that a new user generates memories without
configuring anything, so these tests care about two things above accuracy:
the files we ship are the files we vouched for, and encoding never reaches
the network.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from one_memory.embedding_assets import (
    BUILTIN_EMBEDDING_DIMENSIONS,
    EMBEDDING_ASSETS,
    AssetVerificationError,
    MissingEmbeddingAssetsError,
    assets_present,
    resolve_asset_dir,
    verify_assets,
)
from one_memory.local_embedding import LocalEmbedder

requires_assets = pytest.mark.skipif(
    not assets_present(),
    reason="built-in model not fetched; run scripts/fetch_embedding_model.py",
)


def _write_assets(target: Path, source: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for asset in EMBEDDING_ASSETS:
        (target / asset.filename).write_bytes((source / asset.filename).read_bytes())


class TestAssetManifest:
    def test_manifest_covers_every_file_the_encoder_opens(self) -> None:
        # A manifest that omits a file the encoder loads would still verify
        # clean while shipping something unvouched for.
        named = {asset.filename for asset in EMBEDDING_ASSETS}
        assert named >= LocalEmbedder.REQUIRED_FILES

    def test_every_asset_declares_a_sha256_and_a_source(self) -> None:
        for asset in EMBEDDING_ASSETS:
            assert len(asset.sha256) == 64, asset.filename
            assert asset.url.startswith("https://"), asset.filename

    def test_declared_dimensions_match_the_model_card(self) -> None:
        assert BUILTIN_EMBEDDING_DIMENSIONS == 512


class TestVerification:
    @requires_assets
    def test_intact_assets_verify(self, tmp_path: Path) -> None:
        # Positive control. Without it, a verifier that always raised would
        # make the corruption test below pass for the wrong reason.
        _write_assets(tmp_path, resolve_asset_dir())
        verify_assets(tmp_path)

    @requires_assets
    def test_a_single_flipped_byte_is_rejected(self, tmp_path: Path) -> None:
        _write_assets(tmp_path, resolve_asset_dir())
        target = tmp_path / "config.json"
        payload = bytearray(target.read_bytes())
        payload[0] ^= 0x01
        target.write_bytes(bytes(payload))

        with pytest.raises(AssetVerificationError) as caught:
            verify_assets(tmp_path)
        assert "config.json" in str(caught.value)

    def test_a_missing_asset_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(AssetVerificationError):
            verify_assets(tmp_path)


class TestBundleResolution:
    def test_a_frozen_bundle_is_searched_before_the_source_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # PyInstaller unpacks data next to sys._MEIPASS. Resolving to the
        # source tree instead would work on this machine and fail in the
        # product, which is the failure mode worth a test.
        bundled = tmp_path / "_MEI" / "one_memory" / "embedding_assets"
        bundled.mkdir(parents=True)
        monkeypatch.setattr("sys._MEIPASS", str(tmp_path / "_MEI"), raising=False)
        monkeypatch.setattr("sys.frozen", True, raising=False)

        assert resolve_asset_dir() == bundled

    def test_the_source_tree_is_used_when_not_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delattr("sys._MEIPASS", raising=False)
        monkeypatch.delattr("sys.frozen", raising=False)

        resolved = resolve_asset_dir()
        assert resolved.name == "embedding_assets"
        assert resolved.parent.name == "one_memory"


class TestEncoding:
    @requires_assets
    def test_vectors_are_512_wide_and_unit_length(self) -> None:
        vectors = LocalEmbedder().encode(["记忆系统", "另一段文字"])

        assert [len(vector) for vector in vectors] == [512, 512]
        for vector in vectors:
            length = sum(value * value for value in vector) ** 0.5
            assert length == pytest.approx(1.0, abs=1e-4)

    @requires_assets
    def test_related_text_scores_above_unrelated_text(self) -> None:
        # Without this, an encoder that returned a constant vector would pass
        # every shape assertion above.
        anchor, related, unrelated = LocalEmbedder().encode(
            [
                "记忆系统的向量宽度必须一致",
                "向量维度不匹配会导致图库被归档",
                "今天午饭吃的是牛肉面",
            ]
        )
        close = sum(a * b for a, b in zip(anchor, related, strict=True))
        far = sum(a * b for a, b in zip(anchor, unrelated, strict=True))

        assert close > far

    @requires_assets
    def test_the_same_text_encodes_identically_across_calls(self) -> None:
        embedder = LocalEmbedder()
        assert embedder.encode(["稳定性"]) == embedder.encode(["稳定性"])

    @requires_assets
    def test_encoding_opens_no_socket(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The whole reason to build the model in is that it works offline.
        # Blocking the socket layer is what proves it, rather than trusting
        # that no library reaches out on first use.
        def refuse(*args: object, **kwargs: object) -> None:
            raise AssertionError("encoding attempted a network connection")

        monkeypatch.setattr(socket.socket, "connect", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)

        # Built fresh under the block on purpose, so loading the weights and
        # the tokenizer is covered too. Warming it up first would leave the
        # one path most likely to reach out, resolving a model by name,
        # untested.
        assert len(LocalEmbedder().encode(["断网之后仍然要能编码"])[0]) == 512

    def test_absent_assets_fail_with_an_actionable_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # This one runs even on a machine that never fetched the model, so a
        # skipped suite still says something about the missing-asset path.
        monkeypatch.setattr("one_memory.local_embedding.resolve_asset_dir", lambda: tmp_path)

        with pytest.raises(MissingEmbeddingAssetsError) as caught:
            LocalEmbedder().encode(["任意文本"])
        assert "fetch_embedding_model" in str(caught.value)
