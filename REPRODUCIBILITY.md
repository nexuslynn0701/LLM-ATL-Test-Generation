# Reproducibility

## Current protocol

The paper retains GPT, Qwen and DeepSeek under four prompt conditions (SM, STM, ASTM, ASTMO), plus Yekta-ACO. The former baseline has been removed from the active CSVs and calculation method lists. All 18 localization formulas remain. RQ3 therefore has 13 configuration columns and 216 paired LLM-versus-ACO comparisons (3 providers × 4 prompt conditions × 18 formulas).

Each two-sided Wilcoxon test pairs common evaluable mutants. ACO localization now uses the same canonical pair outcomes as RQ2 for all three supported subjects: KILLED/ALIVE supply failing/passing tests, and invalid runtime/containment executions are excluded from SBFL. Original per-source rule coverage supplies the spectra. Both rankings and EXAM are recomputed; historical ACO rankings are not retained. Classification uses raw p-values: p_raw >= .05 is Similar; otherwise A12 > .5 is Better, and the remaining cases are Worse. The 216 tests produce 208 Worse, 8 Similar and 0 Better outcomes. Adjusted-p columns are absent.

## Commands

```bash
python -X utf8 code/reproduction/smoke_test.py
python -X utf8 code/reproduction/build_tables.py
python -X utf8 code/reproduction/injection_tests.py
```

GNU make is optional: the equivalents are `make smoke-test`, `make tables` and `make inject`. Run the table builder before injection checks, because they use rebuilt artifacts.

All 19 paper-facing CSVs are collected under `code/experiment_results/`, organized as RQ1 through RQ5. A successful full build refreshes this directory automatically; failed verification never overwrites it. RQ5 includes `rq5_overall_pooled.csv` for the four-metric figure and `pooled_overall_by_formula.csv` for Tables 16/17. These are rebuilt into `rebuild/rq5/`, checked against the released tables, then exported. The localization table is reaggregated from shipped historical per-mutant records rather than new ATL executions. The report remains at `rebuild/report.json` and `rebuild/report.md`. Internal comparison artifacts remain under `rebuild/` and are compared against the sibling `experiment_results/` author reference when present. A missing reference is not proof of reference equality.

## Verified computation boundaries

- RQ1 validity: 7,200 LLM attempt records; ACO validity counts are released aggregates. Model size: 78 retained rows including three non-applicable ACO cells. Coverage is rebuilt from rule evidence.
- RQ2: 12 LLM prompt configurations plus ACO. Scores, failure summaries, per-mutant counts, four-method kill flags and operator summaries use the retained evidence. The per-mutant builder preserves stable method-order IDs; ACO retains ID 14, leaving a harmless gap in display ordering.
- RQ3: 76,104 retained mutant/formula records; 18-formula Top-1/EXAM summaries; 216 raw-p Wilcoxon/A12 comparisons and updated counts. The 74,160 non-ACO mutant-level rows remain shipped historical inputs. All 1,944 ACO rows are independently rebuilt from 10,600 canonical pairs and complete source-rule coverage.
- RQ4: retained LLM context comparisons and pooled localization metrics.
- RQ5: released workflow metrics are verified against available evidence; overlap is reconstructed from the retained localization records and cross-checked against pair exports where present.

The mirror manifest separates recomputed values, metadata/copied ACO rows and copied/filtered inputs. Schema completeness does not imply independent recomputation of copied fields.

## Status meanings

MATCH: the specified complete comparison passed. PARTIAL: comparable values passed, but explicitly identified evidence, measurements or source-backed inputs remain unavailable or conflicting. MISMATCH/ERROR: the run exits nonzero. The scope gate checks active CSVs for retired-method contamination and enforces 13 RQ3 configurations and 216 comparisons.

The eight-case injection suite checks altered Top-1, altered killed count, impossible validity rounding, a missing RQ4 anchor, a missing column, an invalid candidate count, a stale ACO failing-source count with unchanged evaluability, and an empty reconstructed ACO kill flag. All eight must return MISMATCH. If no sibling author export is present, a temporary reference is built from formal inputs. Tests do not modify reference files.

## Remaining limitations (unaffected by the scope change)

1. ACO/BibTeX canonical pair evidence has been reconstructed by replaying all 100 frozen sources and 40 mutants. The formal input now contains all 4,000 pairs; kill set 32/40 and failure rate 53.625% match RQ2. Supported ACO mutation/failure, kill flags and operator scores are rebuilt without the former missing-matrix exceptions. Ledger text and non-applicable cells remain copied metadata.
2. Twelve workflow coverage cells lack per-source evidence. Ant2Maven/DeepSeek/workflow has evidence coverage 100% versus released 280/3%. The report lists all GAP/CONFLICT cells.
3. Ant2Maven/GPT/workflow and Ant2Maven/DeepSeek/workflow kill sets differ between the pair export and localization records by 2 and 7 mutants respectively. RQ5 uses the localization records and retains the paper anchors; the underlying evidence conflict remains.
4. Full historical non-ACO localization spectra are not bundled. The 74,160 non-ACO rows remain input evidence; ACO spectra and 1,944 localization rows are rebuilt from canonical pairs. Fixed-scenario smoke testing demonstrates fresh execution and localization, and does not claim to reproduce all original generated samples.
5. LLM generation is nondeterministic. The supplied prompts and attempt ledger document the experiment; repeating API calls cannot guarantee the original samples.
6. The existing RQ4 LaTeX ladder's left four columns use the older equal-subject view; the current pooled CSV is emitted separately. The baseline-scope update does not change this pre-existing distinction.

The ACO protocol change preserves the 95-mutant evaluable population (BibTeX/CPL/UML = 32/50/13) and all LLM/workflow rows. It changes ACO Top-1/EXAM columns, 214 raw p-values and two classifications. RussellRao's W/S/B count becomes 12/0/0. The before/after paper values are recorded in `code/reproduction/ACO_PROTOCOL_CHANGES.md`. The earlier [trial record](code/reproduction/ACO_BIBTEX_TRIAL.md) explains why changing evaluable flags alone was insufficient.

Java 17 and the bundled ATL/EMF jars support the Windows demonstration. Python dependencies are listed in requirements.txt. Current-scope tables and inference can be rebuilt without network access or API keys.
