"""Disposable local PostgreSQL restore drill. Source is explicitly neuralops_test only.
The dump stays in process memory; no unencrypted backup is written to disk.
"""
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'services'))
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from neuralops.config import settings  # noqa: E402

root = Path(__file__).resolve().parents[1]
url = make_url(settings().database_url)
if url.host not in {'localhost', '127.0.0.1'} or settings().environment == 'production':
    raise SystemExit('Restore drill is local-only and refuses production.')
source = create_engine(url.set(database='neuralops_test'))
admin = create_engine(url.set(database='postgres'), isolation_level='AUTOCOMMIT')
target_name = 'neuralops_restore_' + uuid4().hex[:12]
command = ['docker', 'compose', 'exec', '-T', 'postgres']
created = False
try:
    dump = subprocess.run(command+['pg_dump', '-U', 'neuralops', '-d', 'neuralops_test', '-Fc'], cwd=root, check=True, capture_output=True).stdout
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE {target_name}'))
    created = True
    subprocess.run(command+['pg_restore', '-U', 'neuralops', '-d', target_name, '--no-owner', '--no-privileges', '--exit-on-error'],
                   input=dump, cwd=root, check=True, capture_output=True)
    restored = create_engine(url.set(database=target_name))
    tables = ['spans','traces','incidents','datasets','evaluations','audit_events','expired_traces']
    with source.connect() as before, restored.connect() as after:
        counts = {table: before.scalar(text(f'SELECT count(*) FROM {table}')) for table in tables}
        assert counts == {table: after.scalar(text(f'SELECT count(*) FROM {table}')) for table in tables}
        assert before.execute(text('SELECT id, manifest_hash FROM datasets ORDER BY id')).all() == after.execute(text('SELECT id, manifest_hash FROM datasets ORDER BY id')).all()
    restored.dispose()
    print('Disposable PostgreSQL restore passed: seven table counts and immutable dataset hashes matched. Test source preserved.')
finally:
    source.dispose()
    if created:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE {target_name} WITH (FORCE)'))
    admin.dispose()
