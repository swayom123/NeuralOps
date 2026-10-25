"""Run the pinned source scanner without sending candidate secrets to verification services."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
excluded = r'(^|/)(node_modules|\.venv|\.venv312|\.next|__pycache__|\.pytest_cache|\.ruff_cache|artifacts|test-results|playwright-report|graphify-out)/|(^|/)\.env$|\.tsbuildinfo$|package-lock\.json$|uv\.lock$|generated\.ts$|openapi\.json$'
candidate_scanner = Path(sys.executable).parent / 'detect-secrets'
if candidate_scanner.exists():
    scanner = candidate_scanner
elif shutil.which('detect-secrets'):
    scanner = Path(shutil.which('detect-secrets'))
elif (root / 'services/.venv312/bin/detect-secrets').exists():
    scanner = root / 'services/.venv312/bin/detect-secrets'
elif (root / 'services/.venv/bin/detect-secrets').exists():
    scanner = root / 'services/.venv/bin/detect-secrets'
else:
    scanner = candidate_scanner
result = subprocess.run([str(scanner), 'scan', '--all-files', '--no-verify', '--exclude-files', excluded, str(root)],
                         cwd=root, check=True, capture_output=True, text=True)
report = json.loads(result.stdout)
(root/'artifacts').mkdir(exist_ok=True)
(root/'artifacts/secrets-baseline.json').write_text(result.stdout)
findings = [(path, entry['line_number'], entry['type']) for path, entries in report['results'].items() for entry in entries]
if findings:
    for path, line, kind in findings:
        print(f'Review secret candidate: {path}:{line} ({kind}); matched value withheld.')
    raise SystemExit(1)
print('Source secret scan passed. Generated caches, dependency locks, schema output, ignored local .env and QA artifacts excluded; no candidate values sent over network.')
