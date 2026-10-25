#!/usr/bin/env python3
"""Start the local vertical slice; stop all owned app processes on Ctrl-C."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if '--no-setup' not in sys.argv:
    subprocess.run([sys.executable, str(root/'scripts/setup-local.py')], check=True, cwd=root)
    subprocess.run(['docker', 'compose', 'up', '-d', 'postgres'], check=True, cwd=root)
    for attempt in range(60):
        result = subprocess.run(['docker', 'compose', 'exec', '-T', 'postgres', 'pg_isready', '-U', 'neuralops', '-d', 'neuralops'], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            break
        time.sleep(.5)
    else:
        raise SystemExit('PostgreSQL did not become ready.')
    subprocess.run(['uv', 'sync', '--directory', 'services', '--frozen'], check=True, cwd=root)
    if not (root/'web/node_modules').exists():
        subprocess.run(['npm', 'ci', '--prefix', 'web'], check=True, cwd=root)
    subprocess.run(['uv', 'run', '--directory', 'services', 'alembic', 'upgrade', 'head'], check=True, cwd=root)
commands = [
    ['uv', 'run', '--directory', 'services', 'uvicorn', 'neuralops.api:app', '--host', '127.0.0.1', '--port', '8000', '--no-access-log'],
    ['uv', 'run', '--directory', 'services', 'uvicorn', 'neuralops.telemetry:app', '--host', '127.0.0.1', '--port', '4318', '--no-access-log'],
    ['uv', 'run', '--directory', 'services', 'python', '-m', 'neuralops.worker'],
    ['npm', 'run', 'start' if '--production-web' in sys.argv else 'dev', '--prefix', 'web'],
]
processes = []
try:
    for command in commands:
        processes.append(subprocess.Popen(command, cwd=root, start_new_session=True))
    print('NeuralOps: http://localhost:3000 — explicit local development identity; remote execution disabled.', flush=True)
    while all(process.poll() is None for process in processes):
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    for process in reversed(processes):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
    print('Stopped owned application processes. PostgreSQL data preserved; use docker compose down to stop the database.')
