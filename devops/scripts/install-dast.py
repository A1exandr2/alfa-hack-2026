"""Install official pinned Nuclei and templates into an isolated, non-global directory."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[2]


def download(item):
    url=item['url']
    if not url.startswith(('https://github.com/','https://codeload.github.com/')):
        raise SystemExit('DAST downloads must use official GitHub HTTPS URLs')
    with urllib.request.urlopen(url,timeout=90) as response:data=response.read(250_000_000)  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- reviewed lock URL; HTTPS host allowlist and SHA-256 verification.
    if hashlib.sha256(data).hexdigest()!=item['sha256']:raise SystemExit('DAST download checksum mismatch')
    return data


def main():
    lock=json.loads((ROOT/'devops/dast/tools.lock.json').read_text())
    destination=Path(os.environ.get('NUCLEI_TOOLS_DIR',ROOT/'.local/dast'))
    destination.mkdir(parents=True,exist_ok=True)
    binary=download(lock['nuclei'])
    with zipfile.ZipFile(io.BytesIO(binary)) as archive:(destination/'nuclei').write_bytes(archive.read('nuclei'))
    (destination/'nuclei').chmod(0o755)
    templates=destination/'templates'
    if templates.exists():shutil.rmtree(templates)
    templates.mkdir()
    with tarfile.open(fileobj=io.BytesIO(download(lock['templates'])),mode='r:gz') as archive:
        for entry in archive:
            parts=Path(entry.name).parts[1:]
            if not parts or '..' in parts or Path(entry.name).is_absolute():continue
            target=templates.joinpath(*parts)
            if entry.isdir():target.mkdir(parents=True,exist_ok=True)
            elif entry.isfile():
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.extractfile(entry) as source,target.open('wb') as output:shutil.copyfileobj(source,output)
            else:raise SystemExit('Unsupported template archive entry')
    (destination/'tools.lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    print('Installed Nuclei '+lock['nuclei']['version']+' and official templates '+lock['templates']['version']+'; SHA-256 verified.')


if __name__=='__main__':main()
