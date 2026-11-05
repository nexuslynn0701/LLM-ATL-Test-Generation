from pathlib import Path
import ast
import copy
import csv
from fractions import Fraction
import json
import math
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CODE))
from experiment_pipeline.evidence import ROOT,validate_cell,load_run,save_json
from experiment_pipeline.aggregate import metric_row,exam_rows,formulas,FORMULA_NAMES,export_evidence,rq5
import run_pipeline


def cell():
    return dict(schema=1,status='complete',subject='Synthetic',provider='gpt',condition='astmo',attempts=3,
                rules=['a','b','c'],faults={'m':['a','b']},sources=[
        dict(source_id='0001',source_present=True,original_success=True,trace_eligible=True,in_estar=True,
             covered_rules=['a'],outcomes={'m':'KILLED'}),
        dict(source_id='0002',source_present=True,original_success=True,trace_eligible=True,in_estar=True,
             covered_rules=['b'],outcomes={'m':'ALIVE'}),
        dict(source_id='0003',source_present=True,original_success=True,trace_eligible=True,in_estar=True,
             covered_rules=['b','c'],outcomes={'m':'INVALID_RUNTIME'})])


class EvidenceTests(unittest.TestCase):
    def test_baseline_label_does_not_change_sbfl_calculation(self):
        original=list(exam_rows(cell()))
        baseline_cell=cell()
        baseline_cell.update(provider='aco',condition='aco')
        baseline=list(exam_rows(baseline_cell,provider_label='Yekta-ACO'))
        for expected,actual in zip(original,baseline):
            self.assertEqual(actual['provider'],'Yekta-ACO')
            self.assertEqual(actual['cell_kind'],'baseline')
            for field in ['formula','evaluable','failing_sources','best_rank','exam_ac','tie_size']:
                self.assertEqual(actual[field],expected[field])

    def test_invalid_pairs_retained_in_failure_denominator_not_kills(self):
        row=metric_row(validate_cell(cell()))
        self.assertEqual(row['failure_rate_pct_numerator'],100)
        self.assertEqual(row['failure_rate_pct_denominator'],3)
        self.assertEqual(row['invalid_pairs'],1)
        self.assertEqual(row['killed_mutants'],1)

    def test_missing_duplicate_and_unknown_outcomes_rejected(self):
        for edit in [lambda c:c['sources'][0]['outcomes'].clear(),
                     lambda c:c['sources'].append(c['sources'][0]),
                     lambda c:c['sources'][0]['outcomes'].update(m='TIMEOUT')]:
            c=cell();edit(c)
            with self.assertRaises(ValueError):validate_cell(c)

    def test_zero_valid_is_na_and_attempts_are_not_hardcoded_100(self):
        c=cell()
        for s in c['sources']:
            s.update(original_success=False,trace_eligible=False,in_estar=False,covered_rules=[],outcomes={})
        row=metric_row(validate_cell(c))
        self.assertEqual(row['validity_pct'],'0.000000000000000')
        self.assertEqual(row['failure_rate_pct'],'--')
        self.assertEqual(row['total_pairs'],0)

    def test_all_18_formulas_match_published_rebuild_tie_handling(self):
        # Execute only the old pure calculation function; no replay imports/data.
        path=CODE/'rq3/rebuild_top1_source.py'
        node=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body
                  if isinstance(n,ast.FunctionDef) and n.name=='calc')
        ns=dict(NAMES=FORMULA_NAMES,ns=formulas(),math=math,F=Fraction,
                mean=lambda v:sum(v,Fraction(0))/len(v))
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),ns)
        expected=ns['calc']({'a':[1,0,0,1],'b':[0,1,1,0],'c':[0,0,1,1]},['a','b'],1,3)
        actual=list(exam_rows(cell()))
        self.assertEqual(len(actual),18)
        for row in actual:
            for field,value in expected[row['formula']].items():
                self.assertEqual(str(row[field]),value,(row['formula'],field))

    def test_survivor_has_no_exam(self):
        c=cell();c['sources'][0]['outcomes']['m']='ALIVE'
        self.assertTrue(all(r['evaluable']==0 and r['exam_ac']=='' for r in exam_rows(c)))

    def test_spectrum_exports_invalid_separately(self):
        with tempfile.TemporaryDirectory() as temp:
            export_evidence([cell()],temp)
            with open(Path(temp)/'rq3_test_rule_spectra_long.csv',newline='') as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),9)
            self.assertEqual({r['test_outcome'] for r in rows},{'FAIL','PASS','INVALID'})

    def test_pooled_metrics_and_overlap(self):
        a=cell();b=cell();b['condition']='workflow'
        b['sources'][0]['outcomes']['m']='ALIVE'
        with tempfile.TemporaryDirectory() as temp:
            rq5([a,b],temp)
            with open(Path(temp)/'mutant_overlap.csv',newline='') as f:
                row=next(csv.DictReader(f))
            self.assertEqual(row['astmo_only_mutants'],'1')
            self.assertEqual(row['workflow_only_mutants'],'0')

    def test_incomplete_run_refuses_aggregation(self):
        with tempfile.TemporaryDirectory() as temp:
            key=dict(subject='Synthetic',provider='gpt',condition='astmo')
            save_json(Path(temp)/'run.json',dict(schema=1,n=3,cells=[key],protocol={}))
            with self.assertRaises(FileNotFoundError):load_run(temp)

    def test_infrastructure_error_is_not_kill(self):
        with self.assertRaises(RuntimeError):
            run_pipeline.check_infrastructure({'returncode':1,'stderr':'ClassNotFoundException'})

    def test_multitarget_comparison_requires_all_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'one.xmi';p.write_text('<target/>')
            with self.assertRaises(FileNotFoundError):
                run_pipeline.targets({'outputs':{'A':str(p),'B':str(p.with_name('absent.xmi'))}})

    def test_generation_dispatches_formal_prompt_and_resumes_without_new_call(self):
        sys.path.insert(0,str(run_pipeline.RUNTIME))
        key=dict(subject='BibTeX2DocBook',provider='gpt',condition='astmo')
        args=SimpleNamespace(n=1,generation_timeout=30)
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            def fake_process(command, **kwargs):
                self.assertEqual(command[command.index('--prompt-version')+1],'formal')
                root=Path(command[command.index('--output-dir')+1])
                (root/'gpt').mkdir(parents=True)
                (root/'gpt/multi_config_results.csv').write_text('status\nGEN_FAIL\n')
            with patch('src.llm.llm_client.get_api_key',return_value='unit-test-key'), \
                 patch.object(run_pipeline.subprocess,'run',side_effect=fake_process) as process:
                run_pipeline.generate(directory,key,args)
                run_pipeline.generate(directory,key,args)
                self.assertEqual(process.call_count,1)
            self.assertNotIn('unit-test-key',(directory/'generation_complete.json').read_text())

    def test_interrupted_generation_does_not_reissue_paid_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);save_json(directory/'generation_started.json',{})
            with patch.object(run_pipeline.subprocess,'run') as process:
                with self.assertRaisesRegex(RuntimeError,'Interrupted generation'):
                    run_pipeline.generate(directory,{},SimpleNamespace())
                process.assert_not_called()

    def test_parallel_mutants_normalize_source_once(self):
        sys.path.insert(0,str(run_pipeline.RUNTIME))
        from src.executor import transformation_executor as executor
        with patch.object(executor,'_prepare_source_model',return_value=('normalized.xmi',None)) as prep, \
             patch.object(executor,'run_transformation',return_value={'success':True}) as execute:
            result=executor.run_mutants_parallel('original.xmi','out','0001',['m1','m2'],max_workers=2)
            prep.assert_called_once()
            self.assertEqual(set(result),{'m1','m2'})
            self.assertTrue(all(c.args[0]=='normalized.xmi' for c in execute.call_args_list))


if __name__=='__main__':unittest.main()
