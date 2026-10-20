"""Return a reviewable treatment recommendation from measured/editorial evidence."""
import argparse,json

def select(r):
    old=r.get('old_footage_fraction'); meaningful=r.get('substantial_new_material'); threshold=r.get('reuse_threshold',.7)
    if not 0<=threshold<=1: raise ValueError('reuse_threshold must be 0..1')
    if old is not None and not 0<=old<=1: raise ValueError('old_footage_fraction must be 0..1')
    risk='unknown' if old is None or meaningful is None else ('high' if old>=threshold and not meaningful else 'review')
    opening=r.get('opening_drop_seconds')
    if opening is not None and 0<=opening<=3:
        treatment='new opening only';reason='Early drop: test the first 2 seconds while keeping the rest fixed.'
    elif r.get('opening_untested',True):
        treatment='new opening only';reason='Start with the cheapest isolated test; visual/narrative assessment must support the new opening.'
    elif r.get('clear_subject') and r.get('restyle_motion_suitable'):
        treatment='restyle';reason='Clear subject and suitable motion support a visual transformation test.'
    elif r.get('shared_theme') and r.get('new_narrative_payoff'):
        treatment='mashup';reason='Clips share a theme and build to a new payoff.'
    else:
        treatment='hold / collect evidence';reason='No supported treatment beyond the opening test.'
    return {'treatment':treatment,'reason':reason,'considered_first':'new opening only',
            'mashup_reuse_risk':risk,'reuse_note':'70% is a configurable editorial heuristic, not a platform rule. Mostly old footage with little new substance needs originality review. No automatic claim of reduced reach or rewards eligibility.',
            'experiment_rule':'One change per test; record platform, profile, credits and 24h/72h/7d results.'}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');a=p.parse_args();print(json.dumps(select(json.load(open(a.input,encoding='utf-8'))),indent=2))
