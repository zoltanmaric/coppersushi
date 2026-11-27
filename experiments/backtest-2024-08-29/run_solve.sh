#!/bin/bash
# Always runs the solve from the worktree, so `python -m coppersushi.pypsa_eur` can import.
set -u
cd /Users/ljube/git/coppersushi/worktrees/solve-2024 || exit 1
PATH=/opt/homebrew/bin:$PATH exec /Users/ljube/git/coppersushi/.venv/bin/python -m coppersushi.pypsa_eur "$@"
