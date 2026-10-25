"""Server-side immutable release activation with health checks and application rollback."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from urllib.request import Request, urlopen


def unpack(archive,destination):
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            parts=Path(member.name).parts
            if not parts or Path(member.name).is_absolute() or '..' in parts or not member.isfile():
                raise ValueError('Unsafe archive entry')
            if '.env' in parts or '.local' in parts or '.git' in parts or '.aws' in parts or member.name.endswith('/keys.txt'):
                raise ValueError('Private artifact in release archive')
            target=destination/member.name
            target.parent.mkdir(parents=True,exist_ok=True)
            with tar.extractfile(member) as source,target.open('xb') as output:shutil.copyfileobj(source,output)
            target.chmod(0o644)


def switch(link,target):
    temporary=link.with_name(link.name+'.next')
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target,target_is_directory=True)
    os.replace(temporary,link)


def run(args):
    subprocess.run(args,check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--sha',required=True)
    parser.add_argument('--root',type=Path,default=Path('/opt/credit'))
    args=parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}',args.sha):raise SystemExit('Invalid release SHA')
    root=args.root
    (root/'state').mkdir(parents=True,exist_ok=True,mode=0o700)
    with (root/'state/deploy.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        release=root/'releases'/args.sha
        release.parent.mkdir(parents=True,exist_ok=True)
        if not release.exists():
            staging=Path(tempfile.mkdtemp(prefix='.staging-',dir=release.parent))
            try:
                unpack(args.archive,staging)
                (staging/'.release-id').write_text(args.sha+'\n')
                os.replace(staging,release)
            finally:
                if staging.exists():shutil.rmtree(staging)
        elif (release/'.release-id').read_text().strip()!=args.sha:
            raise SystemExit('Existing release does not match its identifier')
        key=Path(os.environ.get('SOPS_AGE_KEY_FILE','/etc/credit/age/keys.txt'))
        environment=os.environ.copy();environment['SOPS_AGE_KEY_FILE']=str(key)
        # Verify decryption and Compose before changing the active release.
        subprocess.run(['python3',str(release/'devops/scripts/server-runtime.py'),'check'],check=True,env=environment)
        current=root/'current'
        old=current.resolve() if current.is_symlink() else None
        if current.exists() and not current.is_symlink():raise SystemExit('current must be a symlink')
        switch(current,release)
        try:
            run(['systemctl','reload-or-restart','credit.service'])
            # Runtime up already waits for all container healthchecks.
            if old and old!=release:switch(root/'previous',old)
            state=root/'state/deployments.json'
            history=json.loads(state.read_text()) if state.exists() else []
            if not history or history[-1]['sha']!=args.sha:
                history.append({'sha':args.sha,'deployed_at':datetime.now(timezone.utc).isoformat()})
            temporary=state.with_suffix('.tmp');temporary.write_text(json.dumps(history[-100:],indent=2)+'\n');temporary.chmod(0o600);os.replace(temporary,state)
        except Exception:
            if old and old!=release:
                switch(current,old)
                run(['systemctl','reload-or-restart','credit.service'])
                print('Previous application release restored. Database migrations were not downgraded.')
            raise
        # A cleanup failure must not trigger application rollback after a healthy deployment.
        run(['python3',str(release/'devops/scripts/cleanup-images.py'),'--root',str(root),'--apply'])
        print('Deployment activated: '+args.sha)


if __name__=='__main__':main()
