#!/usr/bin/env python3
"""Export an approved, committed package; never publish it."""
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote
from pdlc import ROOT, REQUIRED_REFS, read_json, ready_errors, inside

def export_package(item, root=ROOT):
    errors = ready_errors(item, root)
    if errors:
        raise ValueError('; '.join(errors))
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip():
        raise ValueError('Commit all PDLC changes before export to preserve provenance')
    destination = root / 'handoff/exports' / f"{item['id']}-r{item['revision']}-{commit[:12]}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError('Package exists; do not overwrite. Increment revision for a changed requirement.')
    # Include only explicit local supporting refs; no recursive inclusion of raw interviews.
    refs = [item['path']] + [item[k] for k in REQUIRED_REFS]
    refs += [a['ref'] for a in item['approvals'].values() if isinstance(a, dict)]
    files = set()
    external = []
    for ref in refs:
        if ref.startswith(('https://', 'http://')):
            external.append(ref)
            continue
        p = (root / unquote(ref.split('#')[0])).resolve()
        if not inside(p, root) or not p.is_file():
            raise ValueError(f'Invalid local reference: {ref}')
        if p.relative_to(root.resolve()).parts[:2] == ('evidence', 'extracted'):
            raise ValueError('Do not export raw evidence automatically; prepare a minimal approved QA/decision extract')
        files.add(p)
    claims = [c for c in read_json(root, 'knowledge/claims.json') if c['id'] in item['claim_ids']]
    src_ids = {c['source'] for c in claims}
    sources = [s for s in read_json(root, 'evidence/manifest.json') if s['id'] in src_ids]
    content = {str(p.relative_to(root.resolve())): p.read_bytes() for p in files}
    metadata = {'spec':item, 'pdlc_commit':commit, 'claims':claims, 'source_manifest':sources,
                'external_refs':external, 'sha256':{p:hashlib.sha256(b).hexdigest() for p,b in content.items()},
                'note':'Raw source texts are not bundled. Resolve other relative links in the PDLC repository at pdlc_commit.'}
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in sorted(content.items()):
            archive.writestr(path, data)
        archive.writestr('package.json', json.dumps(metadata, ensure_ascii=False, indent=2))
    return destination

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    matches = [s for s in read_json(ROOT, 'specs/register.json') if s['id'] == args.id]
    if len(matches) != 1:
        parser.error('Unknown or ambiguous spec ID')
    errors = ready_errors(matches[0])
    if errors:
        print('NOT READY:\n' + '\n'.join('- ' + e for e in errors))
        sys.exit(2)
    if args.check:
        print('Structural readiness passed; approvals and content must be reviewed by their owners.')
    else:
        try:
            print(export_package(matches[0]))
        except (ValueError, subprocess.CalledProcessError, FileNotFoundError) as error:
            print(str(error), file=sys.stderr)
            sys.exit(2)
