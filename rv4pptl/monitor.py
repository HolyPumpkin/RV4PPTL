"""Exact monitor construction for fixed-boundary PPTL projection specifications.

Input denotes ((len(d1),...,len(dm)) prj (len(m) & B)); true.
B is a Boolean AST over (proposition, projected-position) variables.
This is a restricted backend, not an arbitrary-PPTL parser or translator.
No external dependencies. Python 3.10+.
"""
from itertools import product
from collections import deque

def At(name, sample): return ('at', name, sample)
def And(*args): return ('and', *args)
def Or(*args): return ('or', *args)
def Not(arg): return ('not', arg)

def variables(expr):
    if isinstance(expr, bool): return set()
    if expr[0] == 'at': return {(expr[2], expr[1])}
    if expr[0] not in ('and', 'or', 'not'): raise ValueError('Unknown AST operator')
    if expr[0] == 'not' and len(expr) != 2: raise ValueError('Unary negation required')
    return set().union(*(variables(x) for x in expr[1:]))

def evaluate(expr, env):
    if isinstance(expr, bool): return expr
    op = expr[0]
    if op == 'at': return env[(expr[2], expr[1])]
    if op == 'not': return not evaluate(expr[1], env)
    if op == 'and': return all(evaluate(x, env) for x in expr[1:])
    if op == 'or': return any(evaluate(x, env) for x in expr[1:])
    raise ValueError(op)

def raw_backend(gaps, atoms, expr):
    if not gaps or any(type(d) is not int or d <= 0 for d in gaps):
        raise ValueError('A nonempty sequence of positive integer gaps is required')
    atoms = tuple(sorted(set(atoms)))
    positions = [0]
    for d in gaps: positions.append(positions[-1] + d)
    horizon = positions[-1] + 1
    vs = sorted(variables(expr))
    if any(type(j) is not int or not 0 <= j < len(positions) or p not in atoms for j,p in vs):
        raise ValueError('Variable outside the declared projected trace/alphabet')
    accepted = frozenset(bits for bits in product((False,True), repeat=len(vs))
                         if evaluate(expr,dict(zip(vs,bits))))
    alphabet = tuple(product((False,True), repeat=len(atoms)))
    # A tuple state stores next source position and residual satisfying rows.
    start = (0, accepted)
    states, ids, todo, trans = [start], {start:0}, deque([start]), {}
    while todo:
        state = todo.popleft()
        for a in alphabet:
            if isinstance(state,str): target = state
            else:
                i, rows = state
                if not rows: target = 'FALSE'
                else:
                    pending = [(j,p) for j,p in vs if positions[j] >= i]
                    now = [(j,p) for j,p in pending if positions[j] == i]
                    observed = tuple(a[atoms.index(p)] for j,p in now)
                    nextrows = frozenset(row[len(now):] for row in rows
                                         if row[:len(now)] == observed)
                    if not nextrows: target = 'FALSE'
                    elif i + 1 == horizon: target = 'TRUE'
                    else: target = (i+1,nextrows)
            if target not in ids:
                ids[target]=len(states); states.append(target); todo.append(target)
            trans[(ids[state],a)] = ids[target]
    yes = {ids['TRUE']} if 'TRUE' in ids else set()
    no = {ids['FALSE']} if 'FALSE' in ids else set()
    positive = dict(finite=yes,infinite=yes)
    negative = dict(finite=set(range(len(states)))-yes-{0},infinite=no)
    return dict(atoms=atoms,alphabet=alphabet,states=states,trans=trans,start=0,
                positive=positive,negative=negative,positions=positions,horizon=horizon)

def live_states(backend, acceptance):
    """For this acyclic-depth backend, infinite runs end in an absorbing sink."""
    trans=backend['trans']; alphabet=backend['alphabet']
    infinite={q for q in acceptance['infinite']
              if all(trans[q,a]==q for a in alphabet)}
    live=set(acceptance['finite']) | infinite
    reverse={q:set() for q in range(len(backend['states']))}
    for (q,a),target in trans.items(): reverse[target].add(q)
    todo=deque(live)
    while todo:
        q=todo.popleft()
        for predecessor in reverse[q]-live:
            live.add(predecessor); todo.append(predecessor)
    return live

def compile_projection(gaps,atoms,expr):
    backend=raw_backend(gaps,atoms,expr)
    pos=live_states(backend,backend['positive'])
    neg=live_states(backend,backend['negative'])
    # Both deterministic components share transitions. Only diagonal pairs
    # are reachable in their product; represent each pair by one state ID.
    verdict={}
    for q in range(len(backend['states'])):
        if q not in pos and q not in neg: raise AssertionError('Both components reject')
        verdict[q]='TRUE' if q not in neg else ('FALSE' if q not in pos else '?')
    return dict(**backend,verdict=verdict,positive_live=pos,negative_live=neg)

def simulate(monitor, letters):
    state=monitor['start']
    out=[monitor['verdict'][state]]
    for letter in letters:
        if set(letter) != set(monitor['atoms']): raise ValueError('Alphabet mismatch')
        if any(type(v) is not bool for v in letter.values()): raise ValueError('Boolean letters required')
        a=tuple(letter[p] for p in monitor['atoms'])
        state=monitor['trans'][state,a]
        out.append(monitor['verdict'][state])
    return out

def hot_event_monitor():
    pairs=Or(*(And(At('q',i),At('q',j)) for i in range(4) for j in range(i+1,4)))
    return compile_projection([2,2,4],['p','q'],And(At('p',0),pairs))

if __name__ == '__main__':
    monitor=hot_event_monitor()
    print({'states':len(monitor['states']),'alphabet':len(monitor['alphabet']),
           'positions':monitor['positions'],'horizon':monitor['horizon']})
