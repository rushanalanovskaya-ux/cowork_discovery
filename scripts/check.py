#!/usr/bin/env python3
"""Validate internal references and handoff readiness; does not verify product claims."""
import re
import sys
from urllib.parse import unquote
from pdlc import ROOT, read_json, ready_errors, score, inside

def validate(root=ROOT):
    errors = []
    sources = read_json(root, 'evidence/manifest.json')
    claims = read_json(root, 'knowledge/claims.json')
    items = read_json(root, 'backlog/items.json')
    specs = read_json(root, 'specs/register.json')
    for name, records in [('source', sources), ('claim', claims), ('MVP', items), ('spec', specs)]:
        ids = [x['id'] for x in records]
        if len(ids) != len(set(ids)):
            errors.append(f'duplicate {name} ID')
    source_ids = {x['id'] for x in sources}
    claim_ids = {x['id'] for x in claims}
    item_ids = {x['id'] for x in items}
    for s in sources:
        if not (root / s['extraction']).is_file():
            errors.append(f"{s['id']}: extraction file missing")
        if not re.fullmatch(r'[0-9a-f]{64}', s['sha256']):
            errors.append(f"{s['id']}: invalid source SHA256")
    for c in claims:
        if c['source'] not in source_ids or not c.get('locator') or not c.get('limitation'):
            errors.append(f"{c['id']}: incomplete provenance")
        if c['source'] == 'SRC-034':
            errors.append(f"{c['id']}: unread OCR source cannot support a claim")
    for i in items:
        if i['source'] not in source_ids or not (root / 'backlog/items' / (i['id'] + '.md')).is_file():
            errors.append(f"{i['id']}: missing source/card")
        fields = ('reach', 'impact', 'confidence', 'effort_person_weeks')
        # Validate filled values even if another input is still missing.
        for field in fields:
            if i.get(field) is not None:
                probe = dict(reach=1, impact=1, confidence=1, effort_person_weeks=1, score_evidence='validation')
                probe[field] = i[field]
                if score(probe)[1]:
                    errors.append(f"{i['id']}: invalid {field}")
        if all(i.get(f) is not None for f in fields) and score(i)[1]:
            errors.append(f"{i['id']}: {score(i)[1]}")
    allowed = {'shaping', 'ready', 'in_sdd', 'delivered', 'validated', 'stopped', 'superseded'}
    for s in specs:
        if not set(s['mvp_ids']) <= item_ids or not set(s['claim_ids']) <= claim_ids:
            errors.append(f"{s['id']}: invalid traceability IDs")
        if not (root / s['path']).is_file() or s.get('status') not in allowed:
            errors.append(f"{s['id']}: missing file or invalid status")
        if type(s.get('revision')) is not int or s['revision'] < 1:
            errors.append(f"{s['id']}: invalid revision")
        if s['status'] in ('ready', 'in_sdd', 'delivered', 'validated'):
            errors.extend(f"{s['id']}: {e}" for e in ready_errors(s, root))
    # Historical extracts can contain broken original links. Check authored knowledge only.
    for p in root.rglob('*.md'):
        rel = p.relative_to(root)
        if rel.parts[:2] == ('evidence', 'extracted') or rel.parts[:2] == ('handoff', 'exports'):
            continue
        body = re.sub(r'```.*?```', '', p.read_text(encoding='utf-8'), flags=re.S)
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', body):
            if target.startswith(('https://', 'http://', 'mailto:', '#')):
                continue
            target = unquote(target.split('#')[0].strip('<>'))
            resolved = (p.parent / target).resolve()
            if not inside(resolved, root) or not resolved.exists():
                errors.append(f'{rel}: broken or escaping link {target}')
    return errors, (len(sources), len(claims), len(items), len(specs))

if __name__ == '__main__':
    errors, counts = validate()
    if errors:
        print('\n'.join('ERROR: ' + e for e in errors))
        sys.exit(1)
    print('OK: %s sources, %s claims, %s backlog items, %s specs; links and structural gates valid.' % counts)
    print('Product approval, source truth and implementation are not verified by this check.')
