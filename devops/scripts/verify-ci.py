"""Require a successful CI run for the exact main commit, including manual deployment."""
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request,urlopen


def main():
    repository=os.environ['GITHUB_REPOSITORY'];sha=os.environ['RELEASE_SHA']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository) or not re.fullmatch('[0-9a-f]{40}',sha):raise SystemExit('Invalid repository or commit')
    query=urlencode({'head_sha':sha,'branch':'main','status':'completed','per_page':50})
    url=f'https://api.github.com/repos/{repository}/actions/workflows/ci.yml/runs?{query}'
    req=Request(url,headers={'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github+json'})
    with urlopen(req,timeout=30) as response:runs=json.load(response)['workflow_runs']  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- fixed api.github.com HTTPS endpoint; repository and SHA are validated.
    matching=[r for r in runs if r['head_sha']==sha and r['head_branch']=='main']
    if not matching or matching[0]['conclusion']!='success':raise SystemExit('The exact main commit has not passed CI; deployment refused')
    print('Exact main commit passed CI.')


if __name__=='__main__':main()
