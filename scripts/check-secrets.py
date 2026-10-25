"""Verify known local deployment secrets never occur in source or browser build artifacts.
This complements (and does not replace) pattern/entropy secret scanning.
"""
from pathlib import Path
import os

root = Path(__file__).resolve().parents[1]
values = {}
if (root/'.env').exists():
    for line in (root/'.env').read_text().splitlines():
        key, separator, value = line.partition('=')
        if separator and key in {'SESSION_SECRET', 'POSTGRES_PASSWORD', 'OIDC_CLIENT_SECRET'} and len(value) >= 16:
            values[key] = value.encode()
for key in {'SESSION_SECRET', 'POSTGRES_PASSWORD', 'OIDC_CLIENT_SECRET'}:
    value = os.environ.get(key, '')
    if len(value) >= 16:
        values[key + '_runtime'] = value.encode()
paths = [root/'web/.next/static', root/'web/components', root/'web/app', root/'services/neuralops', root/'docs']
count = 0
for folder in paths:
    for file in folder.rglob('*'):
        if not file.is_file() or '__pycache__' in file.parts:
            continue
        content = file.read_bytes()
        for key, value in values.items():
            if value in content:
                # Never include the matched value in output.
                raise SystemExit(f'Secret exposure detected: {key} in {file.relative_to(root)}')
        count += 1
print(f'Known-secret check passed across {count} source/browser files; no secret values printed.')
