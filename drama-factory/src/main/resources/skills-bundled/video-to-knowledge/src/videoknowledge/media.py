import json
import math
import os
from pathlib import Path
import re
import shutil

from .common import command, inside, now, read_json, sha, write_json

CUES = re.compile(r'截图|图表|表格|画面|提示词|第一|第二|步骤|关键|注意|不要|结论|'
                  r'chart|table|screen|step|important|example|do not', re.I)


def find_model(explicit=None):
    return Path(explicit or os.environ.get('WHISPER_CPP_MODEL') or
                Path.home()/'.local/share/whisper.cpp/models/ggml-large-v3-turbo.bin').expanduser()


def probe(path):
    data=json.loads(command(['ffprobe','-v','error','-show_streams','-show_format','-of','json',path]))
    duration=float(data['format']['duration'])
    types={s.get('codec_type') for s in data['streams']}
    if 'video' not in types or not math.isfinite(duration) or duration<=0:
        raise ValueError('Not a complete finite video')
    # Decode both ends; a successful HTTP request alone does not validate media.
    for start in [0,max(0,duration-1)]:
        command(['ffmpeg','-v','error','-ss',str(start),'-i',path,'-t','1','-f','null','-'])
    return dict(duration=duration,has_audio='audio' in types,
                streams=[{k:s.get(k) for k in ['codec_type','codec_name','width','height','sample_rate']}
                         for s in data['streams']],sha256=sha(path),bytes=Path(path).stat().st_size)


def parse_srt(path, duration=None):
    text=Path(path).read_text(encoding='utf-8-sig').replace('\r\n','\n').strip()
    segments=[]
    def seconds(value):
        h,m,s=re.split('[:,.]',value)[:3]
        millis=re.split('[:,.]',value)[3]
        if int(m)>59 or int(s)>59:
            raise ValueError('Invalid SRT timestamp')
        return int(h)*3600+int(m)*60+int(s)+int(millis)/1000
    for block in re.split(r'\n\s*\n',text):
        lines=block.splitlines()
        if len(lines)<3 or not lines[0].strip().isdigit():
            raise ValueError('Invalid SRT block')
        match=re.fullmatch(r'(\d{2,}:\d{2}:\d{2}[,.]\d{3}) --> (\d{2,}:\d{2}:\d{2}[,.]\d{3})(?: .*?)?',lines[1].strip())
        if not match:
            raise ValueError('SRT must have timestamped segments')
        start,end=seconds(match[1]),seconds(match[2])
        if end<=start or (duration is not None and end>duration+1.5):
            raise ValueError('SRT timestamp outside video duration')
        segments.append(dict(id=int(lines[0]),start=start,end=end,text='\n'.join(lines[2:])))
    if not segments or len({s['id'] for s in segments})!=len(segments):
        raise ValueError('Empty or duplicate SRT segments')
    if any(a['start']>b['start'] for a,b in zip(segments,segments[1:])):
        raise ValueError('SRT is not in time order')
    return segments


def anchor_times(segments,duration,budget=24):
    if budget<4 or budget>100:
        raise ValueError('Frame budget must be 4..100')
    ceiling=duration-min(0.5,duration/5)
    baseline=[ceiling*i/(budget//2-1) for i in range(budget//2)]
    cues=[s for s in segments if CUES.search(s['text'])]
    stride=max(1,math.ceil(len(cues)/max(1,budget//6)))
    proposed=[dict(seconds=t,reason='coverage',segment_ids=[]) for t in baseline]
    for s in cues[::stride]:
        for t in [s['start'],(s['start']+s['end'])/2,s['end']+0.5]:
            proposed.append(dict(seconds=max(0,min(t,ceiling)),reason='transcript_cue',segment_ids=[s['id']]))
    by_time={}
    for row in proposed:
        key=round(row['seconds'],2)
        if key in by_time:
            by_time[key]['segment_ids']=sorted(set(by_time[key]['segment_ids']+row['segment_ids']))
            if row['reason']=='transcript_cue':by_time[key]['reason']=row['reason']
        else:by_time[key]=dict(row,seconds=key)
    return sorted(by_time.values(),key=lambda r:r['seconds'])[:budget]


def frames(job,times=None,budget=24):
    job=Path(job)
    manifest=read_json(job/'manifest.json')
    media=inside(job,manifest['media_path'])
    if sha(media)!=manifest['media']['sha256']:
        raise ValueError('Media changed since download verification')
    duration=manifest['media']['duration']
    if manifest.get('segments_sha256') and sha(job/'segments.json')!=manifest['segments_sha256']:
        raise ValueError('Segment metadata changed; review before extracting more frames')
    segments=read_json(job/'segments.json') if (job/'segments.json').exists() else []
    proposed=anchor_times(segments,duration,budget) if times is None else [
        dict(seconds=float(t),reason='agent_requested',segment_ids=[]) for t in times]
    directory=job/'frames';directory.mkdir(exist_ok=True)
    existing=read_json(job/'frames.json') if (job/'frames.json').exists() else []
    if (job/'frames.json').exists() and sha(job/'frames.json')!=manifest.get('frames_sha256'):
        raise ValueError('Frame metadata changed; review before extracting more frames')
    for row in proposed:
        seconds=row['seconds']
        if not math.isfinite(seconds) or not 0<=seconds<duration:
            raise ValueError('Frame time outside video')
        if any(abs(f['seconds']-seconds)<0.01 for f in existing):
            continue
        frame_id='f-'+str(len(existing)+1).zfill(4)
        target=directory/(frame_id+'.jpg')
        if target.exists():
            raise ValueError('Refusing to overwrite frame')
        command(['ffmpeg','-v','error','-ss',str(seconds),'-i',media,'-frames:v','1',
                 '-vf','scale=960:960:force_original_aspect_ratio=decrease','-q:v','3','-threads','1',target])
        if not target.is_file() or target.stat().st_size==0:
            raise ValueError('Frame extraction produced no file')
        existing.append(dict(row,id=frame_id,path=str(target.relative_to(job)),sha256=sha(target)))
    write_json(job/'frames.json',existing)
    manifest['frame_count']=len(existing)
    manifest['frames_sha256']=sha(job/'frames.json')
    write_json(job/'manifest.json',manifest)
    return existing


def process(job,srt=None,whisper_model=None,whisper_bin=None,language='auto',budget=24):
    job=Path(job);manifest=read_json(job/'manifest.json')
    if manifest['status']!='downloaded':
        raise ValueError('Process requires a downloaded job; create a new job instead of overwriting')
    media=inside(job,manifest['media_path'])
    if sha(media)!=manifest['media']['sha256']:
        raise ValueError('Media changed')
    transcription='not_available_no_audio'
    if srt:
        target=job/'transcript.srt'
        if target.exists():raise ValueError('Transcript already exists')
        # Validate before copying; never claim alignment from a filename alone.
        parse_srt(srt,manifest['media']['duration'])
        shutil.copyfile(srt,target)
        transcription='user_supplied_srt_unverified_alignment'
    elif manifest['media']['has_audio']:
        model=find_model(whisper_model)
        executable=whisper_bin or os.environ.get('WHISPER_CPP_BIN') or shutil.which('whisper-cli')
        if not executable or not model or not Path(model).is_file():
            raise ValueError('Local ASR needs whisper-cli and --whisper-model / WHISPER_CPP_MODEL')
        audio=job/'audio.wav'
        if audio.exists() or (job/'transcript.srt').exists():
            raise ValueError('Refusing to overwrite processing artifacts')
        command(['ffmpeg','-v','error','-i',media,'-vn','-ac','1','-ar','16000','-codec:a','pcm_s16le',audio])
        command([executable,'-f',audio,'-m',model,'-of',job/'transcript','-osrt','-otxt','-oj',
                 '-l',language,'--no-prints'],timeout=3600)
        transcription='local_whisper_cpp'
    segments=parse_srt(job/'transcript.srt',manifest['media']['duration']) if (job/'transcript.srt').exists() else []
    write_json(job/'segments.json',segments)
    frame_rows=frames(job,budget=budget)
    manifest.update(status='material_ready',semantic_status='needs_review',processed_at=now(),
                    transcription_method=transcription,segment_count=len(segments),frame_count=len(frame_rows),
                    transcript_sha256=sha(job/'transcript.srt') if segments else None,
                    segments_sha256=sha(job/'segments.json'),frames_sha256=sha(job/'frames.json'),
                    coverage=dict(video_duration=manifest['media']['duration'],
                                  last_transcript_end=segments[-1]['end'] if segments else None,
                                  visual='timestamp/cue candidates; not semantic frame recognition',
                                  semantic_reviewed=False))
    write_json(job/'manifest.json',manifest)
    return manifest
