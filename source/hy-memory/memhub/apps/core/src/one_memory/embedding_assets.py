"""What the built-in embedding model consists of, and how we vouch for it.

The weights are not in git: the repository is going public and a 24MB binary
does not belong in its history. They are fetched at build time by
`scripts/fetch_embedding_model.py` and checked against the digests below, so
what ships is pinned here even though the bytes are not.

Source is a mechanical ONNX export of `BAAI/bge-small-zh-v1.5`, which is MIT.
The export repository states its `base_model` but declares no licence of its
own; see OPEN-ITEMS A-32 before the release audit.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

BUILTIN_EMBEDDING_MODEL = "bge-small-zh-v1.5"
BUILTIN_EMBEDDING_DIMENSIONS = 512
BUILTIN_EMBEDDING_MAX_TOKENS = 512

_SOURCE = "https://huggingface.co/Xenova/bge-small-zh-v1.5/resolve/main"


@dataclass(frozen=True)
class EmbeddingAsset:
    filename: str
    url: str
    sha256: str


EMBEDDING_ASSETS: tuple[EmbeddingAsset, ...] = (
    EmbeddingAsset(
        "model_int8.onnx",
        f"{_SOURCE}/onnx/model_int8.onnx",
        "b9837c19ce154ff0726d398ee77abbc03a7faf0476c6f93016c84e531be7ebb5",
    ),
    EmbeddingAsset(
        "tokenizer.json",
        f"{_SOURCE}/tokenizer.json",
        "48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26",
    ),
    EmbeddingAsset(
        "config.json",
        f"{_SOURCE}/config.json",
        "d4193ead3a810fd694fa8a31d7fc72fbaebc0668b603e398734bf2f6538ff42f",
    ),
    EmbeddingAsset(
        "tokenizer_config.json",
        f"{_SOURCE}/tokenizer_config.json",
        "e6f3b96db926a37d4039995fbf5ad17de158dfb8f6343d607e4dbaad18d75f5a",
    ),
    EmbeddingAsset(
        "special_tokens_map.json",
        f"{_SOURCE}/special_tokens_map.json",
        "b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3",
    ),
)

ASSET_DIR_NAME = "embedding_assets"


class AssetVerificationError(RuntimeError):
    """An asset is absent, or its bytes are not the bytes we vouched for."""


class MissingEmbeddingAssetsError(RuntimeError):
    """The built-in model was never fetched into this tree."""


def resolve_asset_dir() -> Path:
    """Where the model files live, in the product and in a source checkout.

    PyInstaller unpacks bundled data under `sys._MEIPASS`, so a frozen build
    must look there: resolving relative to this file would point inside the
    archive, which exists at build time and not at run time.
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle is not None:
        return Path(bundle) / "one_memory" / ASSET_DIR_NAME
    return Path(__file__).resolve().parent / ASSET_DIR_NAME


def assets_present(directory: Path | None = None) -> bool:
    root = directory if directory is not None else resolve_asset_dir()
    return all((root / asset.filename).is_file() for asset in EMBEDDING_ASSETS)


def digest_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_assets(directory: Path | None = None) -> None:
    """Raise unless every declared asset is present with the declared digest."""
    root = directory if directory is not None else resolve_asset_dir()
    problems: list[str] = []
    for asset in EMBEDDING_ASSETS:
        path = root / asset.filename
        if not path.is_file():
            problems.append(f"{asset.filename}: missing")
            continue
        actual = digest_of(path)
        if actual != asset.sha256:
            problems.append(f"{asset.filename}: sha256 {actual} does not match {asset.sha256}")
    if problems:
        raise AssetVerificationError("; ".join(problems))
