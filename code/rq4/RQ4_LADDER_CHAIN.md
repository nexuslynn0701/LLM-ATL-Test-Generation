# RQ4 CSV calculation

Run `python -X utf8 code/reproduction/build_tables.py --only rq4` to verify RQ4.
Run the full builder to export the unified collection of 19 paper CSVs.

The two current RQ4 files are:

- `results/experiment_results/RQ4/rq4_ladder_four_columns_pooled.csv`: validity,
  rule coverage, mutation score and failure rate. Mutation and failure are
  checked against pooled counts in `results/rq2/supplementary/`.
- `results/experiment_results/RQ4/rq4_top1_exam_pooled.csv`: pooled localization
  metrics and changes relative to SM. `pool_localization.py` reads
  `results/experiment_results/RQ3/mutant_level_exam.csv` and pools evaluable
  mutants across subjects and all 18 formulas per LLM/context.

Top-1 is the proportion with best rank at most one. EXAM-AC uses tie-mid
ranks recovered onto the exact `2 * rule_count * n_faulty_rules` rank grid.
Fractions are pooled before display rounding. Supplementary audit records
remain under `results/rq4/supplementary/`. Older equal-subject summaries in
that directory are historical evidence, not the current pooled paper CSVs.
