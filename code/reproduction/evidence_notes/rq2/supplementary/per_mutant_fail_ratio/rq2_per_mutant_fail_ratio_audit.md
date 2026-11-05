# RQ2 Per-Mutant Fail-Ratio — Audit Report (All Subjects)

Generated: 2026-10-15T07:19:28.515012+00:00

Quantile method: numpy 2.5.3, `numpy.percentile(..., [25,50,75])`, `method='linear'` (linear interpolation).

## 1. Denominator & Outcome Definitions

- `n_original_executable_sources` = distinct source_ids with `original_success == '1'` in `source_mutant_outcomes.csv` (the mutant-testing-phase signal).
- Sources whose original ATL failed at mutant-testing time (`original_success == '0'`) are excluded from BOTH the denominator and the outcome counts.
- 2026-10-15: the bundled outcomes file carries the Ant0030 replay patch — the 100 Ant2Maven/gpt/astmo/0030 rows were restored to `original_success == '1'` with the outcomes of `results/rq2/supplementary/audits/rq23_ant0030_replay.csv` (14 KILLED / 72 ALIVE / 14 INVALID_RUNTIME), so GPT-ASTMO on Ant2Maven has n = 96, matching the released tables.
- `fail_ratio = n_killed / n_original_executable_sources`; ERROR and INVALID count as `not killed` and stay in the denominator.
- `KILLED→killed, ALIVE→alive, ERROR→error, INVALID_CONTAINMENT/INVALID_RUNTIME/ORIGINAL_FAIL→invalid`.
- `workflow` condition is RQ4-only and excluded, matching the RQ2 pipeline.

## 2. Subject: Ant2Maven

- Eligible mutants: **100** (excluded stillborn/invalid=0, equivalent=0, not_evaluated=0)
- Long-CSV rows: 1300 (methods with data × 100 mutants)

### Ant2Maven — Source suite size

| Method | n_original_executable_sources |
|---|---:|
| GPT-SM | 100 |
| GPT-STM | 100 |
| GPT-ASTM | 98 |
| GPT-ASTMO | 96 |
| Qwen-SM | 88 |
| Qwen-STM | 96 |
| Qwen-ASTM | 66 |
| Qwen-ASTMO | 100 |
| DeepSeek-Flash-SM | 97 |
| DeepSeek-Flash-STM | 97 |
| DeepSeek-Flash-ASTM | 77 |
| DeepSeek-Flash-ASTMO | 69 |
| MM-Random | 100 |
| Yekta-ACO | — |

### Ant2Maven — Mutation-score & fail-ratio cross-check

| Method | n_src | Killed | MS% | Exp MS% | Match | meanFR% | Exp FR% | FR match | status |
|---|---:|---:|---:|---:|---|---:|---:|---|
| GPT-SM | 100 | 33 | 33.0 | 33.0 | ✅ | 10.27 | — | — | OK |
| GPT-STM | 100 | 30 | 30.0 | 30.0 | ✅ | 11.09 | — | — | OK |
| GPT-ASTM | 98 | 43 | 43.0 | 43.0 | ✅ | 28.3163 | — | — | OK |
| GPT-ASTMO | 96 | 41 | 41.0 | 41.0 | ✅ | 21.0521 | — | — | OK |
| Qwen-SM | 88 | 30 | 30.0 | 30.0 | ✅ | 15.9318 | — | — | OK |
| Qwen-STM | 96 | 38 | 38.0 | 38.0 | ✅ | 18.1875 | — | — | OK |
| Qwen-ASTM | 66 | 40 | 40.0 | 40.0 | ✅ | 29.803 | — | — | OK |
| Qwen-ASTMO | 100 | 27 | 27.0 | 27.0 | ✅ | 15.92 | — | — | OK |
| DeepSeek-Flash-SM | 97 | 23 | 23.0 | 23.0 | ✅ | 12.8969 | — | — | OK |
| DeepSeek-Flash-STM | 97 | 36 | 36.0 | 36.0 | ✅ | 12.8454 | — | — | OK |
| DeepSeek-Flash-ASTM | 77 | 39 | 39.0 | 39.0 | ✅ | 20.1429 | — | — | OK |
| DeepSeek-Flash-ASTMO | 69 | 36 | 36.0 | 36.0 | ✅ | 17.058 | — | — | OK |
| MM-Random | 100 | 39 | 39.0 | 39.0 | ✅ | 36.52 | — | — | OK |
| Yekta-ACO |  |  |  | — | — |  | — | — | N/A |

### Ant2Maven — sanity-check issues

✅ none (ACO conflict flagged separately).

## 2. Subject: BibTeX2DocBook

- Eligible mutants: **40** (excluded stillborn/invalid=0, equivalent=0, not_evaluated=0)
- Long-CSV rows: 520 (methods with data × 40 mutants)

### BibTeX2DocBook — Source suite size

| Method | n_original_executable_sources |
|---|---:|
| GPT-SM | 100 |
| GPT-STM | 99 |
| GPT-ASTM | 100 |
| GPT-ASTMO | 100 |
| Qwen-SM | 90 |
| Qwen-STM | 91 |
| Qwen-ASTM | 99 |
| Qwen-ASTMO | 100 |
| DeepSeek-Flash-SM | 100 |
| DeepSeek-Flash-STM | 100 |
| DeepSeek-Flash-ASTM | 96 |
| DeepSeek-Flash-ASTMO | 71 |
| MM-Random | 100 |
| Yekta-ACO | — |

### BibTeX2DocBook — Mutation-score & fail-ratio cross-check

| Method | n_src | Killed | MS% | Exp MS% | Match | meanFR% | Exp FR% | FR match | status |
|---|---:|---:|---:|---:|---|---:|---:|---|
| GPT-SM | 100 | 29 | 72.5 | 72.5 | ✅ | 64.75 | 64.8 | ✅ | OK |
| GPT-STM | 99 | 27 | 67.5 | 67.5 | ✅ | 64.9747 | 65.0 | ✅ | OK |
| GPT-ASTM | 100 | 34 | 85.0 | 85.0 | ✅ | 78.775 | 78.8 | ✅ | OK |
| GPT-ASTMO | 100 | 32 | 80.0 | 80.0 | ✅ | 76.525 | 76.5 | ✅ | OK |
| Qwen-SM | 90 | 26 | 65.0 | 65.0 | ✅ | 49.8056 | 49.8 | ✅ | OK |
| Qwen-STM | 91 | 26 | 65.0 | 65.0 | ✅ | 51.8681 | 51.9 | ✅ | OK |
| Qwen-ASTM | 99 | 32 | 80.0 | 80.0 | ✅ | 72.8788 | 72.9 | ✅ | OK |
| Qwen-ASTMO | 100 | 32 | 80.0 | 80.0 | ✅ | 70.025 | 70.0 | ✅ | OK |
| DeepSeek-Flash-SM | 100 | 25 | 62.5 | 62.5 | ✅ | 62.5 | 62.5 | ✅ | OK |
| DeepSeek-Flash-STM | 100 | 25 | 62.5 | 62.5 | ✅ | 62.5 | 62.5 | ✅ | OK |
| DeepSeek-Flash-ASTM | 96 | 32 | 80.0 | 80.0 | ✅ | 74.7656 | 74.8 | ✅ | OK |
| DeepSeek-Flash-ASTMO | 71 | 32 | 80.0 | 80.0 | ✅ | 72.1831 | 72.2 | ✅ | OK |
| MM-Random | 100 | 31 | 77.5 | 77.5 | ✅ | 61.75 | 61.8 | ✅ | OK |
| Yekta-ACO |  |  |  | 100.0 | — |  | — | — | MISSING_PAIR_INPUT |

### BibTeX2DocBook — sanity-check issues

✅ none (ACO conflict flagged separately).

## 2. Subject: CPL2SPL

- Eligible mutants: **50** (excluded stillborn/invalid=0, equivalent=0, not_evaluated=0)
- Long-CSV rows: 500 (methods with data × 50 mutants)

### CPL2SPL — Source suite size

| Method | n_original_executable_sources |
|---|---:|
| GPT-SM | 17 |
| GPT-STM | 5 |
| GPT-ASTM | 18 |
| GPT-ASTMO | 17 |
| Qwen-SM | — |
| Qwen-STM | — |
| Qwen-ASTM | — |
| Qwen-ASTMO | — |
| DeepSeek-Flash-SM | 1 |
| DeepSeek-Flash-STM | 2 |
| DeepSeek-Flash-ASTM | 2 |
| DeepSeek-Flash-ASTMO | 2 |
| MM-Random | 100 |
| Yekta-ACO | 96 |

### CPL2SPL — Mutation-score & fail-ratio cross-check

| Method | n_src | Killed | MS% | Exp MS% | Match | meanFR% | Exp FR% | FR match | status |
|---|---:|---:|---:|---:|---|---:|---:|---|
| GPT-SM | 17 | 41 | 82.0 | 82.0 | ✅ | 72.7059 | — | — | OK |
| GPT-STM | 5 | 38 | 76.0 | 76.0 | ✅ | 73.6 | — | — | OK |
| GPT-ASTM | 18 | 45 | 90.0 | 90.0 | ✅ | 70.3333 | — | — | OK |
| GPT-ASTMO | 17 | 42 | 84.0 | 84.0 | ✅ | 65.1765 | — | — | OK |
| Qwen-SM |  |  | 0.0 | — | ✅ |  | — | — | NO_EXECUTABLE |
| Qwen-STM |  |  | 0.0 | — | ✅ |  | — | — | NO_EXECUTABLE |
| Qwen-ASTM |  |  | 0.0 | — | ✅ |  | — | — | NO_EXECUTABLE |
| Qwen-ASTMO |  |  | 0.0 | — | ✅ |  | — | — | NO_EXECUTABLE |
| DeepSeek-Flash-SM | 1 | 33 | 66.0 | 66.0 | ✅ | 66.0 | — | — | OK |
| DeepSeek-Flash-STM | 2 | 40 | 80.0 | 80.0 | ✅ | 74.0 | — | — | OK |
| DeepSeek-Flash-ASTM | 2 | 38 | 76.0 | 76.0 | ✅ | 75.0 | — | — | OK |
| DeepSeek-Flash-ASTMO | 2 | 41 | 82.0 | 82.0 | ✅ | 65.0 | — | — | OK |
| MM-Random | 100 | 38 | 76.0 | 76.0 | ✅ | 32.06 | — | — | OK |
| Yekta-ACO | 96 | 50 | 100.0 | 100.0 | ✅ | 33.3958 | — | — | OK |

### CPL2SPL — sanity-check issues

✅ none (ACO conflict flagged separately).

## 2. Subject: Ecore2Maude

- Eligible mutants: **50** (excluded stillborn/invalid=0, equivalent=0, not_evaluated=0)
- Long-CSV rows: 650 (methods with data × 50 mutants)

### Ecore2Maude — Source suite size

| Method | n_original_executable_sources |
|---|---:|
| GPT-SM | 66 |
| GPT-STM | 57 |
| GPT-ASTM | 56 |
| GPT-ASTMO | 68 |
| Qwen-SM | 30 |
| Qwen-STM | 44 |
| Qwen-ASTM | 34 |
| Qwen-ASTMO | 86 |
| DeepSeek-Flash-SM | 79 |
| DeepSeek-Flash-STM | 88 |
| DeepSeek-Flash-ASTM | 59 |
| DeepSeek-Flash-ASTMO | 82 |
| MM-Random | 40 |
| Yekta-ACO | — |

### Ecore2Maude — Mutation-score & fail-ratio cross-check

| Method | n_src | Killed | MS% | Exp MS% | Match | meanFR% | Exp FR% | FR match | status |
|---|---:|---:|---:|---:|---|---:|---:|---|
| GPT-SM | 66 | 49 | 98.0 | 98.0 | ✅ | 97.0909 | — | — | OK |
| GPT-STM | 57 | 50 | 100.0 | 100.0 | ✅ | 95.4386 | — | — | OK |
| GPT-ASTM | 56 | 50 | 100.0 | 100.0 | ✅ | 97.5 | — | — | OK |
| GPT-ASTMO | 68 | 50 | 100.0 | 100.0 | ✅ | 98.1176 | — | — | OK |
| Qwen-SM | 30 | 50 | 100.0 | 100.0 | ✅ | 97.8 | — | — | OK |
| Qwen-STM | 44 | 50 | 100.0 | 100.0 | ✅ | 98.5 | — | — | OK |
| Qwen-ASTM | 34 | 50 | 100.0 | 100.0 | ✅ | 98.2353 | — | — | OK |
| Qwen-ASTMO | 86 | 50 | 100.0 | 100.0 | ✅ | 98.0233 | — | — | OK |
| DeepSeek-Flash-SM | 79 | 50 | 100.0 | 100.0 | ✅ | 97.4177 | — | — | OK |
| DeepSeek-Flash-STM | 88 | 50 | 100.0 | 100.0 | ✅ | 95.5227 | — | — | OK |
| DeepSeek-Flash-ASTM | 59 | 49 | 98.0 | 98.0 | ✅ | 97.1864 | — | — | OK |
| DeepSeek-Flash-ASTMO | 82 | 49 | 98.0 | 98.0 | ✅ | 96.6341 | — | — | OK |
| MM-Random | 40 | 45 | 90.0 | 90.0 | ✅ | 80.15 | — | — | OK |
| Yekta-ACO |  |  |  | — | — |  | — | — | N/A |

### Ecore2Maude — sanity-check issues

✅ none (ACO conflict flagged separately).

## 2. Subject: Grafcet2PetriNet

- Eligible mutants: **30** (excluded stillborn/invalid=0, equivalent=0, not_evaluated=0)
- Long-CSV rows: 390 (methods with data × 30 mutants)

### Grafcet2PetriNet — Source suite size

| Method | n_original_executable_sources |
|---|---:|
| GPT-SM | 98 |
| GPT-STM | 97 |
| GPT-ASTM | 99 |
| GPT-ASTMO | 100 |
| Qwen-SM | 100 |
| Qwen-STM | 100 |
| Qwen-ASTM | 100 |
| Qwen-ASTMO | 100 |
| DeepSeek-Flash-SM | 100 |
| DeepSeek-Flash-STM | 100 |
| DeepSeek-Flash-ASTM | 97 |
| DeepSeek-Flash-ASTMO | 100 |
| MM-Random | 100 |
| Yekta-ACO | — |

### Grafcet2PetriNet — Mutation-score & fail-ratio cross-check

| Method | n_src | Killed | MS% | Exp MS% | Match | meanFR% | Exp FR% | FR match | status |
|---|---:|---:|---:|---:|---|---:|---:|---|
| GPT-SM | 98 | 22 | 73.3333 | 73.3 | ✅ | 69.0476 | — | — | OK |
| GPT-STM | 97 | 21 | 70.0 | 70.0 | ✅ | 68.6942 | — | — | OK |
| GPT-ASTM | 99 | 22 | 73.3333 | 73.3 | ✅ | 68.3838 | — | — | OK |
| GPT-ASTMO | 100 | 22 | 73.3333 | 73.3 | ✅ | 68.2 | — | — | OK |
| Qwen-SM | 100 | 22 | 73.3333 | 73.3 | ✅ | 73.1333 | — | — | OK |
| Qwen-STM | 100 | 22 | 73.3333 | 73.3 | ✅ | 72.7333 | — | — | OK |
| Qwen-ASTM | 100 | 22 | 73.3333 | 73.3 | ✅ | 72.8667 | — | — | OK |
| Qwen-ASTMO | 100 | 22 | 73.3333 | 73.3 | ✅ | 72.1 | — | — | OK |
| DeepSeek-Flash-SM | 100 | 22 | 73.3333 | 73.3 | ✅ | 69.9333 | — | — | OK |
| DeepSeek-Flash-STM | 100 | 22 | 73.3333 | 73.3 | ✅ | 70.3667 | — | — | OK |
| DeepSeek-Flash-ASTM | 97 | 22 | 73.3333 | 73.3 | ✅ | 71.4777 | — | — | OK |
| DeepSeek-Flash-ASTMO | 100 | 22 | 73.3333 | 73.3 | ✅ | 70.3333 | — | — | OK |
| MM-Random | 100 | 21 | 70.0 | 70.0 | ✅ | 70.0 | — | — | OK |
| Yekta-ACO |  |  |  | — | — |  | — | — | N/A |

### Grafcet2PetriNet — sanity-check issues

✅ none (ACO conflict flagged separately).

## 2. Subject: UML2ER

- Eligible mutants: **18** (excluded stillborn/invalid=0, equivalent=0, not_evaluated=0)
- Long-CSV rows: 252 (methods with data × 18 mutants)

### UML2ER — Source suite size

| Method | n_original_executable_sources |
|---|---:|
| GPT-SM | 94 |
| GPT-STM | 100 |
| GPT-ASTM | 100 |
| GPT-ASTMO | 100 |
| Qwen-SM | 100 |
| Qwen-STM | 100 |
| Qwen-ASTM | 100 |
| Qwen-ASTMO | 100 |
| DeepSeek-Flash-SM | 98 |
| DeepSeek-Flash-STM | 100 |
| DeepSeek-Flash-ASTM | 98 |
| DeepSeek-Flash-ASTMO | 96 |
| MM-Random | 100 |
| Yekta-ACO | 100 |

### UML2ER — Mutation-score & fail-ratio cross-check

| Method | n_src | Killed | MS% | Exp MS% | Match | meanFR% | Exp FR% | FR match | status |
|---|---:|---:|---:|---:|---|---:|---:|---|
| GPT-SM | 94 | 16 | 88.8889 | 88.9 | ✅ | 88.4161 | — | — | OK |
| GPT-STM | 100 | 16 | 88.8889 | 88.9 | ✅ | 88.7778 | — | — | OK |
| GPT-ASTM | 100 | 16 | 88.8889 | 88.9 | ✅ | 88.8889 | — | — | OK |
| GPT-ASTMO | 100 | 16 | 88.8889 | 88.9 | ✅ | 88.8333 | — | — | OK |
| Qwen-SM | 100 | 16 | 88.8889 | 88.9 | ✅ | 88.8889 | — | — | OK |
| Qwen-STM | 100 | 16 | 88.8889 | 88.9 | ✅ | 88.8889 | — | — | OK |
| Qwen-ASTM | 100 | 16 | 88.8889 | 88.9 | ✅ | 88.8889 | — | — | OK |
| Qwen-ASTMO | 100 | 16 | 88.8889 | 88.9 | ✅ | 88.8889 | — | — | OK |
| DeepSeek-Flash-SM | 98 | 16 | 88.8889 | 88.9 | ✅ | 85.941 | — | — | OK |
| DeepSeek-Flash-STM | 100 | 16 | 88.8889 | 88.9 | ✅ | 87.0 | — | — | OK |
| DeepSeek-Flash-ASTM | 98 | 16 | 88.8889 | 88.9 | ✅ | 88.2086 | — | — | OK |
| DeepSeek-Flash-ASTMO | 96 | 16 | 88.8889 | 88.9 | ✅ | 88.8889 | — | — | OK |
| MM-Random | 100 | 18 | 100.0 | 100.0 | ✅ | 92.3333 | — | — | OK |
| Yekta-ACO | 100 | 13 | 72.2222 | 100.0 | ❌ | 70.0556 | — | — | OK_STRICT_CANONICAL |

### UML2ER — sanity-check issues

- ❌ CHECK5 FAIL: UML2ER/Yekta-ACO MS=72.2222 vs table 100.0 (ACO canonical vs legacy)

## 3. Yekta-ACO Pair-Data Provenance

ACO is evaluated on the three Troya subjects using the **canonical replay** matrix. This matrix disagrees with the legacy aggregate (which feeds the current RQ2 table's Yekta-ACO = 100%).

| Subject | canonical MS% | legacy MS% | agree? |
|---|---:|---:|---|
| BibTeX2DocBook | MISSING_PAIR_INPUT | 100.0 | ❌ |
| CPL2SPL | 100.0 (50/50) | 100.0 (50/50) | ✅ |
| UML2ER | 72.2 (13/18) | 100.0 (18/18) | ❌ |

- `source_mutant_outcomes_aco_replay_cpl_uml.csv` — canonical replay for CPL2SPL/UML2ER (converted from results/rq1/supplementary/aco/estar_evidence).
- `source_mutant_outcomes_aco_canonical_bibtex.csv` — canonical BibTeX2DocBook pair matrix, **pending** re-export from the original workspace; the subject is reported as MISSING_PAIR_INPUT.
- `source_mutant_outcomes_aco_legacy.csv` — legacy supplementary (deprecated for source-level evidence).

⚠️ The long/summary CSVs ship the **canonical** matrix. If a figure must match the legacy aggregate instead, use the legacy matrix for Yekta-ACO on BibTeX2DocBook and UML2ER. CPL2SPL agrees at 100% either way.

## 4. Data-Quality Notes (original_success == '0' exclusions)

The following source models have `original_success == '0'` in `source_mutant_outcomes.csv` — i.e. the original ATL re-execution failed during mutant testing, so all their mutant outcomes are ERROR/ORIGINAL_FAIL and they are excluded from the fail-ratio denominator (Ant2Maven/0030 was restored by the 2026-10-15 replay patch, see §1):

| Subject | Provider | Condition | Source | Outcome | n_rows |
|---|---|---|---|---|---:|
| Grafcet2PetriNet | gpt | sm | 0023 | ORIGINAL_FAIL | 30 |
| Grafcet2PetriNet | gpt | stm | 0004 | ORIGINAL_FAIL | 30 |
| Grafcet2PetriNet | gpt | stm | 0051 | ORIGINAL_FAIL | 30 |
| Grafcet2PetriNet | gpt | stm | 0075 | ORIGINAL_FAIL | 30 |
| Grafcet2PetriNet | gpt | astm | 0062 | ORIGINAL_FAIL | 30 |

## 5. NO_EXECUTABLE / N/A / MISSING cells

| Subject | Cell | Status |
|---|---|---|
| Ant2Maven | Yekta-ACO | N/A (tool-incompatible) |
| BibTeX2DocBook | Yekta-ACO | MISSING_PAIR_INPUT (canonical BibTeX matrix pending) |
| CPL2SPL | Qwen-SM | NO_EXECUTABLE |
| CPL2SPL | Qwen-STM | NO_EXECUTABLE |
| CPL2SPL | Qwen-ASTM | NO_EXECUTABLE |
| CPL2SPL | Qwen-ASTMO | NO_EXECUTABLE |
| Ecore2Maude | Yekta-ACO | N/A (tool-incompatible) |
| Grafcet2PetriNet | Yekta-ACO | N/A (tool-incompatible) |
