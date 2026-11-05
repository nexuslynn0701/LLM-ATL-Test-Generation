# ACO/BibTeX isolated replay trial (2026-11-05)

Historical trial against the pre-unification localization table. The matrix has since been promoted into formal inputs and all three ACO subjects now use canonical localization. Current paper changes are in ACO_PROTOCOL_CHANGES.md; discrepancy counts below describe the earlier reference, not the current unified CSVs.

The trial executed all 100 archived ACO sources against the original
BibTeX2DocBook transformation and all 40 canonical compiled mutants. Source
CSVs were not replaced.

Results:

- Original executions / trace eligibility: 100/100.
- Source/mutant pairs: 4,000, including 231 INVALID_RUNTIME outcomes.
- Killed mutants: 32/40 (80%), with exactly the released kill set.
- Killed pairs: 2,145/4,000; failure rate 53.625%, exactly the released RQ2 value.
- Coverage: 7/9 rules; all 100 per-source coverage sets match the archived
  coverage records.
- The existing RQ2 builder successfully consumes the new matrix, producing
  its normal 9-column summary and 40 per-mutant rows, with no missing pairs.
- Fresh SBFL: 720 mutant/formula records and 6,480 rule/formula score rows.

The RQ3 historical localization inputs do not match the new canonical
failure labels. For example, Mutant1 has 74 failing sources in the new
execution versus 38 in the historical localization table. Historical RQ3
failing-source counts sum to 1,259 over the 40 mutants, rather than 2,145.
Among the 576 mutant/formula rows used by both localization populations,
139 EXAM values, 56 best ranks and 100 tie sizes differ. These are not display
rounding differences. For example, Ochiai EXAM for Mutant28 is 0.444444444444
in the replay and 0.5 in the historical input.

`code/rq3/apply_yekta_canonical_population.py` documents the earlier decision
to change the baseline's evaluable flags while retaining its old rankings.
Replaying the canonical XMI-difference oracle therefore cannot be assumed to
regenerate those retained rankings. Finding the historical baseline SBFL
evidence or revising the baseline localization protocol is still required
before updating paper tables and their statistical comparisons.

A diagnostic that accepts warning-bearing, parseable mutant outputs produces
35/40 kills and a 59.4% failure rate, also differing from RQ2. It is not used
as a replacement policy. Execution errors were not relabeled to force a match.

Run from the bundle root in Git Bash:

```bash
export JAVA_TOOL_OPTIONS='-Xms16m -Xmx128m -XX:ActiveProcessorCount=2 -XX:TieredStopAtLevel=1'
python -u -X utf8 code/reproduction/replay_aco_bibtex.py --n 10 --workers 4 --run-dir work/runs/aco_bibtex_trial
python -u -X utf8 code/reproduction/replay_aco_bibtex.py --n 100 --workers 4 --run-dir work/runs/aco_bibtex_trial --resume
unset JAVA_TOOL_OPTIONS
```

The first command is a subset trial; its percentages are not a reproduction
claim for the full suite. The second extends the same checkpoints to all
100 sources. Resume requires unchanged source hashes, metamodels, compiled
transformations and calculation code. Java resource tuning was checked on
one source: all 40 mutant outcomes and original rule coverage were unchanged.

Outputs are under the chosen run's `derived/` directory, including:

- `source_mutant_outcomes_aco_canonical_bibtex.csv`
- `mutant_level_exam.csv`
- `rule_spectra.csv`
- `sbfl_rule_scores.csv`
- `metrics.csv`
- `report.json` and, for full runs with differences, `localization_differences.csv`

The diagnostic output is not automatically promoted into `results/`,
`results/rq2/supplementary/inputs/aco/` or the paper CSV directory. Other subjects, workflows and
the remaining reproduction gaps have not been rerun by this trial.
