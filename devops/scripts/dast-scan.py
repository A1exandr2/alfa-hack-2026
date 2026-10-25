"""Post-deploy HTTP Nuclei scan, report export and explicit High/Critical gate."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler,build_opener

ROOT=Path(__file__).resolve().parents[2]
EXCLUDE='dos,fuzz,bruteforce,headless,code,intrusive'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def target_url(value):
    parsed=urlsplit(value)
    if parsed.scheme not in {'https','http'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'','/'}:
        raise ValueError('Use the exact public site origin, without credentials, path, query or fragment')
    return value.rstrip('/')


def ready(target):
    # Also validates TLS. Do not follow a redirect to a different site.
    with build_opener(NoRedirect()).open(target+'/api/v1/ready',timeout=20) as response:
        data=json.load(response)
    if data.get('status')!='ok' or data.get('service')!='backend':raise RuntimeError('Deployment readiness failed')


def gate(path):
    if not path.exists():raise ValueError('Nuclei report is missing')
    severities=Counter()
    for line in path.read_text().splitlines():
        if not line.strip():continue
        item=json.loads(line)
        if not isinstance(item,dict) or not item.get('template-id'):raise ValueError('Invalid Nuclei report entry')
        severity=item.get('info',{}).get('severity','unknown').lower()
        severities[severity]+=1
    return dict(severities),bool(severities['high'] or severities['critical'])


def sanitize(raw, report):
    findings=[]
    if raw.exists():
        for line in raw.read_text().splitlines():
            if not line.strip():continue
            item=json.loads(line)
            # Do not publish extracted values, responses, cookies or curl commands as artifacts.
            url=urlsplit(item.get('matched-at',''))
            matched=url._replace(query='',fragment='',netloc=url.hostname or '').geturl()
            findings.append({'template-id':item.get('template-id'),
                'info':{'name':item.get('info',{}).get('name'),'severity':item.get('info',{}).get('severity','unknown')},
                'matched-at':matched})
    report.write_text(''.join(json.dumps(item)+'\n' for item in findings))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',default=os.environ.get('PRODUCTION_URL'),required=not bool(os.environ.get('PRODUCTION_URL')))
    parser.add_argument('--tools',type=Path,default=Path(os.environ.get('NUCLEI_TOOLS_DIR',ROOT/'.local/dast')))
    parser.add_argument('--output',type=Path,default=ROOT/'.local/dast-report')
    args=parser.parse_args()
    target=target_url(args.target)
    ready(target)
    args.output.mkdir(parents=True,exist_ok=True)
    config=args.output/'config';config.mkdir(exist_ok=True)
    cache=args.output/'cache';cache.mkdir(exist_ok=True)
    env=os.environ.copy();env['XDG_CONFIG_HOME']=str(config.resolve());env['XDG_CACHE_HOME']=str(cache.resolve())
    # Only the pinned, signed official HTTP templates; no code/headless/OAST/fuzzing.
    common=[str((args.tools/'nuclei').resolve()),'-duc','-no-stdin','-no-color','-dut',
            '-t',str((args.tools/'templates/http').resolve()),'-type','http','-etags',EXCLUDE]
    listed=subprocess.run(common+['-tl','-silent'],env=env,capture_output=True,text=True,timeout=180)
    if listed.returncode:raise SystemExit('Nuclei template loading failed')
    count=sum(1 for line in listed.stdout.splitlines() if line.strip().endswith(('.yaml','.yml')))
    if count<1000:raise SystemExit('Insufficient official HTTP templates loaded; refusing an empty scan')
    result=args.output/'findings.jsonl'
    raw=args.output/'.raw-findings.jsonl'
    raw.write_text('');raw.chmod(0o600)
    command=common+['-u',target,'-dr','-ni','-or','-ot','-jsonl','-o',str(raw.resolve()),
                    '-rl','15','-c','4','-timeout','8','-retries','1']
    try:
        with (args.output/'scanner.log').open('w') as log:
            try:scan=subprocess.run(command,env=env,stdout=subprocess.DEVNULL,stderr=log,timeout=1800)
            except subprocess.TimeoutExpired:raise SystemExit('Nuclei scan timed out; result is incomplete') from None
        sanitize(raw,result)
    finally:raw.unlink(missing_ok=True)
    if scan.returncode:raise SystemExit('Nuclei execution failed; inspect scanner.log')
    ready(target)
    counts,blocked=gate(result)
    summary={'target':target,'official_http_templates':count,'severities':counts,'blocked':blocked,
             'tool_versions':json.loads((args.tools/'tools.lock.json').read_text())}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(f'Nuclei completed with {count} official HTTP templates; findings by severity: {counts}')
    if blocked:raise SystemExit('DAST blocked: High/Critical vulnerabilities detected')


if __name__=='__main__':main()
