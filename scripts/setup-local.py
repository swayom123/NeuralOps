#!/usr/bin/env python3
"""Generate local secrets without printing them. Never overwrites existing configuration."""
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / '.env'
if target.exists():
    print('.env already exists; preserved.')
else:
    password = secrets.token_urlsafe(32)
    content = f'''ENVIRONMENT=development
DEV_AUTH=true
PUBLIC_ORIGIN=http://localhost:3000
SESSION_SECRET={secrets.token_urlsafe(48)}
POSTGRES_PASSWORD={password}
DATABASE_URL=postgresql+psycopg://neuralops:{password}@127.0.0.1:15432/neuralops
API_INTERNAL_URL=http://127.0.0.1:8000
'''
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        file.write(content)
    print('Generated private .env for isolated local development.')
