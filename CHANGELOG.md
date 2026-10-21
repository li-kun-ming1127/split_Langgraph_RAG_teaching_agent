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

## 2026-10-21 — VC-002 — Connect verified GitHub remote and publish baseline

- Reason: user supplied and explicitly approved the split-project GitHub destination and requested publication of the existing baseline.
- Destination: `https://github.com/li-kun-ming1127/split_Langgraph_RAG_teaching_agent.git`, remote `origin`, branch `chore/version-control-baseline`.
- Preflight: clean worktree, no prior remote, exact original two commits retained; `git ls-remote --symref` succeeded with no remote refs before the first push. No unrelated remote history was found.
- Files: only `CHANGELOG.md` changes in this follow-up; remote configuration is local Git metadata. The published tree contains the 15 previously reviewed source/configuration/documentation/dependency files.
- Security checks: scanned every file and commit message in both original revisions for known local credential values and selected API key, token, private-key and credential-URL patterns. No matches found. All on-disk env credentials, data files, model resources and generated index files are ignored; none appear in either historical tree. No ignored file is tracked. No dedicated secret scanner is installed, so this is a heuristic review, not an absolute security guarantee.
- Tests: both diffs passed whitespace checks; all 9 Python files parsed in both revisions. No application runtime test or private-data model call was made. No business code, local credentials, PDFs, models or indexes were changed.
- Published baseline: `e00e563861f5b6a72be359859ef7c041d71b15cb`, retaining ancestor `b5c5f0528a7929900f00e6abd893afe22ed77e85` without rewriting either commit.
- Push: confirmed — `git push -u origin chore/version-control-baseline` succeeded, tracking was configured, and a fresh remote query matched the published baseline hash. This resolves the VC-001 missing-remote blocker.
- Ledger follow-up: this documentation-only commit records the already confirmed baseline publication. Its own hash and separate push result are reported at delivery and discoverable in Git history; no self-referential amendment is used.

## 2026-10-21 — VC-003 — Consolidate long-term Git/GitHub management policy

- Goal: integrate the user's current safety/branch/testing/recovery rules with the existing documents, using 《Git和GitHub管理代码的方式》 as reference material rather than executing its old-project examples.
- Starting state: clean worktree on related branch `chore/version-control-baseline`, starting commit `34c17efae8974e22d6568c92235e0d66cc27e5e2`. `origin` matches the project URL. A fresh `git ls-remote --symref origin` matched that hash; no remote `main` or divergent history was present.
- Visibility: GitHub repository metadata reported `public` on 2026-10-21. No explicit public-publication approval has been given for this task; no push or visibility change will be performed. Previously published commits remain remote/public.
- Files/modules: only `AGENTS.md`, `README.md`, `.gitignore`, `CHANGELOG.md`; no business module, dependency, private data, model or index changes intended.
- Changes: retain single-Agent/module/filename boundaries; add exact preflight checks, branch naming and latest-main rules, visibility/history/merge/tag gates, precise validation and state reporting. Preserve existing recovery guidance and prior log entries. Ignore tox/nox environments and Streamlit secret backup variants while retaining sanitized example support.
- Tests: `git diff --check` passed; `git diff --stat`/`git diff --name-only` confirmed exactly four management files changed; `git ls-files -ci --exclude-standard` was empty. `git check-ignore --stdin -z` regression assertions passed for all 226 local credential/data/model/index files and the new tox/nox/secret-backup cases; `git check-ignore -q` confirmed source, dependency and sanitized-example exceptions. Python stdin checks with the existing Python 3.12 interpreter parsed all 9 tracked Python files, verified required policy clauses and scanned all 3 existing revisions plus the four edited files for known local secrets/selected credential patterns (no matches). PowerShell `Get-FileHash -Algorithm SHA256` confirmed all 8 existing top-level source files unchanged. These are heuristic security checks, not a dedicated scanner or formal guarantee.
- Not run: application module imports and MCP/Redis/RAG/UI/model integration tests; this is a management-document-only task and runtime imports/calls can initialize services or require private credentials. DOCX rendering not run: only reference text was extracted, no Word artifact is edited or delivered.
- Task commit: pending local validation/commit; its hash will be recorded in a ledger follow-up without rewriting existing history.
- Status: local policy changes reviewed and validation passed; commit pending. Push blocked by Public visibility without explicit publication approval; not merged into `main`, no version tag or release created.
- Known issues/next steps: obtain a decision on private visibility versus explicit public publication, then recheck all push gates. Establishing a tested stable `main` remains a separate decision; existing application integration defects are not fixed by this task.

## Entry template

- Task ID / date:
- Starting branch / commit:
- Reason:
- Files:
- Changes:
- Exact test commands / actual results:
- Not-run tests / reasons and explicit failures/limitations:
- Task commit hash (or pending with reason):
- Push destination/status (or blocked reason):
- Merged into main / evidence or reason not merged:
- Version tag / release status:
- Worktree cleanliness:
- Known issues / follow-up decisions:
