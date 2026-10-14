"""Retained adapter algorithms for reconstruction from archived PPTL2BA graphs.

This adapter has a known last-sample defect, shown in the diagnostic tables. It is retained
only to reproduce the historical results and the diagnostic comparison.
External translator invocation and machine-specific paths are excluded.
"""
import html as _html
import itertools
import re

_LIT = re.compile(r"\((\w+)\)")

def label_literals(label):
    """All parenthesized literals in a label."""
    return _LIT.findall(label)

def atoms_of(label):
    return {x for x in label_literals(label) if x not in ("TRUE", "tau", "EMPTY") and not re.fullmatch(r"l\d+", x)}

def tokenize_label(label):
    """Tokenize a tool label like '(q) && (m)', '!(p)', '!(q) || !(m)', 'TRUE', 'tau'."""
    toks = []
    i = 0
    while i < len(label):
        c = label[i]
        if c in " \t":
            i += 1
            continue
        m = _LIT.match(label, i)
        if m:
            toks.append(m.group(0)); i = m.end(); continue
        if label[i:i+2] in ("&&", "||"):
            toks.append(label[i:i+2]); i += 2; continue
        m = re.match(r"TRUE|tau|false", label[i:])
        if m:
            toks.append(m.group(0)); i += m.end(); continue
        if c in "!()":
            toks.append(c); i += 1; continue
        raise ValueError("cannot tokenize label %r at %d" % (label, i))
    return toks

class LabelParser:
    """Recursive descent over !, &&, ||, literals."""
    def __init__(self, toks):
        self.toks, self.i = toks, 0
    def peek(self): return self.toks[self.i] if self.i < len(self.toks) else None
    def parse(self):
        v = self.parse_or()
        if self.i != len(self.toks):
            raise ValueError("leftover tokens %r" % self.toks[self.i:])
        return v
    def parse_or(self):
        v = self.parse_and()
        while self.peek() == "||":
            self.i += 1; r = self.parse_and(); v = ("or", v, r)
        return v
    def parse_and(self):
        v = self.parse_not()
        while self.peek() == "&&":
            self.i += 1; r = self.parse_not(); v = ("and", v, r)
        return v
    def parse_not(self):
        if self.peek() == "!":
            self.i += 1; return ("not", self.parse_not())
        t = self.peek()
        if t == "(":
            self.i += 1; v = self.parse_or()
            assert self.peek() == ")"; self.i += 1
            return v
        if t is None:
            raise ValueError("unexpected end")
        self.i += 1
        if t == "TRUE": return ("const", True)
        if t == "false": return ("const", False)
        return ("lit", t[1:-1])   # "(p)" -> lit p

def parse_label(label):
    if label.strip() == "TRUE": return ("const", True)
    return LabelParser(tokenize_label(label)).parse()

def eval_label(expr, assignment, l_as=True):
    """Evaluate under an assignment {ap: bool}. l-literals (chop markers) are
    treated as don't-care TRUE: they are bookkeeping letters of the LNFG->SBA
    construction, not observable inputs."""
    t = expr[0]
    if t == "const": return expr[1]
    if t == "lit":
        a = expr[1]
        if re.fullmatch(r"l\d+", a): return l_as
        if a in ("TRUE",): return True
        return bool(assignment[a])
    if t == "not": return not eval_label(expr[1], assignment, l_as)
    if t == "and": return eval_label(expr[1], assignment, l_as) and eval_label(expr[2], assignment, l_as)
    if t == "or":  return eval_label(expr[1], assignment, l_as) or  eval_label(expr[2], assignment, l_as)
    raise ValueError(expr)

def _dot_rows(text):
    rows = re.findall(r"<TR>(.*?)</TR>", text, re.S)
    out = []
    for r in rows:
        cells = re.findall(r"<TD>(.*?)</TD>", r, re.S)
        out.append([_html.unescape(c) for c in cells])
    return out

def scc_tarjan(states, succ):
    """Recursive Tarjan SCC (standard). succ: state -> iterable of states.
    Graphs here are tiny (tens of states), recursion depth is fine."""
    index, low, stack, on, sccs = {}, {}, [], set(), []
    idx = [0]
    def strong(v):
        index[v] = low[v] = idx[0]; idx[0] += 1
        stack.append(v); on.add(v)
        for w in succ.get(v, ()):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop(); on.discard(w); comp.append(w)
                if w == v: break
            sccs.append(comp)
    for s in states:
        if s not in index:
            strong(s)
    return sccs

def sba_to_nfa(sba, l_as=False, prune_fin=True):
    """Prefix NFA. Two views of the transition relation:
      - moves (observable letters): tau dropped (stutter tail is not an
        observable event); when l_as=False, transitions carrying chop-boundary
        literals l1,l2,... are dropped too (internal markers of the LNFG->SBA
        translation that never fire under observable letters).
      - emptiness graph: tau kept (the stutter tail sigma.tau^omega is part of
        the accepted word), l-literals dropped when l_as=False.
    When prune_fin, transitions exiting a fin(l)-labeled node (a chop segment
    that may terminate only at a labeled boundary point) are dropped from the
    moves: such boundaries are internal events that never fire in an observable
    stream. Likewise, unguarded (TRUE) exits of chop-disjunction nodes (whose
    formula contains ';' but is not a negation) are dropped: they let a run
    cross a chop boundary without the boundary event.
    Accepting = states with nonempty SBA language, computed via SCCs on the
    emptiness graph."""
    def is_l(l):
        return any(re.fullmatch(r"l\d+", x) for x in label_literals(l))
    def src_formula(s):
        return sba["nodes"].get(s, "")
    edges = []            # observable moves
    edges_E = []          # emptiness graph (observable + tau)
    for (s, l, d) in sba["edges"]:
        fs = src_formula(s)
        fd = src_formula(d)
        if l.strip() == "tau":
            edges_E.append((s, l, d))
            continue
        if not l_as and is_l(l):
            continue
        if prune_fin:
            if "fin(" in fs:
                continue          # exit of a fin-labeled node: boundary event
            # unguarded chop-crossing exit: the source is a chop disjunction
            # with a negated side (";" and "!" present, top operator not "!")
            # and the target is not a fin-labeled node
            if (";" in fs and "!" in fs and not fs.strip().startswith("!")
                    and "fin(" not in fd):
                continue
        edges.append((s, l, d))
        edges_E.append((s, l, d))
    succ = {}
    for (s, l, d) in edges_E:
        succ.setdefault(s, set()).add(d)
    states = list(sba["nodes"].keys())
    sccs = scc_tarjan(states, succ)
    # SCCs that contain an accepting state and admit an infinite run
    live = set()
    for comp in sccs:
        if any(q in sba["accept"] for q in comp):
            if len(comp) > 1 or any(q in succ.get(q, ()) for q in comp):
                live |= set(comp)
    # states that can reach a live SCC
    rev = {}
    for (s, l, d) in edges_E:
        rev.setdefault(d, set()).add(s)
    reach_live = set(live)
    stack = list(live)
    while stack:
        q = stack.pop()
        for p in rev.get(q, ()):
            if p not in reach_live:
                reach_live.add(p); stack.append(p)
    return dict(states=states, init=sba["init"], edges=edges,
                accept=reach_live, aps=sba["aps"], label_expr=sba["label_expr"])

def minterms(aps):
    aps = sorted(aps)
    out = []
    for bits in itertools.product([False, True], repeat=len(aps)):
        out.append(dict(zip(aps, bits)))
    return out

def nfa_to_dfa(nfa, l_as=True):
    """Subset construction over minterms; totalized with a dead state.
    l_as: how chop-marker literals (l1, l2, ...) are evaluated under observable
    minterms (True = don't-care; False = never fire)."""
    mt = minterms(nfa["aps"])
    start = frozenset({nfa["init"]})
    # remove unreachable start-subset via tau-free moves? NFA init reachable by definition
    Q, delta, acc, work = {start}, {}, set(), [start]
    dead = frozenset()
    id_of = {start: 0}
    while work:
        S = work.pop()
        for mi in mt:
            T = set()
            for q in S:
                for (s, l, d) in nfa["edges"]:
                    if s == q and eval_label(nfa["label_expr"][l], mi, l_as=l_as):
                        T.add(d)
            T = frozenset(T)
            if not T:
                if dead not in id_of:
                    id_of[dead] = len(id_of)
                    Q.add(dead)
                T = dead
            else:
                if T not in id_of:
                    id_of[T] = len(id_of)
                    Q.add(T); work.append(T)
            delta[(S, _mi_key(mi))] = T
        if any(q in nfa["accept"] for q in S):
            acc.add(S)
    if dead in Q:   # totalize: the dead state loops to itself on every letter
        for mi in mt:
            delta[(dead, _mi_key(mi))] = dead
    # reindex
    ids = {s: i for i, s in enumerate(Q)}
    trans = {}
    for (S, mi_key), T in delta.items():
        trans[(ids[S], mi_key)] = ids[T]
    acc_ids = {ids[s] for s in acc}
    dead_id = ids[dead] if dead in Q else None
    return dict(states=len(Q), init=ids[start], trans=trans, accept=acc_ids,
                dead=dead_id, minterms=mt, n=len(nfa["aps"]))

def _mi_key(mi):
    return mi if isinstance(mi, tuple) else tuple(sorted(mi.items()))

def hopcroft(dfa):
    """Minimize a total DFA. Transitions keyed by minterm (as tuple). Returns
    minimized DFA dict with states 0..k-1, plus a mapping old->new."""
    n, mt = dfa["states"], dfa["minterms"]
    keys = [_mi_key(m) for m in mt]
    # trans[state][key] = target
    trans = [{} for _ in range(n)]
    for (s, mi), t in dfa["trans"].items():
        trans[s][_mi_key(mi)] = t
    P = [set(dfa["accept"]), set(range(n)) - set(dfa["accept"])]
    P = [p for p in P if p]
    # worklist algorithm (Hopcroft)
    W = list(P)
    inv = {}          # (key, target) -> set of sources
    for s in range(n):
        for k in keys:
            inv.setdefault((k, trans[s][k]), set()).add(s)
    while W:
        A = W.pop()
        for k in keys:
            X = set()
            for a in A:
                X |= inv.get((k, a), set())
            if not X: continue
            newP = []
            for Y in P:
                i, d = Y & X, Y - X
                if i and d:
                    newP.extend([i, d])
                    if Y in W:
                        W.remove(Y); W.extend([i, d])
                    else:
                        W.append(i if len(i) <= len(d) else d)
                else:
                    newP.append(Y)
            P = newP
    block = {}
    for i, Y in enumerate(sorted(P, key=lambda Y: min(Y))):
        for s in Y: block[s] = i
    k_states = len(P)
    new_trans = {}
    for (s, mi), t in dfa["trans"].items():
        new_trans[(block[s], mi)] = block[t]
    new_acc = {block[s] for s in dfa["accept"]}
    new_init = block[dfa["init"]]
    new_dead = block[dfa["dead"]] if dfa["dead"] is not None else None
    return dict(states=k_states, init=new_init, trans=new_trans, accept=new_acc,
                dead=new_dead, minterms=mt, n=dfa["n"])

def product_monitor(dfa_phi, dfa_nphi):
    """Product of the two minimized DFAs with three-valued verdicts (the
    'Monitor' definition). Returns reachable FSM + verdict labeling."""
    mt = dfa_phi["minterms"]
    keys = [_mi_key(m) for m in mt]
    d1 = {}
    for (s, mi), t in dfa_phi["trans"].items(): d1[(s, _mi_key(mi))] = t
    d2 = {}
    for (s, mi), t in dfa_nphi["trans"].items(): d2[(s, _mi_key(mi))] = t
    start = (dfa_phi["init"], dfa_nphi["init"])
    states, verdict, trans = {start}, {}, {}
    work = [start]
    dead1, dead2 = dfa_phi["dead"], dfa_nphi["dead"]
    TRUE, FALSE = "TRUE", "FALSE"
    while work:
        st = work.pop()
        q1, q2 = st
        if q1 == dead1: verdict[st] = FALSE; continue
        if q2 == dead2: verdict[st] = TRUE; continue
        verdict[st] = "?"
        for k in keys:
            t1, t2 = d1[(q1, k)], d2[(q2, k)]
            if t1 == dead1:
                nxt = FALSE
            elif t2 == dead2:
                nxt = TRUE
            else:
                nxt = (t1, t2)
                if nxt not in states:
                    states.add(nxt); work.append(nxt)
            trans[(st, k)] = nxt
    # absorbing terminal states
    fsm = dict(states=states, start=start, verdict=verdict, trans=trans,
               minterms=mt, n=dfa_phi["n"], TRUE=TRUE, FALSE=FALSE)
    return fsm

def simulate(fsm, letters):
    """letters: list of assignments {ap: bool} (in minterm format). Returns
    list of verdicts (one per prefix)."""
    st, out = fsm["start"], []
    for mi in letters:
        k = _mi_key(mi)
        if st in (fsm["TRUE"], fsm["FALSE"]):   # absorbing verdict states
            out.append(st)
            continue
        st = fsm["trans"][(st, k)]
        out.append(fsm["verdict"].get(st, st))
    return out
