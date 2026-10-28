"""Mac search and received-file hints on synthetic data; no real vault or configuration."""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
import uuid

import zstandard

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import vault_cli
from message_display import file_attachment_size
from fixture_factory import ALICE, build

ARTIFACT_ROOT = Path(os.environ.get("YICHEN_WECHAT_TEST_ROOT") or tempfile.mkdtemp(prefix="wechat-search-tests-")).resolve()
FILE_TYPE = (6 << 32) | 49
LINK_TYPE = (5 << 32) | 49


def file_xml(title: str, size: int | None = None) -> str:
    attach = f"<appattach><totallen>{size}</totallen><fileext>zip</fileext></appattach>" if size is not None else ""
    return f"<msg><appmsg><title>{title}</title><type>6</type>{attach}</appmsg></msg>"


def packed(text: str) -> bytes:
    return zstandard.ZstdCompressor().compress(text.encode("utf-8"))


class MacSearchTests(unittest.TestCase):
    def setUp(self):
        self.root = ARTIFACT_ROOT / (self._testMethodName + "-" + uuid.uuid4().hex) / "vault"
        build(self.root)
        table = vault_cli.message_table(ALICE)
        rows = [
            (1, 1, 1, 1000, 2, "很早以前提到的星河计划", 0),
            (2, 2, 1, 1001, 2, packed("压缩存储的长文本，也提到了星河"), 4),
            (3, 3, FILE_TYPE, 1002, 2, packed(file_xml("yt-studio-v1.0.zip", 87778)), 4),
            (4, 4, 3, 1003, 2, packed('<msg><img length="1"/></msg>'), 4),
            (5, 5, FILE_TYPE, 1004, 2, packed(file_xml("notes.zip")), 4),
            (6, 6, LINK_TYPE, 1005, 2, packed("<msg><appmsg><title>A&amp;B 指南</title><type>5</type></appmsg></msg>"), 4),
        ]
        rows += [(100 + i, 100 + i, 1, 2000 + i, 2, f"无关消息 {i}", 0) for i in range(60)]
        con = sqlite3.connect(self.root / "message/message_0.db")
        try:
            con.execute(f"CREATE TABLE [{table}](local_id INTEGER,server_id INTEGER,local_type INTEGER,create_time INTEGER,real_sender_id INTEGER,message_content BLOB,compress_content BLOB,WCDB_CT_message_content INTEGER)")
            con.executemany(f"INSERT INTO [{table}] VALUES(?,?,?,?,?,?,NULL,?)", rows)
            con.commit()
        finally:
            con.close()

    def search(self, *argv):
        out = io.StringIO()
        with mock.patch.object(vault_cli, "load_config", return_value={}), redirect_stdout(out):
            code = vault_cli.main(["--decrypted-dir", str(self.root), "search", *argv]) or 0
        self.assertEqual(code, 0)
        return [message["content"] for message in json.loads(out.getvalue())["messages"]]

    def test_global_search_reads_compressed_text_and_file_names(self):
        self.assertEqual(self.search("星河"), ["很早以前提到的星河计划", "压缩存储的长文本，也提到了星河"])
        self.assertEqual(self.search("yt-studio"), ["[文件] yt-studio-v1.0.zip"])
        self.assertEqual(self.search("zip", "--type", "file"), ["[文件] yt-studio-v1.0.zip", "[文件] notes.zip"])

    def test_labels_and_placeholders_alone_are_not_matches(self):
        self.assertEqual(self.search("文件"), [])
        self.assertEqual(self.search("图片"), [])

    def test_keyword_with_escaped_characters_matches_rendered_title(self):
        self.assertEqual(self.search("A&B"), ["[链接] A&B 指南"])

    def test_chat_search_reaches_messages_older_than_the_limit(self):
        self.assertEqual(self.search("星河", "--chat", ALICE, "--limit", "1"), ["压缩存储的长文本，也提到了星河"])
        self.assertEqual(self.search("星河", "--chat", ALICE, "--limit", "5"), ["很早以前提到的星河计划", "压缩存储的长文本，也提到了星河"])
        self.assertEqual(self.search("yt-studio", "--chat", ALICE, "--type", "file"), ["[文件] yt-studio-v1.0.zip"])


class ReceivedFilePathTests(unittest.TestCase):
    def setUp(self):
        base = ARTIFACT_ROOT / (self._testMethodName + "-" + uuid.uuid4().hex)
        self.db_dir = base / "db_storage"
        self.db_dir.mkdir(parents=True)
        self.month = base / "msg/file/2026-07"
        self.month.mkdir(parents=True)
        (self.month / "a.zip").write_bytes(b"x" * 10)
        (self.month / "a(1).zip").write_bytes(b"y" * 25)
        (self.month / "b(1).zip").write_bytes(b"z" * 7)
        self.ts = int(datetime(2026, 7, 30, 12).timestamp())

    def hint(self, xml):
        return vault_cli.media_hint(FILE_TYPE, xml, True, self.db_dir, ALICE, self.ts)

    def test_renamed_copy_is_found_by_recorded_size(self):
        self.assertEqual(self.hint(file_xml("a.zip", 25)), f"[文件] a.zip\n{self.month / 'a(1).zip'}")
        self.assertEqual(self.hint(file_xml("a.zip", 10)), f"[文件] a.zip\n{self.month / 'a.zip'}")
        self.assertEqual(self.hint(file_xml("b.zip", 7)), f"[文件] b.zip\n{self.month / 'b(1).zip'}")

    def test_mismatched_or_unknown_size_never_guesses_a_renamed_copy(self):
        self.assertEqual(self.hint(file_xml("a.zip", 99)), "[文件] a.zip")
        self.assertEqual(self.hint(file_xml("a.zip")), f"[文件] a.zip\n{self.month / 'a.zip'}")
        self.assertEqual(self.hint(file_xml("b.zip")), "[文件] b.zip")

    def test_titles_cannot_leave_the_month_directory(self):
        (self.month.parent / "escape.zip").write_bytes(b"e" * 3)
        self.assertEqual(self.hint(file_xml("../escape.zip", 3)), "[文件] ../escape.zip")

    def test_size_comes_only_from_a_numeric_attachment_length(self):
        self.assertEqual(file_attachment_size(file_xml("a.zip", 25)), 25)
        self.assertIsNone(file_attachment_size(file_xml("a.zip")))
        self.assertIsNone(file_attachment_size("plain text"))
        self.assertIsNone(file_attachment_size("<msg><appmsg><appattach><totallen>12x</totallen></appattach></appmsg></msg>"))


if __name__ == "__main__":
    unittest.main()
