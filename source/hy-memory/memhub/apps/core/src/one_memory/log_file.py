import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Enough history to cover the run before the one being complained about,
# capped so that a machine left running for months does not fill up.
MAX_BYTES = 4 * 1024 * 1024
KEEP = 3


def log_path(data_dir: Path) -> Path:
    return data_dir / "logs" / "core.log"


def start_logging_to_file(data_dir: Path) -> Path:
    """Also write the log to a file the user can find.

    Core inherits its parent's output streams, so when the app is launched
    the normal way — from the Dock, by launchd — everything it says goes
    nowhere. That includes the loop watchdog: the one report that names what
    stalled the app was unreadable in exactly the situation it exists for.

    The active diagnostic collection level controls Core, HY SDK, and provider
    client records. Uvicorn keeps its request log on its own non-propagating
    loggers.
    """
    destination = log_path(data_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for existing in root.handlers:
        if (
            isinstance(existing, RotatingFileHandler)
            and Path(existing.baseFilename) == destination.resolve()
        ):
            return destination
    handler = RotatingFileHandler(
        destination,
        maxBytes=MAX_BYTES,
        backupCount=KEEP,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    return destination
