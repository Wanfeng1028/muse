import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from videoknowledge.common import inside, read_json, write_json
from videoknowledge.library import acquire, add_cards, export, get, query
from videoknowledge.media import anchor_times, frames, parse_srt, process
from videoknowledge.providers import identify, public_metadata, yt_arguments


class PlatformTests(unittest.TestCase):
    def test_four_platforms_and_share_text(self):
        samples=[('douyin','复制链接 https://www.douyin.com/video/123456789！'),
                 ('bilibili','https://www.bilibili.com/video/BV13x41117TL?p=2'),
                 ('xiaohongshu','https://www.xiaohongshu.com/discovery/item/674051740000000007027a15?xsec_token=test'),
                 ('youtube','https://youtu.be/jNQXAC9IVRw?t=3')]
        for platform,url in samples:
            with self.subTest(platform=platform):self.assertEqual(identify(url).platform,platform)

    def test_public_identity_has_no_access_token(self):
        source=identify('https://www.xiaohongshu.com/explore/674051740000000007027a15?xsec_token=private')
        self.assertNotIn('private',json.dumps(source.public()))
        self.assertNotIn('private',repr(source))
        self.assertIn('private',source.request_url)

    def test_reject_untrusted_or_playlists(self):
        for url in ['https://youtube.com.evil.test/watch?v=jNQXAC9IVRw','https://user:pw@youtube.com/watch?v=jNQXAC9IVRw',
                    'http://127.0.0.1/video/123','https://youtube.com/playlist?list=x','file:///etc/passwd']:
            with self.subTest(url=url),self.assertRaises(ValueError):identify(url)

    def test_cookie_read_is_opt_in(self):
        source=identify('https://youtube.com/watch?v=jNQXAC9IVRw')
        self.assertNotIn('--cookies-from-browser',yt_arguments(source))
        self.assertIn('--cookies-from-browser',yt_arguments(source,'chrome'))

    def test_extractor_identity_must_match(self):
        source=identify('https://youtube.com/watch?v=jNQXAC9IVRw')
        with self.assertRaises(ValueError):public_metadata(dict(id='different'),source)
        bili=identify('https://www.bilibili.com/video/BV1bK411W797')
        self.assertEqual(public_metadata(dict(id='BV1bK411W797_p1'),bili)['id'],bili.id)
        part2=identify('https://www.bilibili.com/video/BV1bK411W797?p=2')
        with self.assertRaises(ValueError):public_metadata(dict(id='BV1bK411W797_p1'),part2)
        self.assertEqual(public_metadata(dict(id='BV1bK411W797_p2'),part2)['id'],part2.id)

    @unittest.skipUnless(shutil.which('node'),'Node not installed')
    def test_xhs_selector_handles_current_stream_keys_and_http(self):
        import subprocess
        from videoknowledge.xhs_bridge import run
        source=identify('https://www.xiaohongshu.com/explore/69378176000000001b03255d?xsec_token=test')
        for key in ['h264','EF5']:
            with self.subTest(key=key):
                note=dict(noteId=source.id,type='video',title='synthetic',user=dict(nickname='fixture'),
                    video=dict(media=dict(video=dict(duration=22),stream={key:[dict(masterUrl='http://sns-video.example.xhscdn.com/fixture.mp4',size=10)]})))
                def fake_browser(argv,timeout=45):
                    if 'open' in argv:return json.dumps(dict(page='owned-tab'))
                    code=argv[-1]
                    setup='global.location='+json.dumps(dict(hostname='www.xiaohongshu.com',pathname='/explore/'+source.id,origin='https://www.xiaohongshu.com',href=source.url))+';'
                    setup+='global.window='+json.dumps(dict(__INITIAL_STATE__=dict(note=dict(noteDetailMap={source.id:dict(note=note)}))))+';'
                    setup+='global.document={title:"synthetic",querySelectorAll:()=>[{duration:22.2}]};'
                    setup+='console.log(eval('+json.dumps(code)+'));'
                    result=subprocess.run(['node','-e',setup],capture_output=True,text=True,check=True)
                    return result.stdout
                with patch('videoknowledge.xhs_bridge.command',side_effect=fake_browser):
                    result=run(source)
                self.assertTrue(result['video']);self.assertEqual(result['id'],source.id)
                self.assertEqual(result['duration'],22.2)

    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):inside('/tmp/job','../../etc/passwd')


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.srt=self.root/'source.srt'
        self.srt.write_text('1\n00:00:00,000 --> 00:00:01,200\n第一步，先验证想法\n\n2\n00:00:01,200 --> 00:00:02,800\n注意边界和证据\n',encoding='utf-8')

    def test_timestamp_alignment_and_cue_budget(self):
        segments=parse_srt(self.srt,3)
        rows=anchor_times(segments,3,8)
        self.assertTrue(any(r['reason']=='transcript_cue' for r in rows))
        self.assertLessEqual(len(rows),8)
        self.assertTrue(all(0<=r['seconds']<3 for r in rows))

    def test_bad_timestamp_rejected(self):
        with self.assertRaises(ValueError):parse_srt(self.srt,0.5)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'ffmpeg not installed')
    def test_end_to_end_storage_retrieval_export_and_drift(self):
        from videoknowledge.common import command
        file=self.root/'synthetic.mp4'
        command(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x120:rate=10',
                 '-f','lavfi','-i','sine=frequency=440','-t','3','-c:v','mpeg4','-c:a','aac',file])
        library=self.root/'library'
        job,manifest=acquire(library,'https://youtube.com/watch?v=jNQXAC9IVRw',file,scope='project:test')
        self.assertEqual(manifest['status'],'downloaded')
        processed=process(job,self.srt,budget=8)
        self.assertEqual(processed['status'],'material_ready')
        self.assertEqual(processed['transcription_method'],'user_supplied_srt_unverified_alignment')
        frame=read_json(job/'frames.json')[0]['id']
        card=dict(id='verify',title='验证想法',kind='workflow',when_to_use='开始实现前',
                  steps=['验证想法'],rationale='减少方向错误',limits=['合成测试素材；不是实际学习结论'],
                  evidence=dict(segment_ids=[1],frame_ids=[frame]))
        cards_file=self.root/'cards.json';write_json(cards_file,dict(cards=[card]))
        bad=dict(card,evidence=dict(segment_ids=[999],frame_ids=[]))
        write_json(cards_file,dict(cards=[bad]))
        with self.assertRaises(ValueError):add_cards(job,cards_file)
        self.assertFalse((job/'cards.json').exists())
        write_json(cards_file,dict(cards=[card]))
        for name in ['segments','frames']:
            metadata_path=job/(name+'.json');original=metadata_path.read_bytes()
            metadata_path.write_text('[]')
            with self.assertRaises(ValueError):add_cards(job,cards_file)
            with self.assertRaises(ValueError):frames(job,[0.4])
            self.assertFalse((job/'cards.json').exists())
            metadata_path.write_bytes(original)
        for evidence in [[],dict(segment_ids='1'),dict(segment_ids=[True])]:
            write_json(cards_file,dict(cards=[dict(card,evidence=evidence)]))
            with self.assertRaises(ValueError):add_cards(job,cards_file)
        write_json(cards_file,dict(cards=[card]))
        cards=add_cards(job,cards_file)
        self.assertEqual(query(library,'验证想法','personal'),[])
        hits=query(library,'验证想法','project:test')
        self.assertEqual(hits[0]['id'],cards[0]['id'])
        self.assertIn('card',get(library,cards[0]['id']))
        original_cards=(job/'cards.json').read_bytes()
        for status in ['candidate','archived','superseded']:
            inactive=dict(cards[0],status=status)
            write_json(job/'cards.json',dict(cards=[inactive]))
            self.assertNotIn('card',get(library,cards[0]['id']))
        (job/'cards.json').write_bytes(original_cards)
        metadata_path=job/'segments.json';original_segments=metadata_path.read_bytes()
        metadata_path.write_text('[]')
        self.assertTrue(get(library,cards[0]['id'])['source_changed'])
        with self.assertRaises(ValueError):export(job,self.root/'stale-vault')
        metadata_path.write_bytes(original_segments)
        malformed=read_json(job/'cards.json')
        malformed['cards'][0]['evidence']['frames'][0]['path']='../../outside.jpg'
        write_json(job/'cards.json',malformed)
        with self.assertRaises(ValueError):export(job,self.root/'unsafe-vault')
        self.assertFalse((self.root/'outside.jpg').exists())
        (job/'cards.json').write_bytes(original_cards)
        original_manifest=(job/'manifest.json').read_bytes()
        bad_manifest=read_json(job/'manifest.json');bad_manifest['id']='../outside'
        write_json(job/'manifest.json',bad_manifest)
        with self.assertRaises(ValueError):export(job,self.root/'unsafe-vault')
        (job/'manifest.json').write_bytes(original_manifest)
        note=Path(export(job,self.root/'vault'))
        self.assertTrue(note.is_file());self.assertTrue((note.parent/'transcript.srt').is_file())
        with self.assertRaises(ValueError):export(job,self.root/'vault')
        with self.assertRaises(ValueError):add_cards(job,cards_file)
        (job/'transcript.srt').write_text('changed')
        result=get(library,cards[0]['id']);self.assertTrue(result['source_changed']);self.assertNotIn('card',result)
        self.assertTrue(query(library,'验证想法','project:test')[0]['source_changed'])


if __name__=='__main__':unittest.main()
