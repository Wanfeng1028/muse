from pathlib import Path

from verify_public_snapshot import scan_snapshot


def test_accepts_reviewed_snapshot_and_pinned_large_font(tmp_path: Path) -> None:
    (tmp_path / ".npmrc").write_text("save-exact=true\n", encoding="utf-8")
    source = Path(__file__).resolve().parents[1] / "apps/web/public/fonts/NotoSansSC-wght.ttf"
    target = tmp_path / "apps/web/public/fonts/NotoSansSC-wght.ttf"
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())

    receipt = scan_snapshot(tmp_path)

    assert receipt["result"] == "passed"
    assert receipt["approved_large_files"] == [
        "apps/web/public/fonts/NotoSansSC-wght.ttf"
    ]


def test_rejects_secrets_sensitive_names_large_files_and_escaping_links(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env.production").write_text("TOKEN=secret\n", encoding="utf-8")
    (tmp_path / "leak.txt").write_text(
        "//registry.example/:_auth"
        + "Token=github_"
        + "pat_"
        + "A" * 45
        + "\n-----BEGIN PRIVATE KEY-----\n"
        + "MIIE" * 32
        + "\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    (tmp_path / "large.bin").write_bytes(b"x" * (10 * 1024 * 1024 + 1))
    (tmp_path / "escape").symlink_to(tmp_path.parent / "outside")

    receipt = scan_snapshot(tmp_path)

    assert receipt["result"] == "failed"
    failures = receipt["failures"]
    assert any(value.startswith("public_sensitive_filename:") for value in failures)
    assert any("public_secret_pattern:npm_auth_token" in value for value in failures)
    assert any("public_secret_pattern:github_token" in value for value in failures)
    assert any("public_secret_pattern:private_key" in value for value in failures)
    assert any(value.startswith("public_large_file_unapproved:") for value in failures)
    assert any(value.startswith("public_symlink_escapes:") for value in failures)
