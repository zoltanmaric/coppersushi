#!/usr/bin/env python3
"""Guard edits to the shared checkout of this repository."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class WriteBlocked(Exception):
    """The shared checkout cannot safely receive this write."""


def git(cwd, *args, allowed=(0,)):
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(cwd), *args],
        capture_output=True,
        timeout=10,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode not in allowed:
        detail = result.stderr.decode(errors="replace").strip()
        raise WriteBlocked(f"git {args[0]} failed: {detail or result.returncode}")
    return result


def absolute(cwd, path):
    # Preserve symlinks here so deletion of a link counts as a write to its directory.
    return Path(os.path.abspath(cwd / path))


def entry_identity(path):
    try:
        entry = path.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    return entry.st_dev, entry.st_ino


def patch_targets(patch):
    paths = []
    in_update = False
    for line in patch.split("\n"):
        # The Codex parser preserves leading spaces in update hunks for context.
        header = line.rstrip() if in_update else line.strip()
        file_match = re.fullmatch(r"\*\*\* (Add|Delete|Update) File: (.+)", header)
        if file_match:
            action, path = file_match.groups()
            paths.append(path)
            in_update = action == "Update"
        elif in_update and header.startswith("*** Move to: "):
            paths.append(header.removeprefix("*** Move to: "))
    return paths


def edit_targets(event):
    cwd = Path(event["cwd"])
    if not cwd.is_absolute():
        raise WriteBlocked("The edit tool did not report an absolute working directory.")
    tool = event["tool_name"]
    tool_input = event["tool_input"]
    if tool == "apply_patch":
        paths = patch_targets(tool_input["command"])
    elif tool in {"Write", "Edit", "MultiEdit"}:
        paths = [tool_input["file_path"]]
    elif tool == "NotebookEdit":
        paths = [tool_input["notebook_path"]]
    else:
        raise WriteBlocked(f"Unknown edit tool {tool!r}.")
    if not paths or not all(isinstance(path, str) and path for path in paths):
        raise WriteBlocked("The edit tool did not report valid destination paths.")
    return cwd, paths


def check(repo, cwd, paths, owned):
    # Git lists the shared checkout first, followed by linked worktrees.
    listing = git(repo, "worktree", "list", "--porcelain", "-z").stdout
    shared, *linked = [
        Path(os.fsdecode(entry.removeprefix(b"worktree "))).resolve()
        for entry in listing.split(b"\0")
        if entry.startswith(b"worktree ")
    ]
    shared_identity = entry_identity(shared)
    if shared_identity is None:
        raise WriteBlocked("The shared checkout directory is missing.")
    linked_identities = {entry_identity(worktree) for worktree in linked} - {None}

    def in_shared_checkout(path):
        # Find the nearest checkout even when the destination does not exist
        # or an existing directory is spelled differently on this filesystem.
        for ancestor in (path, *path.parents):
            identity = entry_identity(ancestor)
            if identity in linked_identities:
                return False
            if identity == shared_identity:
                return True
        return False

    if not any(
        in_shared_checkout(absolute(cwd, path)) or in_shared_checkout((cwd / path).resolve())
        for path in paths
    ):
        return

    # Disable rename detection so both source and destination must be owned.
    status = git(
        shared, "status", "--porcelain=v1", "-z", "--untracked-files=all",
        "--no-renames", "--ignore-submodules=none",
    ).stdout
    owned_paths = {absolute(cwd, path) for path in owned}
    foreign_paths = [
        os.fsdecode(record[3:]) for record in status.split(b"\0")
        if record and shared / os.fsdecode(record[3:]) not in owned_paths
    ]
    if foreign_paths:
        paths = ", ".join(repr(path) for path in foreign_paths[:5])
        if len(foreign_paths) > 5:
            paths += f" and {len(foreign_paths) - 5} more"
        raise WriteBlocked(f"The shared checkout has changes with unverified ownership: {paths}.")

    # Read the remote tip without changing shared refs. A cached tracking ref
    # alone cannot distinguish a fresh checkout from an out-of-date clone.
    remote = git(shared, "ls-remote", "--exit-code", "origin", "refs/heads/main").stdout
    tip, ref = remote.decode("ascii").split()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", tip) or ref != "refs/heads/main":
        raise WriteBlocked("origin did not report a valid main tip.")
    ancestry = git(shared, "merge-base", "--is-ancestor", tip, "HEAD", allowed=(0, 1, 128))
    if ancestry.returncode == 128:
        raise WriteBlocked("The shared checkout cannot verify ancestry of the current origin/main. Fetch origin/main before preparing a worktree.")
    if ancestry.returncode == 1:
        raise WriteBlocked("The shared checkout is stale. Start a dedicated worktree from current origin/main.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hook", action="store_true", help="read a PreToolUse event from stdin")
    parser.add_argument("--owned", action="append", default=[], help="a dirty path verified to belong to this chat")
    parser.add_argument("paths", nargs="*", help="all paths the operation will write")
    args = parser.parse_args()
    if args.hook and (args.paths or args.owned):
        parser.error("--hook reads paths from stdin and cannot declare ownership")
    if not args.hook and not args.paths:
        parser.error("provide at least one write destination")

    try:
        cwd, paths = edit_targets(json.load(sys.stdin)) if args.hook else (Path.cwd(), args.paths)
        check(Path(__file__).resolve().parents[1], cwd, paths, args.owned)
    except (WriteBlocked, OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"Write blocked: {error}\nUse a dedicated worktree when the shared checkout cannot be verified.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
