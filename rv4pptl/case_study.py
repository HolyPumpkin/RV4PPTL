"""Archived preprocessing and clustering routines used by the retained study.

The study uses the background heat variant (bg), six-hour maxima and
first-positive-period cohorts. Other variants are retained but not used.
"""
from pathlib import Path
from collections import Counter, defaultdict
import csv
import math
from . import legacy as mc

CSV = Path(__file__).resolve().parents[1] / "data/weibo/hot_topics_hourly.csv"
PERIOD_H = 6
_bg_cache = {}
_sim_cache = {}

def load_hourly():
    topics = defaultdict(lambda: defaultdict(int))   # topic -> hour -> heat
    seen_hours = set()
    with open(CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            topic, heat, cat = row["title"], row["heat"], row["category"]
            if not topic:
                continue
            if cat in ("荐", "商", "广告"):       # promotional slots
                continue
            try:
                h = int(heat) if heat else 0
            except ValueError:
                h = 0
            key = (row["date"], row["hour"])
            cur = topics[topic][key]
            topics[topic][key] = max(cur, h)
            seen_hours.add(key)
    return topics, sorted(seen_hours)

def period_index(hourkey, first_hour):
    """hourkey=(date,HHMM) -> 6h period index relative to the window start."""
    import datetime as dt
    y, mo, dd = map(int, hourkey[0].split("-"))
    t = dt.datetime(y, mo, dd, int(hourkey[1][:2]))
    y0, m0, d0 = map(int, first_hour[0].split("-"))
    t0 = dt.datetime(y0, m0, d0, int(first_hour[1][:2]))
    return int((t - t0).total_seconds() // 3600 // PERIOD_H)

def build_period_heat(topics, hours):
    """topic -> list of per-period heat (0-padded over the window)."""
    first = hours[0]
    idxs = set()
    for t in topics:
        for k in topics[t]:
            idxs.add(period_index(k, first))
    n_periods = max(idxs) + 1 if idxs else 0
    out = {}
    for t, hmap in topics.items():
        row = [0] * n_periods
        for k, h in hmap.items():
            i = period_index(k, first)
            if 0 <= i < n_periods:
                row[i] = max(row[i], h)
        out[t] = row
    return out

def letters_for(topic_heat, r, theta, variant="level", bg_stats=None):
    """Per-period (p, q, m) truth values for one topic's heat series.
    variant: "level"  = own-history level ratio  h/(avg+sd of own previous heats)
             "delta"  = own-history increment    max(0, h-h_prev)/(avg+sd of own prev deltas)
             "bg"     = background level ratio   h/(avg+sd over all topics in the period)
    """
    if variant == "bg" and bg_stats is None:
        raise ValueError("bg variant needs bg_stats")
    n = len(topic_heat)
    ls = []
    prev = []
    prev_delta = []
    last_h = 0
    for i, h in enumerate(topic_heat):
        p = h > 0
        if variant == "bg":
            avg, sd = bg_stats[i]
            q = (h / (avg + sd)) > r if (avg + sd) > 0 else p
        else:
            if not prev:
                q = p                      # no history: entering burst counts
            elif variant == "level":
                avg = sum(prev) / len(prev)
                sd = math.sqrt(sum((x - avg) ** 2 for x in prev) / len(prev))
                q = (h / (avg + sd)) > r if (avg + sd) > 0 else p
            else:  # delta
                d = max(0, h - last_h)
                avg = sum(prev_delta) / len(prev_delta)
                sd = math.sqrt(sum((x - avg) ** 2 for x in prev_delta) / len(prev_delta))
                q = (d / (avg + sd)) > r if (avg + sd) > 0 else p
        cum = sum(prev) + h
        m = cum < theta
        ls.append((p, q, m))
        if p:
            prev.append(h)
            prev_delta.append(max(0, h - last_h))
            last_h = h
        else:
            prev_delta.append(0)
    return ls

def bg_stats_for(heats):
    """Per-period (avg, sd) of heat over all topics (background level)."""
    n = max((len(v) for v in heats.values()), default=0)
    out = []
    for i in range(n):
        vals = [h[i] for h in heats.values() if h[i] > 0]
        if vals:
            avg = sum(vals) / len(vals)
            sd = math.sqrt(sum((x - avg) ** 2 for x in vals) / len(vals))
            out.append((avg, sd))
        else:
            out.append((0.0, 0.0))
    return out
    """Per-period (p, q, m) truth values for one topic's heat series."""
    n = len(topic_heat)
    ls = []
    prev = []
    for i, h in enumerate(topic_heat):
        p = h > 0
        if not prev:
            q = p                      # no history: entering burst counts
        else:
            avg = sum(prev) / len(prev)
            var = sum((x - avg) ** 2 for x in prev) / len(prev)
            sd = math.sqrt(var)
            q = (h / (avg + sd)) > r if (avg + sd) > 0 else p
        cum = sum(prev) + h
        m = cum < theta
        ls.append((p, q, m))
        if p:
            prev.append(h)
    return ls

def drive_monitor(letters, fsm):
    """Returns final verdict for the topic (TRUE/FALSE/?).
    letters: list of (p, q, m) tuples; the monitor's minterms are over
    {p, q}, so the (unused) m value is dropped before stepping."""
    assignments = [{"p": p, "q": q} for (p, q, _m) in letters]
    sim = mc.simulate(fsm, assignments)
    return sim[-1] if sim else "?"

def detect_rv(topic_heats, r, theta, fsm, variant="level", bg_stats=None, min_periods=1):
    """Detected topics = those whose monitor reaches TRUE.
    Each topic's stream is trimmed to start at its first active period."""
    det = []
    for t, h in topic_heats.items():
        if not any(h):
            continue
        start = next(i for i, x in enumerate(h) if x > 0)
        hs = h[start:]
        bg = bg_stats[start:] if bg_stats else None
        ls = letters_for(hs, r, theta, variant=variant, bg_stats=bg)
        if len(ls) < min_periods:
            continue
        if drive_monitor(ls, fsm) == fsm["TRUE"]:
            det.append((t, sum(1 for x in h if x > 0)))
    det.sort(key=lambda x: -x[1])
    return det

def bigrams(text):
    s = set()
    for i in range(len(text) - 1):
        s.add(text[i:i + 2])
    return s

def jaccard(a, b):
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)

def _bg(d):
    if d not in _bg_cache:
        _bg_cache[d] = bigrams(d)
    return _bg_cache[d]

def _sims(docs):
    """Precompute all pairwise similarities of `docs` (symmetric dict,
    keyed by (min, max) pair of document strings)."""
    from itertools import combinations
    out = {}
    for a, b in combinations(docs, 2):
        out[(a, b)] = jaccard(_bg(a), _bg(b))
    return out

def _sim(sims, a, b):
    if a == b:
        return 1.0
    return sims[(a, b)] if a < b else sims[(b, a)]

def single_pass(docs, threshold, topk, sims=None):
    if sims is None:
        sims = _sims(docs)
    clusters = []
    for d in docs:
        placed = False
        for c in clusters:
            if any(_sim(sims, d, x) >= threshold for x in c):
                c.append(d)
                placed = True
                break
        if not placed:
            clusters.append([d])
    clusters.sort(key=lambda c: -len(c))
    return [c[0] for c in clusters[:topk]]

def hac(docs, stop_ratio, topk, sims=None):
    if sims is None:
        sims = _sims(docs)
    clusters = [[d] for d in docs]
    active = set(range(len(clusters)))
    # single-link agglomerative clustering on Jaccard similarity;
    # the rep of a cluster is the member doc maximizing its summed
    # similarity to the cluster members (as in the original definition).
    reps = {i: docs[i] for i in active}
    import heapq
    heap = []
    ids = sorted(active)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            heapq.heappush(heap, (-_sim(sims, reps[a], reps[b]), a, b))
    target = max(1, int(len(docs) * stop_ratio))
    while len(active) > target and heap:
        neg_sim, a, b = heapq.heappop(heap)
        if a not in active or b not in active:
            continue
        # merge b into a
        for x in clusters[b]:
            clusters[a].append(x)
        # update rep of a to the union-set center (use max-sim item)
        best = max(clusters[a], key=lambda x: sum(_sim(sims, x, y) for y in clusters[a]))
        reps[a] = best
        active.discard(b)
        for c in list(active):
            if c != a:
                heapq.heappush(heap, (-_sim(sims, reps[a], reps[c]), a, c))
    out = [clusters[i] for i in active]
    out.sort(key=lambda c: -len(c))
    return [c[0] for c in out[:topk]]

def kmeans(docs, k, topk, iters=30, seed=42, sims=None):
    import random
    random.seed(seed)
    docs = list(docs)
    if k >= len(docs):
        return [max(docs, key=lambda x: 0)] * topk
    if sims is None:
        sims = _sims(docs)
    medoids = random.sample(docs, k)
    for _ in range(iters):
        assign = {}
        for d in docs:
            j = max(range(k), key=lambda i: _sim(sims, d, medoids[i]))
            assign.setdefault(j, []).append(d)
        new_medoids = []
        for j in range(k):
            members = assign.get(j, [])
            if members:
                new_medoids.append(max(members, key=lambda d: sum(_sim(sims, d, x) for x in members)))
            else:
                new_medoids.append(random.choice(docs))
        medoids = new_medoids
    sizes = Counter()
    best = {}
    for d in docs:
        j = max(range(k), key=lambda i: _sim(sims, d, medoids[i]))
        sizes[j] += 1
        best[j] = max(best.get(j, ""), d, key=lambda x: len(x))
    ranked = sorted(best.items(), key=lambda kv: -sizes[kv[0]])
    return [b for _, b in ranked[:topk]]
