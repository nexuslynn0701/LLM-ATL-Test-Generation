# Environment, Model Access, and Provenance

This file records the facts an artifact reviewer needs to judge the credibility
of the pipeline: which LLMs were called with which parameters and when, which
tool versions execute the ATL chain, where the subjects and mutants come from,
and which ledger records which generated models entered which mutation run.
Everything below is stated with the in-package file that carries the fact.

## LLM access

| Role | Provider | Model id |
|---|---|---|
| GPT | OpenAI | `gpt-5.1` |
| Qwen | Alibaba Cloud | `qwen3-max` |
| DeepSeek | DeepSeek | `deepseek-v4-flash` |

- Alias → model id mapping: `code/pipeline/src/experiment/run_ladder_experiment.py`
  (`gpt → gpt-5.1`, `qwen → qwen3-max`, `deepseek-flash → deepseek-v4-flash`).
- Sampling: `temperature = 0.2` for all providers, set in
  `code/pipeline/src/llm/llm_client.py`. No `top_p` or `seed` overrides are
  sent to the APIs; remaining parameters are provider defaults. (A deterministic
  per-attempt seed schedule exists in `openllm_config.py` but belongs to the
  local open-weight model line, which is not used for the paper's results.)
- Per-call audit: `code/pipeline/src/llm/call_logger.py` records, for every API
  call, the resolved model string returned by the provider, token usage, the
  sampling parameters actually sent, retries, and the
  subject/condition/attempt context (JSONL).
- Access window: **2026-06-01 – 2026-08-06**, identical for all three providers,
  derived from the `timestamp` column of
  `results/rq1/supplementary/generation_attempt_records/generation_attempt_records.csv`.
- Raw responses are **not** part of this package (see Scope in `README.md`);
  API output is non-deterministic, so reproduction is defined at the level of
  the shipped per-attempt ledger plus the harness.

## Feedback-driven (FD) workflow prompts

The RQ5 workflow starts from six fully rendered initial prompts
(`data/workflow/prompts/<subject>.txt`) and one template
(`data/workflow/prompts/template.txt`). Later turns are assembled at runtime:
covered-rule feedback is appended to the next request, and failed executions go
through the adaptive repair component — see the six-step loop in
`data/workflow/README.md` and `data/workflow/src/generator/test_generator.py`
("ATL verification with adaptive repair"). The complete workflow engine
(Python + Java sources, dependencies, entry point `run_workflow.py`) is in
`data/workflow/`.

## Execution environment

| Component | Version | Evidence |
|---|---|---|
| ATL | 3.6.0 (`v201505180909`) | `org.eclipse.m2m.atl_*_3.6.0.*.jar` in `code/pipeline/lib/` |
| EMF | 2.11.0 | `org.eclipse.emf.*-2.11.0*.jar` in `code/pipeline/lib/` |
| Eclipse core runtime | 3.11.1 | `org.eclipse.core.runtime_3.11.1.*.jar` in `code/pipeline/lib/` |
| JDK | 17.0.7 LTS (Windows) — used for every in-package replay/verification run of this artifact | this machine's replays; `ATLRunner` runs without an Eclipse install (`code/pipeline/lib/ATLRunner.java`) |
| Python | ≥ 3.10 with `requirements.txt` | execution and data-analysis scripts |

The generation runs themselves predate this package (Linux); the exact jar
versions the pipeline executes against are pinned and shipped in
`code/pipeline/lib/`.

## Subjects

- Six ATL transformation subjects; local copies in `subjects/<subject>/`:
  metamodel (`.ecore`), original **and** trace-instrumented transformations
  (`transformations/`), and scenarios (`scenarios/`).
- Upstream: cases from the public ATL transformation zoo as used by prior work
  on mutation testing for model transformations (cited in the paper).
  `BibTeX2DocBook` was renamed from the upstream directory
  `models_BibTexML2DocBook` (recorded in `subjects/INDEX.md`).
- Study additions (not available upstream): the scenario sets, the OCL
  constraint files (`data/ocl/<subject>/`), and the instrumented
  transformation copies used for rule-coverage tracing.

## Mutants (shipped in full)

Mutation scores are a direct function of the mutant set, so the set itself is
part of this package: `data/mutants/<subject>/` contains every mutant ATL/ASM
file plus its manifest.

| Subject | Mutants in the experiment denominator | Provenance |
|---|---|---|
| Ant2Maven | 100 accepted `FormalMutant`s | generator-produced; accepted list in `Ant2Maven_FormalMutant_manifest.json` |
| Grafcet2PetriNet | 30 manual mutants | hand-edited spec single-point changes; `Grafcet2PetriNet_ManualMutant_manifest.json` (671 additional `FormalMutant` sources are retained but excluded from the denominator) |
| others | operator mutants with per-subject manifests | same directory |

## Which generated models entered which mutation run

- Population ledger: `results/rq1/supplementary/source_population.csv`
  (`artifact_exists`, `in_estar` select the final E\* population; the 79
  attempts without an artifact are retained there with their status).
- Kill matrix: `results/experiment_results/RQ2/mutant_kill_matrix.csv`;
  per-mutant fail-ratio inputs in `results/rq2/supplementary/inputs/source_mutant_outcomes.csv`.
- `code/reproduction/verify.py` cross-checks ledger ↔ regenerated artifacts and
  the 300-file ACO SHA ledger whenever generated outputs are present, and
  reports a SKIP line otherwise.

## Baselines

- **Yekta-ACO**: third-party search-based tool (cited in the paper). The search
  tool is not redistributed. Frozen source models are in `data/test_cases/`,
  with their population metadata in `data/test_cases/_metadata/aco/`.
  Source evidence is under `results/rq1/supplementary/aco/`; mutation evidence
  is under `results/rq2/supplementary/`. Run configuration is documented in
  the paper's baseline section.

## Entry points and expected runtimes

Measured on a commodity laptop (Windows, warm cache), from the package root:

| Command | Wall time |
|---|---|
| `python code/reproduction/verify.py` | ~2 s (~2 s also in SKIP mode without generated XMI) |
| `python code/prepare_pipeline.py --check` | < 1 s |
| `python -m unittest discover -s code/rq1 -p "test_*.py"` | ~2 s |
| `python code/rq1/check_failure_taxonomy.py` | < 1 s |
| `python code/rq1/rule_coverage.py` | ~1 s |
| `python code/reproduction/build_tables.py` | ~1–2 min |

The 19 paper CSVs are in `results/experiment_results/`. Supporting evidence is
under `results/rq1/supplementary/` through `results/rq5/supplementary/`.
See `REPRODUCIBILITY.md` for the calculation commands and evidence boundaries.
