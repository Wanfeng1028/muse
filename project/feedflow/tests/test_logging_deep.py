import io
import json
import logging

import pytest

from feedflow import logging as ff_logging


@pytest.fixture
def clean_root_logger():
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    for handler in list(root.handlers):
        root.removeHandler(handler)
    yield root
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)


@pytest.fixture
def captured_lines(clean_root_logger, capsys):
    ff_logging.setup_logging("INFO")
    stream = io.StringIO()
    for handler in logging.getLogger().handlers:
        handler.stream = stream
    yield stream
    ff_logging.clear_request_id()


def _read_json_lines(stream):
    out = stream.getvalue()
    lines = [line for line in out.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_request_id_roundtrip_and_clear():
    assert ff_logging.get_request_id() is None
    token = ff_logging.set_request_id("req-abc-123")
    assert ff_logging.get_request_id() == "req-abc-123"
    ff_logging.clear_request_id()
    assert ff_logging.get_request_id() is None
    assert token is not None


def test_json_formatter_basic_fields(captured_lines):
    logger = ff_logging.get_logger("feedflow.test.basic")
    logger.info("抓取完成 %s 条", 7)
    records = _read_json_lines(captured_lines)
    assert len(records) == 1
    payload = records[0]
    assert payload["level"] == "INFO"
    assert payload["logger"] == "feedflow.test.basic"
    assert payload["msg"] == "抓取完成 7 条"
    assert payload["request_id"] is None
    assert payload["extra"] is None
    assert "ts" in payload and payload["ts"].endswith("+00:00")


def test_json_formatter_includes_request_id(captured_lines):
    ff_logging.set_request_id("trace-42")
    logger = ff_logging.get_logger("feedflow.test.rid")
    logger.warning("限流命中")
    records = _read_json_lines(captured_lines)
    assert len(records) == 1
    assert records[0]["request_id"] == "trace-42"
    assert records[0]["level"] == "WARNING"
    assert records[0]["msg"] == "限流命中"


def test_json_formatter_extra_serializable_fields(captured_lines):
    logger = ff_logging.get_logger("feedflow.test.extra")
    logger.info("抓取失败", extra={"feed_id": 11, "status": 404, "url": "http://x/y"})
    records = _read_json_lines(captured_lines)
    assert len(records) == 1
    extra = records[0]["extra"]
    assert extra["feed_id"] == 11
    assert extra["status"] == 404
    assert extra["url"] == "http://x/y"


def test_json_formatter_extra_unserializable_becomes_repr(captured_lines):
    logger = ff_logging.get_logger("feedflow.test.unserializable")
    logger.info("对象字段", extra={"obj": object()})
    records = _read_json_lines(captured_lines)
    assert len(records) == 1
    extra = records[0]["extra"]
    assert "obj" in extra
    assert isinstance(extra["obj"], str)
    assert extra["obj"].startswith("<object object at")


def test_json_formatter_keeps_chinese_unencoded(captured_lines):
    logger = ff_logging.get_logger("feedflow.test.chinese")
    logger.info("标题党变体去重 相似标题聚类")
    out = captured_lines.getvalue()
    assert "标题党变体去重 相似标题聚类" in out
    records = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert records[0]["msg"] == "标题党变体去重 相似标题聚类"


def test_json_formatter_handles_bad_placeholder():
    formatter = ff_logging.JsonFormatter()
    record = logging.LogRecord(
        "feedflow.test.badfmt", logging.INFO, __file__, 108,
        "畸形 XML %d 解析失败", ("not-a-number",), None,
    )
    payload = json.loads(formatter.format(record))
    assert "畸形 XML" in payload["msg"]
    assert "解析失败" in payload["msg"]


def test_json_formatter_includes_exception(captured_lines):
    logger = ff_logging.get_logger("feedflow.test.exc")
    try:
        raise TimeoutError("抓取超时")
    except TimeoutError:
        logger.exception("抓取失败")
    records = _read_json_lines(captured_lines)
    assert len(records) == 1
    assert records[0]["level"] == "ERROR"
    assert records[0]["msg"] == "抓取失败"
    assert "TimeoutError" in records[0]["extra"]["exc_info"]
    assert "抓取超时" in records[0]["extra"]["exc_info"]


def test_setup_logging_no_duplicate_handlers(clean_root_logger):
    ff_logging.setup_logging("INFO")
    ff_logging.setup_logging("INFO")
    ff_logging.setup_logging("DEBUG")
    root = logging.getLogger()
    json_handlers = [
        h for h in root.handlers if getattr(h, "_feedflow_json_handler", False)
    ]
    assert len(json_handlers) == 1
    assert root.level == logging.DEBUG
    assert json_handlers[0].level == logging.DEBUG


def test_setup_logging_invalid_level_falls_back_to_info(clean_root_logger):
    ff_logging.setup_logging("not-a-level")
    root = logging.getLogger()
    assert root.level == logging.INFO
    json_handlers = [
        h for h in root.handlers if getattr(h, "_feedflow_json_handler", False)
    ]
    assert len(json_handlers) == 1
    assert json_handlers[0].level == logging.INFO


def test_setup_logging_non_string_level_uses_info(clean_root_logger):
    ff_logging.setup_logging(12345)
    root = logging.getLogger()
    assert root.level == logging.INFO
    json_handlers = [
        h for h in root.handlers if getattr(h, "_feedflow_json_handler", False)
    ]
    assert len(json_handlers) == 1


def test_setup_logging_filters_below_level(captured_lines):
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    for handler in root.handlers:
        handler.setLevel(logging.WARNING)
    logger = ff_logging.get_logger("feedflow.test.filter")
    logger.debug("调试细节")
    logger.info("普通信息")
    logger.warning("限流告警")
    records = _read_json_lines(captured_lines)
    assert len(records) == 1
    assert records[0]["level"] == "WARNING"
    assert records[0]["msg"] == "限流告警"


def test_logger_names_are_independent(captured_lines):
    a = ff_logging.get_logger("feedflow.test.a")
    b = ff_logging.get_logger("feedflow.test.b")
    assert a is logging.getLogger("feedflow.test.a")
    assert b is logging.getLogger("feedflow.test.b")
    a.info("feed a")
    b.info("feed b")
    records = _read_json_lines(captured_lines)
    names = [r["logger"] for r in records]
    assert names == ["feedflow.test.a", "feedflow.test.b"]


def test_multiple_lines_are_independent_json(captured_lines):
    logger = ff_logging.get_logger("feedflow.test.multi")
    logger.info("空 feed 跳过")
    logger.error("超大 feed 截断", extra={"size": 1024})
    records = _read_json_lines(captured_lines)
    assert len(records) == 2
    assert records[0]["msg"] == "空 feed 跳过"
    assert records[0]["extra"] is None
    assert records[1]["msg"] == "超大 feed 截断"
    assert records[1]["extra"]["size"] == 1024