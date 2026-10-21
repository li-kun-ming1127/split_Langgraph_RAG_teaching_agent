# Project instructions

## Scope and storage

- Project: `D:\pycharm\split_Langgraph_RAG_teaching_agent`.
- Preserve existing Python behavior unless the task explicitly requires changes.
- Keep the current single-Agent Windows Python/Streamlit/LangGraph/MCP/private-PDF RAG architecture. Do not introduce multiple agents, add `retriever.py`, or redistribute module responsibilities without explicit task authorization. `app.py` owns UI; `config.py` configuration; `auth.py` authentication/permissions/HMAC; `services.py` model/embedding/MCP clients; `memory.py` Redis history/context; `agent.py` orchestration; `utils.py` helpers; `mcp_server.py` parsing/OCR/Multi-Vector retrieval and MCP tools.
- Keep source filenames stable. Use commits, branches and approved tags, not `_v2`, `_final` or date-suffixed source copies, for version history. A temporary pre-restore safety backup is not a parallel source version.
- Read/install personal skills only under `C:\Users\李坤明\.codex\skills`; preserve `.system` and plugin-managed locations. Compare existing content before replacing it.
- Codex diagnostic/reconnection artifacts belong under `C:\Users\李坤明\.codex\diagnostics`, subject to filesystem permissions. Do not use retired `D:\Codex`; `D:\OpenAI` is a separate active runtime.
- Historical rollout backups are reference material; do not import them into active session databases without an explicit recovery request.

## Mandatory preflight

1. Confirm the working directory and `git rev-parse --show-toplevel` match this project.
2. Read `git status --short --branch`, `git branch -vv`, `git log --oneline --decorate -10`, `git diff`, and `git diff --cached`. On an unborn branch, report the absence of commits rather than treating it as corruption.
3. Inspect `git remote -v`. If a URL embeds credentials, redact them in output. Never assume an inherited remote belongs to this split project.
4. Identify untracked files, user changes, conflicts, credentials and generated data. Do not silently include unrelated user changes in a task commit.
5. Preserve pre-existing edits. If changes overlap or cannot be separated safely, explain the situation and obtain direction; do not discard, overwrite, auto-stash or stage them indiscriminately.
6. Before editing, establish the target branch/upstream relationship using fresh remote information when available. Local remote-tracking refs may be stale. Missing remotes, unknown/divergent history or unresolved conflicts require a report; do not blindly push, merge, pull or reset. Safe local-only work may continue if it does not depend on resolving the remote issue.

## Branches and commits

- The user authorizes meaningful local commits for completed, logically independent project tasks, subject to these safety checks and tool permissions.
- `main` is the only intended stable branch. New features use `feat/<short-description>`, fixes `fix/<short-description>`, documentation `docs/<short-description>` and maintenance `chore/<short-description>`. An existing related development branch may be reused without creating a duplicate.
- Create/switch branches only when clean and safe; otherwise explain the state first. When starting from `main`, fetch the latest `origin/main`, inspect its relationship to local history, then create the task branch from that verified tip. Do not develop unverified changes directly on `main`. If `origin/main` does not exist, report it and agree on a tested baseline before creating it; a development branch is not stable merely because GitHub makes it the default.
- Do not automatically merge into `main`, push unchecked changes to `main`, create release tags, or change remotes. Confirm destination ownership and purpose with the user first.
- Review the diff, run task-relevant checks, and run `git diff --check` plus `git diff --cached --check` before committing.
- Stage explicit task-owned paths, not blanket `git add .` or forced adds. Review `git diff --cached --name-status`, `git diff --cached --stat` and the complete staged diff before committing.
- Use descriptive conventional messages with `feat:`, `fix:`, `refactor:`, `perf:`, `test:`, `docs:` or `chore:`, such as `fix: correct MCP authentication` or `docs: document recovery workflow`.
- Failed tests, unresolved conflicts, unexplained changes or unresolved security findings block a normal completion commit/push. Report the failure; a separately authorized WIP checkpoint must be clearly labeled unverified.
- Never delete edits to make checks pass. Never use force pushes, `git reset --hard`, `git clean`, history rewriting, destructive restores or tag replacement without explicit authorization.
- No automatic release tags. Create a stable-version tag only after the user confirms the exact commit and tag.

## Required post-change validation

- Inspect the complete task diff and run `git diff --check`; before committing also inspect the staged diff and run `git diff --cached --check`.
- Choose syntax, safe module-import and behavioral checks appropriate to the change. For MCP, RAG, authentication, Redis, Agent or UI changes, prioritize focused regression coverage. Respect existing test conventions; do not build an unrelated test framework during documentation-only tasks.
- Assess requirements for credentials, Redis/MCP services, model downloads, network calls, cost and long index builds before running tests. Mock external dependencies where appropriate; never imply mocks prove live integration.
- Record exact commands and actual outcomes. Mark every omitted relevant test as **未运行 / not run**, with a reason. Documentation-only validation does not certify the existing application as stable.
- Check for unintended edits to env files, private data, models, indexes, dependencies or unrelated modules; check Python changes for circular imports, newly hardcoded old-project paths and broken dependency boundaries. Existing machine-specific setup examples are not permission to hardcode more paths in business code.
- On failure, diagnose and report it; do not weaken authentication/permissions, delete features or alter tests merely to hide a defect. Do not merge unverified changes into stable history.

## GitHub visibility, history and merge gates

- The only approved project remote is `https://github.com/li-kun-ming1127/split_Langgraph_RAG_teaching_agent.git`. Check both fetch and push URLs; never overwrite an unexpected `origin` automatically.
- Before **every push**, check current GitHub visibility using repository metadata. If it is **Public**, stop unless the user explicitly approves public publication after being informed of that visibility. Earlier push authorization is not a blanket public-publication exemption. If visibility is unknown, fail closed and report it. Do not change repository visibility yourself.
- A visibility blocker does not prevent reviewed local documentation commits. Keep them on the development branch and report that they have no new remote recovery point.
- Review the entire outgoing commit history, not just the latest tree, for secrets and unauthorized data. Recheck remote refs/history and confirm the push cannot overwrite someone else's work. A clean working tree and passing `.gitignore` checks alone are insufficient.
- After completion, review and appropriate tests, push the development branch first only when visibility/history/security gates pass. Merge into `main` only in a separately authorized merge task, after synchronizing and inspecting the remote main branch and verifying both changes and the resulting integration. Preserve meaningful changes from both sides of conflicts; do not blindly choose one side. A PR is preferred when available, not presumed configured.
- If a task is incomplete, tests fail, security findings remain or major design decisions await the user, remain on the development branch and report the blocker. Never delete valuable branches automatically.
- This repository already has history: do not reinitialize it. On any future first-connection/recovery scenario, inspect existing local history, remote URL, visibility and refs. A genuinely empty, approved remote may receive an explicitly agreed tested baseline; an existing remote requires comparison and an agreed integration plan, never replacement or unrelated-history merging by default.
- Tags such as `v1.0.0`, `v1.1.0` and `v1.1.1` identify verified stable milestones, not merely completed paperwork. Confirm the exact commit and unused tag name; never move/overwrite an existing tag. Push only the approved tag when remote synchronization is requested and all visibility/security gates pass.

## Secrets and private data

- Never commit real API keys, MCP HMAC secrets, access tokens, passwords, private keys or secret-bearing URLs, even to a private repository.
- `.gitignore` is not a security scanner and does not untrack existing files. Check `git ls-files -ci --exclude-standard`; if sensitive files are already tracked, stop and obtain approval before changing tracking/history. Suspected exposed credentials must be rotated, not merely deleted from the latest tree.
- Scan the staged content, including generated docs and dependency URLs. When available, use a dedicated secret scanner; disclose when checks are only heuristic.
- Keep actual `*.env`, `.streamlit/secrets.toml`, logs, environments, model weights and generated RAG indexes out of commits. Examples contain names and blank values only.
- Do not remove protective ignore rules or force-add ignored sensitive files for convenience. Ignore rules need review whenever new artifact or credential formats are introduced.
- Raw PDFs/CSVs and any new data formats require explicit upload approval. Small size or Git LFS does not grant permission. LFS is remote data upload, not encryption.
- Do not delete, rebuild or upload existing indexes/data as a side effect of Git setup. Do not read secrets into tool output.
- Full model/vision tests can send private document content to external services and incur costs; obtain authorization when not already covered by the task.

## Changelog and completion ledger

- Update `CHANGELOG.md` for each logical task with date (Asia/Shanghai), goal/reason, files/modules, behavior changes, exact test commands/results, omitted tests/reasons, important commit references, push destination/status, merge-to-main status, tag/release status, and known issues/next actions.
- Keep **completed**, **committed**, **pushed**, **merged** and **released** distinct. Local task completion is not a push, a development push is not a main merge, and a merge or tag alone is not proof of a GitHub Release.
- A commit cannot contain its own final hash. Use a stable task ID in its initial entry, then append the completed task commit hash in a separate small documentation-ledger commit. Do not repeatedly amend commits trying to record their own hash.
- The ledger records the task commit, not recursively its own bookkeeping hash. Report the final HEAD hash in the delivery message; Git history identifies the ledger commit.
- Record push status honestly: pending, blocked, failed, or confirmed. After a confirmed task push, a ledger-only follow-up can record it; report any failure pushing that follow-up separately.
- Push a completed task to its corresponding GitHub branch only after the exact remote is user-confirmed, the current visibility gate passes, staged/history secret checks pass and test results are explicit. If the remote contains unrelated history, stop; do not force push or automatically combine histories.
- If no approved remote/network/credentials are available, retain local commits, record the reason, and provide a later `git push -u origin <branch>` command. Never invent a repository URL or create a remote repository without authorization.
- Final report: repository, current branch and starting commit, remote, files/changes, exact tests/results and not-run checks, task/final commit hashes, push result, main-merge status, tag/release status, worktree cleanliness, and remaining decisions/risks. Base every claim on actual results.

## Recovery

- Prefer read-only history inspection first. A restore/revert is a separate user-authorized task.
- Check the worktree, identify the exact source commit/file/tag and explain all affected files before any recovery. Protect uncommitted user changes first, then use an explicitly sourced `git restore` for a single file or `git revert` for shared history.
- Before replacing a working file, preserve its current version (including uncommitted edits) in a timestamped local backup, then review the intended historical content.
- Revert shared commits with a new `git revert` commit on a dedicated branch, rather than rewriting published history. Abort on unresolved conflicts and report them.
- Git does not back up ignored credentials, PDFs, model files, Redis data or indexes. Use separately authorized encrypted backups; never upload those automatically.
- These are agent workflow rules, not installed Git hooks or server-side enforcement. Recommend repository branch protection once a verified remote exists; do not claim it is enabled locally.
