"""Recompute paper tables, semantic checks, and historical detector selections.

Expected numbers are read only by comparison routines, never used as results.
The external PPTL2BA translation and its original wall-clock time are archived
inputs; they are not claimed to be executed by this reproduction.
"""
from pathlib import Path
from itertools import product
from collections import Counter
import argparse
import csv
import datetime as dt
import hashlib
import json
import platform
import re
import sys
import time

from . import legacy, case_study as study
from .monitor import hot_event_monitor, simulate
from .validation import run_checks
from .baselines import hac_replay

ROOT = Path(__file__).resolve().parents[1]
VERDICTS = {"TRUE": "true", "FALSE": "false", "?": "inconclusive"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_equal(actual, expected, description):
    if actual != expected:
        raise ValueError(f"{description}: mismatch\nactual={actual!r}\nexpected={expected!r}")


def load_automaton(kind):
    folder = ROOT / "data/legacy_automata" / kind

    def rows(name):
        return legacy._dot_rows((folder / name).read_text(encoding="gbk"))

    nodes = {int(r[0][4:]): r[1] for r in rows("BANode.dot")
             if len(r) == 2 and re.fullmatch(r"Node\d+", r[0])}
    edges = []
    for r in rows("BAEdge.dot"):
        if len(r) == 3 and (m := re.fullmatch(r"Node(\d+)->Node(\d+)", r[2])):
            edges.append((int(m[1]), r[1], int(m[2])))
    accept = {int(q) for r in rows("BAAccept.dot") for c in r
              for q in re.findall(r"Node(\d+)", c)}
    initial = next(int(q) for r in rows("LNFGNode.dot") for c in r
                   for q in re.findall(r"Node(\d+)", c))
    return dict(nodes=nodes, edges=edges, accept=accept, init=initial,
                aps=set().union(*(legacy.atoms_of(label) for _, label, _ in edges)),
                label_expr={label: legacy.parse_label(label) for _, label, _ in edges})


def reconstruct_legacy():
    automata = [load_automaton(k) for k in ("phi", "nphi")]
    nfas = [legacy.sba_to_nfa(a, l_as=False, prune_fin=True) for a in automata]
    dfas = [legacy.nfa_to_dfa(n, l_as=False) for n in nfas]
    minimal = [legacy.hopcroft(d) for d in dfas]
    monitor = legacy.product_monitor(*minimal)
    sizes = [[len(a["nodes"]), len(n["states"]), d["states"], m["states"]]
             for a, n, d, m in zip(automata, nfas, dfas, minimal)]
    return monitor, dict(positive=sizes[0], negative=sizes[1],
                         allocated_monitor_states=len(monitor["states"]) + 2)


def bounded_verdict(trace):
    if len(trace) > 9 or (trace and not trace[0]["p"]):
        return "false"
    seen = sum(trace[i]["q"] for i in (0, 2, 4, 8) if i < len(trace))
    unseen = sum(i >= len(trace) for i in (0, 2, 4, 8))
    return "inconclusive" if seen + unseen >= 2 else "false"


def diagnostics(old, direct):
    counts = Counter()
    misses = 0
    for bits in product((False, True), repeat=9):
        trace = [dict(p=True, q=b) for b in bits]
        result = VERDICTS[legacy.simulate(old, trace)[-1]]
        counts[result] += 1
        matches = sum(bits[i] for i in (0, 2, 4, 8)) >= 2
        misses += matches and result != "true"
    rows = []
    for high in ([0, 2], [0, 8]):
        for length in (9, 10):
            trace = [dict(p=True, q=i in high) for i in range(length)]
            rows.append(dict(high_positions=high, length=length,
                             bounded=bounded_verdict(trace),
                             previous_adapter=VERDICTS[legacy.simulate(old, trace)[-1]],
                             direct_backend=VERDICTS[simulate(direct, trace)[-1]]))
    return dict(counts, last_sample_misses=misses), rows


def load_study():
    topics, hours = study.load_hourly()
    heats = study.build_period_heat(topics, hours)
    background = study.bg_stats_for(heats)
    calibration, evaluation = {}, {}
    origin = dt.datetime(2023, 5, 28)
    for title, heat in heats.items():
        active = [i for i, h in enumerate(heat) if h > 0]
        if not active:
            continue
        day = (origin + dt.timedelta(hours=6 * active[0])).date().isoformat()
        if "2023-05-28" <= day <= "2023-06-10":
            calibration[title] = heat
        elif "2023-06-11" <= day <= "2023-06-24":
            evaluation[title] = heat
    with open(study.CSV, encoding="utf-8", newline="") as handle:
        rows = sum(1 for _ in csv.DictReader(handle))
    stats = dict(rows=rows, snapshots=len(hours), titles=len(topics),
                 positive_topics=sum(any(h > 0 for h in hs) for hs in heats.values()),
                 calibration_topics=len(calibration), evaluation_topics=len(evaluation))
    return heats, background, calibration, evaluation, stats


def rerun_old_selections(monitor, calibration, evaluation, background, retained):
    result = {}
    for key, cohort in (("rv_train", calibration), ("rv_test", evaluation)):
        result[key] = {}
        for threshold in retained["r_grid"]:
            selected = [title for title, _ in study.detect_rv(
                cohort, threshold, 1e12, monitor, variant="bg", bg_stats=background)]
            # Selection order is not a score input; topic membership must be exact.
            check_equal(sorted(selected), sorted(retained[key][str(threshold)]),
                        f"historical selections {key} r={threshold}")
            result[key][str(threshold)] = selected
    return result


def replay_selected(heats, background, retained, monitor):
    rows = []
    for cohort in ("rv_train", "rv_test"):
        for title in retained[cohort]["1.0"]:
            hs = heats[title]
            start = next(i for i, h in enumerate(hs) if h > 0)
            letters = study.letters_for(hs[start:], 1.0, 1e12,
                                        variant="bg", bg_stats=background[start:])
            trace = [dict(p=p, q=q) for p, q, _ in letters]
            verdicts = simulate(monitor, trace)
            predicate = (len(trace) >= 9 and trace[0]["p"]
                         and sum(trace[i]["q"] for i in (0, 2, 4, 8)) >= 2)
            rows.append(dict(cohort=cohort, title=title, periods=len(trace),
                             first_true_prefix=verdicts.index("TRUE") if "TRUE" in verdicts else None,
                             satisfies=predicate, final_verdict=VERDICTS[verdicts[-1]]))
    return dict(topics=len(rows), satisfying=sum(r["satisfies"] for r in rows),
                monitor_true=sum(r["final_verdict"] == "true" for r in rows)), rows


def score(titles, labels, event_map):
    positives, negatives = set(labels["true"]), set(labels["false"])
    if positives & negatives:
        raise ValueError("Conflicting proxy labels")
    missing = set(titles) - positives - negatives
    if missing:
        raise ValueError(f"Unlabeled titles cannot be treated as negatives: {sorted(missing)}")
    if len(set(titles)) != len(titles):
        raise ValueError("Duplicate selected title")
    hot = [t for t in titles if t in positives]
    n, h, e = len(titles), len(hot), len({event_map.get(t, t) for t in hot})
    if not n or not h:
        raise ValueError("Paper rows require positive denominators")
    p, d = h / n, e / h
    harmonic = 2 * p * d / (p + d)
    return [n, h, e, f"{p:.3f}", f"{d:.3f}", f"{harmonic:.3f}"]


def metric_tables(retained):
    folder = ROOT / "data/weibo"
    train_labels = read_json(folder / "ground_truth.json")["train"]
    test_labels = read_json(folder / "ground_truth_test.json")["test"]
    train_events = read_json(folder / "event_map.json")["train"]
    test_events = read_json(folder / "event_map_test.json")["test"]
    calibration = [[str(r), *score(retained["rv_train"][str(r)], train_labels, train_events)]
                   for r in retained["r_grid"]]
    methods = [("Previous RV4PPTL prototype", retained["rv_test"]["1.0"]),
               ("Single-pass", retained["sp_test"]), ("HAC routine", retained["hac_test"]),
               ("K-means label (medoids)", retained["kmeans_test"])]
    evaluation = [[name, *score(titles, test_labels, test_events)] for name, titles in methods]
    return calibration, evaluation


def rerun_baselines(evaluation, retained):
    docs = sorted(evaluation)
    print(f"Building title similarities for {len(docs)} topics...", flush=True)
    similarities = study._sims(docs)
    methods = [
        ("sp_test", lambda: study.single_pass(docs, 0.05, 15, sims=similarities)),
        ("hac_test", lambda: hac_replay(docs, 0.07, 15, sims=similarities)),
        ("kmeans_test", lambda: study.kmeans(docs, max(1, int(len(docs) * 0.06)),
                                            20, sims=similarities)),
    ]
    results = {}
    for name, run in methods:
        print(f"Re-running retained {name} routine...", flush=True)
        titles = run()
        check_equal(titles, retained[name], f"baseline {name} ordered selections")
        results[name] = titles
    return results


def integrity_checks():
    manifest = read_json(ROOT / "data/provenance.json")
    checked = 0
    for item in manifest["files"]:
        if item.get("transformation") == "byte-identical":
            actual = hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
            check_equal(actual, item["sha256"], f"input hash {item['path']}")
            checked += 1
    return checked


def markdown_table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |"] +
                     ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def report_markdown(results):
    chunks = ["# RV4PPTL reproduction results", "All requested comparisons passed.",
              "## Table 1: diagnostic verdicts",
              markdown_table(["q positions", "Observations", "Bounded", "Previous", "Direct"],
                             [[r["high_positions"], r["length"], r["bounded"],
                               r["previous_adapter"], r["direct_backend"]] for r in results["table_1"]]),
              "## Table 2: previous prototype sizes",
              markdown_table(["Property", "SBA", "NFA", "DFA", "Minimized DFA"],
                             [[k, *results["table_2"][k]] for k in ("positive", "negative")]),
              "## Table 3: retained calibration selections",
              markdown_table(["r", "N", "H", "E", "P", "D", "H_PD"], results["table_3"]),
              "## Table 4: retained evaluation selections",
              markdown_table(["Method", "N", "H", "E", "P", "D", "H_PD"], results["table_4"]),
              "## Scope",
              "Tables 3–4 use the retained proxy labels. D is distinctness, not recall. "
              "The corrected backend is validated separately and replayed on the 26 retained topics. "
              "The prototype selections were re-executed from CSV and archived automata. "
              "These scores are not a full-cohort evaluation of the corrected backend.",
              "Baseline algorithms re-executed: " + str(results["baseline_algorithms_rerun"]),
              "The 2.386-second generation time is an archived observation, not a new timing measurement."]
    return "\n\n".join(chunks) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs")
    parser.add_argument("--rerun-baselines", action="store_true",
                        help="Also execute the three historical clustering routines (slower, more RAM).")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    start = time.perf_counter()
    expected = read_json(ROOT / "expected/paper_results.json")
    retained = read_json(ROOT / "data/retained_results.json")
    results = {"paper_version": expected["paper_version"], "input_files_verified": integrity_checks()}
    print("Checking the direct backend and reconstructing the previous adapter...", flush=True)
    validation = run_checks()
    results["validation"] = dict(inputs=validation["input_count"],
                                 prefix_checks=validation["prefix_verdict_checks"],
                                 mismatches=validation["mismatch_count"],
                                 direct_states=validation["compiler_states"])
    old, results["table_2"] = reconstruct_legacy()
    direct = hot_event_monitor()
    results["legacy_diagnostic"], results["table_1"] = diagnostics(old, direct)
    print("Loading CSV and re-running both historical detector cohorts at all five thresholds...", flush=True)
    heats, background, calibration, evaluation, results["data"] = load_study()
    selections = rerun_old_selections(old, calibration, evaluation, background, retained)
    results["retained_replay"], replay = replay_selected(heats, background, retained, direct)
    # Metrics consume regenerated prototype selections, not copies of expected counts.
    metric_inputs = dict(retained, **selections)
    if args.rerun_baselines:
        regenerated_baselines = rerun_baselines(evaluation, retained)
        metric_inputs.update(regenerated_baselines)
    results["table_3"], results["table_4"] = metric_tables(metric_inputs)
    results["baseline_algorithms_rerun"] = args.rerun_baselines
    results["historical_detector_selections_match"] = True
    for key in ("data", "validation", "legacy_diagnostic", "table_1", "table_2",
                "table_3", "table_4", "retained_replay"):
        check_equal(results[key], expected[key], key)
    # Read the retained two-proposition log; results.json describes an older 3-AP build.
    log = (ROOT / "data/two_proposition_check.log").read_text(encoding="utf-8")
    match = re.search(r'"total_time_s"\s*:\s*([\d.]+)', log)
    if not match:
        raise ValueError("Missing two-proposition timing record")
    results["historical_timing_seconds"] = float(match[1])
    check_equal(results["historical_timing_seconds"], expected["historical_timing_seconds"], "recorded timing")
    results["all_requested_checks_passed"] = True
    results["environment"] = dict(python=platform.python_version(), system=platform.system(),
                                  elapsed_seconds=round(time.perf_counter() - start, 3))
    args.output.mkdir(parents=True, exist_ok=True)
    for name, obj in [("results.json", results), ("semantic_validation.json", validation),
                      ("selected_topic_replay.json", replay), ("historical_selections.json", selections)]:
        (args.output / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "paper_tables.md").write_text(report_markdown(results), encoding="utf-8")
    print(f"PASS: all four tables and semantic checks match paper {expected['paper_version']}.\nOutputs: {args.output}", flush=True)
    print(f"Elapsed: {results['environment']['elapsed_seconds']} s; baseline rerun: {args.rerun_baselines}")


if __name__ == "__main__":
    main()
