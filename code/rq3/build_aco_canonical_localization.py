"""Build ACO SBFL from the same canonical pair outcomes used by RQ2.

KILLED/ALIVE are failing/passing tests. Invalid runtime/containment executions
are excluded from SBFL counts, while RQ2 retains them in its pair denominator.
No published rankings or historical EXAM values enter this calculation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
for folder in (ROOT/'code',ROOT/'code/pipeline'):
    if str(folder) not in sys.path:sys.path.append(str(folder))
from experiment_pipeline.aggregate import exam_rows
from experiment_pipeline.evidence import read_csv, write_csv
from src.analyzer.coverage_analyzer import extract_rules_and_helpers

BIB_PAIRS=ROOT/'code/rq2/data/aco/source_mutant_outcomes_aco_canonical_bibtex.csv'
OTHER_PAIRS=ROOT/'code/rq2/data/aco/source_mutant_outcomes_aco_replay_cpl_uml.csv'
COVERAGE=ROOT/'results/rq1/supplementary/model_size_audit/aco_archive/source_rule_coverage_aco.csv'
EXPECTED_SOURCES={'BibTeX2DocBook':100,'CPL2SPL':96,'UML2ER':100}
ATL_NAMES={'BibTeX2DocBook':'BibTeX2DocBook','CPL2SPL':'CPL2SPL','UML2ER':'SimpleUml2ER'}
EXPECTED_MUTANTS={'BibTeX2DocBook':40,'CPL2SPL':50,'UML2ER':18}
OUTCOMES={'KILLED':'KILLED','ALIVE':'ALIVE','INVALID_RUNTIME':'INVALID_RUNTIME',
          'INVALID_CONTAINMENT':'INVALID_RUNTIME'}


def source_id(value):
    match=re.search(r'(?:^|_)(\d{4})$',str(value))
    if not match:raise ValueError('Unrecognized canonical source identifier: '+str(value))
    return match.group(1)


def make_cell(subject,pairs,coverage,rules,faults,expected_sources):
    """Validate a complete source x mutant matrix and source x rule matrix."""
    matrix=defaultdict(dict)
    for row in pairs:
        if row['subject']!=subject:raise ValueError('Pair subject mismatch')
        sid=source_id(row['source_id'])
        mutant=row['mutant_id']
        if row.get('original_success','1')!='1':
            raise ValueError('Canonical ACO pairs must be original-executable sources')
        if mutant not in faults or row['outcome'] not in OUTCOMES:
            raise ValueError(f'Unknown mutant/outcome: {subject}/{sid}/{mutant}')
        if mutant in matrix[sid]:raise ValueError(f'Duplicate pair: {subject}/{sid}/{mutant}')
        matrix[sid][mutant]=OUTCOMES[row['outcome']]
    if len(matrix)!=expected_sources:
        raise ValueError(f'{subject}: expected {expected_sources} sources, found {len(matrix)}')
    for sid,values in matrix.items():
        if set(values)!=set(faults):raise ValueError(f'Incomplete mutant matrix: {subject}/{sid}')
    flags=defaultdict(dict)
    for row in coverage:
        if row['subject']!=subject:raise ValueError('Coverage subject mismatch')
        sid=source_id(row.get('raw_source_id') or row['source_id'])
        rule=row['rule_id']
        if sid not in matrix or rule not in rules or row['covered'] not in {'0','1'}:
            raise ValueError(f'Unknown coverage source/rule/flag: {subject}/{sid}/{rule}')
        if rule in flags[sid]:raise ValueError(f'Duplicate coverage flag: {subject}/{sid}/{rule}')
        flags[sid][rule]=row['covered']=='1'
    for sid in matrix:
        if set(flags[sid])!=set(rules):raise ValueError(f'Incomplete rule coverage: {subject}/{sid}')
    if any(not f or not set(f)<=set(rules) for f in faults.values()):
        raise ValueError('Fault mapping is outside the original rule universe')
    return dict(subject=subject,provider='aco',condition='aco',rules=sorted(rules),faults=faults,
                sources=[dict(source_id=sid,original_success=True,trace_eligible=True,in_estar=True,
                              covered_rules=sorted(r for r,v in flags[sid].items() if v),outcomes=matrix[sid])
                         for sid in sorted(matrix)])


def load_cells(bib_pairs=BIB_PAIRS,other_pairs=OTHER_PAIRS,coverage_path=COVERAGE):
    pair_rows=read_csv(bib_pairs)+read_csv(other_pairs)
    if {r['subject'] for r in pair_rows}!=set(EXPECTED_SOURCES):
        raise ValueError('Canonical pair files must cover exactly the three ACO subjects')
    coverage_rows=read_csv(coverage_path)
    metadata=read_csv(ROOT/'code/rq2/data/canonical_mutants.csv')
    cells=[]
    for subject,n in EXPECTED_SOURCES.items():
        rules=extract_rules_and_helpers(str(ROOT/'subjects'/subject/'transformations'/(ATL_NAMES[subject]+'.atl')))['rules']
        selected=[r for r in metadata if r['subject']==subject and r['evaluated_in_exported_matrix']=='1']
        faults={r['mutant_id']:list(filter(None,re.split(r'[;,|]',r['faulty_rule']))) for r in selected}
        if subject=='CPL2SPL':faults['CPL2SPL_Mutant47']=['CPL2Program','SubAction2Function']
        if len(faults)!=EXPECTED_MUTANTS[subject]:raise ValueError('Canonical mutant universe changed: '+subject)
        cells.append(make_cell(subject,[r for r in pair_rows if r['subject']==subject],
                               [r for r in coverage_rows if r['subject']==subject],rules,faults,n))
    return cells


def build(bib_pairs=BIB_PAIRS,other_pairs=OTHER_PAIRS,coverage_path=COVERAGE):
    cells=load_cells(bib_pairs,other_pairs,coverage_path)
    rows=[r for cell in cells for r in exam_rows(cell,provider_label='Yekta-ACO')]
    rows.sort(key=lambda r:(r['subject'],r['mutant_id'],r['formula']))
    if len(rows)!=1944:raise ValueError('Expected 108 ACO mutants x 18 formulas')
    return rows,cells


def export(folder,bib_pairs=BIB_PAIRS,other_pairs=OTHER_PAIRS,coverage_path=COVERAGE):
    folder=Path(folder)
    rows,cells=build(bib_pairs,other_pairs,coverage_path)
    write_csv(folder/'aco_mutant_level_exam.csv',rows)
    spectra=[]
    audits=[]
    for cell in cells:
        totals=Counter(outcome for s in cell['sources'] for outcome in s['outcomes'].values())
        killed={m for s in cell['sources'] for m,o in s['outcomes'].items() if o=='KILLED'}
        audits.append(dict(subject=cell['subject'],n_estar=len(cell['sources']),mutants=len(cell['faults']),
                           pairs=sum(totals.values()),killed_pairs=totals['KILLED'],
                           alive_pairs=totals['ALIVE'],invalid_pairs=totals['INVALID_RUNTIME'],
                           killed_mutants=len(killed)))
        for mutant in cell['faults']:
            for rule in cell['rules']:
                counts=[0,0,0,0]
                for source in cell['sources']:
                    outcome=source['outcomes'][mutant]
                    if outcome=='INVALID_RUNTIME':continue
                    counts[(0 if outcome=='KILLED' else 1)+(0 if rule in source['covered_rules'] else 2)]+=1
                spectra.append(dict(subject=cell['subject'],mutant_id=mutant,rule_id=rule,
                                    ef=counts[0],ep=counts[1],nf=counts[2],np=counts[3]))
    write_csv(folder/'aco_rule_spectra.csv',spectra)
    audit=dict(protocol='RQ2 canonical oracle; invalid executions excluded from SBFL; 18 formulas and tie-mid EXAM',
               inputs=[dict(path=str(Path(p).relative_to(ROOT)).replace('\\','/'))
                       for p in [bib_pairs,other_pairs,coverage_path]],subjects=audits,
               mutant_formula_rows=len(rows),rule_spectra_rows=len(spectra))
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    return rows,audit


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'rebuild/rq3/aco_canonical')
    args=parser.parse_args()
    _,audit=export(args.output)
    print(json.dumps(audit,indent=2))
