from pathlib import Path
import copy
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'rq3'))
from build_aco_canonical_localization import make_cell,source_id


def fixture():
    pairs=[dict(subject='S',source_id=s,mutant_id='m',outcome=o)
           for s,o in [('source_0001','KILLED'),('source_0002','INVALID_CONTAINMENT')]]
    coverage=[dict(subject='S',raw_source_id=s,rule_id=r,covered=str(int((s,r) in {('0001','a'),('0002','b')})))
              for s in ['0001','0002'] for r in ['a','b']]
    return pairs,coverage


class CanonicalAcoTests(unittest.TestCase):
    def build(self,pairs,coverage):
        return make_cell('S',pairs,coverage,['a','b'],{'m':['a']},2)

    def test_invalid_containment_is_not_a_passing_or_failing_test(self):
        from experiment_pipeline.aggregate import exam_rows
        pairs,coverage=fixture()
        cell=self.build(pairs,coverage)
        self.assertEqual(cell['sources'][1]['outcomes']['m'],'INVALID_RUNTIME')
        rows=list(exam_rows(cell,provider_label='Yekta-ACO'))
        self.assertEqual(len(rows),18)
        self.assertTrue(all(r['failing_sources']==1 and r['evaluable']==1 for r in rows))

    def test_missing_or_duplicate_pair_cannot_pass(self):
        pairs,coverage=fixture()
        for invalid in [pairs[:1],pairs+[pairs[0]]]:
            with self.assertRaises(ValueError):self.build(invalid,coverage)

    def test_partially_missing_source_coverage_cannot_pass(self):
        pairs,coverage=fixture()
        for invalid in [coverage[:3],coverage+[coverage[0]]]:
            with self.assertRaises(ValueError):self.build(pairs,invalid)

    def test_unknown_outcome_or_rule_cannot_pass(self):
        pairs,coverage=fixture()
        bad=copy.deepcopy(pairs);bad[0]['outcome']='UNKNOWN'
        with self.assertRaises(ValueError):self.build(bad,coverage)
        bad=copy.deepcopy(coverage);bad[0]['rule_id']='unknown'
        with self.assertRaises(ValueError):self.build(pairs,bad)

    def test_archived_identifiers_normalize_to_one_source(self):
        for value in ['0001','source_0001','aco_BibTeX2DocBook_0001']:
            self.assertEqual(source_id(value),'0001')
        with self.assertRaises(ValueError):source_id('missing')


if __name__=='__main__':unittest.main()
