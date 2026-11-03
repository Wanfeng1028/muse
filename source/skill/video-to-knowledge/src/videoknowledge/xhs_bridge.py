"""Read one owned Xiaohongshu page and transfer its muxed video; no cookie export."""
import base64
import json
from pathlib import Path
import time
import uuid

from .common import command


def run(source,out=None,session=None):
    session=session or ('v2k-xhs-'+uuid.uuid4().hex[:8])
    def call(*parts):
        return json.loads(command(['opencli','browser',session,'--window','background',*parts],timeout=45))
    tab=str(call('open',source.request_url)['page'])
    guard="if(location.hostname!=='www.xiaohongshu.com'||!location.pathname.endsWith('/'+ID))throw Error('source mismatch');".replace('ID',json.dumps(source.id))
    inspect=r"""
const detail=window.__INITIAL_STATE__?.note?.noteDetailMap?.[ID];
const note=detail?.note;
if(!note)return JSON.stringify({ready:false});
if(note.noteId&&note.noteId!==ID)throw Error('source mismatch');
if(note.type!=='video')return JSON.stringify({ready:true,video:false,type:note.type});
const media=note.video?.media;
const options=Object.values(media?.stream||{}).flatMap(v=>Array.isArray(v)?v:[]);
const candidate=options.filter(s=>s.masterUrl||s.master_url).sort((a,b)=>(a.size||0)-(b.size||0))[0];
if(!candidate)return JSON.stringify({ready:false});
const url=new URL(candidate.masterUrl||candidate.master_url,location.href);
if(url.protocol==='http:')url.protocol='https:';
if(url.protocol!=='https:'||!url.hostname.endsWith('.xhscdn.com'))throw Error('unsupported media origin');
window.__v2kXhsResource={id:ID,url:url.href};
const player=Array.from(document.querySelectorAll('video')).find(v=>isFinite(v.duration)&&v.duration>0);
const duration=player?.duration||media?.video?.duration||0;
return JSON.stringify({ready:true,video:true,id:ID,title:note.title||document.title,
 author:note.user?.nickname||null,description:note.desc||null,duration,
 url:location.origin+'/explore/'+ID,platform:'xiaohongshu',backend:'opencli_browser_fetch'});
""".replace('ID',json.dumps(source.id))
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        result=call('eval','--tab',tab,"(()=>{"+guard+inspect+"})()")
        if result.get('ready'):
            break
        time.sleep(1)
    else:
        raise RuntimeError('No matching video loaded in the target Xiaohongshu page')
    if not result.get('video'):
        raise ValueError('image_only_post: this note has no video; no transcript was created')
    if out is None:
        return result
    fetch=r"""
const resource=window.__v2kXhsResource;
if(!resource||resource.id!==ID)throw Error('source mismatch');
const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
try{
 const response=await fetch(resource.url,{credentials:'omit',signal:controller.signal});
 if(!response.ok)throw Error('media access denied');
 const reader=response.body.getReader(),chunks=[];let size=0;
 while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;
  if(size>50*1024*1024){await reader.cancel();throw Error('transfer limit');}chunks.push(value);}
 const blob=new Blob(chunks,{type:'video/mp4'});
 const base64=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);
  r.onerror=reject;r.readAsDataURL(blob)});
 return JSON.stringify({base64,bytes:size});
}finally{clearTimeout(timer)}
""".replace('ID',json.dumps(source.id))
    saved=call('eval','--tab',tab,'(async()=>{'+guard+fetch+'})()')
    payload=base64.b64decode(saved['base64'],validate=True)
    if len(payload)!=saved['bytes'] or not payload:
        raise RuntimeError('Media transfer byte mismatch')
    path=Path(out)/'media.mp4'
    with path.open('xb') as f:
        f.write(payload)
    path.chmod(0o600)
    return path,result
