"""Unadjusted RQ3 tests, strict all-11 selection with pooled-mean fallback.

Baseline: ACO only (216 tests). LLM internal: 1,188 tests.
The current A12 direction rule is retained in the requested result; a separate
signed-rank direction analysis tests whether A12 can be removed from decisions.
All decisions use raw p-values.
Run from any directory: python code/rq3/build_raw_p_all11_mean_fallback.py
"""
import csv
import itertools
import json
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import numpy as np
import scipy
from scipy.stats import mannwhitneyu, rankdata, wilcoxon

from build_strict_significance_selection import CELLS, FORMULAS, label

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'results/rq3/data/mutant_level_exam.csv'
OUT = ROOT / 'results/rq3/supplementary/raw_p_all11_mean_fallback_20261103'
TABLES = ROOT / 'results/rq3/tables'
FORMULAS = sorted(FORMULAS, key=lambda x: x[1].lower())
ACO = ('Yekta-ACO', 'aco')


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def exact_exam(row):
    den = 2 * int(row['rule_count']) * int(row['n_faulty_rules'])
    value = Fraction(row['exam_ac'])
    exact = Fraction(round(value * den), den)
    assert abs(exact - value) < Fraction(1, 10**10)
    return exact


def compare(formula, ca, cb, grid):
    x, y = grid[formula, ca], grid[formula, cb]
    keys = sorted(x.keys() & y.keys())
    a, b = np.array([x[k] for k in keys]), np.array([y[k] for k in keys])
    d = a - b  # Preserve published raw-p input precision and zero handling.
    nz = d[d != 0]
    ranks = rankdata(abs(nz), method='average')
    wplus, wminus = float(ranks[nz > 0].sum()), float(ranks[nz < 0].sum())
    assert wplus + wminus == len(nz) * (len(nz) + 1) / 2
    if len(nz):
        result = wilcoxon(a, b, zero_method='wilcox', alternative='two-sided', method='auto')
        p, stat = float(result.pvalue), float(result.statistic)
        assert stat == min(wplus, wminus)
    else:
        p, stat = 1., 0.
    a12 = 1 - float(mannwhitneyu(a, b, alternative='two-sided').statistic) / (len(a) * len(b))
    # Independent probability-of-superiority check, including half-credit ties.
    enumerated = (np.count_nonzero(a[:, None] < b[None, :]) + .5 * np.count_nonzero(a[:, None] == b[None, :])) / (len(a) * len(b))
    assert abs(a12 - enumerated) < 1e-14
    class_a12 = class_wilcoxon = 'Similar'
    if p < .05:
        assert a12 != .5 and wplus != wminus
        class_a12 = 'Better' if a12 > .5 else 'Worse'
        class_wilcoxon = 'Better' if wminus > wplus else 'Worse'
    return dict(formula=formula, cell_a=label(ca), cell_b=label(cb),
                n_common=len(keys), n_nonzero=len(nz), p_raw=p,
                W_two_sided=stat, W_plus=wplus, W_minus=wminus,
                mean_paired_difference=float(d.mean()), median_paired_difference=float(np.median(d)),
                A12=a12, classification_A12=class_a12, classification_wilcoxon=class_wilcoxon)


def select(internal, means, class_field):
    chosen, details = [], []
    labels = list(map(label, CELLS))
    for f, name in FORMULAS:
        rs = [r for r in internal if r['formula'] == f]
        wins, losses = Counter(), Counter()
        for r in rs:
            if r[class_field] == 'Similar':
                continue
            a, b = r['cell_a'], r['cell_b']
            winner, loser = (a, b) if r[class_field] == 'Better' else (b, a)
            wins[winner] += 1
            losses[loser] += 1
        best = [c for c in labels if wins[c] == 11]
        worst = [c for c in labels if losses[c] == 11]
        best_reason = 'significantly_better_than_all_11' if best else 'minimum_pooled_mean_fallback'
        worst_reason = 'significantly_worse_than_all_11' if worst else 'maximum_pooled_mean_fallback'
        if not best:
            value = min(means[f, c] for c in labels)
            best = [c for c in labels if means[f, c] == value]
        if not worst:
            value = max(means[f, c] for c in labels)
            worst = [c for c in labels if means[f, c] == value]
        chosen.append(dict(formula=f, formula_display=name, best=' / '.join(best), worst=' / '.join(worst),
                           best_reason=best_reason, worst_reason=worst_reason,
                           best_mean_exam=float(means[f, best[0]]), worst_mean_exam=float(means[f, worst[0]]),
                           significant_internal_pairs=sum(r['p_raw'] < .05 for r in rs)))
        for c in labels:
            details.append(dict(formula=f, cell=c, significant_wins=wins[c], significant_losses=losses[c],
                                nonsignificant_comparisons=11-wins[c]-losses[c],
                                qualifies_best=int(wins[c] == 11), qualifies_worst=int(losses[c] == 11)))
    return chosen, details


def counts(tests, field):
    out = []
    for f, name in FORMULAS:
        c = Counter(r[field] for r in tests if r['formula'] == f)
        assert sum(c.values()) == 12
        out.append(dict(formula=f, formula_display=name, Worse=c['Worse'], Similar=c['Similar'], Better=c['Better']))
    return out


def latex(caption, tag, columns, header, rows, note):
    return '\n'.join([
        r'\begin{table}[t]', r'\centering', r'\caption{'+caption+'}', r'\label{'+tag+'}',
        r'\begin{tabular}{'+columns+'}', r'\toprule', ' & '.join(header)+r' \\', r'\midrule',
        *[' & '.join(row)+r' \\' for row in rows], r'\bottomrule', r'\end{tabular}',
        r'\par\smallskip', r'\begin{minipage}{\linewidth}\footnotesize '+note,
        r'\end{minipage}', r'\end{table}', ''])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = read(SOURCE)
    grid, pooled = defaultdict(dict), defaultdict(list)
    for r in rows:
        cell = (r['provider'], r['condition'])
        if r['evaluable'] != '1' or cell not in CELLS + [ACO]:
            continue
        key = (r['formula'], cell)
        mutant = (r['subject'], r['mutant_id'])
        assert mutant not in grid[key]
        grid[key][mutant] = float(r['exam_ac'])
        pooled[r['formula'], label(cell)].append(exact_exam(r))
    means = {key: sum(vals, Fraction(0))/len(vals) for key, vals in pooled.items()}
    internal = [compare(f, ca, cb, grid) for f, _ in FORMULAS for ca, cb in itertools.combinations(CELLS, 2)]
    baseline = [compare(f, ca, ACO, grid) for f, _ in FORMULAS for ca in CELLS]
    assert len(internal) == 1188 and len(baseline) == 216
    prior = {(r['formula'], r['provider']+'-'+r['condition'].upper()): r
             for r in read(ROOT/'results/rq3/data/rq3_pairwise_tests.csv') if r['baseline']=='Yekta-ACO'}
    for r in baseline:
        old = prior[r['formula'], r['cell_a']]
        for field in ['p_raw', 'A12', 'n_common']:
            assert abs(r[field]-float(old[field])) < 1e-12
    prior_internal = {(r['formula'], r['cell_a'], r['cell_b']): r for r in read(
        ROOT/'results/rq3/supplementary/pairwise_significance_only/llm_internal_pairwise_tests.csv')}
    for r in internal:
        old = prior_internal[r['formula'], r['cell_a'], r['cell_b']]
        assert abs(r['p_raw']-float(old['p_raw'])) < 1e-12
        assert abs(r['A12']-float(old['A12_a'])) < 1e-12
        assert r['n_common'] == int(old['n_common'])
    chosen, details = select(internal, means, 'classification_A12')
    signed_chosen, signed_details = select(internal, means, 'classification_wilcoxon')
    baseline_counts = counts(baseline, 'classification_A12')
    signed_counts = counts(baseline, 'classification_wilcoxon')
    old_best = {r['formula']: r for r in read(ROOT/'results/rq3/data/rq3_best_worst.csv')}
    selection_changes = [r['formula'] for r in chosen if any(r[k] != old_best[r['formula']][k] for k in ['best', 'worst'])]
    changes_a12_vs_signed = [dict(scope=scope, **r) for scope, tests in [('ACO',baseline),('LLM_internal',internal)]
                              for r in tests if r['classification_A12'] != r['classification_wilcoxon']]
    changed_old = [dict(**r, previous_classification=prior[r['formula'],r['cell_a']]['classification'])
                   for r in baseline if r['classification_A12'] != prior[r['formula'],r['cell_a']]['classification']]
    for filename, data in [('table11_selection.csv',chosen),('table12_aco_counts.csv',baseline_counts),
                           ('llm_internal_pairwise_tests.csv',internal),('aco_pairwise_tests.csv',baseline),
                           ('configuration_win_loss_counts.csv',details),
                           ('table11_selection_wilcoxon_direction.csv',signed_chosen),
                           ('table12_aco_counts_wilcoxon_direction.csv',signed_counts),
                           ('configuration_win_loss_counts_wilcoxon_direction.csv',signed_details),
                           ('changes_from_previous_table.csv',changed_old),
                           ('direction_method_differences.csv',changes_a12_vs_signed)]:
        if data:
            write(OUT/filename,data)
    common = ('Two-sided paired Wilcoxon signed-rank tests compare EXAM scores on mutants killed by both suites. '
              r'Significance is determined by unadjusted $p<0.05$; no multiple-comparison correction is applied. ')
    a12_direction = r'$A_{12}>0.5$ favors the first suite; $A_{12}<0.5$ favors the second. '
    signed_direction = (r'For paired differences $d=\mathrm{EXAM}_{A}-\mathrm{EXAM}_{B}$, '
                        r'$W_+$ and $W_-$ denote positive and negative rank sums after zero differences are omitted. '
                        r'A significant result favors A when $W_->W_+$ and B when $W_+>W_-$. ')
    select_note = ('A suite qualifies as best (worst) only if it is significantly better (worse) than all 11 alternatives. '
                   'If no suite qualifies, select the lowest (highest) pooled mean EXAM among all 12 configurations. '
                   "Pooled means use each configuration's own evaluable mutants. ")
    for suffix, selections, cs, direction in [('',chosen,baseline_counts,a12_direction),
                                              ('_wilcoxon_direction',signed_chosen,signed_counts,signed_direction)]:
        rows11 = [[r['formula_display'],r['best'].replace('-',' (')+')',r['worst'].replace('-',' (')+')'] for r in selections]
        rows12 = [[r['formula_display']]+[str(r[k]) for k in ['Worse','Similar','Better']] for r in cs]
        table11 = latex('Best and worst LLM-generated test suites for SBFL approaches.',
                        'tab:rq3bw-selection','lll',['Formula','Best suite','Worst suite'],rows11,common+direction+select_note)
        table12 = latex('Statistical comparison of 12 LLM-generated test suites with ACO.',
                        'tab:rq3bw-pairwise-counts','lrrr',['Formula','W','S','B'],rows12,
                        common+direction+'The first suite is the LLM configuration. W/S/B denote worse, no statistically significant difference, and better relative to ACO.')
        (TABLES/('table11_raw_p_all11_mean_fallback'+suffix+'.tex')).write_text(table11,encoding='utf-8')
        (TABLES/('table12_aco_raw_p'+suffix+'.tex')).write_text(table12,encoding='utf-8')
        if suffix == '_wilcoxon_direction':
            final11 = latex('Best and worst LLM-generated test suites for SBFL approaches.',
                            'tab:rq3bw-selection','lll',['Formula','Best suite','Worst suite'],rows11,
                            common+select_note+'All 18 formulas use the mean-based fallback for both selections.')
            final12 = latex('Statistical comparison of 12 LLM-generated test suites with ACO.',
                            'tab:rq3bw-pairwise-counts','lrrr',['Formula','W','S','B'],rows12,
                            common+'W/B indicate significantly higher/lower EXAM scores for the LLM than for ACO. '
                            'S indicates that no significant difference is observed.')
            (TABLES/'table11_final_uncorrected.tex').write_text(final11,encoding='utf-8')
            (TABLES/'table12_final_uncorrected.tex').write_text(final12,encoding='utf-8')
            write(OUT/'table11_final.csv', [dict(Formula=r['formula_display'],Best=r['best'],Worst=r['worst']) for r in selections])
            write(OUT/'table12_final.csv', [dict(Formula=r['formula_display'],W=r['Worse'],S=r['Similar'],B=r['Better']) for r in cs])
    report = dict(scipy_version=scipy.__version__,
                  alpha=.05,p_used='raw two-sided paired Wilcoxon',multiple_comparison_correction='none',
                  baseline='Yekta-ACO only',baseline_comparisons=len(baseline),internal_comparisons=len(internal),
                  primary_direction='A12',alternative_direction='Wilcoxon signed rank sums for d=EXAM_A-EXAM_B',
                  selection_rule='all-11 significant wins/losses; otherwise min/max pooled mean over all 12 cells',
                  best_fallback_formulas=sum(r['best_reason']=='minimum_pooled_mean_fallback' for r in chosen),
                  worst_fallback_formulas=sum(r['worst_reason']=='maximum_pooled_mean_fallback' for r in chosen),
                  selection_changes_from_pasted_table=selection_changes,
                  baseline_totals={k:sum(r[k] for r in baseline_counts) for k in ['Worse','Similar','Better']},
                  signed_rank_baseline_totals={k:sum(r[k] for r in signed_counts) for k in ['Worse','Similar','Better']},
                  baseline_directions_disagree=sum(r['scope']=='ACO' for r in changes_a12_vs_signed),
                  internal_directions_disagree=sum(r['scope']=='LLM_internal' for r in changes_a12_vs_signed),
                  signed_rank_selection_changes=[r['formula'] for r,s in zip(chosen,signed_chosen) if any(r[k]!=s[k] for k in ['best','worst'])],
                  signed_rank_best_fallback_formulas=sum(r['best_reason']=='minimum_pooled_mean_fallback' for r in signed_chosen),
                  signed_rank_worst_fallback_formulas=sum(r['worst_reason']=='maximum_pooled_mean_fallback' for r in signed_chosen),
                  changed_classifications_from_previous_table=len(changed_old),
                  prior_raw_statistics_match=True,independent_A12_enumeration_verified=True,
                  signed_rank_sums_match_scipy_statistic=True)
    (OUT/'audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    lines = ['# RQ3：无多重比较校正，显著全胜/全负优先、均值回退','',
             '两组检验均使用原始双侧配对 Wilcoxon p < 0.05。当前主结果保留 A12 判断方向，另附完全由 Wilcoxon 符号秩方向决定的结果供判断是否删除 A12。',
             'Best/Worst 需要显著胜过/输给其余全部 11 个配置；没有满足者时，从全部 12 个配置按 pooled mean EXAM 最低/最高选择。','',
             '| Formula | Best | Worst | ACO W | ACO S | ACO B |','|---|---|---|---:|---:|---:|']
    for r,c in zip(chosen,baseline_counts):
        lines.append('| '+' | '.join([r['formula_display'],r['best'],r['worst']]+[str(c[k]) for k in ['Worse','Similar','Better']])+' |')
    lines.extend(['', '汇总：'+json.dumps(report['baseline_totals']),
                  'A12 与 Wilcoxon 方向比较：基线分类差异 '+str(report['baseline_directions_disagree'])+' 项；LLM 内部分类差异 '+str(report['internal_directions_disagree'])+' 项。',
                  '两种方向定义导致 Best/Worst 表名称不同的公式：'+str(report['signed_rank_selection_changes'])+'。',
                  'Similar 仅表示未检出显著差异。这里的原始 p 阈值不控制整组多重比较的错误率。',
                  '校正前的逐项 p 和 A12 已与历史统计结果核对；基线仅有 ACO。所有比较均在共同击杀集上逐 mutant 配对；均值回退使用各配置自身可评价集合。'])
    (OUT/'TABLES.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    print(json.dumps(baseline_counts,indent=2))


if __name__ == '__main__':
    main()
