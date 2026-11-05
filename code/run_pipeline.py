#!/usr/bin/env python3
"""Fresh-run pipeline. Default preflight performs no generation or API calls."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from experiment_pipeline.evidence import (ROOT, RUNTIME, PROVIDERS, SCHEMA, protocol,
                                          read_csv, save_json, validate_cell, load_run)


def preflight():
    if not RUNTIME.is_dir():
        subprocess.run([sys.executable, str(ROOT/'code/prepare_pipeline.py')], check=True)
    if not shutil.which('java'):
        raise RuntimeError('Java is required; java was not found on PATH')
    for folder in ('src','scripts','lib'):
        for source in (ROOT/'code/pipeline'/folder).rglob('*'):
            if source.is_file() and '__pycache__' not in source.parts:
                copied = RUNTIME/source.relative_to(ROOT/'code/pipeline')
                if not copied.is_file() or source.read_bytes() != copied.read_bytes():
                    raise RuntimeError(f'Stale runtime file: {copied}; run code/prepare_pipeline.py --refresh-code')
    for name in ['ATLRunner', 'ATLRunnerMulti']:
        cp = os.pathsep.join([str(RUNTIME/'lib'/'*'), str(RUNTIME/'lib')])
        p = subprocess.run(['java','-cp',cp,name], capture_output=True, timeout=30)
        if b'Usage:' not in p.stdout+p.stderr:
            raise RuntimeError(f'{name} cannot start: {(p.stdout+p.stderr).decode(errors="replace")}')
    p = protocol()
    sys.path.insert(0, str(RUNTIME))
    from src.experiment.run_ladder_experiment import DATASETS, CONDITIONS, build_execution_prompt
    for subject, ds in DATASETS.items():
        paths = [ds['dataset_dir']/ds['source_mm'], ds['dataset_dir']/ds['trace_mm'],
                 ds['dataset_dir']/ds['atl_file'], ds['dataset_dir']/ds['ocl_file'],
                 ds['dataset_dir']/'transformations'/(ds.get('atl_exec_name',ds['atl_name'])+'.asm')]
        paths += [ds['dataset_dir']/m for m in ds['target_mms']]
        if any(not path.is_file() for path in paths):
            raise FileNotFoundError(f'Missing assets: {subject}')
        for condition in CONDITIONS:
            build_execution_prompt(subject,condition,'formal')
    print('PASS: Java runners, six subjects, 288 formal compiled mutants, and 24 frozen prompts.', flush=True)
    return p




def check_infrastructure(result):
    message = (result.get('stderr') or '')+' '+(result.get('error') or '')
    if result['returncode'] == -1 or any(t in message for t in (
            'ClassNotFoundException', 'NoClassDefFoundError', 'UnsupportedClassVersionError',
            'unknown protocol: c', 'OutOfMemoryError', 'Could not reserve enough space')):
        raise RuntimeError('ATL infrastructure error (not a mutant kill): '+message)


def targets(result):
    outputs = result.get('outputs') or {'OUT': result.get('output')}
    for path in outputs.values():
        if not path:
            raise ValueError('Missing target output')
        ET.parse(path)
    return outputs


def generate(cell_dir, key, args):
    marker = cell_dir/'generation_complete.json'
    gen = cell_dir/'generation'
    if marker.exists():
        saved = json.loads(marker.read_text(encoding='utf-8'))
        for relative in saved['files']:
            if not (cell_dir/relative).is_file():
                raise ValueError('Generated source changed after checkpoint')
        return gen
    started = cell_dir/'generation_started.json'
    if started.exists():
        raise RuntimeError(f'Interrupted generation at {cell_dir}; refusing to silently repeat API calls. '
                           'Recover the saved generation records or start a separate run.')
    env = dict(os.environ, PYTHONIOENCODING='utf-8', LLM_CALL_LOG=str(cell_dir/'llm_calls.jsonl'))
    from src.llm.llm_client import get_api_key
    aliases = {'gpt':'openai','qwen':'qwen','deepseek':'deepseek-flash'}
    variables = {'gpt':'OPENAI_API_KEY','qwen':'QWEN_API_KEY','deepseek':'DEEPSEEK_API_KEY'}
    env[variables[key['provider']]] = get_api_key(aliases[key['provider']])
    if key['condition'] == 'workflow':
        command = [str(ROOT/'data/workflow/run_workflow.py'), '--subject',key['subject'],
                   '--provider',key['provider'],'--n',str(args.n),'--atl-lib',str(RUNTIME/'lib'),
                   '--output-root',str(gen)]
    else:
        command = ['-m','src.experiment.run_ladder_experiment','--provider',
                   'deepseek-flash' if key['provider'] == 'deepseek' else key['provider'],
                   '--condition',key['condition'],'--datasets',key['subject'],'--n-models',str(args.n),
                   '--prompt-version','formal',
                   '--output-dir',str(gen)]
    save_json(started, {'cell':key,'attempts':args.n})
    with (cell_dir/'generation.log').open('w', encoding='utf-8') as log:
        subprocess.run([sys.executable,*command], cwd=RUNTIME, env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=args.generation_timeout)
    if key['condition'] == 'workflow':
        records = json.loads((gen/key['subject']/key['provider']/'generation_summary.json').read_text(encoding='utf-8'))
    else:
        records = read_csv(gen/key['provider']/'multi_config_results.csv')
    if len(records) != args.n:
        raise RuntimeError(f'Generation produced {len(records)} attempt records; expected {args.n}')
    save_json(marker, {'attempts':len(records), 'files':[
        str(f.relative_to(cell_dir)) for f in gen.rglob('*') if f.is_file() and f.suffix in ('.xmi','.json','.csv')]})
    return gen


def execute_cell(run, key, universe, args):
    from src.experiment.run_ladder_experiment import DATASETS, get_executor_config
    from src.executor.transformation_executor import run_transformation, run_mutants_parallel
    from src.analyzer.sbfl_analyzer import _parse_trace_rules
    from src.analyzer.coverage_analyzer import compare_xmi_models
    cell_dir = run/'cells'/key['subject']/key['provider']/key['condition']
    cell_dir.mkdir(parents=True, exist_ok=True)
    finished = cell_dir/'cell.json'
    if finished.exists():
        completed = validate_cell(json.loads(finished.read_text(encoding='utf-8')))
        if args.mode == 'replay':
            for record in completed['sources']:
                sid = record['source_id']
                source = args.source_root/key['subject']/key['condition']/key['provider']/f'{sid}.xmi'
                saved_input = cell_dir/'inputs'/f'{sid}.xmi'
                present = source.is_file()
                if record.get('source_present') != present or (present and (
                        not saved_input.is_file() or saved_input.read_bytes() != source.read_bytes())):
                    raise ValueError(f'Source changed on resume: {source}')
        print('Resume completed cell:', '/'.join(key.values()), flush=True)
        return
    ds = DATASETS[key['subject']]
    cfg = get_executor_config(key['subject'])
    cfg['timeout'] = args.atl_timeout
    cfg['max_workers'] = args.workers
    gen = generate(cell_dir, key, args) if args.mode == 'generate' else None
    records = []
    for i in range(1,args.n+1):
        sid = f'{i:04d}'
        if gen is not None:
            if key['condition'] == 'workflow':
                source = gen/key['subject']/key['provider']/'generated_models'/f'source_model_{sid}.xmi'
            else:
                source = gen/key['provider']/'generated_models'/key['subject']/key['condition']/f'source_model_{sid}.xmi'
        else:
            source = args.source_root/key['subject']/key['condition']/key['provider']/f'{sid}.xmi'
        checkpoint = cell_dir/'sources'/f'{sid}.json'
        present = source.is_file()
        if checkpoint.exists():
            record = json.loads(checkpoint.read_text(encoding='utf-8'))
            saved_input = cell_dir/'inputs'/f'{sid}.xmi'
            if record['source_present'] != present or (present and (not saved_input.is_file() or saved_input.read_bytes() != source.read_bytes())):
                raise ValueError(f'Source changed on resume: {source}')
            records.append(record)
            continue
        record = {'source_id':sid, 'source_present':present, 'original_success':False,
                  'trace_eligible':False,'in_estar':False,'covered_rules':[], 'outcomes':{},
                  'status':'GENERATION_FAILURE' if gen else 'MISSING_ARCHIVED_SOURCE'}
        if present:
            local = cell_dir/'inputs'/f'{sid}.xmi'
            local.parent.mkdir(exist_ok=True)
            shutil.copy2(source,local)
            output = cell_dir/'outputs'/f'output_{sid}.xmi'
            result = run_transformation(str(local),str(output),ds['atl_name'],cfg)
            check_infrastructure(result)
            save_json(cell_dir/'execution_logs'/f'{sid}_original.json',result)
            record['original_success'] = result['success']
            record['status'] = 'ATL_EXEC_FAIL'
            if result['success']:
                try:
                    original = targets(result)
                    ET.parse(result['trace'])
                    covered = _parse_trace_rules(result['trace'])
                    if not covered <= set(universe['rules']):
                        raise ValueError(f'Unknown trace rules: {covered-set(universe["rules"])}')
                except (ET.ParseError, TypeError, OSError):
                    record['status'] = 'UNVERIFIABLE_OUTPUT'
                else:
                    record.update(trace_eligible=True,in_estar=True,covered_rules=sorted(covered),status='OK')
                    mutations = run_mutants_parallel(str(local),str(output.parent),sid,
                                                    sorted(universe['faults']),cfg,args.workers)
                    for mutant, mutated in mutations.items():
                        check_infrastructure(mutated)
                        outcome = 'INVALID_RUNTIME'
                        if mutated['success']:
                            try:
                                other = targets(mutated)
                                if set(original) != set(other):
                                    raise ValueError('Target output names changed')
                                outcome = 'ALIVE' if all(compare_xmi_models(original[k],other[k]) for k in original) else 'KILLED'
                            except (ET.ParseError, OSError):
                                outcome = 'INVALID_RUNTIME'
                        record['outcomes'][mutant] = outcome
                    save_json(cell_dir/'execution_logs'/f'{sid}_mutants.json',mutations)
        save_json(checkpoint,record)
        records.append(record)
        print('/'.join(key.values()),sid,record['status'],
              f'{sum(o == "KILLED" for o in record["outcomes"].values())} killed',flush=True)
    cell = dict(schema=SCHEMA,status='complete',attempts=args.n,**key,**universe,sources=records)
    validate_cell(cell)
    save_json(finished,cell)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode',choices=['preflight','replay','generate','aggregate'],default='preflight')
    ap.add_argument('--run-dir',type=Path)
    ap.add_argument('--source-root',type=Path,default=ROOT/'data/test_cases')
    ap.add_argument('--subjects',nargs='+')
    ap.add_argument('--providers',nargs='+',choices=list(PROVIDERS),default=list(PROVIDERS))
    ap.add_argument('--conditions',nargs='+',choices=['sm','stm','astm','astmo','workflow'],default=['sm','stm','astm','astmo','workflow'])
    ap.add_argument('--n',type=int,default=100)
    ap.add_argument('--workers',type=int,default=4)
    ap.add_argument('--atl-timeout',type=int,default=300)
    ap.add_argument('--generation-timeout',type=int,default=21600)
    ap.add_argument('--resume',action='store_true')
    args = ap.parse_args(argv)
    if min(args.n,args.workers,args.atl_timeout,args.generation_timeout) < 1:
        ap.error('Counts and timeouts must be positive')
    if args.mode != 'preflight' and args.run_dir is None:
        ap.error('--run-dir is required')
    if args.mode == 'aggregate':
        from experiment_pipeline.aggregate import aggregate_run
        print(aggregate_run(args.run_dir)); return
    universes = preflight()
    subjects = args.subjects or list(universes)
    if set(subjects)-set(universes):
        ap.error('Unknown subject')
    if any(len(v) != len(set(v)) for v in (subjects,args.providers,args.conditions)):
        ap.error('Duplicate matrix selections')
    if args.mode == 'preflight':
        return
    run = args.run_dir.resolve()
    # Protect immutable inputs and formal results from accidental execution output.
    for protected in ['results','data','subjects','code']:
        if run == ROOT or run.is_relative_to(ROOT/protected):
            ap.error('Use a new run directory outside results/data/subjects/code, e.g. work/runs/demo')
    args.source_root = args.source_root.resolve()
    keys = [dict(subject=s,provider=p,condition=c) for s in subjects for p in args.providers for c in args.conditions]
    if args.mode == 'replay':
        for key in keys:
            folder = args.source_root/key['subject']/key['condition']/key['provider']
            if not folder.is_dir():
                ap.error(f'Source cell directory missing: {folder}')
    plan = dict(schema=SCHEMA,mode=args.mode,n=args.n,cells=keys,
                source_root=str(args.source_root) if args.mode == 'replay' else None,
                atl_timeout=args.atl_timeout,
                protocol={s:universes[s] for s in subjects})
    manifest = run/'run.json'
    if run.exists():
        if not args.resume or not manifest.is_file():
            ap.error('Run directory exists; use --resume for a compatible run or choose a new directory')
        if json.loads(manifest.read_text(encoding='utf-8')) != plan:
            ap.error('Resume plan mismatch; choose a new run directory')
    else:
        save_json(manifest,plan)
    for key in keys:
        execute_cell(run,key,universes[key['subject']],args)
    from experiment_pipeline.aggregate import aggregate_run
    out = aggregate_run(run)
    save_json(run/'complete.json',{'schema':SCHEMA,'cells':len(keys),'derived':str(out.relative_to(run))})
    print('Completed:',out,flush=True)


if __name__ == '__main__':
    main()
