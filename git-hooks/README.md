# Git hooks

Repository-wide Git safeguards, independent of the Copper Sushi and blog products.
`post-checkout` checks new checkout bases; `install.py` installs it into the shared
Git hooks directory so all worktrees use it. Tests and fixtures live here.

Install the checkout base guard once per clone:

```sh
python3 git-hooks/install.py
```

New worktree checkouts fetch `origin/main` and fail unless `HEAD` contains that commit.
The worktree remains created; rebase it before starting work. A failed fetch also fails
the command. Ordinary branch switches are unaffected, and the existing checkout hook
(including Git LFS) is preserved. `git worktree add --no-checkout` does not run checkout
hooks. Clones with a custom `core.hooksPath` need to integrate the guard there manually.


Run `pixi run pytest -q git-hooks` from the repository root. Tests use temporary
local repositories and require no network or installed hook. The root test suite
also discovers them.
