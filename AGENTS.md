# Project instructions

## Scope and storage

- Project: `D:\pycharm\split_Langgraph_RAG_teaching_agent`.
- Preserve existing Python behavior unless the task explicitly requires changes.
- Read/install personal skills only under `C:\Users\李坤明\.codex\skills`; preserve `.system` and plugin-managed locations. Compare existing content before replacing it.
- Codex diagnostic/reconnection artifacts belong under `C:\Users\李坤明\.codex\diagnostics`, subject to filesystem permissions. Do not use retired `D:\Codex`; `D:\OpenAI` is a separate active runtime.
- Historical rollout backups are reference material; do not import them into active session databases without an explicit recovery request.

## Mandatory preflight

1. Confirm the working directory and `git rev-parse --show-toplevel` match this project.
2. Read `git branch --show-current`, `git status --short --branch`, `git log -5 --oneline`, `git diff`, and `git diff --cached`. On an unborn branch, report the absence of commits rather than treating it as corruption.
3. Inspect `git remote -v`. If a URL embeds credentials, redact them in output. Never assume an inherited remote belongs to this split project.
4. Identify untracked files, user changes, conflicts, credentials and generated data. Do not silently include unrelated user changes in a task commit.
5. Preserve pre-existing edits. If changes overlap or cannot be separated safely, explain the situation and obtain direction; do not discard, overwrite, auto-stash or stage them indiscriminately.

## Branches and commits

- The user authorizes meaningful local commits for completed, logically independent project tasks, subject to these safety checks and tool permissions.
- Prefer a dedicated `feat/...`, `fix/...`, `refactor/...` or `chore/...` branch. Create/switch branches only when clean and safe; otherwise explain the state first.
- Do not automatically merge into `main`, push unchecked changes to `main`, create release tags, or change remotes. Confirm destination ownership and purpose with the user first.
- Review the diff, run task-relevant checks, and run `git diff --check` plus `git diff --cached --check` before committing.
- Stage explicit task-owned paths, not blanket `git add .` or forced adds. Review `git diff --cached --name-status`, `git diff --cached --stat` and the complete staged diff before committing.
- Use descriptive conventional messages, such as `fix: correct MCP authentication` or `docs: document recovery workflow`.
- Failed tests, unresolved conflicts, unexplained changes or unresolved security findings block a normal completion commit/push. Report the failure; a separately authorized WIP checkpoint must be clearly labeled unverified.
- Never delete edits to make checks pass. Never use force pushes, `git reset --hard`, `git clean`, history rewriting, destructive restores or tag replacement without explicit authorization.
- No automatic release tags. Create a stable-version tag only after the user confirms the exact commit and tag.

## Secrets and private data

- Never commit real API keys, MCP HMAC secrets, access tokens, passwords, private keys or secret-bearing URLs, even to a private repository.
- `.gitignore` is not a security scanner and does not untrack existing files. Check `git ls-files -ci --exclude-standard`; if sensitive files are already tracked, stop and obtain approval before changing tracking/history. Suspected exposed credentials must be rotated, not merely deleted from the latest tree.
- Scan the staged content, including generated docs and dependency URLs. When available, use a dedicated secret scanner; disclose when checks are only heuristic.
- Keep actual `*.env`, `.streamlit/secrets.toml`, logs, environments, model weights and generated RAG indexes out of commits. Examples contain names and blank values only.
- Raw PDFs/CSVs and any new data formats require explicit upload approval. Small size or Git LFS does not grant permission. LFS is remote data upload, not encryption.
- Do not delete, rebuild or upload existing indexes/data as a side effect of Git setup. Do not read secrets into tool output.
- Full model/vision tests can send private document content to external services and incur costs; obtain authorization when not already covered by the task.

## Changelog and completion ledger

- Update `CHANGELOG.md` for each logical task with date (Asia/Shanghai), reason, files, changes, exact tests/results, commit reference and push status.
- A commit cannot contain its own final hash. Use a stable task ID in its initial entry, then append the completed task commit hash in a separate small documentation-ledger commit. Do not repeatedly amend commits trying to record their own hash.
- The ledger records the task commit, not recursively its own bookkeeping hash. Report the final HEAD hash in the delivery message; Git history identifies the ledger commit.
- Record push status honestly: pending, blocked, failed, or confirmed. After a confirmed task push, a ledger-only follow-up can record it; report any failure pushing that follow-up separately.
- Push a completed task to its corresponding GitHub branch only after the exact remote is user-confirmed, staged/history secret checks pass and test results are explicit. If the remote contains unrelated history, stop; do not force push or automatically combine histories.
- If no approved remote/network/credentials are available, retain local commits, record the reason, and provide a later `git push -u origin <branch>` command. Never invent a repository URL or create a remote repository without authorization.
- Final report: repository, branch, remote, files changed, tests/limitations, task and final commit hashes, push result, and remaining risks.

## Recovery

- Prefer read-only history inspection first. A restore/revert is a separate user-authorized task.
- Before replacing a working file, preserve its current version (including uncommitted edits) in a timestamped local backup, then review the intended historical content.
- Revert shared commits with a new `git revert` commit on a dedicated branch, rather than rewriting published history. Abort on unresolved conflicts and report them.
- Git does not back up ignored credentials, PDFs, model files, Redis data or indexes. Use separately authorized encrypted backups; never upload those automatically.
- These are agent workflow rules, not installed Git hooks or server-side enforcement. Recommend repository branch protection once a verified remote exists; do not claim it is enabled locally.
