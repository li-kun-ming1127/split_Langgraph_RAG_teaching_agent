# Private-course Matplotlib RAG teaching assistant

Python + Streamlit + LangGraph/LangChain + MCP + Redis. This project processes local course PDFs, builds a persistent retrieval index and exposes retrieval tools to a teaching agent.

## Status and scope

The repository baseline preserves existing code, not a certified working release. Index construction has historical success records, but full chat integration is not yet verified. Known follow-up issues include UI `question`/`answer` versus Graph `messages` contracts, message accumulation, and dictionary versus `Document` source-display types. The earlier MCP context/time-window fix is preserved.

Visual understanding is optional. The existing index uses OCR fallback; it does not demonstrate trained multimodal embeddings or multi-agent orchestration. Online model calls can transmit course text, and configured vision calls can transmit images, to external providers.

## Modules

| File | Responsibility |
| --- | --- |
| `app.py` | Streamlit UI/login/chat/source display |
| `config.py` | Environment, paths, models, services and budgets |
| `auth.py` | User access, session context, signed MCP tokens |
| `mcp_server.py` | PDF/OCR, representations, persistent index, MMR/RRF, MCP server |
| `agent.py` | Agent graph and tool orchestration |
| `memory.py` | Redis history, summaries, cache and context budget |
| `services.py` | Model/embedding factories and authenticated MCP client |
| `utils.py` | Result parsing and token-usage callbacks |

Only Redis, `mcp_server.py` and the Streamlit app are separate running services. Do not run every module independently.

Keep this single-Agent architecture and the module responsibilities above. Do not add multi-agent orchestration or `retriever.py` without an approved design task. Keep filenames stable; use Git commits/branches/tags rather than source copies named `v2`, `final` or dates. Temporary ignored backups before an authorized restore are a safety measure, not a second version-management system.

## Environment and secrets

- Existing local Python: `D:\pycharm\langchain\LangChain_project\venv312\Scripts\python.exe` (Python 3.12). This path is machine-specific.
- The dependency snapshot is `environment_backup/20261017_195339/requirements-freeze.txt`. It is an environment snapshot, not a validated minimal cross-platform lockfile. Review before installing into a new isolated environment; do not overwrite an existing environment blindly.
- Provide authorized PDFs named in `config.py`, local `embedding_models/text2vec-base-chinese`, Redis and the configured Tesseract/Poppler installations. These are intentionally absent from Git.
- `.env.example` documents variables only. `config.py` does not automatically load a root `.env`. Use process environment variables or existing files under `API_Key_and_Tools`: `Deepseek_API_Key.env`, `MCP_TOKEN_SECRET.env`, and optional `SERPAPI_API_Key.env`.
- Never replace existing secret files with the example. Set a supported `TEXT_MODEL_NAME` only if overriding the default; do not set it to an empty value.
- Run `API_Key_and_Tools/ensure_mcp_secret.py` only when initializing/checking the local signing secret. It preserves an already valid secret. Both processes must use the same secret.
- `APP_USER_TOKENS_JSON` maps user IDs to SHA-256 access-token digests; `APP_USER_KB_ACCESS_JSON` maps users to permitted knowledge-base IDs. No users are enabled by default.
- Optional `VISION_MODEL`, `VISION_MODEL_BASE_URL`, `VISION_API_KEY` belong to the MCP server environment. Changing index-relevant settings may rebuild the index and incur costs; do this only deliberately, with approved data processing.
- Token-usage callbacks do not constitute complete system-wide billing telemetry.

## Local startup (after fixing the known chat integration issues)

Use three PowerShell terminals. Commands are instructions, not actions performed by this Git setup task.

Terminal A, for the existing local Redis installation:

```powershell
Set-Location 'D:\pycharm\redis'
& '.\redis-server.exe' --bind 127.0.0.1 --port 6379
```

Verify from another terminal with `D:\pycharm\redis\redis-cli.exe ping` (expect `PONG`). Do not expose unauthenticated Redis to the network.

Terminal B:

```powershell
Set-Location 'D:\pycharm\split_Langgraph_RAG_teaching_agent'
$python = 'D:\pycharm\langchain\LangChain_project\venv312\Scripts\python.exe'
& $python '.\mcp_server.py'
```

Wait for index prewarming and MCP startup without exceptions. The default tool endpoint is `http://127.0.0.1:8000/mcp`, not a chat page. A new index can invoke paid models; existing data must not be deleted to make startup succeed.

Terminal C, configure a local user without echoing their original access token:

```powershell
Set-Location 'D:\pycharm\split_Langgraph_RAG_teaching_agent'
$python = 'D:\pycharm\langchain\LangChain_project\venv312\Scripts\python.exe'
$tokenHash = & $python -c "import getpass,hashlib; print(hashlib.sha256(getpass.getpass('Access token: ').encode('utf-8')).hexdigest())"
$env:APP_USER_TOKENS_JSON = @{student01=$tokenHash.Trim()} | ConvertTo-Json -Compress
$env:APP_USER_KB_ACCESS_JSON = @{student01=@('matplotlib-course-v1')} | ConvertTo-Json -Compress
$env:REDIS_URL = 'redis://localhost:6379/0'
& $python -m streamlit run '.\app.py' --server.address 127.0.0.1 --server.port 8501
```

Open `http://127.0.0.1:8501`. Log in as `student01` using the original access token, not its hash/API key. Terminal environment variables are not persisted. These commands start the services; they do not fix the known code defects.

## Checks

No automated application test suite exists at this baseline. Do not equate syntax checking with end-to-end testing.

```powershell
$python = 'D:\pycharm\langchain\LangChain_project\venv312\Scripts\python.exe'
& $python -c "import ast,pathlib; files=list(pathlib.Path('.').glob('*.py'))+[pathlib.Path('API_Key_and_Tools/ensure_mcp_secret.py')]; [ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p)) for p in files]; print('Syntax OK:',len(files))"
git diff --check
git diff --cached --check
git status --short --branch
git ls-files -ci --exclude-standard
```

The last command should show no tracked files that match ignore rules. Review staged content for secrets as well; ignored filenames alone are insufficient. Runtime tests should cover authenticated tool access, multiple users, first question/follow-up, references and failure paths, using mocks before paid/private-data calls.

## Git workflow

Follow `AGENTS.md`. Verify this repository root, branch, status, diffs, history and remote at every task start. Preserve user edits. Work on a dedicated branch only after confirming the switch is safe; never auto-merge into `main`.

Stage explicit task paths, inspect `git diff --cached`, run relevant checks, update `CHANGELOG.md`, and commit a logically complete task. Record its hash in a small follow-up changelog commit; that ledger does not recursively record its own hash. Known baseline application defects must remain documented, not mislabeled as tests passing.

The confirmed `origin` is `https://github.com/li-kun-ming1127/split_Langgraph_RAG_teaching_agent.git`. Check its fetch and push URLs rather than assuming the current configuration is correct. Never replace an unexpected remote or reinitialize this existing repository. A private repository is not permission to upload secrets or course data.

**Visibility gate:** before every push, read fresh GitHub repository metadata. Public repositories require explicit user approval for public publication; unknown visibility blocks pushing as well. Do not change visibility without authorization. As checked on 2026-10-21, this repository is **Public**; this management-policy task therefore remains local. The previously uploaded baseline is already public; withholding new pushes does not remove it or undo previous publication.

At this check, the remote contains `chore/version-control-baseline` at `34c17ef` and uses it as its default branch; no `main` exists. This is a development recovery baseline, not a verified stable release. Do not create `main` just to satisfy a naming convention: first agree on and validate a stable baseline in a separate task.

Only after visibility, history, security and test checks pass, the branch-specific push command is:

```text
git push -u origin chore/version-control-baseline
```

Run it only if `origin` and that branch have been verified. Never force push. If push fails, retain local commits and report the error. Branch protections and pull-request checks require separate server-side setup; local instructions do not enforce them.

### Task checklist and branch lifecycle

Before editing:

```text
git rev-parse --show-toplevel
git status --short --branch
git branch -vv
git log --oneline --decorate -10
git remote -v
git diff
git diff --cached
```

Identify existing edits and ownership before proceeding. Do not auto-stash, discard or mix unrelated edits into a task commit. Inspect fresh remote refs; fetching and inspecting is safer than an unconditional `pull` that may merge. Missing/unclear remote history or conflicts must be reported before a push or merge.

`main` is the sole intended stable branch. Use `feat/<description>`, `fix/<description>`, `docs/<description>` or `chore/<description>`. Reuse a related development branch when appropriate. When starting a new task from `main`, first fetch/check the latest `origin/main` and create a clean task branch from that verified tip. Do not run those steps blindly when `main` is absent or local changes/history are unresolved.

After editing, inspect the complete diff, run `git diff --check`, and select suitable syntax, safe import and focused functional checks. MCP/RAG/authentication/Redis/Agent/UI changes need relevant regression coverage. Assess services, credentials, downloads, costs and potential index rebuilds before testing. Mark omitted tests **未运行 / not run** and explain why; do not weaken permissions or alter tests to hide failures. Check for accidental changes to secrets/data/models/indexes/dependencies, circular imports, old-project path hardcoding and changed module boundaries.

Use explicit staging and `git diff --cached --check`. Commit small complete tasks with `feat:`, `fix:`, `refactor:`, `perf:`, `test:`, `docs:` or `chore:`. Review all outgoing historical content, not just the worktree. Never weaken `.gitignore` or force-add private artifacts to simplify a commit.

Push the verified development branch before a separately authorized stable merge. Before merging, synchronize and inspect the remote `main`, review differences, test integration and preserve both sides' valid work if conflicts occur. Incomplete tasks, failed tests or unresolved risks stay on a development branch. Do not force push, reset hard, clean files or delete valuable branches to resolve divergence.

Only verified milestones receive an explicitly approved, unique tag such as `v1.0.0`, `v1.1.0` or `v1.1.1`. Never move existing tags. Tag pushes obey the same visibility/security gates and occur only when synchronization is requested.

### Status reporting and source document

`CHANGELOG.md` and the final report must distinguish these states:

| State | Evidence |
| --- | --- |
| Completed | Task scope reviewed and relevant checks have explicit results |
| Committed | Local commit hash exists |
| Pushed | Fresh remote ref matches the intended commit |
| Merged | Verified integration into `main`, not merely a development push |
| Released | Explicit verified milestone/tag and, if applicable, actual GitHub Release; never inferred |

Record date, objective, files/modules, behavior changes, exact tests/results, not-run tests/reasons, commit hashes, push/merge/tag statuses, worktree cleanliness and follow-up issues. For final handoff also identify the starting commit and current branch. Do not label syntax-only or documentation checks as a successful application test.

These rules adapt the reference document 《Git和GitHub管理代码的方式》: stable main, task branches, small commits and milestone tags. Its old `ReAct_agent_loop_with_toolnode.py` filename and feature branch are examples from another project, not current instructions. Do not copy its blanket `git add .`, unconditional pull/merge, hard-reset or branch-deletion sequences; the current explicit safety rules take precedence. The reference DOCX is read-only source material and is not copied into this repository.

## What Git excludes and why

- Actual credentials, Python environments/caches, logs, temporary files and `.local_backups/` are excluded.
- `embedding_models/` is reviewed downloaded model/vendor content, not application source. Fetch from an authorized model distribution separately.
- Only the generated `docs/multivector/matplotlib_v2/` subtree is excluded, not all of `docs/`.
- Raw PDFs/CSVs under `data/` are quarantined pending explicit rights/upload approval; code in other directories is not excluded by this rule. New data formats still require manual review.
- Machine-specific environment diagnostics are excluded individually; the dependency freeze snapshot remains versioned.
- `API_Key_and_Tools/ensure_mcp_secret.py` remains versioned; the entire tools directory is not ignored.

Existing local inventory: three PDFs total 7,880,436 bytes, one CSV 102,056 bytes, model resources 410,192,970 bytes, generated index assets 6,969,757 bytes. No private data is included in the initial baseline.

Ordinary Git is suitable for small authorized static data but retains copies in history. Git LFS reduces repository object growth for large binaries but still uploads content and has hosting/storage considerations. Neither provides permission or encryption. Local-only/encrypted external storage avoids remote disclosure but needs a separate backup plan. Current default: retain locally; no deletion/rebuild/upload.

## Recovery without rewriting history

Read-only inspection:

```text
git log --oneline --decorate -10
git show <commit> --stat
git log --oneline -- agent.py
git show <commit>:agent.py
```

To restore one file, first get approval and preserve the current version. Example after reviewing the chosen commit:

```powershell
$backup = Join-Path '.local_backups' (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Item -LiteralPath '.\agent.py' -Destination (Join-Path $backup 'agent.py')
```

Then run `git restore --source=<approved-commit> --worktree -- agent.py`, inspect the diff, test, update the changelog and make a new commit. This replaces that working file; do not run it on unknown user edits. Restoring one file does not automatically restore dependencies or external data.

To undo a committed change safely, on a clean approved feature branch run `git revert <approved-commit>` to create an inverse commit. Review/test it and update the ledger before pushing. On conflicts, stop for review; `git revert --abort` cancels that in-progress revert. Do not substitute `reset --hard` or force push. Inspect dependency changes before reverting older commits.

Git can recover only committed content since the baseline. Ignored secrets, PDFs, models, Redis data and indexes need separately authorized encrypted backups on independent storage. Local commits protect against mistaken edits, not disk failure. Remote recovery is unavailable until a verified push succeeds. Create release tags only with user confirmation; no `v1.0.0` tag is implied by initialization.
