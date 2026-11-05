#!/usr/bin/env python3
"""Bridge: pipeline run outputs -> rqx-style rule spectra long CSV.

This replaces the missing top-level ``export_sbfl_detailed.py`` stage that
``run_pipeline.sh`` (stage 6) and ``scripts/auto_sbfl_v2.sh`` referenced. It
exports the per-test/per-rule detail that the mutation-testing SBFL pipeline
already computes internally (``src/analyzer/sbfl_analyzer.py``) into the exact
8-column schema of ``rq3_test_rule_spectra_long.csv`` — the input format of
the verified mutant47 rebuild chain:

    subject,provider,condition,model_id,mutant_id,rule_id,rule_covered,test_outcome

Semantics (identical to compute_sbfl_for_mutant):
  * one row per (test model x mutant x rule) for every executed pair;
  * rule_covered = 1 iff the rule fired in the test model's trace XMI
    (traces are taken from the original execution, the same list
    compute_sbfl_for_mutant reuses across mutants);
  * test_outcome = FAIL iff the XMI-diff oracle detects a difference between
    the original and the mutant transformation outputs (PASS otherwise).
    The OCL-oracle variant of that decision is available separately via
    scripts/recompute_sbfl_ocl_oracle.py.

The output feeds the aggregation chain directly, e.g.:

    python code/rq3/replay_sandbox.py                 # prepare inputs
    python code/rq3/rebuild_top1_source_adapted.py    # spectra -> mutant_level_exam.csv

Usage:
    python scripts/export_rule_spectra_long.py \
        --results-root <dir-containing-outputs> \
        [--provider gpt|qwen|deepseek-flash|yekta_aco] \
        [--method GPT_fl_aware_v2]        # legacy alias: provider inferred from prefix \
        [--dataset all|Ant2Maven ...] [--condition sm ...] \
        [-o rule_spectra_long.csv] [--datasets-root DIR]

``--provider`` defaults to inference from ``--method`` (GPT*->gpt, Qwen*->qwen,
DeepSeek*->deepseek-flash, Yekta*->yekta_aco) and then
from the results-root directory name. Condition values pass through the
sub-directory names found under ``outputs/<dataset>/``.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.experiment.run_ladder_experiment import DATASETS          # noqa: E402
from src.analyzer.coverage_analyzer import extract_rules_and_helpers  # noqa: E402
from src.analyzer.sbfl_analyzer import (                            # noqa: E402
    _parse_trace_rules,
    _outputs_differ,
)

PROVIDER_ALIASES = [
    ('gpt', 'gpt'), ('qwen', 'qwen'), ('deepseek', 'deepseek-flash'),
    ('yekta', 'yekta_aco'),
]


def infer_provider(token: str) -> str:
    t = token.strip().lower()
    for prefix, name in PROVIDER_ALIASES:
        if t.startswith(prefix):
            return name
    raise SystemExit(f'Cannot infer provider from {token!r}; pass --provider explicitly.')


def out_names(ds: dict) -> list[str]:
    return list(ds.get('executor_target_mms', {})) if ds.get('executor_target_mms') else []


def model_indices(cond_dir: Path) -> list[str]:
    idx = sorted({m.group(1) for p in cond_dir.glob('output_*_trace.xmi')
                  if (m := re.fullmatch(r'output_(\d+)_trace\.xmi', p.name))})
    return idx


def original_output(cond_dir: Path, idx: str, outs: list[str]):
    if outs:
        result = {}
        for out in outs:
            p = cond_dir / f'output_{idx}_{out}.xmi'
            if not p.is_file():
                return None
            result[out] = str(p)
        return result
    p = cond_dir / f'output_{idx}.xmi'
    return str(p) if p.is_file() else None


def mutant_names(cond_dir: Path, idx: str, outs: list[str]) -> set[str]:
    names = set()
    for p in cond_dir.glob(f'output_{idx}_*.xmi'):
        stem = p.name[len(f'output_{idx}_'):-len('.xmi')]
        if stem == 'trace':
            continue
        for out in outs:
            if stem.endswith('_' + out):
                stem = stem[:-(len(out) + 1)]
                break
        if stem:
            names.add(stem)
    return names


def mutant_output(cond_dir: Path, idx: str, mutant: str, outs: list[str]):
    if outs:
        result = {}
        for out in outs:
            p = cond_dir / f'output_{idx}_{mutant}_{out}.xmi'
            if not p.is_file():
                return None
            result[out] = str(p)
        return result
    p = cond_dir / f'output_{idx}_{mutant}.xmi'
    return str(p) if p.is_file() else None


def export(results_root: Path, provider: str, datasets: list[str],
           conditions: list[str], out_path: Path, datasets_root: Path) -> int:
    outputs_root = results_root / 'outputs'
    if not outputs_root.is_dir():
        raise SystemExit(f'No outputs/ directory under {results_root}')
    available = sorted(d for d in outputs_root.iterdir() if d.is_dir())
    selected = [d for d in available if d.name in datasets]
    missing = set(datasets) - {d.name for d in selected}
    if missing:
        raise SystemExit(f'Requested datasets not present under outputs/: {sorted(missing)}')

    rule_cache: dict[str, list[str]] = {}

    def all_rules(subject: str) -> list[str]:
        if subject not in rule_cache:
            ds = DATASETS[subject]
            atl = datasets_root / Path(ds['dataset_dir']).name / ds['atl_file']
            if not atl.is_file():
                raise SystemExit(f'ATL not found for {subject}: {atl}')
            rule_cache[subject] = extract_rules_and_helpers(str(atl))['rules']
        return rule_cache[subject]

    n_rows = n_pairs = 0
    with out_path.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['subject', 'provider', 'condition', 'model_id',
                    'mutant_id', 'rule_id', 'rule_covered', 'test_outcome'])
        for ds_dir in selected:
            subject = ds_dir.name
            rules = all_rules(subject)
            outs = out_names(DATASETS[subject])
            for cond_dir in sorted(p for p in ds_dir.iterdir() if p.is_dir()):
                if conditions and cond_dir.name not in conditions:
                    continue
                traces: dict[str, set] = {}
                originals: dict[str, object] = {}
                for idx in model_indices(cond_dir):
                    traces[idx] = _parse_trace_rules(str(cond_dir / f'output_{idx}_trace.xmi'))
                    originals[idx] = original_output(cond_dir, idx, outs)
                mutants = set()
                for idx in traces:
                    mutants |= mutant_names(cond_dir, idx, outs)
                for mutant in sorted(mutants):
                    for idx in sorted(traces):
                        orig = originals[idx]
                        mut = mutant_output(cond_dir, idx, mutant, outs)
                        if orig is None or mut is None:
                            continue
                        failed = _outputs_differ(orig, mut)
                        n_pairs += 1
                        covered = traces[idx]
                        outcome = 'FAIL' if failed else 'PASS'
                        for rule in rules:
                            w.writerow([subject, provider, cond_dir.name, idx.zfill(4),
                                        mutant, rule, int(rule in covered), outcome])
                            n_rows += 1
                    print(f'  {subject}/{cond_dir.name}/{mutant}: '
                          f'{len(traces)} models -> cumulative {n_rows} rows', flush=True)
    print(f'Wrote {out_path}: {n_rows} rows, {n_pairs} (model x mutant) pairs, '
          f'provider={provider}')
    return n_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--results-root', type=Path, required=True,
                    help='directory containing outputs/<dataset>/<condition>/')
    ap.add_argument('--provider', help='spectra provider column value')
    ap.add_argument('--method', help='legacy alias; provider inferred from its prefix')
    ap.add_argument('--dataset', nargs='+', default=['all'],
                    help='dataset (subject) names, or "all"')
    ap.add_argument('--condition', nargs='+', default=[],
                    help='condition sub-directory names (default: all)')
    ap.add_argument('-o', '--output', type=Path, default=None,
                    help='output CSV (default: <results-root>/rule_spectra_long.csv)')
    ap.add_argument('--datasets-root', type=Path, default=ROOT / 'datasets',
                    help='root containing models_* datasets (default: pipeline datasets/)')
    args = ap.parse_args()

    if args.provider:
        provider = args.provider
    elif args.method:
        provider = infer_provider(args.method)
    else:
        provider = infer_provider(args.results_root.resolve().name)
    datasets = ([d for d in DATASETS] if args.dataset == ['all']
                else [d for d in args.dataset])
    unknown = [d for d in datasets if d not in DATASETS]
    if unknown:
        raise SystemExit(f'Unknown datasets {unknown}; known: {list(DATASETS)}')
    out_path = args.output or (args.results_root / 'rule_spectra_long.csv')
    export(args.results_root, provider, datasets, args.condition, out_path,
           args.datasets_root)


if __name__ == '__main__':
    main()
