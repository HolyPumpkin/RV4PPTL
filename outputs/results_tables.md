# RV4PPTL reproduction results

All requested comparisons passed.

## Table 1: diagnostic verdicts

| q positions | Observations | Bounded | Previous | Direct |
| --- | --- | --- | --- | --- |
| [0, 2] | 9 | inconclusive | true | true |
| [0, 2] | 10 | false | true | true |
| [0, 8] | 9 | inconclusive | inconclusive | true |
| [0, 8] | 10 | false | false | true |

## Table 2: previous prototype sizes

| Property | SBA | NFA | DFA | Minimized DFA |
| --- | --- | --- | --- | --- |
| positive | 30 | 30 | 21 | 21 |
| negative | 21 | 21 | 28 | 15 |

## Table 3: retained calibration selections

| r | N | H | E | P | D | H_PD |
| --- | --- | --- | --- | --- | --- | --- |
| 1.0 | 17 | 14 | 13 | 0.824 | 0.929 | 0.873 |
| 0.9 | 18 | 15 | 13 | 0.833 | 0.867 | 0.850 |
| 0.8 | 20 | 16 | 14 | 0.800 | 0.875 | 0.836 |
| 0.7 | 25 | 20 | 16 | 0.800 | 0.800 | 0.800 |
| 0.6 | 33 | 24 | 20 | 0.727 | 0.833 | 0.777 |

## Table 4: retained evaluation selections

| Method | N | H | E | P | D | H_PD |
| --- | --- | --- | --- | --- | --- | --- |
| Previous RV4PPTL prototype | 9 | 8 | 6 | 0.889 | 0.750 | 0.814 |
| Single-pass | 15 | 4 | 4 | 0.267 | 1.000 | 0.421 |
| HAC routine | 15 | 3 | 3 | 0.200 | 1.000 | 0.333 |
| K-means label (medoids) | 20 | 10 | 10 | 0.500 | 1.000 | 0.667 |

## Scope

Tables 3–4 use the retained proxy labels. D is distinctness, not recall. The corrected backend is validated separately and replayed on the 26 retained topics. The prototype selections were re-executed from CSV and archived automata. These scores are not a full-cohort evaluation of the corrected backend.

Baseline algorithms re-executed: False

The 2.386-second generation time is an archived observation, not a new timing measurement.
