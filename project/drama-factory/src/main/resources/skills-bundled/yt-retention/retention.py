"""Strict retention analysis: CSV headers and explicit time units are required."""
import argparse, csv, json, math

def load_csv(path, units, duration=None, time_column='position', retention_column='retention'):
    if units not in ('seconds','percent'): raise ValueError('Explicit seconds or percent units are required')
    if duration is not None and (not math.isfinite(duration) or duration<=0): raise ValueError('Duration must be finite and positive')
    if units == 'percent' and (duration is None or duration <= 0):
        raise ValueError('Percentage positions require a positive --duration in seconds')
    rows, skipped = [], []
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not {time_column, retention_column} <= set(reader.fieldnames):
            raise ValueError('Specify the actual header names with --time-column and --retention-column')
        for line, r in enumerate(reader, 2):
            try:
                x = float(r[time_column].strip().rstrip('%'))
                y = float(r[retention_column].strip().rstrip('%'))
                if not all(map(math.isfinite, (x,y))) or x < 0 or y < 0:
                    raise ValueError('negative or non-finite value')
                if units == 'percent' and x > 100: raise ValueError('position exceeds 100 percent')
                t = x * duration / 100 if units == 'percent' else x
                if duration and t > duration: raise ValueError('position exceeds duration')
                if rows and t <= rows[-1][0]: raise ValueError('duplicate or out-of-order position')
                rows.append((t,y))
            except (ValueError, TypeError, AttributeError, KeyError) as e:
                skipped.append({'line':line,'reason':str(e)})
    if len(rows) < 2: raise ValueError('Need at least two valid data points')
    return rows, skipped

def analyse(rows):
    cutoff = min(30, rows[-1][0])
    def interpolate(t):
        for (a,y),(b,z) in zip(rows,rows[1:]):
            if a <= t <= b: return y + (z-y)*(t-a)/(b-a)
        return None
    end = interpolate(cutoff)
    leak = rows[0][1] - end if rows[0][0] == 0 and end is not None else None
    drops = [{'from':a,'to':b,'lost_percentage_points':y-z,'rate_pp_per_second':(y-z)/(b-a)}
             for (a,y),(b,z) in zip(rows,rows[1:]) if y>z]
    return {'opening_window_seconds':cutoff,'opening_loss_percentage_points':leak,
            'drop_intervals':sorted(drops,key=lambda r:-r['rate_pp_per_second'])[:5],
            'limitation':'Sampled intervals, not exact exit seconds or proof of cause; no universal healthy threshold.'}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('csv')
    p.add_argument('--units',required=True,choices=['seconds','percent']); p.add_argument('--duration',type=float)
    p.add_argument('--time-column',default='position'); p.add_argument('--retention-column',default='retention')
    p.add_argument('--transcript'); p.add_argument('--json',action='store_true'); a=p.parse_args()
    try:
        rows,skipped=load_csv(a.csv,a.units,a.duration,a.time_column,a.retention_column)
        out=analyse(rows); out.update(points=len(rows),skipped_rows=skipped)
        if a.transcript:
            import importlib.util
            from pathlib import Path
            spec=importlib.util.spec_from_file_location('deadair',Path(__file__).parent.parent/'yt-edit'/'deadair.py')
            m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); cues=m.load(a.transcript)
            for drop in out['drop_intervals']:
                drop['nearby_speech']=' '.join(t for s,e,t in cues if s<=drop['to'] and e>=drop['from'])[:400]
        print(json.dumps(out,indent=2))
    except ValueError as e: p.error(str(e))
if __name__=='__main__': main()
