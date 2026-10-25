"""Delete only old release images belonging to Credit; never prune volumes or other projects."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess

TAG=re.compile(r'^credit-backend:([0-9a-f]{40})$')


def candidates(images, active_ids, keep_shas, now, minimum_age_hours=24):
    cutoff=now-timedelta(hours=minimum_age_hours)
    remove=[]
    for image in images:
        if image.get('Config',{}).get('Labels',{}).get('io.credit.project')!='credit':continue
        if image['Id'] in active_ids:continue
        created=datetime.fromisoformat(image['Created'].replace('Z','+00:00'))
        if created>=cutoff:continue
        for tag in image.get('RepoTags') or []:
            match=TAG.fullmatch(tag)
            if match and match[1] not in keep_shas:remove.append(tag)
    return sorted(set(remove))


def output(args):
    return subprocess.check_output(args,text=True).strip()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/opt/credit'))
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--keep',type=int,default=3)
    parser.add_argument('--minimum-age-hours',type=int,default=24)
    args=parser.parse_args()
    if args.keep<2 or args.minimum_age_hours<1:raise SystemExit('Keep at least current+previous and a minimum age of one hour')
    state=args.root/'state/deployments.json'
    if not state.exists():raise SystemExit('Deployment state is missing; cleanup refused')
    history=json.loads(state.read_text())
    keep={e['sha'] for e in history[-args.keep:]}
    for link in ['current','previous']:
        marker=args.root/link/'.release-id'
        if marker.exists():keep.add(marker.read_text().strip())
    ids=output(['docker','image','ls','--filter','label=io.credit.project=credit','--quiet','--no-trunc']).splitlines()
    if not ids:
        print('No managed images to clean.');return
    images=json.loads(output(['docker','image','inspect',*sorted(set(ids))]))
    containers=output(['docker','ps','--all','--quiet']).splitlines()
    active=set()
    if containers:
        active={c['Image'] for c in json.loads(output(['docker','container','inspect',*containers]))}
    remove=candidates(images,active,keep,datetime.now(timezone.utc),args.minimum_age_hours)
    print(f'Protected {len(keep)} release versions; eligible old images: {len(remove)}.')
    for tag in remove:
        if args.apply:
            # No --force: Docker also protects any image still referenced by a container.
            subprocess.run(['docker','image','rm',tag],check=True)
        else:print('Would remove '+tag)
    if args.apply:
        subprocess.run(['docker','image','prune','--force','--filter','label=io.credit.project=credit',
                        '--filter',f'until={args.minimum_age_hours}h'],check=True)


if __name__=='__main__':main()
