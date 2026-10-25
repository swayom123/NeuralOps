# NeuralOps resume audit — 2026-10-25

## Repository evidence and preservation

All seven requested documents were read, alongside migrations, tests, runtime role policy and the relevant API/domain/frontend code. `git status --short` and `git log -8 --oneline` both returned “not a git repository”. No `.git` exists in this directory or its parents; recent commits, uncommitted diffs and exact authorship are unavailable. No repository was initialized and no changes were discarded. A pre-repair source snapshot is at `/tmp/neuralops-resume-before-repairs.tar.gz` (temporary local recovery artifact, excludes environment secrets).

File timestamps and source content suggest the previous work comprised:

- Phase 2 rule detail/patch/soft deletion, dedicated rule routes and incident notes; migration `d93e7f6fa321`, frontend reliability/console changes and tests.
- Phase 3 dataset lineage/description; migration `e74a81b2f093`; extended API/response schemas, replay graders, exports, repeat/contamination checks, submitted-code subprocess execution and `test_phase3.py`.
- Progress documentation still described most Phase 3 additions as absent. Generated OpenAPI/TypeScript had not incorporated all the new response contracts.

These are inferences, not verified agent attribution. Baseline executed: 45 backend tests passed, Ruff/ESLint/TypeScript passed. The successful sandbox tests did not establish hostile-code isolation.

## Confirmed repairs

1. The subprocess runner read a disposable synthetic worker file. It also lacked OS-enforced child-process/network isolation and bounded output capture. API, worker and runner now fail closed; submitted code cannot execute, including old queued execution jobs. No external actions were enabled.
2. Concurrent version publication used an unlocked maximum-version query. Publication now uses scoped transaction locks plus unique lineage/version and scoped parent constraints in new migration `f19a2b3c4d50`. Existing applied migrations, immutable datasets and hashes are preserved.
3. Missing latency/token measurements previously passed configured budgets; they now remain unknown, with null public results and INCONCLUSIVE decisions unless an explicit guardrail failure requires FAIL. The UI shows insufficient data and excludes unknown cases from regression/improvement filters.
4. Arbitrary grader names silently fell back to exact match; names are now allowlisted. Literal safety pattern lengths are bounded, strict JSON rejects NaN/Infinity, and deterministic replay rejects artificial repeats.
5. The original contamination heuristic treated absent inputs as the string “None” and guessed leakage from expected text in outputs. Checks now report repeated inputs/conflicting labels within the dataset; training/tuning overlap is explicitly unknown. Detected duplicates prevent an independent-sample PASS.
6. Exports now require an eligible role and finished run, preserve scope and audit access, and hash the exact typed public JSON. Recipients can reproduce the checksum after removing `report_checksum`.
7. Incident notes claimed append-only behavior without the database trigger. The additive migration adds it; production startup now requires RLS on all 20 protected tables including notes.

## Verification and handoff

See `VERIFICATION.md` for executed checks. A transient full-suite failure occurred while two pytest processes overlapped on the same test database; sequential rerun passed. The source scanner must run through the pinned services Python environment; system Python has no adjacent detect-secrets executable. New public Alembic revision strings are locally allowlisted as non-secret identifiers; scanning remains enabled.

The earliest incomplete milestone remains Phase 3. Safe offline multi-version replay and export work is repaired. Next implement an independently isolated runner with real per-run budgets and provenance, then expose dedicated dataset-version/evaluator UI workflows. Actual repeats, training/tuning overlap, monetary cost, production qualification and isolated remediation execution remain open. Preserve the current fail-closed execution boundaries. Existing Debian container findings were not rescanned or resolved by this source change.
