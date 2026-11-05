"""Verify current method scope and the manuscript's raw-p statistical protocol."""
from pathlib import Path
import csv,re
ROOT=Path(__file__).resolve().parents[2]
RETIRED=re.compile(r'mm[-_\s]?random|mit[-_\s]?random',re.I)
EXCLUDED={'runtime','__pycache__','_replay','archive','archived_output_scripts'}

def check():
    files=[];bad=[]
    for base in ('results','code','data'):
        for path in (ROOT/base).rglob('*.csv'):
            if EXCLUDED.intersection(path.relative_to(ROOT).parts):continue
            files.append(path)
            if RETIRED.search(path.name) or RETIRED.search(path.read_text(encoding='utf-8-sig')):
                bad.append(str(path.relative_to(ROOT)))
    if bad:raise ValueError('Retired baseline in current CSVs: '+', '.join(bad[:10]))
    def read(rel):
        with (ROOT/rel).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    tests=read('results/rq3/data/rq3_pairwise_tests.csv')
    if len(tests)!=216 or {r['baseline'] for r in tests}!={'Yekta-ACO'}:
        raise ValueError('Expected exactly 216 LLM-versus-ACO comparisons')
    fields={'provider','condition','formula','baseline','n_common',
            'p_raw','A12','mean_difference','classification'}
    if set(tests[0])!=fields:
        raise ValueError('RQ3 requires exactly the nine raw-p statistical columns')
    for row in tests:
        p,effect=float(row['p_raw']),float(row['A12'])
        if not (0<=p<=1 and 0<=effect<=1):
            raise ValueError('Invalid p-value or A12 in RQ3')
        expected='Similar' if p>=.05 else 'Better' if effect>.5 else 'Worse'
        if row['classification']!=expected:
            raise ValueError('RQ3 classification must use raw p < .05: '+str(row))
    top=read('results/rq3/data/rq3_top1_pooled.csv')
    if len(top)!=18 or len(top[0])!=14:
        raise ValueError('Expected 18 formulas x 13 configurations plus formula key')
    return len(files)

if __name__=='__main__':print(f'PASS: {check()} current CSVs; 13 configurations and 216 comparisons.')
