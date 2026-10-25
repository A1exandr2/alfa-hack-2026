"""Linux server launcher: decrypt SOPS in memory and feed an explicit env-file to Compose."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('sops_env', ROOT / 'devops/scripts/sops-env.py')
secrets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(secrets)


def hidden_values(data):
    result=[]
    for key, value in secrets.values(data).items():
        if re.search('PASSWORD|SECRET|TOKEN|KEY|DATABASE_URL',key) and value:
            result.append(value)
            if value.startswith("'") and value.endswith("'"):
                result.append(value[1:-1].replace("\\'", "'").replace('\\\\','\\'))
            elif value.startswith('"') and value.endswith('"'):
                try: result.append(json.loads(value).replace('$$','$'))
                except (ValueError,TypeError): pass
    return sorted(set(result),key=len,reverse=True)


class Runtime:
    def __init__(self, data, mode='cpu'):
        if not hasattr(os, 'memfd_create') or not Path('/proc/self/fd').exists():
            raise SystemExit('Server runtime requires Linux with memfd and procfs')
        self.data=data
        self.mode=mode
        self.descriptor=os.memfd_create('credit-compose-env',os.MFD_CLOEXEC)
        os.write(self.descriptor,data)
        os.lseek(self.descriptor,0,os.SEEK_SET)
        self.path=f'/proc/{os.getpid()}/fd/{self.descriptor}'
        self.environment=os.environ.copy()
        for key in secrets.values(data):
            self.environment.pop(key,None)  # An exported stale password must not override SOPS.
        for key in ['COMPOSE_FILE','COMPOSE_PROFILES','COMPOSE_ENV_FILES']:
            self.environment.pop(key,None)
        self.environment['COMPOSE_DISABLE_ENV_FILE']='1'
        release_file=ROOT/'.release-id'
        if release_file.exists():
            release=release_file.read_text().strip()
            if not re.fullmatch('[0-9a-f]{40}',release):raise SystemExit('Invalid release identifier')
            self.environment['BACKEND_IMAGE']='credit-backend:'+release
        self.command=['docker','compose','--project-directory',str(ROOT),'--env-file',self.path,
                      '-f',str(ROOT/'docker-compose.yml')]
        if mode=='gpu':self.command+=['-f',str(ROOT/'docker-compose.gpu.yml')]
        if mode in {'cpu','gpu'}:self.command+=['--profile','llm']
        self.redactions=hidden_values(data)

    def close(self):
        os.close(self.descriptor)

    def run(self, arguments, *, quiet=False):
        # Keep the parent descriptor alive until Compose's CLI plugin finishes reading it.
        result=subprocess.run(self.command+arguments,cwd=ROOT,env=self.environment,
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        output=result.stdout.decode(errors='replace')
        for value in self.redactions:output=output.replace(value,'[REDACTED]')
        if output and (not quiet or result.returncode):print(output,end='',flush=True)
        if result.returncode:raise SystemExit(result.returncode)

    def action(self, action):
        self.run(['config','--quiet'],quiet=True)
        if action=='check':
            print('SOPS verified; Compose validated using memory only. No .env file was read or written.')
        elif action=='up':
            self.run(['up','-d','--build','--wait','--wait-timeout','180'])
            self.bootstrap()
            if self.mode in {'cpu','gpu'}:
                self.run(['exec','-T','ollama','sh','-ec','ollama pull "$OLLAMA_MODEL"'])
            print('Stack ready. SOPS configuration was passed to Compose from memory.')
        elif action=='bootstrap':self.bootstrap()
        elif action=='stop':self.run(['stop'])
        elif action=='status':self.run(['ps','-a'])
        elif action=='logs':self.run(['logs','--tail','100'])

    def bootstrap(self):
        self.run(['run','--rm','--no-deps','admin-bootstrap','python','-m','app.admin.bootstrap','--from-env','--if-missing'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['check','up','stop','status','logs','bootstrap'])
    parser.add_argument('--mode',choices=['core','cpu','gpu'],default=os.environ.get('CREDIT_DEPLOY_MODE','cpu'))
    args=parser.parse_args()
    source=Path(os.environ.get('CREDIT_SECRETS_FILE',secrets.ENCRYPTED))
    runtime=Runtime(secrets.decrypt(source),args.mode)
    try:runtime.action(args.action)
    finally:runtime.close()


if __name__=='__main__':main()
