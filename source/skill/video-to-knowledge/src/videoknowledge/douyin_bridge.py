#!/usr/bin/env python3
"""Download a loaded Douyin MP4 through OpenCLI's logged-in Chrome, without GUI clicks."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import uuid


def cli(args, *parts):
    p = subprocess.run(["opencli", "browser", args.session, "--window", "background", *parts],
                       capture_output=True, text=True, timeout=40)
    if p.returncode:
        # Browser errors can contain signed URLs. Persist only a fixed category,
        # return code, and command kind; never persist or echo raw responses.
        text = (p.stderr + "\n" + p.stdout).lower()
        categories = (
            ("bridge_timeout", ("timeout", "timed out")),
            ("browser_disconnected", ("browser_connect", "not connected", "extension disconnected")),
            ("no_complete_mp4", ("no complete mp4 response",)),
            ("source_mismatch", ("wrong source", "resource identity changed")),
            ("tab_busy", ("tab busy",)),
            ("transfer_limit", ("media exceeds bridge transfer limit",)),
            ("unsupported_media_origin", ("unsupported media origin",)),
        )
        category = next((name for name, phrases in categories
                         if any(phrase in text for phrase in phrases)), "unknown")
        args.safe_cli_failure = dict(exit_code=p.returncode, category=category,
                                     command_kind=parts[0] if parts else "unknown")
        if getattr(args, "created_output", None):
            (args.created_output / "cli-failure.json").write_text(
                json.dumps(args.safe_cli_failure, indent=2))
        raise RuntimeError(f"OpenCLI failed (exit {p.returncode}; category {category}); check Chrome connectivity and the exact target tab")
    try:
        return json.loads(p.stdout)
    except ValueError:
        raise RuntimeError("Unexpected OpenCLI response") from None


def evaluate(args, code):
    return cli(args, "eval", "--tab", args.tab, code)


def guard(args, body):
    urls = ["https://www.douyin.com/" + route + "/" + args.video_id for route in ("video", "note")]
    return "(async()=>{if(!" + json.dumps(urls) + \
           ".includes(location.origin+location.pathname))throw Error('Wrong source');" + body + "})()"


def inspect(args):
    body = r"""
let element=Array.from(document.querySelectorAll('video')).find(v=>isFinite(v.duration)&&v.duration>0);
const duration=element?.duration;let fiber=null;
for(let i=0;element&&i<25;element=element.parentElement,i++){
 const key=Object.keys(element).find(k=>k.startsWith('__reactFiber'));
 if(key){fiber=element[key];break}
}
let item=null;
for(let i=0;fiber&&i<35;fiber=fiber.return,i++){
 const a=fiber.memoizedProps?.awemeInfo;
 if(a&&String(a.awemeId)===VIDEO_ID){item=a;break}
}
if(!item?.video||!duration) return JSON.stringify({ready:false});
const candidates=(item.video.bitRateList||[]).filter(b=>
 b.format==='mp4'&&b.videoFormat==='mp4'&&!b.audioFileId&&b.height>=720&&
 b.dataSize>0&&Array.isArray(b.playAddr)&&b.playAddr.length);
candidates.sort((a,b)=>a.dataSize-b.dataSize);
const chosen=candidates[0];if(!chosen)return JSON.stringify({ready:false});
const urls=chosen.playAddr.map(a=>a.src).filter(u=>typeof u==='string').map(u=>new URL(u,location.href));
if(!urls.length||urls.some(u=>u.protocol!=='https:'||!u.hostname.endsWith('.douyinvod.com')))
 throw Error('Unsupported media origin');
// Keep raw media addresses only inside this page. Do not export the React item/user state.
window.__douyinCommandResource={id:VIDEO_ID,urls:urls.map(u=>u.href),bytes:chosen.dataSize};
return JSON.stringify({ready:true,url:location.origin+location.pathname,video_id:VIDEO_ID,
 title:document.title,post_caption:item.desc||'',author:item.authorInfo?.nickname||item.authorInfo?.nickName||null,
 video:{duration,width:chosen.width,height:chosen.height},expected_bytes:chosen.dataSize,
 format:'mp4',selection:'smallest muxed MP4 with height >=720'});
""".replace("VIDEO_ID", json.dumps(args.video_id))
    return evaluate(args, guard(args, body))


def run(args):
    if args.url:
        match = re.fullmatch(r"https://www\.douyin\.com/video/(\d+)/?", args.url)
        if not match:
            raise RuntimeError("Use a canonical https://www.douyin.com/video/ID URL")
        if args.video_id and args.video_id != match[1]:
            raise RuntimeError("URL and requested ID differ")
        args.video_id = match[1]
    if not args.video_id or not re.fullmatch(r"\d+", args.video_id):
        raise RuntimeError("A numeric --video-id or canonical --url is required")
    if args.command == 'download' and Path(args.output_dir).expanduser().resolve().exists():
        raise RuntimeError("Output directory exists; refusing overwrite")
    if not args.tab:
        args.tab = cli(args, "open", "https://www.douyin.com/video/" + args.video_id)["page"]
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        page = inspect(args)
        if page["ready"]:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("Page/player metadata did not load; no file was downloaded")
    if args.command == "inspect":
        return dict(page, tab=args.tab)
    out = Path(args.output_dir).expanduser().resolve()
    if out.exists():
        raise RuntimeError("Output directory exists; refusing overwrite")
    out.mkdir(parents=True, mode=0o700)
    args.created_output = out
    evidence = dict(page, video=[page['video']])
    (out / "page-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    token = "douyin-" + args.video_id + "-" + uuid.uuid4().hex[:12]
    events = []
    def event(kind, **extra):
        events.append(dict(event=kind, epoch=time.time(), **extra))
        (out / "events.json").write_text(json.dumps(events, indent=2))
    event("download_started")
    body = r"""
const resource=window.__douyinCommandResource;
if(!resource||resource.id!==VIDEO_ID)throw Error('Resource identity changed');
if(resource.bytes>50*1024*1024)throw Error('Media exceeds bridge transfer limit');
if(window.__douyinCommandBusy)throw Error('Tab busy');
window.__douyinCommandBusy=TOKEN;
try{
 let blob=null;
 for(const url of resource.urls){
  const c=new AbortController(),timer=setTimeout(()=>c.abort(),20000);
  try{
   const response=await fetch(url,{credentials:'omit',signal:c.signal});
   if(!response.ok||!/^video\/mp4(?:;|$)/i.test(response.headers.get('content-type')||''))continue;
   const b=await response.blob();if(b.size===resource.bytes){blob=b;break}
  }catch{}finally{clearTimeout(timer)}
 }
 if(!blob)throw Error('No complete MP4 response');
 if(blob.size>50*1024*1024)throw Error('Media exceeds bridge transfer limit');
 const data=await new Promise((resolve,reject)=>{const r=new FileReader();
   r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(Error('Blob read failed'));
   r.readAsDataURL(blob)});
 return JSON.stringify({retrieved:true,bytes:blob.size,base64:data});
}finally{if(window.__douyinCommandBusy===TOKEN)delete window.__douyinCommandBusy}
""".replace("VIDEO_ID", json.dumps(args.video_id)).replace("TOKEN", json.dumps(token))
    saved = evaluate(args, guard(args, body))
    event("media_retrieved", bytes=saved["bytes"])
    media = out / "video.mp4"
    payload = base64.b64decode(saved.pop('base64'), validate=True)
    if len(payload) != saved['bytes'] or len(payload) != page['expected_bytes']:
        raise RuntimeError('Media transfer size mismatch')
    with media.open('xb') as f:
        f.write(payload)
    media.chmod(0o600)
    del payload
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(media)],
                           capture_output=True, text=True)
    if probe.returncode:
        raise RuntimeError("Saved file failed ffprobe")
    info = json.loads(probe.stdout)
    types = {s['codec_type'] for s in info['streams']}
    duration = float(info['format']['duration'])
    if not {'video', 'audio'}.issubset(types) or abs(duration - page['video']['duration']) > 1:
        raise RuntimeError("Media streams or duration do not match the source")
    event("media_verified", duration=duration, bytes=media.stat().st_size)
    result = dict(status='downloaded', semantic_status='needs_review',
                  video_id=args.video_id, video=str(media), duration=duration,
                  bytes=media.stat().st_size, sha256=hashlib.sha256(media.read_bytes()).hexdigest(),
                  tab=args.tab, backend='opencli_browser_fetch')
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['inspect', 'download'])
    p.add_argument('--session', required=True)
    p.add_argument('--tab', help='Exact owned OpenCLI target; otherwise open a new dedicated session')
    p.add_argument('--url')
    p.add_argument('--video-id')
    p.add_argument('--output-dir')
    p.add_argument('--timeout', type=float, default=90)
    args = p.parse_args()
    if args.command == 'download' and not args.output_dir:
        p.error('download requires --output-dir')
    try:
        print(json.dumps(run(args), ensure_ascii=False))
    except (RuntimeError, subprocess.TimeoutExpired, KeyError, ValueError, OSError) as exc:
        message = str(exc) if isinstance(exc, RuntimeError) else 'Command timed out, local I/O failed, or response changed'
        if getattr(args, 'created_output', None):
            out = args.created_output
            if not (out / 'result.json').exists():
                (out / 'failure.json').write_text(json.dumps(dict(status='failed', error=message)))
        print(json.dumps(dict(status='failed', error=message), ensure_ascii=False))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
