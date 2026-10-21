"""Display name MemHub must not fork the technical identity."""

from pathlib import Path

import one_memory.cli as cli
from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.secrets import SERVICE_NAME


def test_display_name_does_not_choose_the_data_directory_or_keychain(tmp_path: Path) -> None:
    default = Settings.model_fields["data_dir"].default
    assert isinstance(default, Path)
    assert default.name == ".one-memory"
    assert ".memhub" not in default.as_posix()
    assert SERVICE_NAME == "one-memory"
    app = create_app(Settings(_env_file=None, data_dir=tmp_path))
    assert app.title == "MemHub Core"


def test_cli_help_keeps_the_existing_command() -> None:
    import io

    output = io.StringIO()
    assert cli.run(["install"], output=output) == 2
    text = output.getvalue()
    assert text.startswith("Usage: one-memory")
    assert "Usage: memhub" not in text
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    scripts = pyproject.read_text().split("[project.scripts]", 1)[1].split("[", 1)[0]
    assert "memhub =" not in scripts
    assert 'one-memory = "one_memory.cli:main"' in scripts
