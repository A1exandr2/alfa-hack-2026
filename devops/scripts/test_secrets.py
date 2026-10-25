"""Exercise encryption, integrity failure and safe provisioning in a temporary project."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2]


class SecretsTests(unittest.TestCase):
    def test_roundtrip_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            scripts=root/'devops/scripts';scripts.mkdir(parents=True)
            for name in ['sops-env.py','init-env.py']:
                shutil.copyfile(SOURCE/'devops/scripts'/name,scripts/name)
            shutil.copyfile(SOURCE/'.env.example',root/'.env.example')
            def run(script,*args,ok=True,env=None):
                result=subprocess.run(['python3',str(scripts/script),*args],cwd=root,capture_output=True,env=env)
                self.assertEqual(result.returncode==0,ok, result.stderr.decode())
                return result
            run('init-env.py')
            original=(root/'.env').read_bytes()
            self.assertNotIn(b'POSTGRES_PASSWORD=\n',original)
            self.assertNotIn(b'JWT_SECRET=\n',original)
            self.assertEqual((root/'.env').stat().st_mode & 0o777,0o600)
            run('init-env.py');self.assertEqual((root/'.env').read_bytes(),original)
            run('sops-env.py','key');run('sops-env.py','key',ok=False)
            run('sops-env.py','encrypt');run('sops-env.py','check')
            ciphertext=(root/'secrets/server.enc.env').read_bytes()
            secret=next(line.split(b'=',1)[1] for line in original.splitlines() if line.startswith(b'JWT_SECRET='))
            self.assertNotIn(secret,ciphertext)
            run('sops-env.py','decrypt',ok=False)
            (root/'.env').unlink()
            run('init-env.py',ok=False)
            run('sops-env.py','decrypt')
            def values(data):
                return dict(line.split(b'=',1) for line in data.splitlines() if b'=' in line and not line.startswith(b'#'))
            self.assertEqual(values((root/'.env').read_bytes()),values(original))
            # A different identity cannot decrypt the committed environment.
            wrong=root/'wrong.agekey'
            subprocess.run(['age-keygen','-o',str(wrong)],check=True,capture_output=True)
            env=os.environ.copy();env['SOPS_AGE_KEY_FILE']=str(wrong)
            env.pop('SOPS_AGE_KEY',None);env.pop('SOPS_AGE_KEY_CMD',None)
            run('sops-env.py','check',ok=False,env=env)
            # Valid file syntax with a modified encrypted MAC must fail integrity.
            lines=ciphertext.decode().splitlines()
            for i,line in enumerate(lines):
                if line.startswith('sops_mac=ENC['):
                    head,tail=line.split('data:',1)
                    lines[i]=head+'data:'+('A' if tail[0]!='A' else 'B')+tail[1:]
                    break
            else:self.fail('Encrypted MAC missing')
            (root/'secrets/server.enc.env').write_text('\n'.join(lines)+'\n')
            run('sops-env.py','check',ok=False)
            self.assertEqual(values((root/'.env').read_bytes()),values(original))

    def test_secret_set_preserves_values_and_does_not_create_server_env(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);scripts=root/'devops/scripts';scripts.mkdir(parents=True)
            for name in ['sops-env.py','init-env.py']:
                shutil.copyfile(SOURCE/'devops/scripts'/name,scripts/name)
            shutil.copyfile(SOURCE/'.env.example',root/'.env.example')
            def call(script,*args,data=None,ok=True):
                result=subprocess.run(['python3',str(scripts/script),*args],cwd=root,input=data,capture_output=True)
                self.assertEqual(result.returncode==0,ok,result.stderr.decode())
                return result
            call('init-env.py');call('sops-env.py','key');call('sops-env.py','encrypt')
            before=(root/'.env').read_bytes()
            value="dummy $NAME #tag 'quote' \\ trailing\\"
            result=call('sops-env.py','set','--name','QA_PASSWORD','--stdin',data=(value+'\n').encode())
            self.assertNotIn(value.encode(),result.stdout+result.stderr)
            self.assertNotIn(value.encode(),(root/'secrets/server.enc.env').read_bytes())
            self.assertIn(b'QA_PASSWORD=\n',(root/'.env.example').read_bytes())
            call('sops-env.py','check')
            after=(root/'.env').read_bytes()
            self.assertIn(next(l for l in before.splitlines() if l.startswith(b'JWT_SECRET=')),after)
            call('sops-env.py','set','--name','INVALID;NAME','--stdin',data=b'ignored',ok=False)
            self.assertEqual((root/'.env').read_bytes(),after)
            with (root/'.env').open('ab') as f:f.write(b'UNSAVED=value\n')
            encrypted_before=(root/'secrets/server.enc.env').read_bytes()
            call('sops-env.py','set','--name','QA_PASSWORD','--stdin',data=b'overwrite',ok=False)
            self.assertEqual((root/'secrets/server.enc.env').read_bytes(),encrypted_before)
            (root/'.env').unlink()
            call('sops-env.py','set','--name','QA_PASSWORD','--stdin',data=b'updated')
            self.assertFalse((root/'.env').exists())
            call('sops-env.py','check')

    def test_example_has_no_values(self):
        for line in (SOURCE/'.env.example').read_text().splitlines():
            if line and not line.lstrip().startswith('#') and '=' in line:
                self.assertEqual(line.partition('=')[2],'')


if __name__=='__main__':
    unittest.main()
