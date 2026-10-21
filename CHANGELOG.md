# Change log

Dates use Asia/Shanghai. This log records verified facts, not assumed end-to-end success.

## 2026-10-21 — VC-001 — Establish safe local version management

- Reason: the split project had no Git repository, remote, history, ignore rules or recovery points.
- Authorization: user confirmed local initialization, an independent branch and an initial safe commit. A project-specific GitHub URL has not been supplied.
- Files: `AGENTS.md`, `.gitignore`, `.env.example`, `README.md`, `CHANGELOG.md`; initial baseline will include the eight existing top-level Python modules, `API_Key_and_Tools/ensure_mcp_secret.py` and the existing dependency freeze snapshot.
- Changes: define task checks/commits, privacy boundaries, branch/push confirmation, explicit staging, changelog bookkeeping and safe recovery procedures. Preserve existing application sources, credentials, PDFs, model files and indexes.
- Existing source state: includes the earlier MCP context/time-window forwarding change. This baseline does not recreate history from before initialization and is not a stable-release certification.
- Data disposition: three PDFs (7,880,436 bytes), one CSV (102,056 bytes), model resources (410,192,970 bytes) and index assets (6,969,757 bytes) remain local pending explicit permission. No data was deleted or rebuilt.
- Initial inspection: no repository, branch, remote, commits, tracked files, `.gitignore`, README or project AGENTS file existed. Three credential-bearing env files were identified without displaying values. No exact known-secret matches or selected credential-pattern matches were found in 10 candidate Python/dependency files; this heuristic is not a comprehensive secret audit.
- Tests: `git diff --check` and `git diff --cached --check` passed; 9 staged Python files passed AST parsing; 15 explicitly staged files passed forbidden-path, 5 MiB size, known-secret and selected credential-pattern checks. `git check-ignore` confirmed private-file exclusions and source/template exceptions; `git ls-files -ci --exclude-standard` returned no paths. SHA-256 hashes of all 8 pre-existing top-level Python files are unchanged. No model/MCP/Redis end-to-end test was run; secret checking is heuristic, not a formal security guarantee.
- Repository: initialized after user confirmation on `chore/version-control-baseline`; no remote configured, no branch switch or merge performed.
- Task commit: `b5c5f0528a7929900f00e6abd893afe22ed77e85` — `chore: establish safe local version control baseline`.
- Ledger follow-up: records this baseline hash without changing application code; its own hash is available from Git history and the delivery report rather than recursively embedded here.
- Push: blocked — no user-confirmed project-specific GitHub URL. No remote configuration or upload authorized by inference.

## Entry template

- Task ID / date:
- Reason:
- Files:
- Changes:
- Tests and explicit failures/limitations:
- Task commit hash (or pending with reason):
- Push destination/status (or blocked reason):
