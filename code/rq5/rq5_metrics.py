"""Exact RQ5 counts and pooled Overall metrics (no plotting dependencies).

The *_pct_numerator/denominator columns encode reduced PERCENTAGES, not
raw experimental counts. Recover counts using the published subject universe;
reject nonintegral counts rather than rounding them into plausible results.
"""
from pathlib import Path
import argparse
import csv
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METRICS = ROOT / 'results/rq5/supplementary/workflow_metrics.csv'
DEFAULT_SUBJECTS = ROOT / 'results/rq1/supplementary/subjects.csv'
DEFAULT_OUTPUT = ROOT / 'rebuild/rq5'
SUBJECTS = ['Ant2Maven', 'BibTeX2DocBook', 'CPL2SPL', 'Ecore2Maude',
            'Grafcet2PetriNet', 'UML2ER']
MODELS = ['GPT', 'Qwen', 'DeepSeek']
FIELDS = {'validity': 'validity_pct', 'rule_coverage': 'coverage_pct',
          'mutation_score': 'mutation_score_pct', 'failure_rate': 'failure_rate_pct'}
CONDITIONS = ('ASTMO', 'Workflow')
MISSING = ('', '--', 'N/A')


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def format_pct(value):
    with localcontext() as ctx:
        ctx.prec = 60
        return format((Decimal(value.numerator) / Decimal(value.denominator))
                      .quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN), '.2f')


def integer_count(value, label):
    if value.denominator != 1 or value < 0:
        raise ValueError(f'{label}: not a nonnegative integer count: {value}')
    return int(value)


def build_counts(metrics_path=DEFAULT_METRICS, subjects_path=DEFAULT_SUBJECTS):
    universe = {r['transformation']: r for r in read_csv(subjects_path)}
    rows = [r for r in read_csv(metrics_path) if r['condition'] in ('astmo', 'workflow')]
    index = {(r['subject'], r['llm'], r['condition']): r for r in rows}
    expected = {(s, m, c.lower()) for s in SUBJECTS for m in MODELS for c in CONDITIONS}
    if len(index) != len(rows) or set(index) != expected:
        raise ValueError('Expected exactly 36 unique subject/model/condition cells')
    counts = []
    for subject in SUBJECTS:
        rules = int(universe[subject]['total_rules'])
        mutants = int(universe[subject]['mutants'])
        if rules <= 0 or mutants <= 0:
            raise ValueError(f'Invalid universe: {subject}')
        for model in MODELS:
            for condition in CONDITIONS:
                row = index[subject, model, condition.lower()]
                valid = int(row['n_estar'])
                if not 0 <= valid <= 100:
                    raise ValueError(f'Invalid E* count: {row}')
                denominators = {'validity': 100, 'rule_coverage': rules,
                                'mutation_score': mutants, 'failure_rate': valid * mutants}
                for metric, field in FIELDS.items():
                    missing = row[field] in MISSING
                    if missing != (valid == 0 and metric != 'validity'):
                        raise ValueError(f'Unexpected missing metric: {row}, {metric}')
                    # Empty suites cover/kill zero elements of the fixed universe.
                    # Failure has no evaluated pairs: 0/0, never a measured 0%.
                    pct = Fraction(0) if missing else Fraction(
                        int(row[field + '_numerator']), int(row[field + '_denominator']))
                    if not 0 <= pct <= 100:
                        raise ValueError(f'Invalid percentage: {row}, {metric}')
                    if not missing and abs(Fraction(row[field]) - pct) > Fraction(1, 10**10):
                        raise ValueError(f'Display/exact percentage mismatch: {row}, {metric}')
                    denominator = denominators[metric]
                    numerator = integer_count(pct * denominator / 100,
                                              f'{subject}/{model}/{condition}/{metric}')
                    if metric == 'validity' and numerator != valid:
                        raise ValueError('Validity disagrees with E* count')
                    if metric == 'mutation_score' and numerator != int(row['killed_mutants']):
                        raise ValueError('Recovered kills disagree with published killed_mutants')
                    counts.append(dict(dataset=subject, model=model, metric=metric,
                        condition=condition, count_numerator=numerator,
                        count_denominator=denominator, source_na=int(missing),
                        basis=('empty_suite_zero_count' if missing else
                               'exact_percentage_times_published_universe')))
    return counts


def pool_counts(counts):
    pooled = []
    for model in MODELS:
        for metric in FIELDS:
            for condition in CONDITIONS:
                cells = [r for r in counts if (r['model'], r['metric'], r['condition']) ==
                         (model, metric, condition)]
                if len(cells) != 6 or {r['dataset'] for r in cells} != set(SUBJECTS):
                    raise ValueError('Pooling requires all six distinct subjects')
                numerator = sum(r['count_numerator'] for r in cells)
                denominator = sum(r['count_denominator'] for r in cells)
                if denominator <= 0:
                    raise ValueError('Overall has no eligible denominator')
                pooled.append(dict(dataset='Overall', model=model, metric=metric,
                    condition=condition, count_numerator=numerator,
                    count_denominator=denominator, source_na=0, basis='pooled_counts'))
    return pooled


def plot_rows(counts):
    rows = []
    for row in counts + pool_counts(counts):
        n, d = row['count_numerator'], row['count_denominator']
        # Preserve the legacy subject-panel display; this does not enter pooling.
        value = Fraction(100 * n, d) if d else Fraction(0)
        overall = row['dataset'] == 'Overall'
        note = ('Pooled raw counts: 100 * sum(numerator) / sum(denominator).' if overall
                else 'No evaluated pairs: undefined 0/0; zero shown only for display.' if not d
                else 'Empty suite: zero covered/killed elements in fixed universe.' if row['source_na']
                else 'Exact cell percentage reconstructed from integer counts.')
        rows.append(dict(dataset=row['dataset'], model=row['model'], metric=row['metric'],
                         condition=row['condition'], plot_value=float(value),
                         n_subjects=6 if overall else 1,
                         zero_assigned=int(not overall and row['source_na']),
                         count_numerator=n, count_denominator=d,
                         aggregation='pooled' if overall else 'subject', note=note))
    return rows


def overall_comparison(counts):
    index = {(r['model'], r['metric'], r['condition']): r for r in pool_counts(counts)}
    result = []
    for model in MODELS:
        for metric in FIELDS:
            out = dict(model=model, metric=metric)
            values = []
            for condition, prefix in [('ASTMO', 'astmo'), ('Workflow', 'fd_astmo')]:
                row = index[model, metric, condition]
                n, d = row['count_numerator'], row['count_denominator']
                value = Fraction(100*n, d)
                values.append(value)
                out.update({prefix+'_numerator': n, prefix+'_denominator': d,
                            prefix+'_pct': format_pct(value)})
            out['delta_pp'] = format_pct(values[1] - values[0])
            result.append(out)
    return result


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def export_tables(counts, folder):
    write_csv(Path(folder) / 'rq5_metric_counts.csv', counts)
    write_csv(Path(folder) / 'rq5_overall_pooled.csv', overall_comparison(counts))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metrics', type=Path, default=DEFAULT_METRICS)
    parser.add_argument('--subjects', type=Path, default=DEFAULT_SUBJECTS)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    counts = build_counts(args.metrics, args.subjects)
    export_tables(counts, args.out)
    for row in overall_comparison(counts):
        print(row)
