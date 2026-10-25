import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('runtime', ROOT/'devops/scripts/server-runtime.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)


class RuntimeTests(unittest.TestCase):
    def test_memory_only_and_stale_environment_is_removed(self):
        payload=b'POSTGRES_PASSWORD=dummy-memory-password\nJWT_SECRET=dummy-jwt-secret\n'
        with patch.dict(os.environ,{'POSTGRES_PASSWORD':'stale','COMPOSE_FILE':'wrong.yml'}):
            r=runtime.Runtime(payload,'core')
        path=r.path
        try:
            self.assertEqual(Path(path).read_bytes(),payload)
            # A child process can read its parent's fd; no inheritance into Docker's plugin is required.
            self.assertEqual(subprocess.check_output(['cat',path]),payload)
            self.assertNotIn('POSTGRES_PASSWORD',r.environment)
            self.assertNotIn('COMPOSE_FILE',r.environment)
            self.assertEqual(r.environment['COMPOSE_DISABLE_ENV_FILE'],'1')
            self.assertNotIn('dummy-memory-password',' '.join(r.command))
        finally:r.close()
        self.assertFalse(Path(path).exists())

    def test_up_and_bootstrap_are_explicit_and_idempotent(self):
        r=runtime.Runtime(b'JWT_SECRET=dummy\n','cpu')
        try:
            calls=[]
            r.run=lambda args,**kw:calls.append(args)
            r.action('up')
            self.assertEqual(calls[0],['config','--quiet'])
            self.assertEqual(calls[1][:3],['up','-d','--build'])
            self.assertIn('--if-missing',calls[2])
            self.assertEqual(calls[3][:3],['exec','-T','ollama'])
        finally:r.close()

    def test_invalid_sops_payload_stops_before_any_docker_command(self):
        with patch.object(runtime.secrets,'decrypt',side_effect=SystemExit('Decryption failed')),patch.object(runtime.subprocess,'run') as docker,patch('sys.argv',['runtime','up']):
            with self.assertRaises(SystemExit):runtime.main()
            docker.assert_not_called()

    def test_actual_compose_reads_parent_memory_file(self):
        # Does not contact the Docker daemon or touch the running application.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'docker-compose.yml').write_text(json.dumps({'services':{'test':{'image':'postgres:16.10-alpine3.22','environment':{'SECRET':'${QA_VALUE}'}}}}))
            with patch.object(runtime,'ROOT',root):r=runtime.Runtime(b'QA_VALUE=dummy-from-memfd\n','core')
            try:
                result=subprocess.run(r.command+['config','--format','json'],env=r.environment,capture_output=True)
                self.assertEqual(result.returncode,0)
                self.assertEqual(json.loads(result.stdout)['services']['test']['environment']['SECRET'],'dummy-from-memfd')
                self.assertFalse((root/'.env').exists())
            finally:r.close()


if __name__=='__main__':unittest.main()
