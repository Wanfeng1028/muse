"""Synthetic privacy and readable-content regressions; never read a real vault."""

from __future__ import annotations

import copy
from datetime import datetime
import html
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import export_chat
import message_display as display
import vault_cli
from fixture_factory import build, GROUP, ALICE
from test_vault_integration import fingerprint, invoke

ARTIFACT_ROOT = Path(os.environ.get("YICHEN_WECHAT_TEST_ROOT") or tempfile.mkdtemp(prefix="wechat-message-display-tests-")).resolve()
SECRET = "SYNTHETIC_ATTACHMENT_CREDENTIAL_82741"
FILE_ID = "SYNTHETIC_FILE_LOCATOR_61985"
BIO = "名称：测试成员\n个人介绍：独立开发者，做开源教育工具。"
JOIN = f'''<?xml version="1.0"?>
<sysmsg type="sysmsgtemplate"><sysmsgtemplate><content_template>
<plain></plain><template><![CDATA["$username$"邀请"$names$"加入了群聊，并分享了$history$ $revoke$]]></template>
<link_list>
<link name="username"><memberlist><member><username>custom_owner_identifier</username><nickname>测试群主</nickname></member></memberlist></link>
<link name="names"><memberlist><member><username>{ALICE}</username><nickname>测试成员</nickname></member></memberlist></link>
<link name="history"><title>12条聊天记录</title><fileid>{FILE_ID}</fileid><aeskey>{SECRET}</aeskey></link>
<link name="revoke" hidden="1"><title>撤销</title><usernamelist><username>{ALICE}</username></usernamelist></link>
</link_list></content_template></sysmsgtemplate></sysmsg>'''
APP = f'''<msg><appmsg><title><![CDATA[{BIO}]]></title><type>57</type><appattach><aeskey>{SECRET}</aeskey><fileid>{FILE_ID}</fileid></appattach></appmsg></msg>'''
RECORD = f'''<recordinfo><title>介绍记录</title><datalist><dataitem datatype="1"><sourcename>测试成员</sourcename><datadesc>{BIO}</datadesc><dataitemsource><fromusr>{ALICE}</fromusr></dataitemsource></dataitem><dataitem datatype="2"><datatitle>附图</datatitle><cdn_dataurl>https://cdn.invalid/?token={SECRET}</cdn_dataurl></dataitem></datalist></recordinfo>'''
FORWARD = f'''<msg><appmsg><title>群聊的聊天记录</title><type>19</type><recorditem><![CDATA[{RECORD}]]></recorditem><aeskey>{SECRET}</aeskey></appmsg></msg>'''
NESTED_BIO = "名称：嵌套成员\n个人介绍：制作社区协作地图。"
NESTED_RECORD = RECORD.replace(BIO, NESTED_BIO)
OUTER_RECORD = f'''<recordinfo><datalist><dataitem datatype="17"><sourcename>转发者</sourcename><datatitle>二次转发</datatitle><recorditem>{html.escape(NESTED_RECORD)}</recorditem></dataitem></datalist></recordinfo>'''
NESTED_FORWARD = f'''<msg><appmsg><title>嵌套聊天记录</title><type>19</type><recorditem>{html.escape(OUTER_RECORD)}</recorditem></appmsg></msg>'''


class PrivacyAssertions:
    def assert_private_fields_absent(self, text):
        for marker in (SECRET, FILE_ID, ALICE, GROUP, "custom_owner_identifier", "<sysmsg", "<appmsg", "<aeskey"):
            self.assertNotIn(marker, text)


class SafeMessageTests(PrivacyAssertions, unittest.TestCase):

    def test_prefixed_system_template_preserves_names_and_event(self):
        for prefix in ("", GROUP + ":\n", GROUP + ":\r\n", "wxid_sender_fixture:\n"):
            with self.subTest(prefix=prefix):
                text = display.format_message_content(10000, prefix + JOIN)
                self.assert_private_fields_absent(text)
                for expected in ("测试群主", "测试成员", "加入了群聊", "12条聊天记录"):
                    self.assertIn(expected, text)
                self.assertNotIn("$", text)
                self.assertNotIn("撤销", text)

    def test_plain_system_and_revoke_notices_remain_readable(self):
        for kind, payload, expected in (
            (10000, '<sysmsg><plain>测试成员修改了群名</plain></sysmsg>', '测试成员修改了群名'),
            (10002, f'<sysmsg type="revokemsg"><revokemsg><session>{ALICE}</session><replacemsg>测试成员撤回了一条消息</replacemsg></revokemsg></sysmsg>', '测试成员撤回了一条消息'),
            (10000, '测试成员加入了群聊', '测试成员加入了群聊'),
        ):
            self.assertEqual(display.format_message_content(kind, payload), expected)

    def test_message_body_in_title_is_preserved(self):
        text = display.format_message_content(49, APP)
        self.assertIn(BIO, text)
        self.assert_private_fields_absent(text)

    def test_merged_forward_preserves_searchable_introduction(self):
        text = display.format_message_content(49, FORWARD)
        self.assertIn(BIO, text)
        self.assertIn('测试成员:', text)
        self.assert_private_fields_absent(text)

    def test_nested_forward_preserves_body_once_for_supported_encodings(self):
        nested_payloads = [
            f'<recorditem>{html.escape(NESTED_RECORD)}</recorditem>',
            f'<recorditem>{html.escape(html.escape(NESTED_RECORD))}</recorditem>',
            f'<recorditem><![CDATA[{NESTED_RECORD}]]></recorditem>',
            f'<recorditem>{NESTED_RECORD}</recorditem>',
            NESTED_RECORD,
        ]
        for nested in nested_payloads:
            with self.subTest(nested=nested[:30]):
                record = f'<recordinfo><datalist><dataitem datatype="17"><datatitle>二次转发</datatitle>{nested}</dataitem></datalist></recordinfo>'
                payload = f'<msg><appmsg><title>嵌套聊天记录</title><type>19</type><recorditem>{html.escape(record)}</recorditem></appmsg></msg>'
                text = display.format_message_content(49, payload)
                self.assertEqual(text.count(NESTED_BIO), 1)
                self.assertIn('二次转发', text)
                self.assert_private_fields_absent(text)

    def test_nested_forward_limits_depth_items_and_malformed_content(self):
        record = NESTED_RECORD
        for _ in range(display.MAX_FORWARD_DEPTH + 2):
            record = f'<recordinfo><datalist><dataitem datatype="17"><recordinfo>{record.removeprefix("<recordinfo>").removesuffix("</recordinfo>")}</recordinfo></dataitem></datalist></recordinfo>'
        payload = f'<msg><appmsg><type>19</type><recorditem>{record}</recorditem></appmsg></msg>'
        text = display.format_message_content(49, payload)
        self.assertIn('更深层转发内容已省略', text)
        self.assertNotIn(NESTED_BIO, text)
        self.assert_private_fields_absent(text)
        item = '<dataitem datatype="1"><datadesc>预算内文本</datadesc></dataitem>'
        many = '<recordinfo><datalist>' + item * (display.MAX_FORWARD_ITEMS + 2) + '</datalist></recordinfo>'
        payload = f'<msg><appmsg><type>19</type><recorditem>{many}</recorditem></appmsg></msg>'
        text = display.format_message_content(49, payload)
        self.assertEqual(text.count('预算内文本'), display.MAX_FORWARD_ITEMS)
        self.assertIn('其余转发内容已省略', text)
        malformed = html.escape(f'<recordinfo><aeskey>{SECRET}')
        broken = f'<recordinfo><datalist><dataitem datatype="17"><recorditem>{malformed}</recorditem></dataitem></datalist></recordinfo>'
        payload = f'<msg><appmsg><type>19</type><recorditem>{broken}</recorditem></appmsg></msg>'
        text = display.format_message_content(49, payload)
        self.assertIn('转发内容无法解析', text)
        self.assert_private_fields_absent(text)

    def test_malformed_unknown_and_entity_payloads_never_fall_back_to_xml(self):
        payloads = [
            (49, f'{GROUP}:\n<msg><appmsg aeskey="{SECRET}"><title>未闭合'),
            (10000, f'<sysmsg><aeskey>{SECRET}'),
            (10002, f'<sysmsg unknown="yes"><fileid>{FILE_ID}</fileid></sysmsg>'),
            (999, f'<unknown salt="{SECRET}" fileid="{FILE_ID}"/>'),
            (49, f'<!DOCTYPE msg [<!ENTITY leaked "{SECRET}">]><msg><appmsg><title>&leaked;</title></appmsg></msg>'),
            (1, f'<aeskey><![CDATA[{SECRET}]]></aeskey>'),
        ]
        for kind, payload in payloads:
            with self.subTest(kind=kind, payload=payload[:30]):
                result = display.format_message_content(kind, payload)
                self.assert_private_fields_absent(result)
                self.assertNotIn('<', result)

    def test_escaped_namespaced_and_embedded_envelopes_are_safe(self):
        for payload in (html.escape(JOIN), html.escape(html.escape(JOIN)), html.escape(html.escape(html.escape(JOIN)))):
            self.assert_private_fields_absent(display.format_message_content(10000, payload))
        namespaced = f'<w:msg xmlns:w="urn:fixture"><w:appmsg><w:title>{BIO}</w:title><w:type>6</w:type><w:aeskey>{SECRET}</w:aeskey></w:appmsg></w:msg>'
        self.assertIn(BIO, display.format_message_content((6 << 32) | 49, namespaced))
        embedded = f'<msg><appmsg><title><![CDATA[<aeskey>{SECRET}</aeskey>]]></title><type>5</type></appmsg></msg>'
        self.assert_private_fields_absent(display.format_message_content(49, embedded))
        deeply_escaped = html.escape(html.escape(f'<aeskey>{SECRET}</aeskey>'))
        payload = f'<msg><appmsg><title><![CDATA[{deeply_escaped}]]></title><type>5</type></appmsg></msg>'
        self.assert_private_fields_absent(display.format_message_content(49, payload))

    def test_metadata_title_is_not_mistaken_for_the_human_title(self):
        payload = f'<msg><appmsg><appattach><title>{SECRET}</title></appattach><title>{BIO}</title><type>5</type></appmsg></msg>'
        result = display.format_message_content(49, payload)
        self.assertIn(BIO, result)
        self.assert_private_fields_absent(result)

    def test_normal_text_headings_numbers_and_public_links_are_preserved(self):
        texts = [BIO, 'Introduction:\nI build learning tools.', 'a < b，2 > 1，价格299元',
                 '文档 https://example.com/guide?id=42，收益10%，日期2026-10-04',
                 '解释 &amp; 和 &lt; 的用法', '代码 <div>hello</div>']
        for text in texts:
            self.assertEqual(display.format_message_content(1, text), text)

    def test_explicit_credentials_are_hidden_without_erasing_other_text(self):
        for text in (f'aeskey="{SECRET}"，介绍正文', f'{{"newformataeskey":"{SECRET}"}}',
                     f'https://cdn.invalid/file?token={SECRET}&page=1', f'salt={SECRET}', f'API_KEY: {SECRET}'):
            self.assertNotIn(SECRET, display.format_message_content(1, text))
        self.assertIn('介绍正文', display.format_message_content(1, f'aeskey="{SECRET}"，介绍正文'))

    def test_output_copy_hides_routing_identifiers_without_mutating_inputs(self):
        original = {'username': 'legacy_custom_account', 'display_name': 'legacy_custom_account',
                    'sender_username': ALICE, 'sender': ALICE, 'raw': {'aeskey': SECRET},
                    'items': [{'content': BIO, 'aeskey': SECRET, 'local_id': 42}]}
        before = copy.deepcopy(original)
        result = display.public_value(original)
        self.assert_private_fields_absent(json.dumps(result, ensure_ascii=False))
        self.assertNotIn('legacy_custom_account', json.dumps(result))
        self.assertIn(BIO, result['items'][0]['content'])
        self.assertEqual(result['items'][0]['local_id'], 42)
        self.assertEqual(original, before)
        explicit = display.public_value(original, include_identifiers=True)
        self.assertEqual(explicit['username'], 'legacy_custom_account')
        self.assertNotIn(SECRET, json.dumps(explicit))


class MessageOutputIntegrationTests(PrivacyAssertions, unittest.TestCase):
    def setUp(self):
        self.case = ARTIFACT_ROOT / ('privacy-' + uuid.uuid4().hex)
        self.case.mkdir(parents=True)
        self.snapshot = self.case / 'snapshot'
        self.fixture = build(self.snapshot)
        rows = [(3, 10000, GROUP + ':\n' + JOIN), (4, 49, APP), (5, 49, FORWARD),
                (6, 49, f'<msg><appmsg aeskey="{SECRET}">'), (7, 1, '普通介绍 299元'),
                (8, 49, NESTED_FORWARD)]
        with sqlite3.connect(self.snapshot / 'message/message_0.db') as con:
            for number, kind, text in rows:
                con.execute(f'INSERT INTO [{self.fixture["table"]}] VALUES(?,?,?,?,?,?,NULL,0)',
                            (number, 100 + number, kind, 1772323400 + number, 99, text))
            con.execute('INSERT INTO Name2Id(rowid,user_name) VALUES(99,?)', ('wxid_unknown_fixture',))
        with sqlite3.connect(self.snapshot / 'session/session.db') as con:
            for definition in ['summary TEXT', 'last_timestamp INTEGER', 'last_msg_type INTEGER', 'last_msg_sender TEXT', 'last_sender_display_name TEXT']:
                con.execute('ALTER TABLE SessionTable ADD COLUMN ' + definition)
            con.execute('INSERT INTO SessionTable VALUES(?,1,?,1772323410,10000,?,?)', (GROUP, JOIN, ALICE, '测试成员'))
        self.before = fingerprint(self.snapshot)

    def mac(self, *args):
        return invoke(vault_cli, ['--decrypted-dir', str(self.snapshot), *args])

    def test_mac_json_text_search_and_session_outputs_are_safe(self):
        for args in [('history', GROUP), ('history', GROUP, '--format', 'text'),
                     ('search', '开源教育工具', '--chat', GROUP), ('sessions', '--format', 'json')]:
            with self.subTest(args=args):
                code, text, err = self.mac(*args)
                self.assertEqual(code, 0, err)
                self.assert_private_fields_absent(text)
                self.assertNotIn('wxid_unknown_fixture', text)
                if args[0] != 'sessions':
                    self.assertIn('开源教育工具', text)
        self.assertEqual(fingerprint(self.snapshot), self.before)

    def test_identifier_opt_in_is_explicit_scoped_and_does_not_reveal_credentials(self):
        code, text, err = self.mac('--include-identifiers', 'history', GROUP)
        self.assertEqual(code, 0, err)
        self.assertIn(GROUP, text)
        self.assertIn('wxid_unknown_fixture', text)
        self.assertNotIn(SECRET, text)
        self.assertNotIn('<sysmsg', text)
        _, safe, _ = self.mac('history', GROUP)
        self.assert_private_fields_absent(safe)
        with mock.patch.object(vault_cli, 'load_config', return_value={}):
            contacts, _ = vault_cli.load_contacts(self.snapshot)
            internal = vault_cli.collect_history(self.snapshot, contacts[GROUP], None, None, 100, 0, None)
        self.assertTrue(any(row['sender_username'] == 'wxid_unknown_fixture' for row in internal))

    def test_nested_forward_can_be_found_by_inner_body_on_both_backends(self):
        for code, text, err in [
            self.mac('search', '社区协作地图', '--chat', GROUP),
            invoke(vault_cli, ['snapshot', '--snapshot', str(self.snapshot), 'search', self.fixture['group_id'], '社区协作地图'], forbid_config=True),
        ]:
            self.assertEqual(code, 0, err)
            messages = json.loads(text)['messages']
            self.assertEqual(len(messages), 1)
            self.assertIn(NESTED_BIO, messages[0]['content'])
            self.assert_private_fields_absent(text)
        self.assertEqual(fingerprint(self.snapshot), self.before)

    def test_media_resolution_uses_safe_human_file_title(self):
        ts = 1772323400
        db_dir = self.case / 'account/db_storage'
        attachment = db_dir.parent / 'msg/file' / datetime.fromtimestamp(ts).strftime('%Y-%m') / 'public-intro.pdf'
        attachment.parent.mkdir(parents=True)
        attachment.write_text('synthetic attachment')
        payload = f'<msg><appmsg><appattach><title>{SECRET}</title><aeskey>{SECRET}</aeskey></appattach><title>public-intro.pdf</title><type>6</type></appmsg></msg>'
        text = vault_cli.format_content(49, payload, True, db_dir, GROUP, ts)
        self.assertIn('public-intro.pdf', text)
        self.assertIn(str(attachment), text)
        self.assert_private_fields_absent(text)
        malformed = f'<!DOCTYPE msg [<!ENTITY leaked "{SECRET}">]><msg><appmsg><title>&leaked;</title><type>6</type></appmsg></msg>'
        self.assert_private_fields_absent(vault_cli.format_content(49, malformed, True, db_dir, GROUP, ts))
        forwarded = vault_cli.format_content(49, NESTED_FORWARD, True, db_dir, GROUP, ts)
        self.assertIn(NESTED_BIO, forwarded)
        self.assert_private_fields_absent(forwarded)
        self.assertEqual(fingerprint(self.snapshot), self.before)

    def test_mac_and_legacy_exports_retain_bios_without_transport_fields(self):
        target = self.case / 'export.md'
        code, _, err = self.mac('export', GROUP, '--output', str(target))
        self.assertEqual(code, 0, err)
        self.assert_private_fields_absent(target.read_text())
        self.assertIn(BIO, target.read_text())
        self.assertIn(NESTED_BIO, target.read_text())
        rows = export_chat.collect_messages(self.snapshot, GROUP, '测试群', None)
        markdown = export_chat.render_markdown(GROUP, '测试群', rows, 'full', None)
        self.assert_private_fields_absent(markdown)
        self.assertIn('开源教育工具', markdown)
        for line in NESTED_BIO.splitlines():
            self.assertIn(line, markdown)
        self.assertEqual(fingerprint(self.snapshot), self.before)

    def test_snapshot_history_search_export_share_safe_readable_messages(self):
        for command in [('history', self.fixture['group_id']), ('search', self.fixture['group_id'], '开源教育工具')]:
            code, text, err = invoke(vault_cli, ['snapshot', '--snapshot', str(self.snapshot), *command], forbid_config=True)
            self.assertEqual(code, 0, err)
            self.assert_private_fields_absent(text)
            self.assertIn('开源教育工具', text)
        target = self.case / 'snapshot.md'
        code, _, err = invoke(vault_cli, ['snapshot', '--snapshot', str(self.snapshot), 'export', self.fixture['group_id'], '--output', str(target), '--confirm-external-output'], forbid_config=True)
        self.assertEqual(code, 0, err)
        self.assert_private_fields_absent(target.read_text())
        self.assertIn(BIO, target.read_text())
        self.assertIn(NESTED_BIO, target.read_text())
        self.assertEqual(fingerprint(self.snapshot), self.before)


# Accounts registered with their own WeChat ID have a username that is not wxid_*,
# so the text pattern cannot catch it; only the record-level rule can.
CUSTOM_ID = 'custom_partner_id'
CUSTOM_ALIAS = 'partner_alias_88'
BARE_ID = 'custom_bare_id'          # contact without remark, nickname or alias
STRANGER_ID = 'custom_stranger_id'  # group speaker and owner missing from contact.db


class CustomIdentifierOutputTests(unittest.TestCase):
    def setUp(self):
        self.case = ARTIFACT_ROOT / ('custom-ids-' + uuid.uuid4().hex)
        self.case.mkdir(parents=True)
        self.snapshot = self.case / 'snapshot'
        self.fixture = build(self.snapshot)
        with sqlite3.connect(self.snapshot / 'contact/contact.db') as con:
            con.execute('INSERT INTO contact VALUES(5,?,?,?,?)', (CUSTOM_ID, '合作伙伴', '合作方王总', CUSTOM_ALIAS))
            con.execute("INSERT INTO contact VALUES(6,?,'','','')", (BARE_ID,))
            con.execute('CREATE TABLE chat_room(id INTEGER, owner TEXT)')
            con.execute('CREATE TABLE chatroom_member(room_id INTEGER, member_id INTEGER)')
            con.execute('INSERT INTO chat_room VALUES(3,?)', (STRANGER_ID,))
            con.executemany('INSERT INTO chatroom_member VALUES(3,?)', [(1,), (6,)])
        with sqlite3.connect(self.snapshot / 'message/message_0.db') as con:
            con.execute('INSERT INTO Name2Id(rowid,user_name) VALUES(77,?)', (STRANGER_ID,))
            con.execute(f'INSERT INTO [{self.fixture["table"]}] VALUES(9,109,1,1772323500,77,?,NULL,0)', ('陌生成员发言：青柚',))
        with sqlite3.connect(self.snapshot / 'session/session.db') as con:
            for definition in ['summary TEXT', 'last_timestamp INTEGER', 'last_msg_type INTEGER', 'last_msg_sender TEXT', 'last_sender_display_name TEXT']:
                con.execute('ALTER TABLE SessionTable ADD COLUMN ' + definition)
            con.execute('INSERT INTO SessionTable VALUES(?,0,?,1772323500,1,?,?)', (GROUP, '陌生成员发言：青柚', STRANGER_ID, ''))
            con.execute('INSERT INTO SessionTable VALUES(?,1,?,1772323400,1,?,?)', (BARE_ID, '私聊问候', BARE_ID, ''))
        with sqlite3.connect(self.snapshot / 'favorite/favorite.db') as con:
            con.execute('CREATE TABLE fav_db_item(local_id INTEGER, type INTEGER, update_time INTEGER, content TEXT, fromusr TEXT, realchatname TEXT)')
            con.execute('INSERT INTO fav_db_item VALUES(1,1,1772323500,?,?,?)',
                        ('<favitem type="1"><desc>收藏的青柚笔记</desc></favitem>', STRANGER_ID, GROUP))
        with sqlite3.connect(self.snapshot / 'sns/sns.db') as con:
            con.execute('DROP TABLE SnsTimeLine')
            con.execute('CREATE TABLE SnsTimeLine(tid INTEGER, user_name TEXT, content TEXT)')
            con.execute('INSERT INTO SnsTimeLine VALUES(1,?,?)', (BARE_ID,
                        f'<TimelineObject><username>{BARE_ID}</username><createTime>1772323500</createTime><contentDesc>青柚朋友圈</contentDesc></TimelineObject>'))
        self.before = fingerprint(self.snapshot)

    def mac(self, *args):
        return invoke(vault_cli, ['--decrypted-dir', str(self.snapshot), *args])

    def test_text_and_json_hide_custom_identifiers_by_default(self):
        cases = [
            (('contacts', '--query', '合作方', '--format', 'text'), '合作方王总'),
            (('contacts', '--query', '合作方'), '合作方王总'),
            (('contacts', '--detail', '合作方王总', '--format', 'text'), '合作方王总'),
            (('contacts', '--query', BARE_ID, '--format', 'text'), display.HIDDEN_ID),
            (('sessions', '--format', 'text'), '私聊问候'),
            (('sessions',), '私聊问候'),
            (('members', GROUP, '--format', 'text'), '客户甲'),
            (('members', GROUP), '客户甲'),
            (('history', GROUP, '--format', 'text'), '陌生成员发言'),
            (('search', '青柚', '--chat', GROUP, '--format', 'text'), '陌生成员发言'),
            (('stats', GROUP, '--format', 'text'), '发言排行'),
            (('stats', GROUP), 'top_senders'),
            (('favorites', '--format', 'text'), '收藏的青柚笔记'),
            (('favorites',), '收藏的青柚笔记'),
            (('moments', '--name', BARE_ID, '--format', 'text'), '青柚朋友圈'),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                code, text, err = self.mac(*args)
                self.assertEqual(code, 0, err)
                self.assertIn(expected, text)
                for marker in (CUSTOM_ID, CUSTOM_ALIAS, BARE_ID, STRANGER_ID):
                    self.assertNotIn(marker, text)
        self.assertEqual(fingerprint(self.snapshot), self.before)

    def test_identifiers_show_only_after_explicit_opt_in(self):
        for args, markers in [
            (('contacts', '--query', '合作方', '--format', 'text'), (CUSTOM_ID, CUSTOM_ALIAS)),
            (('contacts', '--detail', '合作方王总', '--format', 'text'), (CUSTOM_ID, CUSTOM_ALIAS)),
            (('sessions', '--format', 'text'), (BARE_ID, STRANGER_ID)),
            (('members', GROUP, '--format', 'text'), (BARE_ID, STRANGER_ID)),
            (('stats', GROUP, '--format', 'text'), (STRANGER_ID,)),
        ]:
            with self.subTest(args=args):
                code, text, err = self.mac('--include-identifiers', *args)
                self.assertEqual(code, 0, err)
                for marker in markers:
                    self.assertIn(marker, text)


if __name__ == '__main__':
    unittest.main()
