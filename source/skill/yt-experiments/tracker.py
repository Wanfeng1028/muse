"""Local experiments with explicit checkpoint ages and evidence provenance."""
import argparse,json,math
from datetime import datetime,timedelta
from pathlib import Path
CHECKPOINTS={'24h':24,'72h':72,'7d':168}
METRICS=('views','likes','comments','shares','saves','average_watch_seconds','completion_percent','retention_2s_percent')
def timestamp(s):
    t=datetime.fromisoformat(s.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('Use a timezone-aware ISO timestamp')
    return t
def create(id,platform,profile,posted_at,change,credits,original_id=None):
    if change not in ('original','new opening only','restyle','mashup'):raise ValueError('Exactly one supported change per test')
    if not math.isfinite(credits) or credits<0:raise ValueError('Credits must be nonnegative')
    t=timestamp(posted_at)
    return dict(id=id,platform=platform,profile=profile,posted_at=t.isoformat(),change=change,credits=credits,original_id=original_id,
                checkpoints={k:{'due_at':(t+timedelta(hours=h)).isoformat(),'observations':[]} for k,h in CHECKPOINTS.items()})
def observe(record,checkpoint,at,metrics,source,uncertain=False):
    if checkpoint not in CHECKPOINTS:raise ValueError('Unknown checkpoint')
    if not source:raise ValueError('Record manual entry or screenshot filename as source')
    age=(timestamp(at)-timestamp(record['posted_at'])).total_seconds()/3600
    if age<0:raise ValueError('Observation predates posting')
    if not metrics or set(metrics)-set(METRICS):raise ValueError('Unknown or empty metrics')
    for k,v in metrics.items():
        if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or v<0:raise ValueError('Metrics must be finite nonnegative numbers')
        if k.endswith('_percent') and v>100:raise ValueError('Percentage must be 0..100')
        if k in ('views','likes','comments','shares','saves') and int(v)!=v:raise ValueError('Counts must be whole numbers')
    entry=dict(observed_at=at,age_hours=age,offset_hours=age-CHECKPOINTS[checkpoint],metrics=metrics,source=source,uncertain=uncertain)
    record['checkpoints'][checkpoint]['observations'].append(entry);return entry
def compare(original,variant,tolerance_hours=2):
    if variant['original_id']!=original['id'] or (original['platform'],original['profile'])!=(variant['platform'],variant['profile']):raise ValueError('Comparison requires linked original on the same platform and profile')
    out=[]
    for k,h in CHECKPOINTS.items():
        def nearest(r):
            xs=[x for x in r['checkpoints'][k]['observations'] if not x['uncertain'] and abs(x['offset_hours'])<=tolerance_hours]
            return min(xs,key=lambda x:abs(x['offset_hours'])) if xs else None
        a,b=nearest(original),nearest(variant)
        if not a or not b or abs(a['age_hours']-b['age_hours'])>tolerance_hours:
            out.append({'checkpoint':k,'status':'missing or unmatched ages'});continue
        ratios={m:(b['metrics'][m]/v if v else None) for m,v in a['metrics'].items() if m in b['metrics']}
        out.append({'checkpoint':k,'status':'matched','original_age_hours':a['age_hours'],'variant_age_hours':b['age_hours'],'ratios':ratios,
                    'extra_views_per_credit':(b['metrics']['views']-a['metrics']['views'])/variant['credits'] if variant['credits'] and 'views' in a['metrics'] and 'views' in b['metrics'] else None})
    return {'comparisons':out,'note':'Observational comparison, not causal proof. Credit efficiency may be negative; zero credits has no ratio.'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--store',default='experiments.json');sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('add');c.add_argument('id');c.add_argument('--platform',required=True);c.add_argument('--profile',required=True);c.add_argument('--posted-at',required=True);c.add_argument('--change',required=True);c.add_argument('--credits',type=float,required=True);c.add_argument('--original-id')
    o=sub.add_parser('observe');o.add_argument('id');o.add_argument('--checkpoint',choices=CHECKPOINTS,required=True);o.add_argument('--at',required=True);o.add_argument('--metrics',required=True,help='JSON object');o.add_argument('--source',required=True);o.add_argument('--uncertain',action='store_true')
    q=sub.add_parser('compare');q.add_argument('original');q.add_argument('variant');q.add_argument('--tolerance-hours',type=float,default=2)
    sub.add_parser('list');a=p.parse_args();path=Path(a.store);db=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    try:
        by={r['id']:r for r in db}
        if a.command=='add':
            if a.id in by:raise ValueError('Duplicate id')
            if a.change!='original' and (a.original_id not in by or by[a.original_id]['change']!='original'):raise ValueError('Variant must link an existing original')
            r=create(a.id,a.platform,a.profile,a.posted_at,a.change,a.credits,a.original_id)
            if a.original_id and (r['platform'],r['profile'])!=(by[a.original_id]['platform'],by[a.original_id]['profile']):raise ValueError('Original must share platform and profile')
            db.append(r);out=r
        elif a.command=='observe':out=observe(by[a.id],a.checkpoint,a.at,json.loads(a.metrics),a.source,a.uncertain)
        elif a.command=='compare':out=compare(by[a.original],by[a.variant],a.tolerance_hours)
        else:out=db
        if a.command in ('add','observe'):
            temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(json.dumps(db,indent=2),encoding='utf-8');temporary.replace(path)
        print(json.dumps(out,indent=2))
    except (ValueError,KeyError) as e:p.error(str(e))
if __name__=='__main__':main()
