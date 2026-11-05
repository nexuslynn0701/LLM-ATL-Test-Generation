# Current reproduction checks

Run these commands from the repository root after installing requirements.txt
and making Java 17 (including javac) available on PATH:

```bash
python -X utf8 code/reproduction/smoke_test.py
python -X utf8 code/reproduction/build_tables.py
python -X utf8 code/reproduction/verify.py
python -X utf8 code/reproduction/injection_tests.py
```

The smoke test compiles the model-size tool, executes the fixed BibTeX scenario,
compares original and mutant target models, then executes 40 mutants and
computes 18 SBFL formulas (720 localization records). Mutant1's Ochiai result
has best rank 1, eight tied rules and EXAM-AC 0.5. This is a ranking
demonstration; it does not identify one unique top-ranked rule.

The CSV builder checks 20 steps and exports the 19 paper CSVs under
results/experiment_results/. Reconstruction and diagnostic outputs go under
rebuild/. Each results/rq1 through results/rq5 directory contains only
supplementary/ evidence. The normal report has 18 MATCH and 2 PARTIAL steps,
with no MISMATCH or ERROR. Injection tests must catch all eight tampering cases.

Historical replay placeholders, retired orchestration scripts and the unused
local-model extension are excluded from this release. Independent SBFL rank
arithmetic needed by regression tests is retained in code/tests/fixtures/.
The supported fresh-run entry point is code/run_pipeline.py; its default mode
only checks the environment. Replay uses the frozen models in data/test_cases/.
New generation requires explicit provider credentials and is nondeterministic.

The evidence limits remain visible: full historical non-ACO spectra are not
bundled; 74,160 non-ACO localization records are shipped inputs. ACO's 1,944
localization records are rebuilt from 10,600 canonical pairs and source-rule
coverage. Twelve workflow coverage cells lack per-source evidence, one coverage
cell conflicts with available evidence, and two workflow kill sets disagree
between pair and localization records. Cleanup does not resolve these gaps.
See REPRODUCIBILITY.md for the complete computation boundaries.

Subject execution settings are centralized in
code/pipeline/src/experiment/subject_config.py. The ladder entry point and
mutant utilities use that same registry. The alternate experiment framework,
disabled library copies and third-party source-only JARs are excluded from
the runtime bundle. Binary runtime JARs and compiler/runner sources remain.
