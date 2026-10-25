# Contributing to NeuralOps

Thank you for your interest in contributing to **NeuralOps**! NeuralOps is an AI reliability control plane designed with deterministic evidence localization, multi-tenant database isolation, and rigorous security verification.

We welcome contributions from engineers of all backgrounds. Please review this guide before submitting code or proposing architectural changes.

---

## 1. Core Architectural Principles

When writing code or designing features for NeuralOps, follow these principles:

1. **Deterministic Over Probabilistic Where Feasible:** Telemetry attribution, critical paths, error budget burns, and evaluation metrics use deterministic algorithms (e.g., Hoeffding bounds, exact-match scoring) rather than unconstrained LLM heuristics.
2. **Metadata-Only by Default:** Prompts, completions, tool inputs/outputs, HTTP headers, and raw exception payloads are stripped before database persistence. Never log or persist customer payload data.
3. **Least-Privilege Isolation:** All database tables use composite `(organization_id, project_id)` keys with PostgreSQL Row-Level Security (RLS). Production services use dedicated non-login role grants (`neuralops_api`, `neuralops_ingest`, `neuralops_worker`).
4. **No Ambient Remediation Authority:** Automated actions fail closed. Proposals are immutable and cannot execute without verified approval, health-check criteria, and rollback adapters.
5. **No Secret Exposure:** Secrets are managed via environment variables or secret managers. Never commit secrets, test tokens, or private `.env` files.

---

## 2. Prerequisites & Local Environment

Ensure you have the following installed locally:
- **Node.js**: v22+ and `npm`
- **Python**: v3.12+
- **uv**: Fast Python package manager (`pip install uv` or via installer)
- **Docker & Docker Compose**: For running PostgreSQL 17 and containerized services

---

## 3. Getting Started

### 3.1 Initial Setup

Clone the repository and initialize the development environment:

```bash
git clone https://github.com/swayom123/NeuralOps.git
cd NeuralOps

# Setup virtual environment, npm dependencies, and generate local .env
make setup
```

The `setup` script generates an ignored `.env` with cryptographically secure random session and database secrets. It never prints secrets to the console.

### 3.2 Running Development Services

Start the development stack:

```bash
make dev
```

This command:
1. Starts the isolated PostgreSQL 17 container on `127.0.0.1:15432`.
2. Applies all Alembic database migrations.
3. Concurrently launches the FastAPI control API (`:8000`), OTLP ingestion gateway (`:4318`), background worker, and Next.js frontend (`:3000`).

Open your browser to [http://localhost:3000](http://localhost:3000).

*(Note: Use `http://localhost:3000` rather than `127.0.0.1:3000` to ensure strict CSRF origin verification succeeds.)*

---

## 4. Quality & Security Verification Gates

Every pull request must pass the automated verification suite before merging. Run the checks locally with:

```bash
# Run linting, unit tests, typechecks, and frontend build
make check
```

Under the hood, this executes:
- **Python Linting:** `uv run --directory services ruff check neuralops tests migrations`
- **Backend Tests:** `uv run --directory services pytest -q`
- **Web Linting:** `npm run lint --prefix web`
- **Web Typecheck:** `npm run typecheck --prefix web`
- **Web Production Build:** `npm run build --prefix web`

### Additional Security and Contract Audits

Before submitting a pull request, also run:

```bash
# Static security analysis
uv run --directory services bandit -r neuralops -ll

# Dependency vulnerability scanning
uv run --directory services pip-audit --local
npm audit --prefix web --audit-level=low

# Secret leakage scanners
uv run --directory services python ../scripts/scan-secrets.py
python3 scripts/check-secrets.py

# End-to-end browser & accessibility tests (requires running app stack)
npm run test:e2e --prefix web
```

### Contract Synchronization

If you modify Pydantic schemas in `services/neuralops/schemas.py`:

```bash
make contracts
```

This exports `packages/contracts/openapi.json` and updates `web/lib/generated.ts`. Commit both files together.

---

## 5. Development Workflow & Pull Requests

1. **Create a Branch:** Name your branch clearly (e.g., `feat/incident-retention-policy` or `fix/otlp-span-dedup`).
2. **Make Focused Changes:** Keep changes atomic, readable, and well-tested.
3. **Write Tests:** Add unit/integration tests under `services/tests/` or end-to-end tests under `web/tests/`.
4. **Follow Architecture Records:** If making a major architectural change, document an Architectural Decision Record (ADR) in `REASON.md`.
5. **Verify Clean Git Status:** Ensure no unwanted build artifacts, temporary logs, or credentials are added.
6. **Submit PR:** Write a concise description explaining what was changed, why, and how it was verified.

---

## 6. Security Vulnerabilities

Please **do not** create public GitHub issues for security vulnerabilities. Follow the responsible disclosure guidelines in [.github/SECURITY.md](.github/SECURITY.md).
