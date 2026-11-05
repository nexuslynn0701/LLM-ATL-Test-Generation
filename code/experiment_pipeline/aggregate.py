"""Aggregate fresh, complete run evidence; never reads historical replay files."""
import csv
import math
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from statistics import median

from .evidence import ROOT, PROVIDERS, load_run, write_csv, save_json
from .sbfl_formulas import FORMULAS

FORMULA_NAMES = ('ochiai tarantula dstar2 kulczynski2 mountford zoltar arithmetic_mean '
                 'barinel braun_banquet baroni_urbani_buser cohen ochiai2 op2 phi pierce '
                 'rogers_tanimoto russell_rao simple_matching').split()


def formulas():
    return {name: FORMULAS[name] for name in FORMULA_NAMES}


def metric_row(cell):
    eligible = [s for s in cell['sources'] if s['in_estar']]
    n, m, r = len(eligible), len(cell['faults']), len(cell['rules'])
    covered = set().union(*(set(s['covered_rules']) for s in eligible))
    killed = {name for s in eligible for name, out in s['outcomes'].items() if out == 'KILLED'}
    failing = sum(out == 'KILLED' for s in eligible for out in s['outcomes'].values())
    row = dict(subject=cell['subject'], llm=PROVIDERS[cell['provider']], condition=cell['condition'],
               n_estar=n, attempts=cell['attempts'], size='--', killed_mutants=len(killed),
               covered_rules=len(covered), total_rules=r, eligible_mutants=m, killed_pairs=failing,
               total_pairs=n*m,
               invalid_pairs=sum(out == 'INVALID_RUNTIME' for s in eligible for out in s['outcomes'].values()))
    for name, value in [('validity_pct', Fraction(100*n, cell['attempts'])),
                        ('coverage_pct', Fraction(100*len(covered), r) if n else None),
                        ('mutation_score_pct', Fraction(100*len(killed), m) if n else None),
                        ('failure_rate_pct', Fraction(100*failing, n*m) if n else None)]:
        row[name] = f'{float(value):.15f}' if value is not None else '--'
        row[name+'_numerator'] = value.numerator if value is not None else ''
        row[name+'_denominator'] = value.denominator if value is not None else ''
    return row


def exam_rows(cell, provider_label=None):
    funcs = formulas()
    eligible = [s for s in cell['sources'] if s['in_estar']]
    rules = cell['rules']
    for mutant, faults in cell['faults'].items():
        spec = {r: [0, 0, 0, 0] for r in rules}
        failed = 0
        for source in eligible:
            outcome = source['outcomes'][mutant]
            if outcome == 'INVALID_RUNTIME':
                continue
            fail = outcome == 'KILLED'
            failed += fail
            covered = set(source['covered_rules'])
            for rule in rules:
                spec[rule][(0 if fail else 1) + (0 if rule in covered else 2)] += 1
        for name, func in funcs.items():
            row = dict(subject=cell['subject'], provider=provider_label or PROVIDERS[cell['provider']], condition=cell['condition'],
                       cell_kind=('baseline' if provider_label else
                                  'workflow' if cell['condition'] == 'workflow' else 'llm_ladder'),
                       mutant_id=mutant, formula=name, n_faulty_rules=len(faults), rule_count=len(rules),
                       evaluable=int(failed > 0), failing_sources=failed,
                       exam_bc='', exam_ac='', exam_wc='', best_rank='', tie_size='')
            if failed:
                scores = {r: func(*v) for r, v in spec.items()}
                scores = {r: math.inf if math.isinf(v) else round(v, 12) for r, v in scores.items()}
                ranks = []
                for fault in faults:
                    hi = sum(s > scores[fault] for s in scores.values())
                    eq = sum(s == scores[fault] for s in scores.values())
                    ranks.append((hi+1, hi+eq, Fraction(2*hi+1+eq, 2), eq))
                row.update(exam_bc=f'{min(t[0] for t in ranks)/len(rules):.12g}',
                           exam_ac=f'{float(sum(t[2] for t in ranks)/len(ranks)/len(rules)):.12g}',
                           exam_wc=f'{max(t[1] for t in ranks)/len(rules):.12g}',
                           best_rank=min(t[0] for t in ranks),
                           tie_size=f'{sum(t[3] for t in ranks)/len(ranks):.6f}')
            yield row


def rq3(cells, out):
    rows = [row for cell in cells for row in exam_rows(cell)]
    write_csv(Path(out)/'mutant_level_exam.csv', rows)
    groups = defaultdict(list)
    for row in rows:
        groups[(row['provider'], row['condition'], row['formula'])].append(row)
    pooled = []
    for (provider, condition, formula), members in sorted(groups.items()):
        valid = [r for r in members if r['evaluable']]
        exams = [float(r['exam_ac']) for r in valid]
        pooled.append(dict(provider=provider, condition=condition, formula=formula,
                           n_mutants=len(members), n_evaluable=len(valid),
                           top1_rate=sum(r['best_rank'] == 1 for r in valid)/len(valid) if valid else '',
                           mean_exam=sum(exams)/len(exams) if exams else '',
                           median_exam=median(exams) if exams else ''))
    write_csv(Path(out)/'rq3_pooled.csv', pooled)
    return rows


def rq5(cells, out):
    rows = [metric_row(c) for c in cells if c['condition'] in ('astm', 'astmo', 'workflow')]
    if not rows:
        raise ValueError('Run has no ASTM/ASTMO/workflow cells for RQ5')
    write_csv(Path(out)/'workflow_metrics.csv', rows)
    groups = defaultdict(list)
    for row in rows:
        groups[(row['llm'],row['condition'])].append(row)
    pooled = []
    for (llm,condition), members in sorted(groups.items()):
        item = dict(llm=llm,condition=condition,n_subjects=len(members))
        for metric,num,den in [('validity','n_estar','attempts'),
                               ('coverage','covered_rules','total_rules'),
                               ('mutation','killed_mutants','eligible_mutants'),
                               ('failure','killed_pairs','total_pairs')]:
            numerator = sum(r[num] for r in members)
            denominator = sum(r[den] for r in members)
            item[metric+'_numerator'] = numerator
            item[metric+'_denominator'] = denominator
            item[metric+'_pct'] = f'{100*numerator/denominator:.15f}' if denominator else '--'
        pooled.append(item)
    write_csv(Path(out)/'workflow_overall_pooled.csv',pooled)
    indexed = {(c['subject'],c['provider'],c['condition']):c for c in cells}
    overlaps = []
    for (subject,provider,condition), cell in indexed.items():
        other = indexed.get((subject,provider,'astmo'))
        if condition != 'workflow' or other is None:
            continue
        def kills(c):
            return {m for s in c['sources'] if s['in_estar'] for m,o in s['outcomes'].items() if o == 'KILLED'}
        left,right = kills(other),kills(cell)
        if other['faults'] != cell['faults']:
            raise ValueError('ASTMO and workflow mutant universes differ')
        overlaps.append(dict(subject=subject,provider=PROVIDERS[provider],shared_mutants=len(left & right),
                             astmo_only_mutants=len(left-right),workflow_only_mutants=len(right-left),
                             neither_mutants=len(cell['faults'])-len(left|right)))
    if overlaps:
        write_csv(Path(out)/'mutant_overlap.csv',overlaps)
    return rows


def rq4_deltas(metrics, exams, out):
    indexed = {(r['subject'],r['llm'],r['condition']):r for r in metrics}
    rows = []
    for (subject,llm,condition), row in indexed.items():
        base = indexed.get((subject,llm,'sm'))
        if condition not in ('stm','astm','astmo') or base is None:
            continue
        for metric in ('validity_pct','coverage_pct','mutation_score_pct','failure_rate_pct'):
            delta = ''
            if row[metric] != '--' and base[metric] != '--':
                value = Fraction(row[metric+'_numerator'],row[metric+'_denominator'])
                baseline = Fraction(base[metric+'_numerator'],base[metric+'_denominator'])
                delta = f'{float(value-baseline):.15f}'
            rows.append(dict(subject=subject,llm=llm,condition=condition,reference='sm',metric=metric,
                             value=row[metric],reference_value=base[metric],delta_pp=delta))
    write_csv(Path(out)/'deltas_vs_sm.csv',rows,
              ['subject','llm','condition','reference','metric','value','reference_value','delta_pp'])
    # Pool evaluable mutants over subjects AND formulas, as in the revised RQ4 table.
    pools = defaultdict(list)
    for row in exams:
        pools[(row['provider'],row['condition'])].append(row)
    localization = []
    for (provider,condition), members in sorted(pools.items()):
        valid = [r for r in members if r['evaluable']]
        localization.append(dict(provider=provider,condition=condition,n_evaluable=len(valid),
                                 top1_pct=100*sum(r['best_rank']==1 for r in valid)/len(valid) if valid else '',
                                 mean_exam=sum(float(r['exam_ac']) for r in valid)/len(valid) if valid else ''))
    write_csv(Path(out)/'top1_exam_pooled.csv',localization)


def export_evidence(cells, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    schemas = {
        'source_population.csv': ['subject','provider','condition','source_id','original_execution_success','trace_eligible','in_estar'],
        'source_rule_coverage.csv': ['subject','provider','condition','source_id','rule_id','covered'],
        'source_mutant_outcomes.csv': ['subject','provider','condition','source_id','mutant_id','outcome'],
        'rq3_test_rule_spectra_long.csv': ['subject','provider','condition','model_id','mutant_id','rule_id','rule_covered','test_outcome'],
    }
    from contextlib import ExitStack
    with ExitStack() as stack:
        writers = {}
        for name, fields in schemas.items():
            f = stack.enter_context((out/name).open('w', encoding='utf-8', newline=''))
            w = csv.writer(f); w.writerow(fields); writers[name] = w
        for c in cells:
            for s in c['sources']:
                prefix = [c['subject'], c['provider'], c['condition'], s['source_id']]
                writers['source_population.csv'].writerow(prefix+[int(s['original_success']),int(s['trace_eligible']),int(s['in_estar'])])
                if not s['in_estar']:
                    continue
                for rule in c['rules']:
                    writers['source_rule_coverage.csv'].writerow(prefix+[rule,int(rule in s['covered_rules'])])
                for mutant, outcome in s['outcomes'].items():
                    writers['source_mutant_outcomes.csv'].writerow(prefix+[mutant,outcome])
                    for rule in c['rules']:
                        writers['rq3_test_rule_spectra_long.csv'].writerow(prefix+[mutant,rule,int(rule in s['covered_rules']),
                            {'KILLED':'FAIL','ALIVE':'PASS','INVALID_RUNTIME':'INVALID'}[outcome]])


def aggregate_run(run):
    run = Path(run)
    cells = load_run(run)
    out = run/'derived'
    export_evidence(cells, out/'evidence')
    metrics = [metric_row(c) for c in cells]
    for rq in ('rq1', 'rq2', 'rq4'):
        write_csv(out/rq/'cell_metrics.csv', metrics)
    rows = rq3(cells, out/'rq3')
    rq4_deltas(metrics,rows,out/'rq4')
    # Distinguish generation failures from original execution/verification failures.
    validity = []
    for cell in cells:
        validity.append(dict(subject=cell['subject'],provider=PROVIDERS[cell['provider']],condition=cell['condition'],
                             attempts=cell['attempts'],n_original_success=sum(s['original_success'] for s in cell['sources']),
                             n_estar=sum(s['in_estar'] for s in cell['sources']),
                             missing_source=sum(not s['source_present'] for s in cell['sources'])))
    write_csv(out/'rq1/validity.csv',validity)
    mutant_rows = []
    for cell in cells:
        eligible = [s for s in cell['sources'] if s['in_estar']]
        for mutant in cell['faults']:
            fail = sum(s['outcomes'][mutant]=='KILLED' for s in eligible)
            invalid = sum(s['outcomes'][mutant]=='INVALID_RUNTIME' for s in eligible)
            mutant_rows.append(dict(subject=cell['subject'],provider=PROVIDERS[cell['provider']],
                                    condition=cell['condition'],mutant_id=mutant,n_estar=len(eligible),
                                    failing_sources=fail,invalid_sources=invalid,
                                    fail_ratio=fail/len(eligible) if eligible else ''))
    write_csv(out/'rq2/per_mutant_fail_ratio.csv',mutant_rows)
    if any(c['condition'] in ('astm','astmo','workflow') for c in cells):
        rq5(cells, out/'rq5')
    save_json(out/'summary.json', {'cells':len(cells), 'attempts':sum(c['attempts'] for c in cells),
             'n_estar':sum(r['n_estar'] for r in metrics), 'mutant_exam_rows':len(rows),
             'scope':'Only requested cells; no historical values filled in. Model size and historical statistical tables are not regenerated.'})
    return out
