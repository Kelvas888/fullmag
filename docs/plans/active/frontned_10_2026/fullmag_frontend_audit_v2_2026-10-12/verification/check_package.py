#!/usr/bin/env python3
"""Check package structure and manifest. Read-only, no application tests."""
from pathlib import Path
import argparse, collections, hashlib, json, re, sys
from urllib.parse import unquote, urlparse
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return Path(p).relative_to(ROOT).as_posix()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--structural',action='store_true',help='Skip manifest verification during packaging');args=ap.parse_args()
    errors=[];checked={};load=lambda name:json.loads((ROOT/name).read_text(encoding='utf-8'))
    f=load('findings.json');s=load('sources.json');b=load('backlog.json');t=load('tests.json')['tests'];q=load('review_traceability.json')
    for name,rows,count in [('findings',f,28),('sources',s,32),('pull_requests',b['pull_requests'],20),('tests',t,72),('questions',q,24)]:
        ids=[x['id'] for x in rows];checked[name]=len(rows)
        if len(rows)!=count or len(set(ids))!=count:errors.append(name+' count or duplicate ID')
    sourceids={x['id'] for x in s};testids={x['id'] for x in t};prids={x['id'] for x in b['pull_requests']}
    for x in f:
        if not set(x['sources'])<=sourceids:errors.append(x['id']+' source reference')
        if not set(x['pull_requests'])<=prids or not set(x['acceptance_tests'])<=testids:errors.append(x['id']+' task/test reference')
    for x in b['pull_requests']:
        if not set(x['depends_on'])<=prids or not set(x['tests'])<=testids:errors.append(x['id']+' dependency/test reference')
    # Check acyclic dependency graph, independently of document layout.
    graph={x['id']:x['depends_on'] for x in b['pull_requests']};done=set();active=set()
    def visit(i):
        if i in active:raise ValueError('PR dependency cycle at '+i)
        if i in done:return
        active.add(i)
        for dep in graph[i]:visit(dep)
        active.remove(i);done.add(i)
    try:
        for i in graph:visit(i)
    except ValueError as e:errors.append(str(e))
    for x in t:
        if not (ROOT/x['fixture']).is_file():errors.append(x['id']+' missing fixture')
        if not set(x['pull_requests'])<=prids:errors.append(x['id']+' PR reference')
        if x['status']!='planned_not_run':errors.append(x['id']+' misleading execution status')
    old={x['id']:x for x in load('historical/v1_findings.json')}
    for x in f:
        if any(x[key]!=old[x['id']][key] for key in ['priority','kind']):errors.append(x['id']+' historical class changed')
    checked['evidence_classes']=dict(collections.Counter(x['kind'] for x in f))
    h=load('historical/v1_manifest.json');hist=[x for x in h['files'] if x['path'].startswith('reproductions/')]
    for x in hist:
        p=ROOT/x['path']
        if not p.is_file() or sha(p)!=x['sha256']:errors.append('Historical reproduction changed: '+x['path'])
    checked['unchanged_historical_reproduction_files']=len(hist)
    checked['historical_manifest_sha256']=sha(ROOT/'historical/v1_manifest.json')
    # Check actual Markdown link targets, ignoring source code and historical quoted text.
    local_links=0
    for p in [ROOT/'README.md',*(ROOT/'docs').glob('*.md'),ROOT/'verification/README.md']:
        text=re.sub(r'```.*?```','',p.read_text(encoding='utf-8'),flags=re.S)
        for url in re.findall(r'!?\[[^\]\n]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)',text):
            if url.startswith(('#','http:','https:','mailto:','data:')):continue
            target=(p.parent/unquote(url.split('#')[0])).resolve();local_links+=1
            if not target.is_file():errors.append(f'Missing link in {rel(p)}: {url}')
    checked['local_markdown_links']=local_links
    contract=load('state_contracts.json');diagram=(ROOT/'diagrams/02_edit_state_machine.dot').read_text(encoding='utf-8');d04=next((ROOT/'docs').glob('04_*.md')).read_text(encoding='utf-8')
    for phase in contract['object_edit_phases']:
        if phase not in diagram or phase not in d04:errors.append('State missing: '+phase)
    checked['transition_rows']=len(contract['object_edit_transitions'])
    checked['markdown_documents']=len(list((ROOT/'docs').glob('*.md')))
    checked['ui_mockups']=len(list((ROOT/'mockups').glob('*.svg')))
    checked['system_diagrams']=len(list((ROOT/'diagrams').glob('*.dot')))
    for p in ROOT.rglob('*.json'):
        try:json.loads(p.read_text(encoding='utf-8'))
        except Exception as e:errors.append(rel(p)+': '+str(e))
    if not args.structural:
        manifest=load('manifest.json');entries=manifest['files'];checked['manifest_entries']=len(entries)
        actual={rel(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in rel(p)}
        expected={x['path'] for x in entries}
        if actual!=expected:errors.append('Manifest inventory mismatch: '+str(sorted(actual^expected)))
        for x in entries:
            p=ROOT/x['path']
            if not p.is_file() or sha(p)!=x['sha256']:errors.append('Manifest hash mismatch: '+x['path'])
    report={'scope':'document package checks, not Fullmag qualification','mode':'structural_before_manifest' if args.structural else 'full_manifest','status':'pass' if not errors else 'failed','checked':checked,'errors':errors}
    print(json.dumps(report,ensure_ascii=False,indent=2));return int(bool(errors))
if __name__=='__main__':sys.exit(main())
