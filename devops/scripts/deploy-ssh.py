"""Deploy the already tested commit over pinned-host-key SSH; no SOPS identity in CI."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]


def main():
    host=os.environ['DEPLOY_HOST'];user=os.environ['DEPLOY_USER'];sha=os.environ['RELEASE_SHA']
    port=os.environ.get('DEPLOY_PORT','22')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+',host) or host.startswith('-'):raise SystemExit('Invalid deploy host')
    if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_-]*',user):raise SystemExit('Invalid deploy user')
    if not port.isdigit() or not 1<=int(port)<=65535:raise SystemExit('Invalid SSH port')
    if not re.fullmatch('[0-9a-f]{40}',sha):raise SystemExit('Invalid release SHA')
    # Root-only output is not needed: only temporary key files, never echo their values.
    with tempfile.TemporaryDirectory(prefix='credit-deploy-',dir=os.environ.get('RUNNER_TEMP')) as temporary:
        path=Path(temporary);key=path/'identity';known=path/'known_hosts'
        key.write_text(os.environ['DEPLOY_SSH_KEY'].rstrip()+'\n');key.chmod(0o600)
        known.write_text(os.environ['DEPLOY_KNOWN_HOSTS'].rstrip()+'\n');known.chmod(0o600)
        options=['-i',str(key),'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',
                 '-o','UserKnownHostsFile='+str(known),'-o','ConnectTimeout=20']
        transport_env=os.environ.copy()
        transport_env.pop('DEPLOY_SSH_KEY',None)
        transport_env.pop('DEPLOY_KNOWN_HOSTS',None)
        endpoint=user+'@'+host
        ssh=['ssh','-p',port,*options,endpoint]
        remote=subprocess.check_output(ssh+['mktemp -d /tmp/credit-deploy.XXXXXXXX'],text=True,env=transport_env).strip()
        if not re.fullmatch(r'/tmp/credit-deploy\.[A-Za-z0-9]+',remote):raise SystemExit('Invalid remote staging directory')
        scp_endpoint=user+'@'+('['+host+']' if ':' in host else host)
        try:
            subprocess.run(['scp','-P',port,*options,str(ROOT/'.local/deploy/credit-server.tar.gz'),
                            str(ROOT/'devops/scripts/deploy-release.py'),scp_endpoint+':'+remote+'/'],check=True,env=transport_env)
            command=([] if user=='root' else ['sudo','-n'])+['python3',remote+'/deploy-release.py','--archive',remote+'/credit-server.tar.gz','--sha',sha]
            subprocess.run(ssh+[shlex.join(command)],check=True,env=transport_env)
        finally:
            subprocess.run(ssh+['rm -rf -- '+shlex.quote(remote)],check=False,env=transport_env)


if __name__=='__main__':main()
