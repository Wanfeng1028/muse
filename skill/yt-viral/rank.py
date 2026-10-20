"""Compare within a platform/profile, progressively relaxing sparse cohorts."""
import argparse, json, math, statistics

def rank(rows, minimum=4):
    if minimum < 2: raise ValueError('minimum must be at least 2')
    def valid(r):
        try: return bool(r.get('profile') and r.get('platform')) and all(math.isfinite(float(r[k])) and float(r[k])>=0 for k in ('views','duration_seconds','age_hours'))
        except (ValueError,TypeError,KeyError): return False
    clean=[r for r in rows if valid(r)]; results=[]
    for r in clean:
        base=[q for q in clean if (q['platform'],q['profile'])==(r['platform'],r['profile'])]
        def similar(q,k):
            a,b=float(r[k]),float(q[k]); return a==b if min(a,b)==0 else max(a,b)/min(a,b)<=1.5
        tiers=[('profile + format + similar length + similar age',[q for q in base if r.get('format') and q.get('format')==r.get('format') and similar(q,'duration_seconds') and similar(q,'age_hours')]),
               ('profile + format + similar age',[q for q in base if r.get('format') and q.get('format')==r.get('format') and similar(q,'age_hours')]),
               ('same profile, any format, similar age',[q for q in base if similar(q,'age_hours')]),
               ('same profile, any format and age',base)]
        label,cohort=next(((l,c) for l,c in tiers if len(c)>=minimum),tiers[-1])
        median=statistics.median(float(q['views']) for q in cohort)
        out=dict(r,comparison=label,sample_size=len(cohort),too_little_data=len(tiers[0][1])<minimum,
                 confidence='low' if label!=tiers[0][0] or len(cohort)<minimum else 'descriptive',
                 view_multiple=round(float(r['views'])/median,3) if median>0 and len(cohort)>1 else None,
                 warning='Fallback may mix formats, lengths or ages. Ranking is not causal evidence.' if label!=tiers[0][0] else '')
        views=float(r['views']); out['shares_per_1000_views']=float(r['shares'])*1000/views if r.get('shares') is not None and views else None
        out['average_watch_fraction']=float(r['average_watch_seconds'])/float(r['duration_seconds']) if r.get('average_watch_seconds') is not None and float(r['duration_seconds'])>0 else None
        results.append(out)
    results.sort(key=lambda r:(r['platform'],r['profile'],-(r['view_multiple'] or 0)))
    return {'rankings':results,'invalid_rows':len(rows)-len(clean),'note':'Shares and watch fraction are supporting metrics, not mixed into an unexplained composite score.'}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('--minimum',type=int,default=4);a=p.parse_args()
    print(json.dumps(rank(json.load(open(a.input,encoding='utf-8')),a.minimum),indent=2))
