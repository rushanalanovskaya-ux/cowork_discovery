"""Dependency-free checks for the product knowledge contract."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_REFS = ('decision_ref', 'sdd_mapping_ref', 'estimate_ref', 'qa_plan_ref', 'ux_ref', 'metrics_ref', 'rollout_ref')

def inside(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False

def read_json(root, path):
    return json.loads((root / path).read_text(encoding='utf-8'))

def meaningful(value):
    return isinstance(value, str) and value.strip().lower() not in ('', 'tbd', 'todo', 'unknown', 'неизвестно', 'не назначен')

def valid_ref(root, value):
    if not meaningful(value):
        return False
    if value.startswith(('https://', 'http://')):
        from urllib.parse import urlparse
        p = urlparse(value)
        return bool(p.netloc) and '<' not in value and '>' not in value
    from urllib.parse import unquote
    p = (root / unquote(value.split('#')[0])).resolve()
    return inside(p, root) and p.is_file()

def ready_errors(item, root=ROOT):
    errors = []
    if type(item.get('security_required')) is not bool:
        errors.append('security_required must be explicitly true or false')
    if item.get('status') not in ('ready', 'in_sdd', 'delivered', 'validated'):
        errors.append('status is not ready or later')
    if not meaningful(item.get('owner')):
        errors.append('owner is missing')
    if item.get('blockers') != []:
        errors.append('blockers must be an empty list after resolution')
    if not valid_ref(root, item.get('sdd_url')) or not str(item.get('sdd_url')).startswith('https://'):
        errors.append('valid HTTPS sdd_url is missing')
    for key in REQUIRED_REFS:
        if not valid_ref(root, item.get(key)):
            errors.append(f'{key} is missing or unresolved')
    approvals = item.get('approvals', {})
    roles = ['product', 'engineering', 'qa'] + (['security'] if item.get('security_required') else [])
    for role in roles:
        a = approvals.get(role)
        if not isinstance(a, dict) or not meaningful(a.get('by')) or not valid_ref(root, a.get('ref')):
            errors.append(f'{role} approval requires by, date, and ref')
        else:
            from datetime import date
            try:
                date.fromisoformat(a.get('date', ''))
            except (TypeError, ValueError):
                errors.append(f'{role} approval date must be YYYY-MM-DD')
    return errors

def score(item):
    fields = ('reach', 'impact', 'confidence', 'effort_person_weeks')
    missing = [f for f in fields if item.get(f) is None]
    if missing:
        return None, 'missing: ' + ', '.join(missing)
    for key in fields:
        value = item[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None, f'invalid numeric value: {key}'
    if item['reach'] < 0 or item['impact'] not in (0.25, 0.5, 1, 2, 3) or not 0 <= item['confidence'] <= 1 or item['effort_person_weeks'] <= 0:
        return None, 'out-of-range scoring input'
    if not meaningful(item.get('score_evidence')):
        return None, 'missing score_evidence and common measurement horizon'
    return item['reach'] * item['impact'] * item['confidence'] / item['effort_person_weeks'], None
