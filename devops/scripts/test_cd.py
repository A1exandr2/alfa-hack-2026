import importlib.util
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'devops/scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
cleanup=load('cleanup-images');deploy=load('deploy-release');dast=load('dast-scan')


class CDTests(unittest.TestCase):
    def test_cleanup_protects_current_previous_running_young_and_other_projects(self):
        now=datetime.now(timezone.utc)
        def image(sha,**kw):
            return dict(Id=kw.get('id',sha),RepoTags=[kw.get('tag','credit-backend:'+sha)],
                        Created=(now-timedelta(days=kw.get('age',3))).isoformat(),
                        Config={'Labels':{'io.credit.project':kw.get('project','credit')}})
        a,b,c,d,e,f,g=[str(n)*40 for n in range(1,8)]
        images=[image(a),image(b),image(c,id='running'),image(d,age=0),image(e,project='foreign'),image(f),image(g,tag='credit-backend:local')]
        self.assertEqual(cleanup.candidates(images,{'running'},{a,b},now),['credit-backend:'+f])

    def test_archive_rejects_traversal_and_private_files(self):
        import io
        for name in ['../escape','.env','source/.local/keys.txt']:
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory);archive=path/'bad.tar.gz'
                with tarfile.open(archive,'w:gz') as tar:
                    info=tarfile.TarInfo(name);info.size=4;tar.addfile(info,io.BytesIO(b'test'))
                with self.assertRaises(ValueError):deploy.unpack(archive,path/'output')

    def test_release_switch_is_atomic_and_preserves_previous_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);one=root/'one';two=root/'two';one.mkdir();two.mkdir()
            deploy.switch(root/'current',one);self.assertEqual((root/'current').resolve(),one)
            deploy.switch(root/'current',two);self.assertEqual((root/'current').resolve(),two)
            self.assertTrue(one.exists())

    def test_failed_activation_restores_previous_application_release(self):
        import io,subprocess
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'releases'/('a'*40);old.mkdir(parents=True)
            (old/'.release-id').write_text('a'*40)
            deploy.switch(root/'current',old)
            archive=root/'release.tar.gz'
            with tarfile.open(archive,'w:gz') as tar:
                info=tarfile.TarInfo('devops/scripts/server-runtime.py');info.size=4
                tar.addfile(info,io.BytesIO(b'pass'))
            activations=[]
            def command(args,**kwargs):
                if args[0]=='systemctl':
                    activations.append((root/'current').resolve())
                    if len(activations)==1:raise subprocess.CalledProcessError(1,args)
                return subprocess.CompletedProcess(args,0)
            with patch.object(deploy.subprocess,'run',side_effect=command),patch('sys.argv',['deploy','--archive',str(archive),'--sha','b'*40,'--root',str(root)]):
                with self.assertRaises(subprocess.CalledProcessError):deploy.main()
            self.assertEqual(activations,[root/'releases'/('b'*40),old])
            self.assertEqual((root/'current').resolve(),old)
            self.assertFalse((root/'state/deployments.json').exists())

    def test_dast_blocks_high_critical_and_rejects_missing_or_corrupt_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'findings.jsonl'
            with self.assertRaises(ValueError):dast.gate(report)
            report.write_text('');self.assertEqual(dast.gate(report),({},False))
            for severity,blocked in [('info',False),('medium',False),('high',True),('critical',True)]:
                report.write_text(json.dumps({'template-id':'test','info':{'severity':severity}})+'\n')
                self.assertEqual(dast.gate(report)[1],blocked)
            report.write_text('broken');
            with self.assertRaises(ValueError):dast.gate(report)

    def test_dast_does_not_publish_extracted_credentials_or_url_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            raw=Path(directory)/'raw';report=Path(directory)/'report'
            raw.write_text(json.dumps({'template-id':'exposure','info':{'severity':'high','name':'exposure'},
                'matched-at':'https://example.test/config?token=secret-token','extracted-results':['secret-password'],
                'response':'secret-body','curl-command':'Authorization: secret'}))
            dast.sanitize(raw,report)
            for value in ['secret-token','secret-password','secret-body','Authorization:']:self.assertNotIn(value,report.read_text())
            self.assertTrue(dast.gate(report)[1])

    def test_dast_requires_exact_origin(self):
        self.assertEqual(dast.target_url('https://example.test/'),'https://example.test')
        for url in ['file:///tmp/a','https://user:password@example.test','https://example.test/path','https://example.test?token=x']:
            with self.assertRaises(ValueError):dast.target_url(url)


if __name__=='__main__':unittest.main()
