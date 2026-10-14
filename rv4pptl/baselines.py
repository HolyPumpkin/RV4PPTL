"""Faster execution of the retained HAC routine, preserving its update order.

The historical implementation recomputes every within-cluster score at each
merge. Cache scores for existing members and add their similarities to new
members. Recompute contender scores using the original sum expression before
choosing the representative, to preserve ties and Python's summation behavior.
The heap rules and cluster-member ordering are unchanged.
"""
import heapq
import math
from .case_study import _sim, _sims


def hac_replay(docs, stop_ratio, topk, sims=None):
    if sims is None:
        sims = _sims(docs)
    clusters = [[d] for d in docs]
    active = set(range(len(clusters)))
    reps = {i: docs[i] for i in active}
    scores = {d: _sim(sims, d, d) for d in docs}
    heap = []
    ids = sorted(active)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            heapq.heappush(heap, (-_sim(sims, reps[a], reps[b]), a, b))
    target = max(1, int(len(docs) * stop_ratio))
    while len(active) > target and heap:
        _, a, b = heapq.heappop(heap)
        if a not in active or b not in active:
            continue
        left, right = clusters[a], clusters[b]
        for x in left:
            value = scores[x]
            for y in right:
                value += _sim(sims, x, y)
            scores[x] = value
        left.extend(right)
        for x in right:
            scores[x] = sum(_sim(sims, x, y) for y in left)
        # Similarities are in [0, 1]. A conservative accumulated-roundoff
        # bound covers ordinary additions and the built-in sum implementation.
        # Exact/near ties must use fresh original-order sums, not cached scores.
        margin = 8 * math.ulp(1.0) * len(left) ** 2
        highest = max(scores[x] for x in left)
        contenders = [x for x in left if scores[x] >= highest - margin]
        reps[a] = max(contenders, key=lambda x: sum(_sim(sims, x, y) for y in left))
        active.discard(b)
        for c in list(active):
            if c != a:
                heapq.heappush(heap, (-_sim(sims, reps[a], reps[c]), a, c))
    out = [clusters[i] for i in active]
    out.sort(key=lambda c: -len(c))
    return [c[0] for c in out[:topk]]
