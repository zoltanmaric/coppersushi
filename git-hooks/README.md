# Git hooks

Repository-wide safeguards for Git checkout bases and writes to the shared checkout.

## When creating a worktree

Install the checkout base guard once per clone. The installer adds `post-checkout`
to the shared Git hooks directory.

```sh
python3 git-hooks/install.py
```

New worktree checkouts fetch `origin/main` and fail unless `HEAD` contains that commit.
The worktree remains created; rebase it before starting work. A failed fetch also fails
the command. Ordinary branch switches are unaffected, and the existing checkout hook
(including Git LFS) is preserved. `git worktree add --no-checkout` does not run checkout
hooks. Clones with a custom `core.hooksPath` need to integrate the guard there manually.

## Before writing in the shared checkout

The shared checkout is the primary working directory of the clone. Codex
`apply_patch` and Claude Code `Write`, `Edit`, `MultiEdit` and `NotebookEdit` call
`check_write.py` through the repository's `PreToolUse` hooks. Review and trust
the Codex hook in `/hooks` in a trusted project. For Claude Code, use the
project settings in a trusted workspace with hooks enabled.

The check examines every destination, including patch moves and absolute paths,
even when the session runs from a linked worktree. For shared checkout targets,
it checks staged, unstaged and untracked paths and queries `origin` for the
current `main` commit before testing whether it is an ancestor of `HEAD`. It
blocks if a required check fails, the checkout is stale, or any dirty path has
unverified ownership. A failed check leaves the checkout untouched. Fetch
`origin/main` if the check cannot verify ancestry of its current tip. For other
blocked edits, use a dedicated worktree based on current `origin/main`.

Run the same check immediately before a shell write or a write through any
other tool. Pass every write destination using paths relative to the command's
working directory or absolute paths.

```sh
python3 git-hooks/check_write.py -- path/to/file
```

Keep the check and the write in the same shell invocation using `&&`. When
another file is already dirty, use `--owned path` only after verifying that its
existing changes belong to this chat. Repeat the flag for each verified path.
Native edit hooks cannot establish ownership, so they reject any dirty shared
checkout. Workflows that write repeatedly should use a dedicated worktree.

Read-only operations remain available. This guard covers the registered edit
tools and explicit checks. Shell scripts, formatters, generators and other
write tools can change files indirectly. When you cannot name every destination,
run the operation in a dedicated worktree. The check does not lock the worktree
or the remote branch between checking and writing. It excludes ignored files
from dirty status, like standard Git status.

## Testing

Run `pixi run pytest -q git-hooks` from the repository root. Tests use temporary
local repositories and require no network or installed hook. The root test suite
also discovers them.
