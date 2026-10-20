import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from .library import acquire, add_cards, export, get, query
from .media import find_model, frames, process
from .providers import identify, inspect


def main():
    parser=argparse.ArgumentParser(description='Video → transcript/frames → evidence-linked cards → retrieval')
    parser.add_argument('--library',type=Path,default=Path(os.environ.get('V2K_LIBRARY','library')))
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor')
    for name in ['inspect','download']:
        p=sub.add_parser(name);p.add_argument('url')
        p.add_argument('--backend',choices=['auto','browser','yt-dlp'],default='auto')
        p.add_argument('--session');p.add_argument('--cookies-browser',choices=['chrome','firefox','edge','safari','chromium'])
        if name=='download':
            p.add_argument('--file',type=Path,help='Import supplied local media with source provenance')
            p.add_argument('--scope',default='personal')
            p.add_argument('--max-mb',type=int,default=100)
            p.add_argument('--max-duration',type=int,default=3600)
    p=sub.add_parser('process');p.add_argument('--job',type=Path,required=True)
    p.add_argument('--srt',type=Path);p.add_argument('--whisper-model',type=Path)
    p.add_argument('--whisper-bin');p.add_argument('--language',default='auto');p.add_argument('--frame-budget',type=int,default=24)
    p=sub.add_parser('frames');p.add_argument('--job',type=Path,required=True)
    p.add_argument('--times',type=float,nargs='+',required=True)
    p=sub.add_parser('cards');p.add_argument('--job',type=Path,required=True);p.add_argument('--input',type=Path,required=True)
    p=sub.add_parser('query');p.add_argument('question');p.add_argument('--rewrite')
    p.add_argument('--scope',default='personal');p.add_argument('--all-scopes',action='store_true');p.add_argument('--limit',type=int,default=5)
    p=sub.add_parser('get');p.add_argument('id')
    p=sub.add_parser('export');p.add_argument('--job',type=Path,required=True);p.add_argument('--to',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=='doctor':
            result=dict(python=sys.version.split()[0],tools={n:shutil.which(n) for n in
                ['yt-dlp','ffmpeg','ffprobe','whisper-cli','opencli','node']},
                whisper_model_configured=bool(os.environ.get('WHISPER_CPP_MODEL')),
                whisper_model_available=find_model().is_file(),
                platforms={'douyin':'browser requires Chrome/OpenCLI',
                    'bilibili':'yt-dlp','xiaohongshu':'yt-dlp or explicitly selected browser',
                    'youtube':'yt-dlp + JavaScript runtime'},
                boundary='Dependency check only, not live platform acceptance')
        elif args.command=='inspect':
            result=inspect(identify(args.url),args.backend,args.session,args.cookies_browser)
        elif args.command=='download':
            if args.max_mb<1 or args.max_duration<1:raise ValueError('Limits must be positive')
            job,manifest=acquire(args.library,args.url,args.file,args.scope,backend=args.backend,
                session=args.session,cookies_browser=args.cookies_browser,max_mb=args.max_mb,max_duration=args.max_duration)
            result=dict(job=str(job),manifest=manifest)
        elif args.command=='process':
            result=process(args.job,args.srt,args.whisper_model,args.whisper_bin,args.language,args.frame_budget)
        elif args.command=='frames':
            result=frames(args.job,args.times)
        elif args.command=='cards':
            result=add_cards(args.job,args.input)
        elif args.command=='query':
            if not 1<=args.limit<=20:raise ValueError('Limit must be 1..20')
            result=dict(question=args.question,retrieval_query=args.rewrite or args.question,
                hits=query(args.library,args.rewrite or args.question,args.scope,args.limit,args.all_scopes),
                boundary='Lexical matches, not confidence. Read evidence/limits with get before applying.')
        elif args.command=='get':
            result=get(args.library,args.id)
        else:
            result=dict(note=export(args.job,args.to))
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,RuntimeError,OSError,KeyError,TypeError) as error:
        print(json.dumps(dict(status='failed',stage=args.command,error=str(error)),ensure_ascii=False),file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':
    main()
