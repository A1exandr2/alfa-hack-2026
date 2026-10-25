"""Package deployment sources and SOPS ciphertext; exclude all local/private artifacts."""
import hashlib
from pathlib import Path
import re
import tarfile

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'.local/deploy/credit-server.tar.gz'
TREES=['backend','frontend','ml','devops','docs','secrets']
FILES=['Makefile','README.md','.sops.yaml','.env.example','.dockerignore',
       'docker-compose.yml','docker-compose.gpu.yml']
EXCLUDE_PARTS={'.git','.local','.aws','node_modules','.next','__pycache__','.pytest_cache','.venv',
               'target','dist','build','coverage'}


def allowed(path):
    relative=path.relative_to(ROOT)
    if any(part in EXCLUDE_PARTS for part in relative.parts):return False
    if path.is_symlink() or path.name=='.env' or path.name.startswith('.env.') and path.name!='.env.example':return False
    if path.suffix in {'.log','.pyc','.agekey','.dump'}:return False
    if relative.parts[:2] in [('devops','runner'),('ml','artifacts')]:return False
    return path.is_file()


def main():
    paths=[ROOT/name for name in FILES]
    for tree in TREES:paths.extend((ROOT/tree).rglob('*'))
    paths=sorted(set(p for p in paths if allowed(p)))
    if not (ROOT/'secrets/server.enc.env').is_file():raise SystemExit('Encrypt the server configuration first')
    # Reject accidental current plaintext secrets even if a new source file was added to a tree.
    sensitive=[]
    env=ROOT/'.env'
    if env.exists():
        for line in env.read_text().splitlines():
            key,sep,value=line.partition('=')
            if sep and re.search('PASSWORD|SECRET|TOKEN|API_KEY',key) and len(value)>=8:
                sensitive.append(value.encode())
    for path in paths:
        content=path.read_bytes()
        if re.search(rb'AGE-SECRET-KEY-[A-Z0-9]+',content) or any(s in content for s in sensitive):
            raise SystemExit('Packaging refused: a source file contains plaintext key material')
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(OUTPUT,'w:gz') as archive:
        for path in paths:archive.add(path,arcname=str(path.relative_to(ROOT)),recursive=False)
    OUTPUT.chmod(0o600)
    checksum=hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    OUTPUT.with_suffix(OUTPUT.suffix+'.sha256').write_text(checksum+'  '+OUTPUT.name+'\n')
    print(f'Packaged {len(paths)} files: {OUTPUT}')
    print('Contains encrypted settings and public recipient; no .env or private age identity.')


if __name__=='__main__':main()
