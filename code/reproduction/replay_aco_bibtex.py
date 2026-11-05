"""Replay archived ACO/BibTeX sources without changing released results.

Start with --n 10; expand the same checkpointed run with --n 100 --resume.
Every valid source is run against the canonical 40 mutants. Invalid executions
are recorded separately and are never counted as kills or passing SBFL tests.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime
import json
import math
import re
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'code'))
sys.path.insert(0, str(ROOT / 'code/pipeline'))
from experiment_pipeline.aggregate import exam_rows, formulas
from experiment_pipeline.evidence import save_json, read_csv, write_csv
from src.executor.transformation_executor import run_transformation, run_mutants_parallel
from src.analyzer.coverage_analyzer import compare_xmi_models, extract_rules_and_helpers
from src.analyzer.sbfl_analyzer import _parse_trace_rules

SUBJECT = 'BibTeX2DocBook'
SUB = ROOT / 'subjects' / SUBJECT
ARCHIVE = ROOT / 'data/test_cases/BibTeX2DocBook/_baselines/aco/yekta_aco'


def infrastructure_check(result):
    message = ' '.join(str(result.get(k) or '') for k in ('stderr', 'error'))
    if result['returncode'] == -1 or any(s in message for s in (
            'ClassNotFoundException', 'NoClassDefFoundError', 'UnsupportedClassVersionError',
            'OutOfMemoryError', 'Could not reserve enough space')):
        raise RuntimeError('Infrastructure failure, not a mutant kill: ' + message[:500])


def spectra_and_scores(cell, folder):
    functions = formulas()
    spectra, scores = [], []
    eligible = [s for s in cell['sources'] if s['in_estar']]
    for mutant, faults in cell['faults'].items():
        spec = {r: [0, 0, 0, 0] for r in cell['rules']}
        for source in eligible:
            outcome = source['outcomes'][mutant]
            if outcome == 'INVALID_RUNTIME':
                continue
            failing = outcome == 'KILLED'
            for rule in spec:
                spec[rule][(0 if failing else 1) + (0 if rule in source['covered_rules'] else 2)] += 1
        for rule, counts in spec.items():
            spectra.append(dict(mutant_id=mutant, rule_id=rule,
                                n_ef=counts[0], n_ep=counts[1], n_nf=counts[2], n_np=counts[3]))
        for formula, func in functions.items():
            suspiciousness = {r: func(*counts) for r, counts in spec.items()}
            suspiciousness = {r: math.inf if math.isinf(v) else round(v, 12)
                              for r, v in suspiciousness.items()}
            for rule, score in suspiciousness.items():
                higher = sum(v > score for v in suspiciousness.values())
                tied = sum(v == score for v in suspiciousness.values())
                scores.append(dict(mutant_id=mutant, formula=formula, rule_id=rule,
                                   suspiciousness=score, best_rank=higher+1,
                                   worst_rank=higher+tied, mean_rank=(2*higher+1+tied)/2,
                                   is_faulty_rule=int(rule in faults)))
    write_csv(folder / 'rule_spectra.csv', spectra)
    write_csv(folder / 'sbfl_rule_scores.csv', scores)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--n', type=int, default=10)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.n <= 100 or args.workers < 1 or args.timeout < 1:
        parser.error('Require 1 <= n <= 100 and positive workers/timeout')
    run = (args.run_dir or ROOT / 'work/runs' /
           ('aco_bibtex_' + datetime.now().strftime('%Y%m%d_%H%M%S'))).resolve()
    if run == ROOT or any(run.is_relative_to(ROOT / x) for x in ('results','data','subjects','code')):
        parser.error('Use an isolated run directory, e.g. work/runs/aco_bibtex_trial')
    mutants = [r for r in read_csv(ROOT / 'results/rq2/supplementary/inputs/canonical_mutants.csv')
               if r['subject'] == SUBJECT and r['evaluated_in_exported_matrix'] == '1']
    faults = {r['mutant_id']: list(filter(None,re.split(r'[;,|]',r['faulty_rule']))) for r in mutants}
    rules = sorted(extract_rules_and_helpers(str(SUB / 'transformations/BibTeX2DocBook.atl'))['rules'])
    if len(faults) != 40 or len(rules) != 9 or any(not set(f) <= set(rules) for f in faults.values()):
        raise ValueError('Canonical BibTeX universe must be 40 mutants and 9 rules')
    inputs = [ARCHIVE / f'source_{i:04d}.xmi' for i in range(1,101)]
    for path in inputs:
        if not path.is_file():
            raise ValueError('Missing or changed archived source: ' + str(path))
    assets = [Path(__file__), ROOT/'code/experiment_pipeline/aggregate.py',
              ROOT/'code/pipeline/src/executor/transformation_executor.py',
              ROOT/'code/pipeline/src/analyzer/coverage_analyzer.py',
              ROOT/'code/pipeline/src/analyzer/sbfl_analyzer.py',
              ROOT/'code/experiment_pipeline/sbfl_formulas.py',
              SUB/'BibTeX.ecore',SUB/'DocBook.ecore',SUB/'Trace.ecore',
              SUB/'transformations/BibTeX2DocBook.asm']
    assets += [ROOT/f'data/mutants/{SUBJECT}/{name}.asm' for name in faults]
    assets += list((ROOT/'code/pipeline/lib').glob('*.jar'))
    assets += list((ROOT/'code/pipeline/lib').glob('ATLRunner*.class'))
    plan = dict(schema=1, subject=SUBJECT, provider='Yekta-ACO', source_count=args.n,
                timeout=args.timeout, assets=[str(p.relative_to(ROOT)).replace('\\','/') for p in assets], sources=[p.name for p in inputs])
    manifest = run / 'run.json'
    if run.exists():
        if not args.resume or not manifest.exists():
            parser.error('Run exists; choose another directory or use --resume')
        previous = json.loads(manifest.read_text(encoding='utf-8'))
        if args.n < previous['source_count'] or any(previous[k] != plan[k] for k in plan if k != 'source_count'):
            parser.error('Resume requires compatible execution settings and a nondecreasing source count; use a new run after code or asset changes')
    run.mkdir(parents=True, exist_ok=True)
    save_json(manifest, plan)
    formal = {p:p.read_bytes() for p in (ROOT/'results/experiment_results').rglob('*.csv')}
    cfg = dict(java_cp=str(ROOT/'code/pipeline/lib'), source_mm=str(SUB/'BibTeX.ecore'),
               target_mm=str(SUB/'DocBook.ecore'),trace_mm=str(SUB/'Trace.ecore'),
               source_mm_name='BibTeX',target_mm_name='DocBook',trace_mm_name='TMM',
               transformations_dir=str(SUB/'transformations'),timeout=args.timeout,
               reject_containment_warning=True,max_workers=args.workers)
    mutant_cfg = dict(cfg, transformations_dir=str(ROOT/'data/mutants'/SUBJECT))
    sources = []
    print(f'RUN {run}\nReplay {args.n} archived sources x 40 mutants; workers={args.workers}',flush=True)
    archived_evidence = {r['source_id']:r for r in read_csv(
        ROOT/'results/rq1/supplementary/model_size_audit/aco_estar_evidence.csv') if r['subject']==SUBJECT}
    for i, source in enumerate(inputs[:args.n],1):
        sid = f'{i:04d}'
        checkpoint = run/'sources'/f'{sid}.json'
        if checkpoint.exists():
            record = json.loads(checkpoint.read_text(encoding='utf-8'))
            saved_input = run/'execution'/sid/source.name
            if not saved_input.is_file() or saved_input.read_bytes() != source.read_bytes():
                raise ValueError('Checkpoint input changed: ' + sid)
            sources.append(record)
            print(f'{i}/{args.n} source {sid}: checkpoint reused',flush=True)
            continue
        folder = run/'execution'/sid
        folder.mkdir(parents=True, exist_ok=True)
        local = folder/source.name
        shutil.copy2(source, local)
        result = run_transformation(str(local),str(folder/'original.xmi'),'BibTeX2DocBook',cfg)
        infrastructure_check(result)
        save_json(folder/'original_execution.json',result)
        record = dict(source_id=sid,source_present=True,original_success=False,
                      trace_eligible=False,in_estar=False,covered_rules=[],outcomes={},
                      status='ORIGINAL_EXECUTION_FAILED')
        if result['success']:
            ET.parse(result['output'])
            ET.parse(result['trace'])
            covered = sorted(_parse_trace_rules(result['trace']))
            if not set(covered) <= set(rules):
                raise ValueError('Unknown original trace rule: ' + sid)
            record.update(original_success=True,trace_eligible=True,in_estar=True,
                          covered_rules=covered,status='OK',
                          output_elements=len(list(ET.parse(result['output']).getroot().iter())),
                          
                          archived_output_elements=int(archived_evidence[sid]['output_element_count']))
            outcomes = run_mutants_parallel(str(local),str(folder),sid,sorted(faults),mutant_cfg,args.workers)
            save_json(folder/'mutant_executions.json',outcomes)
            if set(outcomes) != set(faults):
                raise ValueError('Missing mutant execution: ' + sid)
            for name, mutated in outcomes.items():
                infrastructure_check(mutated)
                value = 'INVALID_RUNTIME'
                if mutated['success']:
                    try:
                        ET.parse(mutated['output'])
                    except (OSError,ET.ParseError):
                        pass
                    else:
                        value = 'ALIVE' if compare_xmi_models(result['output'],mutated['output']) else 'KILLED'
                record['outcomes'][name] = value
        save_json(checkpoint,record)
        sources.append(record)
        print(f'{i}/{args.n} source {sid}: {record["status"]}; {dict(Counter(record["outcomes"].values()))}',flush=True)
    cell = dict(subject=SUBJECT,provider='aco',condition='aco',rules=rules,faults=faults,sources=sources)
    derived = run/'derived'
    derived.mkdir(exist_ok=True)
    matrix = [dict(subject=SUBJECT,provider='aco',condition='aco',source_id=s['source_id'],
                   original_success=1,mutant_id=m,outcome=outcome)
              for s in sources if s['in_estar'] for m,outcome in sorted(s['outcomes'].items())]
    write_csv(derived/'source_mutant_outcomes_aco_canonical_bibtex.csv',matrix,
              ['subject','provider','condition','source_id','original_success','mutant_id','outcome'])
    exam = list(exam_rows(cell, provider_label='Yekta-ACO'))
    write_csv(derived/'mutant_level_exam.csv',exam)
    spectra_and_scores(cell,derived)
    eligible = [s for s in sources if s['in_estar']]
    killed = {m for s in eligible for m,o in s['outcomes'].items() if o == 'KILLED'}
    counter = Counter(o for s in eligible for o in s['outcomes'].values())
    published = [r for r in read_csv(ROOT/'results/experiment_results/RQ2/mutant_kill_matrix.csv') if r['subject']==SUBJECT]
    published_killed = {r['mutant_id'] for r in published if r['killed_Yekta-ACO'] in ('1','1.0')}
    reference = next(r for r in read_csv(ROOT/'results/experiment_results/RQ2/failure_rates.csv')
                     if r['subject']==SUBJECT and r['method_id']=='Yekta-ACO')
    full = args.n == 100
    counts = dict(attempts=args.n,n_estar=len(eligible),eligible_mutants=40,killed_mutants=len(killed),
                  mutation_score_pct=100*len(killed)/40,
                  failure_rate_pct=100*counter['KILLED']/(len(eligible)*40) if eligible else None,
                  invalid_pairs=counter['INVALID_RUNTIME'])
    write_csv(derived/'metrics.csv',[dict(subject=SUBJECT,provider='Yekta-ACO',**counts)])
    report = dict(scope='Full archived ACO/BibTeX suite' if full else 'Pilot subset; overall paper rates are not comparable',
                  run_dir=str(run),**counts,pair_rows=len(matrix),localization_rows=len(exam),
                  paper_killed_mutants=len(published_killed),paper_mutation_score_pct=float(reference['mutation_score_pct']),
                  paper_failure_rate_pct=float(reference['mean_fail_ratio_pct']),
                  unexpected_killed_mutants=sorted(killed-published_killed),
                  paper_killed_not_observed=sorted(published_killed-killed),
                  
                  original_element_counts_match=sum(s.get('output_elements')==s.get('archived_output_elements') for s in eligible))
    if full:
        report['paper_kill_set_matches']=killed==published_killed
        report['paper_failure_rate_matches']=counts['failure_rate_pct'] is not None and abs(counts['failure_rate_pct']-float(reference['mean_fail_ratio_pct']))<1e-9
        prior={(r['mutant_id'],r['formula']):r for r in read_csv(ROOT/'results/experiment_results/RQ3/mutant_level_exam.csv')
               if r['subject']==SUBJECT and r['provider']=='Yekta-ACO'}
        differences=[]
        for row in exam:
            old=prior.get((row['mutant_id'],row['formula']))
            for field in ['evaluable','failing_sources','exam_ac','best_rank','tie_size']:
                a,b=str(row[field]),old[field] if old else ''
                if a==b:continue
                if a and b and abs(float(a)-float(b))<=1e-9:continue
                differences.append(dict(mutant_id=row['mutant_id'],formula=row['formula'],field=field,rebuilt=a,paper=b))
        report['localization_difference_fields']=len(differences)
        if differences:write_csv(derived/'localization_differences.csv',differences)
    if any(not p.is_file() or p.read_bytes()!=payload for p,payload in formal.items()):
        raise RuntimeError('Formal paper CSV changed during diagnostic replay')
    report['formal_csv_unchanged']=True
    save_json(derived/'report.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
