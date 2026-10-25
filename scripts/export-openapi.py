"""Run from services via uv. No server or credentials are embedded in exported contracts."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services'))
from neuralops.api import app  # noqa: E402

root = Path(__file__).resolve().parents[1]
(root / 'packages/contracts/openapi.json').write_text(json.dumps(app.openapi(), indent=2) + '\n')
print('Exported control API schema.')
