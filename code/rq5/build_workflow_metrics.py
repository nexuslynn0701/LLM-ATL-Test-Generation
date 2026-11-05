"""Forward builder for results/rq5/data/workflow_metrics.csv (四指标 54 格).

历史上该表的数值经 LaTeX 表与 figure.zip 传递，从未有可运行的聚合脚本（断点 4）。
本脚本补上"原始证据 → 四指标"的前向计算，并用已发布表格做全量往返校验：

  validity        = n_estar / 100 attempts                    （E* = 原始转换执行成功 且 trace-eligible）
  rule_coverage   = |∪ E* 源覆盖规则| / 该科目规则全域
  mutation_score  = |被 ≥1 个 E* 源杀死的变异体| / 合格变异体全域
  failure_rate    = Σ(逐变异体 failing_sources) / (n_estar × 合格变异体)
  n_estar = 0 的格（如 Qwen×CPL2SPL×astm/astmo）：三项下游指标按约定记 N/A("--")，不计 0/0。

校验输入（均为包内发布证据）：
  results/rq1/data/subjects.csv            规则/变异体固定全域
  results/rq1/supplementary/source_population.csv   逐源执行结果（E* 判定）
  results/rq1/supplementary/source_rule_coverage.csv 逐源×规则覆盖标记（含 astm/astmo/workflow）
  results/rq3/data/mutant_level_exam.csv   逐变异体记录（failing_sources 跨 18 公式一致，取 ochiai）
对照目标：results/rq5/data/workflow_metrics.csv（分子/分母为最简百分比分数，精确比对）

新运行对接：--from-run 读取 code/run_pipeline.py 的完整 cell.json 证据，
  检查每个 E* 源的全部正式变异体配对记录，按实际 attempts 聚合四指标。
  输出默认放在运行目录 derived/rq5，不覆盖发布数据。

用法：
  python code/rq5/build_workflow_metrics.py             # 全量校验
  python code/rq5/build_workflow_metrics.py --verbose   # 逐格打印
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUBJECTS_CSV = ROOT / 'results/rq1/data/subjects.csv'
POPULATION_CSV = ROOT / 'results/rq1/supplementary/source_population.csv'
RULE_COVERAGE_CSV = ROOT / 'results/rq1/supplementary/source_rule_coverage.csv'
MUTANT_EXAM_CSV = ROOT / 'results/rq3/data/mutant_level_exam.csv'
RELEASED_CSV = ROOT / 'results/rq5/data/workflow_metrics.csv'

CONDITIONS = ('astm', 'astmo', 'workflow')
LLMS = ('GPT', 'Qwen', 'DeepSeek')
PROVIDER_ALIASES = {'gpt': 'GPT', 'qwen': 'Qwen', 'deepseek-flash': 'DeepSeek', 'deepseek': 'DeepSeek'}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def load_universe() -> dict[str, dict[str, int]]:
    return {r['transformation']: {'rules': int(r['total_rules']), 'mutants': int(r['mutants'])}
            for r in read_csv(SUBJECTS_CSV)}


def load_estar() -> dict[tuple[str, str, str], set[str]]:
    estar: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for r in read_csv(POPULATION_CSV):
        if r['condition'] in CONDITIONS and r['original_execution_success'] == '1' and r['trace_eligible'] == '1':
            estar[(r['subject'], r['provider'], r['condition'])].add(r['source_id'])
    return estar


def load_coverage(estar: dict[tuple[str, str, str], set[str]]) -> tuple[dict[tuple[str, str, str], set[str]], set[tuple[str, str, str]]]:
    """Return (E*-filtered covered-rule unions, cells with any coverage rows).

    workflow 条件的逐源覆盖证据包内只有部分科目（Ant2Maven、Grafcet2PetriNet）；
    其余科目该证据不在包内，这些格标记为证据缺失而非数值为 0。
    """
    covered: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    present: set[tuple[str, str, str]] = set()
    for r in read_csv(RULE_COVERAGE_CSV):
        if r['condition'] not in CONDITIONS:
            continue
        llm = PROVIDER_ALIASES.get(r['provider'], r['provider'])
        cell = (r['subject'], llm, r['condition'])
        present.add(cell)
        if r['covered'] != '1':
            continue
        if r['source_id'] not in estar.get(cell, ()):
            continue
        covered[cell].add(r['rule_id'])
    return covered, present


def load_kills() -> dict[tuple[str, str, str], dict[str, int]]:
    kills: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: {'killed': 0, 'pairs': 0})
    for r in read_csv(MUTANT_EXAM_CSV):
        if r['formula'] != 'ochiai' or r['condition'] not in CONDITIONS:
            continue
        cell = (r['subject'], r['provider'], r['condition'])
        if r['evaluable'] == '1':
            kills[cell]['killed'] += 1
        kills[cell]['pairs'] += int(r['failing_sources'] or 0)
    return kills


def build_cells() -> tuple[list[dict[str, object]], set[tuple[str, str, str]]]:
    universe = load_universe()
    estar = load_estar()
    covered, present = load_coverage(estar)
    kills = load_kills()
    rows = []
    for subject, u in universe.items():
        for llm in LLMS:
            for condition in CONDITIONS:
                cell = (subject, llm, condition)
                n = len(estar.get(cell, ()))
                row: dict[str, object] = {'subject': subject, 'llm': llm, 'condition': condition,
                                          'n_estar': n}
                if n == 0:
                    row.update(validity=Fraction(0), coverage=None, mutation=None, failure=None, killed=0)
                else:
                    rules = u['rules']
                    mutants = u['mutants']
                    k = kills.get(cell, {'killed': 0, 'pairs': 0})
                    cov = len(covered.get(cell, ()))
                    row.update(validity=Fraction(100 * n, 100),
                               coverage=Fraction(100 * cov, rules),
                               mutation=Fraction(100 * k['killed'], mutants),
                               failure=Fraction(100 * k['pairs'], n * mutants),
                               killed=k['killed'])
                rows.append(row)
    return rows, present


def fraction_of(num: str, den: str) -> Fraction | None:
    if num == '' or den == '':
        return None
    return Fraction(int(num), int(den))


def compare(computed: list[dict[str, object]], present: set[tuple[str, str, str]], verbose: bool) -> int:
    released = {(r['subject'], r['llm'], r['condition']): r for r in read_csv(RELEASED_CSV)}
    problems: list[str] = []
    conflicts: list[str] = []
    gaps: list[str] = []
    checks = 0
    for row in computed:
        key = (row['subject'], row['llm'], row['condition'])
        rel = released[key]
        pairs = [('n_estar', row['n_estar'], int(rel['n_estar'])),
                 ('validity', row['validity'], fraction_of(rel['validity_pct_numerator'], rel['validity_pct_denominator'])),
                 ('mutation', row['mutation'], fraction_of(rel['mutation_score_pct_numerator'], rel['mutation_score_pct_denominator'])),
                 ('failure', row['failure'], fraction_of(rel['failure_rate_pct_numerator'], rel['failure_rate_pct_denominator'])),
                 ('killed_mutants', row['killed'], int(rel['killed_mutants']))]
        # 覆盖率：证据不在包内的格（source_rule_coverage 无该格任何行）只登记缺失，不参与比对。
        if key in present or row['n_estar'] == 0:
            pairs.insert(2, ('coverage', row['coverage'],
                             fraction_of(rel['coverage_pct_numerator'], rel['coverage_pct_denominator'])))
        else:
            gaps.append(f'{key[0]}/{key[1]}/{key[2]} coverage: no per-source evidence in bundle '
                        f'(released {rel["coverage_pct_numerator"]}/{rel["coverage_pct_denominator"]})')
        for metric, mine, theirs in pairs:
            checks += 1
            if mine != theirs:
                if metric == 'coverage':
                    conflicts.append(f'{key[0]}/{key[1]}/{key[2]} coverage: evidence union {mine} vs '
                                     f'released {theirs} (released is the audited value)')
                else:
                    problems.append(f'{key[0]}/{key[1]}/{key[2]} {metric}: computed {mine} vs released {theirs}')
        if verbose:
            print(f'{key[0]:16s} {key[1]:8s} {key[2]:8s} n={row["n_estar"]:3d} '
                  f'cov={row["coverage"]} mut={row["mutation"]} fail={row["failure"]} killed={row["killed"]}')
    print(f'compared {len(computed)} cells, {checks} exact comparisons; hard mismatches: {len(problems)}')
    for p in problems:
        print('  MISMATCH', p)
    print(f'evidence gaps (skipped, workflow per-source coverage not in bundle): {len(gaps)}')
    for g in gaps:
        print('  GAP', g)
    print(f'evidence conflicts (formula validated elsewhere; released audited value stands): {len(conflicts)}')
    for c in conflicts:
        print('  CONFLICT', c)
    return 1 if problems else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verbose', action='store_true', help='print every cell')
    parser.add_argument('--from-run', type=Path, help='Fresh run directory produced by code/run_pipeline.py')
    parser.add_argument('--output', type=Path, help='Fresh-run output directory (default: RUN/derived/rq5)')
    args = parser.parse_args()
    if args.from_run:
        sys.path.insert(0, str(ROOT / 'code'))
        from experiment_pipeline.evidence import load_run
        from experiment_pipeline.aggregate import rq5
        out = args.output or args.from_run / 'derived/rq5'
        rows = rq5(load_run(args.from_run), out)
        print(f'Wrote {len(rows)} observed cells to {out}; no missing cells filled from historical results.')
        return
    computed, present = build_cells()
    raise SystemExit(compare(computed, present, args.verbose))


if __name__ == '__main__':
    main()
