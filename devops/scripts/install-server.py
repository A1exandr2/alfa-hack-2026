"""One-time production host setup; run on the rented server as root after installing age identity."""
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def main():
    if os.geteuid()!=0:raise SystemExit('Run as root on the production server')
    key=Path('/etc/credit/age/keys.txt')
    if not key.is_file():raise SystemExit('Install the private age identity at /etc/credit/age/keys.txt first')
    key.parent.chmod(0o700);key.chmod(0o600)
    for directory in ['/opt/credit/releases','/opt/credit/state']:
        Path(directory).mkdir(parents=True,exist_ok=True)
    units=ROOT/'devops/systemd'
    for source in units.glob('credit*'):
        if source.suffix in {'.service','.timer','.path'}:
            target=Path('/etc/systemd/system')/source.name
            shutil.copyfile(source,target);target.chmod(0o644)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    # CD applies complete releases; do not deploy half-copied files via the optional watcher.
    subprocess.run(['systemctl','disable','--now','credit-secrets.path'],check=True)
    subprocess.run(['systemctl','enable','credit.service'],check=True)
    subprocess.run(['systemctl','enable','--now','credit-image-cleanup.timer'],check=True)
    print('Host prepared. First CD deployment will activate /opt/credit/current and start the service.')


if __name__=='__main__':main()
