# ACO/BibTeX replay

This command executes frozen ACO source models through the current original
transformation, mutation oracle and 18-formula SBFL calculation. It writes an
isolated run and does not replace the published CSVs.

From the repository root:

```bash
python -u -X utf8 code/reproduction/replay_aco_bibtex.py --n 10 --workers 4 --run-dir work/runs/aco_bibtex_replay
python -u -X utf8 code/reproduction/replay_aco_bibtex.py --n 100 --workers 4 --run-dir work/runs/aco_bibtex_replay --resume
```

The first command uses a subset; the second extends it to all 100 sources.
Resume checks the saved execution plan and compares reused source inputs with
their saved copies. Use a new run directory after changing code, metamodels or
compiled transformations.

The complete frozen suite has 100 executable original models, 4,000 source/mutant
pairs, 32/40 killed mutants (80%), 2,145 killed pairs (53.625% failure rate) and
231 invalid-runtime pairs. SBFL excludes invalid pairs and produces 720
mutant/formula rows. These outcomes now supply the canonical ACO/BibTeX input
under results/rq2/supplementary/inputs/aco/; all three supported ACO subjects
use the same RQ2/SBFL failure-label protocol.

The run's derived/ directory contains the pair matrix, mutant-level EXAM,
rule spectra, SBFL rule scores, metrics and a comparison report. For the full
suite, differences against the shipped localization CSV are listed explicitly.
The prior ACO protocol's numerical changes are documented in
ACO_PROTOCOL_CHANGES.md.
