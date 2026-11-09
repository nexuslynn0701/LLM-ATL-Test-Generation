# LLM-ATL-Test-Generation

We compared test models from GPT, Qwen, and DeepSeek on six ATL transformations, with Yekta-ACO as the baseline. We tried four prompt contexts for each LLM (SM, STM, ASTM, and ASTMO). RQ5 compares ASTMO with FD-ASTMO, which feeds rule coverage back into later prompts.

The model IDs were `gpt-5.1`, `qwen3-max`, and `deepseek-v4-flash`. The [RQ1 generation ledger](results/rq1/supplementary/generation_attempt_records/generation_attempt_records.csv) lists each generation attempt and its status. The frozen test models are in [`data/test_cases/`](data/test_cases/).

The BibTeX2DocBook example shows how the scripts detect a killed mutant and rank its faulty rule. To check the paper results, rebuild the 19 CSVs from the bundled experiment records. Both runs work offline without an LLM API key.

## Setup

We tested the package on Windows with JDK 17.0.7. Use Python 3.10 or later and make sure `java` and `javac` are on your PATH. The ATL and EMF libraries are included.

On Windows, use a short path such as `C:/atl-repro`. A long path can cause the pipeline to fail when it creates its working copy. Run the commands from the repository root in Git Bash.

```bash
python -m pip install -r requirements.txt
```

## 1. Run the mutation and fault localization example

```bash
python -X utf8 code/reproduction/smoke_test.py
```

The smoke test runs the original transformation and 40 mutants on a fixed BibTeX2DocBook input. Mutant1 produces a different XMI output, so the script marks it as `KILLED`. The script uses the original run's rule coverage and the mutant outcomes to rank rules with 18 spectrum-based fault localization (SBFL) formulas.

A successful run ends with `SMOKE TEST: PASS — all checks passed`. Look for Mutant1's `KILLED` row in `rebuild/smoke_loc/derived/evidence/source_mutant_outcomes.csv`.

The localization CSV at `rebuild/smoke_loc/derived/rq3/mutant_level_exam.csv` has 720 rows, one per mutant and formula. For Mutant1, Ochiai ranks the faulty rule `Article_Title_Journal` first in a tie with seven other rules. Mutant1's EXAM-AC score under Ochiai is 0.5.

## 2. Rebuild the RQ1–RQ5 data

```bash
python -X utf8 code/reproduction/build_tables.py --export-dir rebuild/paper_csvs
```

The build checks the results against the [19 paper CSVs](results/experiment_results/). After the checks pass, it writes the CSVs to `rebuild/paper_csvs/`, with one folder per RQ. If you omit `--export-dir`, a successful run updates `results/experiment_results/`.

Read `rebuild/report.md` for the summary or `rebuild/report.json` for the result of each check. The manifest at `rebuild/experiment_results_manifest.json` records where the CSV data came from.

| Status | Meaning |
| --- | --- |
| `MATCH` | All required comparisons passed. |
| `PARTIAL` | The values that could be checked passed. See the report for missing evidence, conflicting records, or differences in how values were compared. |
| `MISMATCH` / `ERROR` | A comparison failed or a step could not run. The script exits with a nonzero status. |

| Research question | CSV directory | Contents |
| --- | --- | --- |
| RQ1 | [RQ1](results/experiment_results/RQ1/) | Test model validity rates, sizes of valid models, and rule coverage. |
| RQ2 | [RQ2](results/experiment_results/RQ2/) | Mutation scores, failure rates, the mutant kill matrix, per-mutant failure counts, and mutation operator statistics. |
| RQ3 | [RQ3](results/experiment_results/RQ3/) | Top-1 rates, EXAM scores, per-mutant localization data, and paired statistical comparisons with Yekta-ACO. |
| RQ4 | [RQ4](results/experiment_results/RQ4/) | Overall metrics and fault localization performance across the four prompt contexts. |
| RQ5 | [RQ5](results/experiment_results/RQ5/) | Testing and fault localization metrics for ASTMO and FD-ASTMO, results by formula, and overlap in the mutants they kill. |

### Optional checks

Run these after step 2. `verify.py` checks the released data for consistency. `injection_tests.py` passes if the verifier catches all eight test discrepancies.

```bash
python -X utf8 code/reproduction/verify.py
python -X utf8 code/reproduction/injection_tests.py
```

## Repository layout

| Path | Contents |
| --- | --- |
| [`subjects/`](subjects/) | Metamodels, original transformations, variants that trace rule coverage, and fixed input scenarios for the six ATL subjects. |
| [`data/mutants/`](data/mutants/) | ATL mutant source files, compiled ASM files, and manifests. |
| [`data/test_cases/`](data/test_cases/) | Frozen LLM and Yekta-ACO test models and their metadata. |
| [`data/ocl/`](data/ocl/), [`data/prompts/`](data/prompts/), [`data/workflow/`](data/workflow/) | OCL constraints, prompts, and the feedback-driven workflow. |
| [`code/`](code/) | Scripts to run ATL, test mutants, compute SBFL scores, and rebuild and check the CSVs. |
| [`results/experiment_results/`](results/experiment_results/) | The 19 paper CSVs organized by research question. |
| [`results/rq1/`](results/rq1/) through [`results/rq5/`](results/rq5/) | Each `supplementary/` folder holds the records for that RQ, such as generation attempts, evidence for individual models or mutants, and rule coverage. |
