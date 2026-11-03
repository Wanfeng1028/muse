from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .common import command


SHORT_HOSTS = {'v.douyin.com', 'b23.tv', 'xhslink.com', 'www.xhslink.com'}
LONG_HOSTS = {'www.douyin.com', 'douyin.com', 'www.bilibili.com', 'bilibili.com',
              'www.xiaohongshu.com', 'xiaohongshu.com', 'www.youtube.com', 'youtube.com',
              'm.youtube.com', 'youtu.be'}


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlsplit(newurl)
        if u.scheme not in {'https', 'http'} or u.hostname not in SHORT_HOSTS | LONG_HOSTS:
            raise ValueError('Share link redirects outside supported platforms')
        if u.username or u.password or u.port not in {None, 80, 443}:
            raise ValueError('Unsafe share-link redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass
class Source:
    platform: str
    id: str
    url: str
    request_url: str = field(repr=False)

    def public(self):
        return dict(platform=self.platform, id=self.id, url=self.url)


def identify(url, resolve_short=True):
    # Accept a URL, or the first URL in copied share text.
    found = re.search(r'https?://[^\s<>]+', url)
    if not found:
        raise ValueError('Provide a supported video URL')
    url = found[0].rstrip('！!，,。)')
    u = urlsplit(url)
    if u.username or u.password or u.port not in {None, 80, 443}:
        raise ValueError('Unsafe URL')
    host = u.hostname
    if host in SHORT_HOSTS:
        if not resolve_short:
            raise ValueError('Share link requires resolution')
        with build_opener(SafeRedirect()).open(Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=20) as r:
            return identify(r.url, resolve_short=False)
    if u.scheme != 'https' or host not in LONG_HOSTS:
        raise ValueError('Only HTTPS video links from the four supported platforms are accepted')
    query = parse_qs(u.query)
    if host in {'www.douyin.com', 'douyin.com'}:
        match = re.fullmatch(r'/video/(\d+)/?', u.path)
        if match:
            clean='https://www.douyin.com/video/'+match[1]
            return Source('douyin', match[1], clean, clean)
    elif host in {'www.bilibili.com', 'bilibili.com'}:
        match = re.fullmatch(r'/video/(BV[0-9A-Za-z]+|av\d+)/?', u.path)
        if match:
            suffix=''
            if 'p' in query:
                part=query['p'][0]
                if not part.isdigit() or int(part)<1:
                    raise ValueError('Invalid Bilibili part')
                suffix='?p='+str(int(part))
            clean='https://www.bilibili.com/video/'+match[1]+suffix
            return Source('bilibili', match[1]+('-p'+str(int(query['p'][0])) if suffix else ''), clean, clean)
    elif host in {'www.xiaohongshu.com', 'xiaohongshu.com'}:
        match = re.fullmatch(r'/(?:explore|discovery/item|search_result)/([0-9a-f]{24})/?', u.path)
        if match:
            clean='https://www.xiaohongshu.com/explore/'+match[1]
            access={k:query[k][0] for k in ['xsec_token','xsec_source'] if k in query}
            return Source('xiaohongshu', match[1], clean, clean+('?' + urlencode(access) if access else ''))
    else:
        vid = u.path.strip('/') if host == 'youtu.be' else (
            u.path.split('/')[-1] if u.path.startswith(('/shorts/', '/embed/')) else query.get('v',[''])[0])
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
            clean='https://www.youtube.com/watch?v='+vid
            return Source('youtube', vid, clean, clean)
    raise ValueError('Not a supported single-video URL (playlists, live and image-only posts are separate)')


def yt_arguments(source, cookies_browser=None):
    args=['yt-dlp','--ignore-config','--no-playlist','--no-progress','--socket-timeout','20',
          '--retries','1','--fragment-retries','1','--js-runtimes','node','--dump-single-json']
    if cookies_browser:
        if cookies_browser not in {'chrome','firefox','edge','safari','chromium'}:
            raise ValueError('Unsupported browser cookie source')
        args += ['--cookies-from-browser',cookies_browser]
    return args


def public_metadata(info, source):
    actual=str(info.get('id',''))
    expected=source.id.split('-p',1)[0]
    matches=actual==expected
    if source.platform=='bilibili':
        part=source.id.split('-p',1)[1] if '-p' in source.id else '1'
        matches=actual==expected+'_p'+part or (actual==expected and part=='1')
        if expected.startswith('av') and info.get('original_url')==source.request_url:
            matches=bool(re.fullmatch(r'BV[0-9A-Za-z]+(?:_p'+part+r')?',actual))
    if not matches:
        raise ValueError('Extractor source identity mismatch')
    return dict(source.public(), title=info.get('title'), author=info.get('uploader'),
                description=info.get('description'), published_at=info.get('upload_date'),
                duration=info.get('duration'), extractor=info.get('extractor_key'),
                resolved_extractor_id=actual,
                format_count=len(info.get('formats',[])))


def inspect(source, backend='auto', session=None, cookies_browser=None):
    backend = ('browser' if source.platform=='douyin' else 'yt-dlp') if backend=='auto' else backend
    if backend=='browser':
        if cookies_browser:
            raise ValueError('Browser bridge reuses the page session; no cookie export')
        if source.platform == 'douyin':
            return json.loads(command([sys.executable, Path(__file__).with_name('douyin_bridge.py'),
               'inspect','--session',session or 'v2k-inspect-douyin','--url',source.url],timeout=150))
        if source.platform == 'xiaohongshu':
            from .xhs_bridge import run
            return run(source, None, session)
        raise ValueError('Browser backend currently supports Douyin and Xiaohongshu')
    info=json.loads(command(yt_arguments(source,cookies_browser)+['--skip-download',source.request_url],timeout=150))
    if info.get('is_live'):
        raise ValueError('Live videos are not supported')
    return public_metadata(info,source)


def download(source, out, backend='auto', session=None, cookies_browser=None, max_mb=100, max_duration=3600):
    backend = ('browser' if source.platform=='douyin' else 'yt-dlp') if backend=='auto' else backend
    if backend=='browser':
        if cookies_browser:
            raise ValueError('Browser bridge does not export cookies')
        if source.platform=='douyin':
            result=json.loads(command([sys.executable,Path(__file__).with_name('douyin_bridge.py'),
                 'download','--session',session or ('v2k-douyin-'+source.id),'--url',source.url,
                 '--output-dir',Path(out)/'download'],timeout=180))
            return Path(result['video']), json.loads((Path(out)/'download/page-evidence.json').read_text())
        if source.platform=='xiaohongshu':
            from .xhs_bridge import run
            return run(source,Path(out),session)
        raise ValueError('Browser backend currently supports Douyin and Xiaohongshu')
    args=yt_arguments(source,cookies_browser)+['--no-simulate','--max-filesize',str(max_mb)+'M',
         '--match-filter',f'!is_live & duration <= {max_duration}',
         '-f','bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b[height<=720]',
         '--merge-output-format','mp4','-o',str(Path(out)/'media.%(ext)s'),source.request_url]
    info=json.loads(command(args,timeout=900))
    files=[p for p in Path(out).glob('media.*') if p.suffix.lower() in {'.mp4','.webm','.mkv'}]
    if len(files)!=1 or files[0].stat().st_size > max_mb*1024*1024:
        raise RuntimeError('No single downloaded video within the configured limit')
    return files[0], public_metadata(info,source)
