"""Versioned evidence contract shared by execution, RQ3 and RQ5.

Invalid mutant executions are recorded, never counted as kills or passing SBFL
tests. Failure-rate denominators retain every E* source x eligible mutant pair.
"""
from pathlib import Path
import csv
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT/'code/runtime/pipeline_toolchain'
PROVIDERS = {'gpt': 'GPT', 'qwen': 'Qwen', 'deepseek': 'DeepSeek'}
SCHEMA = 1


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temp.replace(path)




def protocol():
    sys.path.insert(0, str(RUNTIME))
    from src.experiment.run_ladder_experiment import DATASETS
    from src.analyzer.coverage_analyzer import extract_rules_and_helpers
    counts = {r['transformation']: r for r in read_csv(ROOT/'results/rq1/supplementary/subjects.csv')}
    mutants = read_csv(ROOT/'results/rq2/supplementary/inputs/canonical_mutants.csv')
    result = {}
    for subject, ds in DATASETS.items():
        rules = extract_rules_and_helpers(str(ds['dataset_dir']/ds['atl_file']))['rules']
        selected = [dict(r) for r in mutants if r['subject'] == subject and r['evaluated_in_exported_matrix'] == '1']
        faults = {}
        for row in selected:
            names = set(filter(None, re.split(r'[;|,]', row['faulty_rule'])))
            # Canonical multi-rule fault mapping used by all current localization paths.
            if (subject, row['mutant_id']) == ('CPL2SPL', 'CPL2SPL_Mutant47'):
                names = {'CPL2Program', 'SubAction2Function'}
            if not names or not names <= set(rules):
                raise ValueError(f'Invalid fault mapping: {subject}/{row["mutant_id"]}: {names}')
            faults[row['mutant_id']] = sorted(names)
        if len(faults) != int(counts[subject]['mutants']) or len(rules) != int(counts[subject]['total_rules']):
            raise ValueError(f'Universe mismatch: {subject}')
        for name in faults:
            if not (ds['dataset_dir']/'transformations'/f'{name}.asm').is_file():
                raise FileNotFoundError(f'Missing compiled mutant: {subject}/{name}')
        result[subject] = {'rules': sorted(rules), 'faults': faults}
    return result


def validate_cell(cell):
    if cell.get('schema') != SCHEMA or cell.get('status') != 'complete':
        raise ValueError('Incomplete or unsupported cell evidence')
    if cell['provider'] not in PROVIDERS or cell['attempts'] < 1:
        raise ValueError('Invalid provider or attempt count')
    rules = cell['rules']
    faults = cell['faults']
    if not rules or len(rules) != len(set(rules)) or not faults:
        raise ValueError('Empty or duplicate rule/mutant universe')
    if any(not f or not set(f) <= set(rules) for f in faults.values()):
        raise ValueError('Fault outside the rule universe')
    sources = cell['sources']
    if len(sources) != cell['attempts'] or len({s['source_id'] for s in sources}) != len(sources):
        raise ValueError('Missing or duplicate source attempts')
    for source in sources:
        if not set(source['covered_rules']) <= set(rules):
            raise ValueError('Unknown covered rule')
        eligible = bool(source['original_success'] and source['trace_eligible'])
        if bool(source['in_estar']) != eligible:
            raise ValueError('Inconsistent E* membership')
        pairs = source['outcomes']
        expected = set(faults) if eligible else set()
        if set(pairs) != expected:
            raise ValueError(f'Missing/extra mutant outcomes for {source["source_id"]}')
        if set(pairs.values()) - {'KILLED', 'ALIVE', 'INVALID_RUNTIME'}:
            raise ValueError('Unknown mutant outcome')
    return cell


def load_run(run):
    run = Path(run)
    manifest = json.loads((run/'run.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != SCHEMA:
        raise ValueError('Unsupported run schema')
    cells = []
    for key in manifest['cells']:
        path = run/'cells'/key['subject']/key['provider']/key['condition']/'cell.json'
        cell = validate_cell(json.loads(path.read_text(encoding='utf-8')))
        if any(cell[k] != key[k] for k in key) or cell['attempts'] != manifest['n']:
            raise ValueError(f'Cell does not match run manifest: {path}')
        universe = manifest['protocol'][key['subject']]
        if any(cell[k] != universe[k] for k in ('rules','faults')):
            raise ValueError(f'Rule/mutant universe changed: {path}')
        cells.append(cell)
    if not cells or len({(c['subject'], c['provider'], c['condition']) for c in cells}) != len(cells):
        raise ValueError('Empty/duplicate run matrix')
    return cells
