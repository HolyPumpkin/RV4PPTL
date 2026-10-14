"""Focused semantic validation, not a scalability or application benchmark."""
from pathlib import Path
from itertools import product
import json, hashlib, sys
sys.dont_write_bytecode=True
from .monitor import hot_event_monitor, compile_projection, At, Not, simulate

def oracle(trace):
    # Independently derived from p(0), threshold-two count at 0/2/4/8,
    # and the requirement to observe the entire nine-state initial window.
    if not trace: return '?'
    if not trace[0]['p']: return 'FALSE'
    count=sum(trace[i]['q'] for i in (0,2,4,8) if i<len(trace))
    left=sum(i>=len(trace) for i in (0,2,4,8))
    if count+left<2: return 'FALSE'
    if len(trace)>=9: return 'TRUE' if count>=2 else 'FALSE'
    return '?'

def run_checks():
    m=hot_event_monitor(); checked=0; mismatches=[]
    for p0 in (False,True):
        for bits in product((False,True),repeat=9):
            # Alternate otherwise irrelevant p values; q need not imply p
            # in the unconstrained formal alphabet used by the theorem.
            trace=[{'p':p0 if i==0 else i%2==0,'q':bits[i]} for i in range(9)]
            trace.append({'p':False,'q':False})
            actual=simulate(m,trace)
            expected=[oracle(trace[:n]) for n in range(11)]
            checked+=len(expected)
            if actual!=expected:mismatches.append({'p0':p0,'q':bits,'actual':actual,'expected':expected})
    absorbing_checks=0
    for q,v in m['verdict'].items():
        if v in ('TRUE','FALSE'):
            for a in m['alphabet']:
                assert m['verdict'][m['trans'][q,a]]==v
                absorbing_checks+=1
    # Additional semantic edge cases of the same restricted compiler.
    cases=[]
    for expr,name in [(False,'contradiction'),(True,'horizon_only'),(At('p',0),'first_p'),(Not(At('p',0)),'not_first_p')]:
        mm=compile_projection([1],['p'],expr)
        for bits in product((False,True),repeat=3):
            trace=[{'p':x} for x in bits]
            vals=simulate(mm,trace)
            b=False if expr is False else (True if expr is True else (bits[0] if name=='first_p' else not bits[0]))
            expected=['FALSE' if expr is False else '?', '?' if b else 'FALSE', 'TRUE' if b else 'FALSE', 'TRUE' if b else 'FALSE']
            assert vals==expected,(name,bits,vals,expected)
        cases.append(name)
    result={'scope':'Focused semantic validation, no performance timing or new full-data detection run.',
            'input_count':1024,'prefix_verdict_checks':checked,'mismatch_count':len(mismatches),
            'mismatches':mismatches,'compiler_states':len(m['states']),
            'alphabet_size':len(m['alphabet']),'absorbing_transition_checks':absorbing_checks,
            'edge_case_specs':cases,'finite_empty_word_rejected':all(m['start'] not in m[k]['finite'] for k in ('positive','negative')),
            'source_sha256':hashlib.sha256((Path(__file__).parent/'monitor.py').read_bytes()).hexdigest()}
    assert not mismatches
    return result
