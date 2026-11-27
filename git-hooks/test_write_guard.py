"""Exercise the pre-write guard against real Git repositories and hook payloads."""
import json
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WriteGuardTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.remote = self.root / "remote"
        self.shared = self.root / "shared checkout"
        self.git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(self.root, "clone", str(self.remote), str(self.shared))
        self.git(self.shared, "config", "user.name", "Fixture")
        self.git(self.shared, "config", "user.email", "fixture@example.invalid")
        (self.shared / "a.txt").write_text("base\n")
        self.git(self.shared, "add", "a.txt")
        self.git(self.shared, "commit", "-m", "fixture base")
        self.git(self.shared, "push", "origin", "main")
        self.script = self.shared / "git-hooks" / "check_write.py"
        self.script.parent.mkdir()
        shutil.copyfile(ROOT / "git-hooks" / "check_write.py", self.script)
        (self.shared / ".git/info/exclude").write_text("/git-hooks/\n/worktrees/\n")
        self.linked = self.shared / "worktrees" / "feature"
        self.git(self.shared, "worktree", "add", "-b", "feature", str(self.linked))

    def git(self, cwd, *args):
        return subprocess.check_output(["git", "-C", str(cwd), *args], stderr=subprocess.PIPE, text=True)

    def check_write(self, *args):
        return subprocess.run(
            ["python3", str(self.script), *args],
            cwd=self.shared, capture_output=True, text=True,
        )

    def hook(self, harness, tool, tool_input, cwd=None):
        cwd = self.shared if cwd is None else cwd
        filename = ".codex/hooks.json" if harness == "codex" else ".claude/settings.json"
        hook = json.loads((ROOT / filename).read_text())["hooks"]["PreToolUse"][0]
        self.assertRegex(tool, hook["matcher"])
        return subprocess.run(
            ["/bin/sh", "-c", hook["hooks"][0]["command"]],
            cwd=cwd,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.shared)},
            input=json.dumps({"cwd": str(cwd), "tool_name": tool, "tool_input": tool_input}),
            capture_output=True,
            text=True,
        )

    def test_clean_current_root_allows_writes(self):
        self.assertEqual(self.check_write("a.txt").returncode, 0)

    def test_dirty_created_and_staged_paths_require_explicit_ownership(self):
        (self.shared / "new file.txt").write_text("foreign\n")
        (self.shared / "a.txt").write_text("staged\n")
        self.git(self.shared, "add", "a.txt")
        blocked = self.check_write("--owned", "a.txt", "another.txt")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("unverified ownership: 'new file.txt'", blocked.stderr)
        self.assertEqual(
            self.check_write("--owned", "a.txt", "--owned", "new file.txt", "another.txt").returncode, 0
        )

    def test_rename_reports_undeclared_source(self):
        self.git(self.shared, "mv", "a.txt", "renamed.txt")
        blocked = self.check_write("--owned", "renamed.txt", "other.txt")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("unverified ownership: 'a.txt'", blocked.stderr)

    def test_linked_worktree_bypasses_dirty_and_offline_root(self):
        (self.shared / "a.txt").write_text("foreign\n")
        self.git(self.shared, "remote", "set-url", "origin", str(self.root / "missing"))
        self.assertEqual(self.check_write(str(self.linked / "future/new.txt")).returncode, 0)

    def test_outside_symlink_to_shared_checkout_is_guarded(self):
        (self.shared / "a.txt").write_text("foreign\n")
        alias = self.root / "alias"
        alias.symlink_to(self.shared, target_is_directory=True)
        self.assertEqual(self.check_write(str(alias / "new.txt")).returncode, 2)

    def test_shared_symlink_entry_is_guarded_when_target_is_linked(self):
        alias = self.shared / "linked alias"
        alias.symlink_to(self.linked, target_is_directory=True)
        self.assertEqual(self.check_write(str(alias)).returncode, 2)

    def test_shared_checkout_spelled_with_different_case_is_guarded(self):
        alias = self.shared.with_name(self.shared.name.upper())
        if not alias.exists():
            self.skipTest("requires a case-insensitive filesystem")
        (self.shared / "a.txt").write_text("foreign\n")
        for name in ("a.txt", "new.txt"):
            with self.subTest(name=name):
                blocked = self.check_write(str(alias / name))
                self.assertEqual(blocked.returncode, 2)
                self.assertIn("unverified ownership", blocked.stderr)

    def test_linked_checkout_spelled_with_different_case_is_allowed(self):
        alias = self.linked.with_name(self.linked.name.upper())
        if not alias.exists():
            self.skipTest("requires a case-insensitive filesystem")
        (self.shared / "a.txt").write_text("foreign\n")
        self.assertEqual(self.check_write(str(alias / "new.txt")).returncode, 0)

    def test_remote_advances_beyond_local_tracking_ref(self):
        tracking = self.git(self.shared, "rev-parse", "origin/main")
        self.git(self.linked, "commit", "--allow-empty", "-m", "remote advance")
        self.git(self.linked, "push", "origin", "feature:main")
        self.git(self.shared, "update-ref", "refs/remotes/origin/main", tracking.strip())
        blocked = self.check_write("a.txt")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("shared checkout is stale", blocked.stderr)
        self.assertEqual(self.git(self.shared, "rev-parse", "origin/main"), tracking)

    def test_remote_error_blocks_shared_checkout(self):
        self.git(self.shared, "remote", "set-url", "origin", str(self.root / "missing"))
        blocked = self.check_write("a.txt")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("git ls-remote failed", blocked.stderr)

    def test_codex_patch_checks_move_destination_from_linked_worktree(self):
        (self.shared / "a.txt").write_text("foreign\n")
        patch = "*** Begin Patch\n*** Update File: a.txt\n*** Move to: ../../new.txt\n@@\n-base\n+new\n*** End Patch"
        blocked = self.hook("codex", "apply_patch", {"command": patch}, cwd=self.linked)
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("unverified ownership", blocked.stderr)

    def test_codex_patch_checks_indented_header_after_add_with_crlf(self):
        (self.shared / "a.txt").write_text("foreign\n")
        patch = (
            "*** Begin Patch\r\n*** Add File: new.txt\r\n+linked\r\n"
            "  *** Add File: ../../shared.txt  \r\n+shared\r\n*** End Patch"
        )
        blocked = self.hook("codex", "apply_patch", {"command": patch}, cwd=self.linked)
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("unverified ownership", blocked.stderr)

    def test_claude_edit_checks_absolute_path_from_linked_worktree(self):
        (self.shared / "a.txt").write_text("foreign\n")
        self.assertEqual(self.hook("claude", "Edit", {"file_path": str(self.shared / "a.txt")}, cwd=self.linked).returncode, 2)
        self.assertEqual(self.hook("claude", "Write", {"file_path": str(self.linked / "a.txt")}).returncode, 0)

    def test_unusable_hook_payload_fails_closed(self):
        blocked = self.hook("codex", "apply_patch", {"command": "*** Begin Patch\n*** End Patch"})
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("did not report valid destination paths", blocked.stderr)
