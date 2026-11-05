"""Recompute the 72 absolute values and 54 SM-deltas of the RQ4 ladder table
(tab:rq4-ladder) from bundle-internal data only.

Auxiliary equal-subject summary retained as evidence. This command verifies
the supplementary values; the current paper's pooled CSVs are computed by
code/reproduction/build_tables.py. Arithmetic uses exact Fractions and
ROUND_HALF_EVEN at display time.

Chain position:
    results/experiment_results/ and results/rq*/supplementary/ CSVs  -->  rq4_values_72.csv / rq4_deltas_54.csv
    (Validity/Coverage/Mutation/Failure columns of tab:rq4-ladder)

Inputs:
    results/experiment_results/RQ1/validity.csv
    results/rq1/supplementary/population/estar_population_by_cell.csv
    results/experiment_results/RQ1/rule_coverage.csv
    results/experiment_results/RQ2/mutation_results.csv
    results/experiment_results/RQ2/failure_rates.csv
    results/rq3/supplementary/cell_formula_scores.csv
    results/experiment_results/RQ3/mutant_level_exam.csv

Default mode verifies the recomputation against the existing
results/rq4/supplementary/rq4_values_72_current.csv and
rq4_deltas_54_current.csv.
`--write` regenerates those two CSVs plus the failure audit CSVs in
results/rq4/supplementary/.
"""
import argparse, csv
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from collections import defaultdict

BUNDLE = Path(__file__).resolve().parents[2]
RQ4_DATA = BUNDLE / 'results/experiment_results/RQ4'
RQ4_SUPP = BUNDLE / 'results' / 'rq4' / 'supplementary'
P = ['GPT', 'Qwen', 'DeepSeek']
C = ['sm', 'stm', 'astm', 'astmo']
SUBJECTS = ['Ant2Maven', 'BibTeX2DocBook', 'CPL2SPL', 'Ecore2Maude', 'Grafcet2PetriNet', 'UML2ER']
METRICS = ['Validity', 'Coverage', 'Mutation', 'Failure', 'Top-1', 'EXAM']


def read(rel):
    with (BUNDLE / rel).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def avg(v):
    return sum(v, F(0)) / len(v)


def dec(x):
    with localcontext() as ctx:
        ctx.prec = 60
        return Decimal(x.numerator) / Decimal(x.denominator)


def fmt(x, n=12):
    return str(dec(x).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_EVEN))


def signed(x):
    r = fmt(x, 2)
    return ('+' if not r.startswith('-') else '') + r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true',
                    help='regenerate rq4_values_72.csv / rq4_deltas_54.csv (+ failure audits)')
    args = ap.parse_args()

    # --- cell-level Top-1 / EXAM from the mutant-level file -----------------
    mutants = read('results/experiment_results/RQ3/mutant_level_exam.csv')
    cells = read('results/rq3/supplementary/cell_formula_scores.csv')
    groups = defaultdict(list)
    for r in mutants:
        if r['provider'] in P and r['condition'] in C and r['evaluable'] == '1':
            groups[(r['subject'], r['provider'], r['condition'], r['formula'])].append(r)

    out = []
    mismatches, precision = [], []
    for cell in cells:
        if cell['provider'] not in P or cell['condition'] not in C:
            continue
        key = tuple(cell[k] for k in ['subject', 'provider', 'condition', 'formula'])
        rows = groups[key]
        assert len(rows) == int(cell['killed_mutants']), (key, len(rows), cell['killed_mutants'])
        exam = []
        top = 0
        for r in rows:
            raw = F(r['exam_ac'])
            bound = 2 * int(r['rule_count']) * int(r['n_faulty_rules'])
            exact = F(round(raw * bound), bound)
            if abs(exact - raw) > F(1, 10 ** 11):
                precision.append((key, r['mutant_id'], str(raw), str(exact)))
            exam.append(exact)
            top += F(r['best_rank']) <= 1
        ex = avg(exam)
        t = F(top, len(rows))
        if (abs(ex - F(cell['mean_exam_ac'])) > F(51, 10 ** 8)
                or abs(t - F(cell['top1_rate'])) > F(51, 10 ** 6)):
            mismatches.append(key)
        out.append(dict(key=key, exam=ex, top=t, n=len(rows)))
    print('cell checks', len(out), 'mismatches', len(mismatches), 'rational recovery errors', len(precision))
    assert not mismatches and not precision

    # --- Failure: unique integer pair-count recovery from RQ2 summary -------
    failure_audit = []
    for r in read('results/experiment_results/RQ2/failure_rates.csv'):
        if r['method_id'].replace('DeepSeek-Flash', 'DeepSeek') not in [p + '-' + c.upper() for p in P for c in C]:
            continue
        if r['mean_fail_ratio_pct'] in ('', 'NA', 'N/A'):
            continue
        denom = int(r['n_eligible_mutants']) * int(r['n_original_executable_sources'])
        raw = F(r['mean_fail_ratio_pct'])
        count = round(raw * denom / 100)
        assert F(100, denom) > F(2, 10000)
        assert abs(F(count * 100, denom) - raw) <= F(1, 10000), r
        assert r['status'] in ('OK', 'OK_STRICT_CANONICAL'), r
        failure_audit.append((r['method_id'], r['subject'], count, denom, F(count * 100, denom), raw))
    print('failure reconstructed', len(failure_audit))

    fcounts = defaultdict(dict)
    for r in mutants:
        if r['provider'] in P and r['condition'] in C:
            key = (r['subject'], r['provider'] + '-' + r['condition'].upper())
            v = int(r['failing_sources'])
            assert r['mutant_id'] not in fcounts[key] or fcounts[key][r['mutant_id']] == v
            fcounts[key][r['mutant_id']] = v
    fc_bad = []
    for method, sub, count, denom, exact, raw in failure_audit:
        method = method.replace('DeepSeek-Flash', 'DeepSeek')
        total = sum(fcounts[(sub, method)].values())
        if total != count:
            fc_bad.append((sub, method, count, total))
    print('Failure raw count differences (RQ2 recovery vs RQ3 failing_sources):', len(fc_bad), fc_bad[:5])

    # --- assemble the 72 values ---------------------------------------------
    valid = {(r['Generator'].lower(), r['Cond.']): r for r in read('results/experiment_results/RQ1/validity.csv')}
    estar = {(r['provider'], r['condition'], r['subject']): int(r['n_estar'])
             for r in read('results/rq1/supplementary/population/estar_population_by_cell.csv')}
    cov = {(r['llm'], r['prompt_condition'], r['subject']): r
           for r in read('results/experiment_results/RQ1/rule_coverage.csv')}
    mut = {(r['approach'].replace('DeepSeek-Flash', 'DeepSeek'), r['prompt_condition'], r['subject']): r
           for r in read('results/experiment_results/RQ2/mutation_results.csv')}
    fail = {(method.replace('DeepSeek-Flash', 'DeepSeek'), s): (n, d, x, raw)
            for method, s, n, d, x, raw in failure_audit}

    values = {}
    for p in P:
        for c in C:
            vv, cc, mm, ff = [], [], [], []
            for s in SUBJECTS:
                v = F(valid[(p.lower(), c.upper())][s])
                assert v == estar.get((p, c, s), 0)
                vv.append(v)
                cr = cov[(p, c.upper(), s)]
                mr = mut[(p, c.upper(), s)]
                cc.append(F(100 * int(cr['covered_rules'] or 0), int(cr['total_rules'])))
                mm.append(F(100 * int(mr['killed_mutants'] or 0), int(mr['eligible_mutants'])))
                fl = fail.get((p + '-' + c.upper(), s))
                if fl:
                    ff.append(fl[2])
            subset = [r for r in out if r['key'][1:3] == (p, c)]
            vals = [avg(vv), avg(cc), avg(mm), avg(ff),
                    100 * avg([r['top'] for r in subset]),
                    avg([r['exam'] for r in subset])]
            for metric, x in zip(METRICS, vals):
                values[(metric, p, c)] = x

    absolute, deltas = [], []
    for metric in METRICS:
        for p in P:
            for c in C:
                x = values[(metric, p, c)]
                absolute.append(dict(metric=metric, LLM=p, context=c.upper(),
                                     value_15dp=fmt(x, 15), numerator=x.numerator,
                                     denominator=x.denominator, display_2dp=fmt(x, 2)))
                if c == 'sm':
                    continue
                base = values[(metric, p, 'sm')]
                d = (base - x) if metric == 'EXAM' else (x - base)
                deltas.append(dict(metric=metric, LLM=p, context=c.upper(), baseline='SM',
                                   direction='SM - context' if metric == 'EXAM' else 'context - SM',
                                   delta_15dp=fmt(d, 15), numerator=d.numerator,
                                   denominator=d.denominator, display_2dp=signed(d)))
    assert len(absolute) == 72 and len(deltas) == 54

    # --- verify / write ------------------------------------------------------
    for name, recomputed in [('rq4_values_72_current.csv', absolute), ('rq4_deltas_54_current.csv', deltas)]:
        existing = read('results/rq4/supplementary/' + name)
        keyfn = lambda r: (r['metric'], r['LLM'], r['context'])
        existing_map = {keyfn(r): r for r in existing}
        bad = [r for r in recomputed
               if existing_map[keyfn(r)]['value_15dp' if 'values' in name else 'delta_15dp']
               != r['value_15dp' if 'values' in name else 'delta_15dp']]
        print(f'{name}: {"MATCH (identical to existing file)" if not bad else str(len(bad)) + " MISMATCHED rows"}')
        assert not bad

    if args.write:
        def write_csv(path, rows):
            with path.open('w', encoding='utf-8-sig', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
        write_csv(RQ4_SUPP / 'rq4_values_72_current.csv', absolute)
        write_csv(RQ4_SUPP / 'rq4_deltas_54_current.csv', deltas)
        write_csv(RQ4_SUPP / 'rq4_failure_count_audit.csv',
                  [dict(method=m, subject=s, inferred_RQ2_killed_pairs=n, pair_denominator=d,
                        recovered_percent=fmt(x, 15), published_percent=str(raw),
                        RQ3_killed_pairs=sum(fcounts[(s, m.replace('DeepSeek-Flash', 'DeepSeek'))].values()),
                        RQ3_mutant_count=len(fcounts[(s, m.replace('DeepSeek-Flash', 'DeepSeek'))]))
                   for m, s, n, d, x, raw in failure_audit])
        print('rewrote', RQ4_SUPP / 'rq4_values_72_current.csv', RQ4_SUPP / 'rq4_deltas_54_current.csv',
              RQ4_SUPP / 'rq4_failure_count_audit.csv')


if __name__ == '__main__':
    main()
