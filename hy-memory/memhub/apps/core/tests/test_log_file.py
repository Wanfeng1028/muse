import logging

from one_memory.log_file import KEEP, MAX_BYTES, log_path, start_logging_to_file


def _detach(destination) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "baseFilename", None) == str(destination.resolve()):
            root.removeHandler(handler)
            handler.close()


def test_what_the_watchdog_says_survives_a_dock_launch(tmp_path) -> None:
    """The app inherits its parent's output, which the Dock throws away.

    A stall report that names the blocking call is the whole point of the
    watchdog, and it was being written to a stream nobody could read whenever
    the app was started the way users start it.
    """
    destination = start_logging_to_file(tmp_path)
    try:
        logging.getLogger("one_memory.loop_watchdog").warning("event loop blocked for 2.7s")
    finally:
        _detach(destination)

    written = destination.read_text(encoding="utf-8")
    assert "event loop blocked for 2.7s" in written
    assert "one_memory.loop_watchdog" in written
    # Timestamped, or a report cannot be lined up with what the user saw.
    assert "WARNING" in written


def test_the_log_lives_where_the_data_does(tmp_path) -> None:
    assert log_path(tmp_path) == tmp_path / "logs" / "core.log"
    start_logging_to_file(tmp_path)
    try:
        assert (tmp_path / "logs" / "core.log").exists()
    finally:
        _detach(log_path(tmp_path))


def test_a_machine_left_running_for_months_does_not_fill_up(tmp_path) -> None:
    """Unbounded logs are their own outage, so this is capped and rotated."""
    destination = start_logging_to_file(tmp_path)
    logger = logging.getLogger("one_memory.noisy")
    try:
        line = "x" * 4096
        for _ in range(4000):
            logger.info(line)
    finally:
        _detach(destination)

    written = sorted(path.name for path in (tmp_path / "logs").iterdir())
    assert written == ["core.log", "core.log.1", "core.log.2", "core.log.3"]
    total = sum(path.stat().st_size for path in (tmp_path / "logs").iterdir())
    assert total < MAX_BYTES * (KEEP + 2)


def test_starting_twice_does_not_write_everything_twice(tmp_path) -> None:
    """Core is restarted in place after a crash; handlers must not stack up."""
    destination = start_logging_to_file(tmp_path)
    again = start_logging_to_file(tmp_path)
    try:
        assert again == destination
        logging.getLogger("one_memory.once").warning("只应出现一次")
    finally:
        _detach(destination)

    assert destination.read_text(encoding="utf-8").count("只应出现一次") == 1
