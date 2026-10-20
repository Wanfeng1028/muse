from pathlib import Path
import re
import shutil
import uuid

from .common import inside, now, read_json, sha, terms, write_json
from .media import probe
from .providers import download, identify


def validate_scope(scope):
    if not re.fullmatch(r'personal|project:[a-z0-9][a-z0-9-]*',scope):
        raise ValueError('Scope must be personal or project:<id>')


def acquire(library,url,file=None,scope='personal',**options):
    validate_scope(scope)
    source=identify(url)
    root=Path(library).expanduser().resolve();(root/'jobs').mkdir(parents=True,exist_ok=True)
    job_id=source.platform+'-'+source.id+'-'+uuid.uuid4().hex[:8]
    job=root/'jobs'/job_id;job.mkdir(mode=0o700)
    manifest=dict(schema_version=1,id=job_id,source=source.public(),scope=scope,
                  status='acquiring',semantic_status='needs_review',created_at=now())
    write_json(job/'manifest.json',manifest)
    try:
        if file:
            original=Path(file).expanduser().resolve(strict=True)
            if not original.is_file() or original.stat().st_size>options.get('max_mb',100)*1024*1024:
                raise ValueError('Local file is not regular media within the size limit')
            media=job/('media'+original.suffix.lower());shutil.copyfile(original,media)
            page=dict(source.public(),title=original.stem,acquisition='user_supplied_local_media')
        else:
            media,page=download(source,job,**options)
        verified=probe(media)
        expected=page.get('duration')
        if expected and abs(float(expected)-verified['duration'])>max(1.5,float(expected)*0.01):
            raise ValueError('Downloaded media duration does not match source')
        if verified['bytes']>options.get('max_mb',100)*1024*1024:
            raise ValueError('Media exceeds configured size limit')
        if verified['duration']>options.get('max_duration',3600):
            raise ValueError('Media exceeds configured duration limit')
        manifest.update(status='downloaded',media_path=str(media.relative_to(job)),media=verified,
                        title=page.get('title'),acquisition='local_import' if file else
                        ('browser' if options.get('backend')=='browser' or source.platform=='douyin' and options.get('backend','auto')=='auto' else 'yt-dlp'))
        write_json(job/'source.json',page)
        write_json(job/'manifest.json',manifest)
        return job,manifest
    except Exception as error:
        # Source identity/stage survive failure; never fill success with old files.
        manifest.update(status='acquisition_failed',error=str(error))
        write_json(job/'manifest.json',manifest)
        raise


def add_cards(job,input_path):
    job=Path(job).resolve();manifest=read_json(job/'manifest.json')
    if manifest['status'] not in {'material_ready','cards_ready'}:
        raise ValueError('Cards require processed material')
    if (job/'cards.json').exists():
        raise ValueError('Refusing to overwrite existing cards; review in a new revision/job')
    segments=read_json(job/'segments.json');frames=read_json(job/'frames.json')
    for name in ['segments','frames']:
        if sha(job/(name+'.json'))!=manifest.get(name+'_sha256'):
            raise ValueError('Processed '+name+' metadata changed or lacks a verification hash; process a new job')
    segment_map={s['id']:s for s in segments};frame_map={f['id']:f for f in frames}
    incoming=read_json(input_path)
    cards=incoming['cards'] if isinstance(incoming,dict) else incoming
    if not isinstance(cards,list) or not cards:
        raise ValueError('Cards must be a nonempty array')
    ids=set();output=[]
    for card in cards:
        if not isinstance(card,dict):raise ValueError('Each card must be an object')
        for key in ['id','title','kind','when_to_use','steps','rationale','limits','evidence']:
            if key not in card or not card[key]:raise ValueError('Missing card field: '+key)
        if not isinstance(card['id'],str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',card['id']) or card['id'] in ids:
            raise ValueError('Invalid or duplicate card ID')
        ids.add(card['id'])
        if card['kind'] not in {'method','workflow','interaction_pattern','claim','resource'}:
            raise ValueError('Unsupported card kind')
        if not all(isinstance(card[k],str) for k in ['id','title','kind','when_to_use','rationale']):
            raise ValueError('Card text fields must be strings')
        if not isinstance(card['steps'],list) or not isinstance(card['limits'],list):
            raise ValueError('Steps and limits must be arrays')
        if not all(isinstance(s,str) and s.strip() for s in card['steps']+card['limits']):
            raise ValueError('Steps and limits need nonempty text')
        evidence=card['evidence']
        if not isinstance(evidence,dict):raise ValueError('Evidence must be an object')
        selected_s=evidence.get('segment_ids',[]);selected_f=evidence.get('frame_ids',[])
        if not isinstance(selected_s,list) or not isinstance(selected_f,list):
            raise ValueError('Evidence IDs must be arrays')
        if any(type(s) is not int for s in selected_s) or any(not isinstance(f,str) for f in selected_f):
            raise ValueError('Invalid evidence ID type')
        if not selected_s and not selected_f:raise ValueError('Card needs source evidence')
        if any(s not in segment_map for s in selected_s) or any(f not in frame_map for f in selected_f):
            raise ValueError('Card references nonexistent transcript segment or frame')
        artifacts=[dict(path=manifest['media_path'],sha256=manifest['media']['sha256'])]
        if sha(inside(job,manifest['media_path']))!=manifest['media']['sha256']:
            raise ValueError('Media changed; review before card creation')
        if selected_s:
            artifacts.append(dict(path='segments.json',sha256=manifest['segments_sha256']))
            artifacts.append(dict(path='transcript.srt',sha256=manifest['transcript_sha256']))
            if sha(job/'transcript.srt')!=manifest['transcript_sha256']:
                raise ValueError('Transcript changed; review material before card creation')
        for frame_id in selected_f:
            frame=frame_map[frame_id]
            if sha(inside(job,frame['path']))!=frame['sha256']:
                raise ValueError('Frame changed; review before card creation')
            artifacts.append(dict(path=frame['path'],sha256=frame['sha256']))
        output.append(dict(card,id=manifest['id']+':'+card['id'],scope=manifest['scope'],
            status='needs_review',generation_method='agent_authored_source_grounded',
            source=manifest['source'],created_at=now(),evidence=dict(evidence,
            segments=[segment_map[s] for s in selected_s],frames=[frame_map[f] for f in selected_f],
            artifacts=artifacts),verification_scope='Evidence references/hash validated; claims not semantically approved'))
    write_json(job/'cards.json',dict(schema_version=1,cards=output),exclusive=True)
    manifest.update(status='cards_ready',card_count=len(output));write_json(job/'manifest.json',manifest)
    return output


def discover(library):
    root=Path(library).expanduser().resolve()
    for path in sorted((root/'jobs').glob('*/cards.json')):
        if not path.resolve().is_relative_to(root):continue
        for card in read_json(path)['cards']:
            yield path.parent,card


def changed(job,card,cache=None):
    cache={} if cache is None else cache
    for artifact in card['evidence']['artifacts']:
        path=inside(job,artifact['path'])
        if path not in cache:
            cache[path]=sha(path) if path.is_file() else None
        if cache[path]!=artifact['sha256']:return True
    return False


def query(library,question,scope='personal',limit=5,all_scopes=False):
    validate_scope(scope);tokens=terms(question);hits=[];cache={}
    for job,card in discover(library):
        if card['status'] in {'candidate','archived','superseded'}:continue
        if not all_scopes and card['scope']!=scope:continue
        score=3*len(tokens & terms(card['title']))+2*len(tokens & terms(card['when_to_use']))+len(tokens & terms(card.get('retrieval_terms','')))
        if score:
            drift=changed(job,card,cache)
            hits.append(dict(id=card['id'],title=card['title'],scope=card['scope'],score=score,
                             status='needs_review' if drift else card['status'],
                             source_changed=drift,source=card['source'],job=str(job)))
    return sorted(hits,key=lambda r:(-r['score'],r['id']))[:limit]


def get(library,card_id):
    for job,card in discover(library):
        if card['id']==card_id:
            if card['status'] in {'candidate','archived','superseded'}:
                return dict(id=card_id,status=card['status'],action='Inactive card content withheld')
            if changed(job,card):
                return dict(id=card_id,status='needs_review',source_changed=True,
                            action='Review changed evidence; stale card content withheld')
            return dict(card=card,source_changed=False,job=str(job))
    raise ValueError('Unknown card ID')


def export(job,destination):
    job=Path(job).resolve();manifest=read_json(job/'manifest.json');cards=read_json(job/'cards.json')['cards']
    if any(changed(job,c) for c in cards):raise ValueError('Evidence changed; cannot export stale cards')
    target=Path(destination).expanduser().resolve();target.mkdir(parents=True,exist_ok=True)
    if not isinstance(manifest['id'],str) or not re.fullmatch(r'[a-zA-Z0-9_-]+',manifest['id']):
        raise ValueError('Invalid export job ID')
    folder=inside(target,manifest['id'])
    for card in cards:
        for f in card['evidence']['frames']:
            inside(folder,f['path'])
    if folder.exists():raise ValueError('Export exists; refusing overwrite')
    folder.mkdir()
    lines=['---','id: '+manifest['id'],'kind: source','scope: '+manifest['scope'],
           'status: needs_review','---','','# '+(manifest.get('title') or manifest['id']),
           '',f"Source: {manifest['source']['url']}",'','ASR/frame evidence is unreviewed.','']
    for card in cards:
        lines += ['## '+card['title'],'',card['when_to_use'],'']+['- '+s for s in card['steps']]
        lines += ['',card['rationale'],'','Limits:']+['- '+s for s in card['limits']]+['']
        for f in card['evidence']['frames']:
            dst=folder/f['path'];dst.parent.mkdir(parents=True,exist_ok=True)
            if not dst.exists():shutil.copyfile(inside(job,f['path']),dst)
            lines.append(f"![{f['seconds']:.2f}s]({f['path']})")
        lines += ['','Transcript segments: '+str(card['evidence'].get('segment_ids',[])),'']
    if (job/'transcript.srt').is_file():
        shutil.copyfile(job/'transcript.srt',folder/'transcript.srt')
        lines += ['[Original SRT](transcript.srt)','']
    write_json(folder/'cards.json',dict(cards=cards))
    (folder/'note.md').write_text('\n'.join(lines),encoding='utf-8')
    return str(folder/'note.md')
