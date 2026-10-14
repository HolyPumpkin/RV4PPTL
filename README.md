# RV4PPTL

Runtime verification of hot events based on Propositional Projection Temporal Logic (PPTL).

RV4PPTL provides:

- a fixed-boundary monitor for PPTL projection specifications of the form
  `((len(d1), ..., len(dm)) prj (len(m) & B)); true`, where `B` is a Boolean formula over
  projected positions;
- a case study that applies the monitor to hot-event detection on a real-world hot-search
  topic dataset;
- a reproduction driver that recomputes every reported result from the archived inputs and
  compares it against archived expected values.

Pure Python 3.10+ standard library — no third-party packages, no network access.

## Quick start

```console
python reproduce.py
```

This runs the full pipeline: semantic validation of the monitor backend, rebuilding of the
legacy automata from archived graphs, replay of historical topic selections, and
recomputation of all result tables. Every result is compared with the archived expected
values; any mismatch exits with a non-zero status.

To also re-run the three clustering baselines (Single-pass, HAC, and medoid-style K-means)
from scratch:

```console
python reproduce.py --rerun-baselines
```

Use a different output directory:

```console
python reproduce.py --output outputs/check2
```

On success the script prints `PASS` and writes the following to `outputs/`:

| File | Contents |
|---|---|
| `results_tables.md` | Human-readable result tables |
| `results.json` | Numeric results, comparison status, runtime environment, timings |
| `semantic_validation.json` | 1,024 inputs, 11,264 prefix-verdict comparisons |
| `selected_topic_replay.json` | Replay of 26 historical topic selections |
| `historical_selections.json` | Detector selections recomputed at five thresholds |

Input data and expected results are never modified.

## Monitor API

```python
from rv4pptl import hot_event_monitor, simulate, At, And, Not, compile_projection

monitor = hot_event_monitor()
trace = [{"p": True, "q": i in (0, 8)} for i in range(10)]
verdicts = simulate(monitor, trace)
assert verdicts[8] == "?"
assert verdicts[9:] == ["TRUE", "TRUE"]

# Projected positions 0, 1, 2 map to original positions 0, 2, 5.
another = compile_projection([2, 3], ["p", "q"],
                             And(At("p", 0), Not(At("q", 2))))
```

`simulate` includes the initial output, so index `n` holds the verdict after reading `n`
observations. The internal verdict encoding `TRUE / FALSE / ?` corresponds to
`true / false / inconclusive` in the reports. This example monitors the initial window only;
it does not perform sliding-window search.

## Repository layout

| Path | Contents |
|---|---|
| `rv4pptl/monitor.py` | Fixed-boundary PPTL projection monitor (current backend) |
| `rv4pptl/validation.py` | Semantic validation of the backend |
| `rv4pptl/legacy.py` | Previous adapter, kept for historical comparison |
| `rv4pptl/case_study.py` | Original clustering pipeline (Single-pass, HAC, K-means) |
| `rv4pptl/baselines.py` | Optimized HAC replay used by the full mode |
| `rv4pptl/reproduction.py` | Reproduction driver |
| `tests/` | Unit tests |
| `data/` | Archived inputs (see below) |
| `expected/` | Archived expected results, used only for comparison |
| `outputs/` | Generated reports (git-ignored) |

## Data

Original data source: the [weibo-hot-hub](https://github.com/lonnyzhang423/weibo-hot-hub)
hot-search archive. This repository ships processed hourly CSV data from 2023-05-28 to
2023-06-24; downloading snapshots and parsing raw pages are outside the reproduction scope.

- `data/weibo/` — hourly data, retained positive/negative proxy labels, event-deduplication maps.
- `data/legacy_automata/` — archived automaton graphs for the positive and negative properties.
- `data/retained_results.json` — archived outputs of the earlier prototype, including
  construction metadata from an earlier three-proposition version.
- `data/two_proposition_check.log` — archived construction and timing log.
- `data/provenance.json` — input provenance, SHA-256 hashes, and migration notes.

The `ground_truth` naming in the data files is historical. These labels are proxy judgments
produced by a news heuristic, not a full manual annotation. `D = E/H` is distinctness and
`H_PD` is the harmonic score of precision and distinctness; neither is recall or standard F1.

## Scope notes

- The two monitors must not be combined into a single performance result.
  `rv4pptl/monitor.py` is the fixed-boundary backend; `rv4pptl/legacy.py` preserves the
  previous adapter, including the missed-final-sample issue it exhibits.
- The 2.386-second timing recorded in `data/two_proposition_check.log` is an archived record
  from the original machine. The legacy pipeline is rebuilt from the archived PPTL2BA output
  graphs; the external PPTL2BA translator is not re-executed.
- The monitor backend accepts sample intervals and a Boolean syntax tree; it is not a
  general PPTL text parser.

## Tests

```console
python -m unittest discover -s tests -v
```

