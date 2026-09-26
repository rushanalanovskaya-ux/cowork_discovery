import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pdlc import ROOT, read_json, ready_errors, score, REQUIRED_REFS
from handoff import export_package

class ContractTests(unittest.TestCase):
    def test_score_missing_is_not_zero(self):
        self.assertIsNone(score({'reach':None})[0])
        value = dict(reach=0, impact=2, confidence=0.5, effort_person_weeks=2, score_evidence='same horizon')
        self.assertEqual(score(value)[0], 0)
        value['reach'] = 100
        self.assertEqual(score(value)[0], 50)
        value['effort_person_weeks'] = 0
        self.assertIsNone(score(value)[0])

    def test_bad_scores(self):
        for key, value in [('reach',-1), ('impact',4), ('confidence',1.1), ('reach',True), ('impact',float('nan'))]:
            data = dict(reach=1,impact=1,confidence=1,effort_person_weeks=1,score_evidence='reference')
            data[key] = value
            self.assertIsNone(score(data)[0])

    def test_incomplete_spec_blocked(self):
        spec = copy.deepcopy(read_json(ROOT,'specs/register.json')[0])
        spec.update(status='shaping', owner=None, blockers=['Missing evidence'])
        self.assertTrue(ready_errors(spec))

    def test_package_gate_and_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for p in ['specs','knowledge','evidence']:
                (root/p).mkdir()
            (root/'review.md').write_text('Approved test-only review. Not real approval.')
            (root/'specs/PDLC-TEST.md').write_text('# Test fixture')
            (root/'knowledge/claims.json').write_text('[]')
            (root/'evidence/manifest.json').write_text('[]')
            (root/'.gitignore').write_text('handoff/exports/\n')
            spec=dict(id='PDLC-TEST',revision=1,status='ready',path='specs/PDLC-TEST.md',owner='Test only',blockers=[],sdd_url='https://example.org/test-sdd',security_required=True,claim_ids=[],approvals={})
            for key in REQUIRED_REFS:spec[key]='review.md'
            for role in ['product','engineering','qa','security']:
                spec['approvals'][role]={'by':'Test only','date':'2026-09-26','ref':'review.md'}
            self.assertEqual(ready_errors(spec,root),[])
            bad=copy.deepcopy(spec);bad['blockers']=['unresolved']
            self.assertTrue(ready_errors(bad,root))
            bad=copy.deepcopy(spec);bad['approvals']['security']=None
            self.assertTrue(ready_errors(bad,root))
            bad=copy.deepcopy(spec);bad['qa_plan_ref']='missing.md'
            self.assertTrue(ready_errors(bad,root))
            bad=copy.deepcopy(spec);bad['approvals']['qa']['date']='yesterday'
            self.assertTrue(ready_errors(bad,root))
            def git(*args):return subprocess.check_output(['git',*args],cwd=root,stderr=subprocess.DEVNULL,text=True)
            git('init');git('symbolic-ref','HEAD','refs/heads/main');git('add','.')
            git('-c','user.name=PDLC test','-c','user.email=test@example.invalid','commit','-m','test fixture')
            path=export_package(spec,root)
            with zipfile.ZipFile(path) as z:
                data=json.loads(z.read('package.json'))
                self.assertEqual(data['pdlc_commit'],git('rev-parse','HEAD').strip())
                self.assertIn('specs/PDLC-TEST.md',z.namelist())
                self.assertFalse(any('extracted' in n for n in z.namelist()))
            with self.assertRaises(ValueError):export_package(spec,root)
            (root/'review.md').write_text('Changed after approval')
            spec['revision']=2
            with self.assertRaises(ValueError):export_package(spec,root)

if __name__=='__main__':unittest.main()
