"""Exercise native worktree creation against a local, deliberately stale clone."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures/checkout-guard"


class CheckoutGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.remote = self.directory / "remote"
        self.clone = self.directory / "clone"
        self.git(self.directory, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.seed = self.directory / "seed"
        self.git(self.directory, "clone", str(self.remote), str(self.seed))
        for repo in (self.seed,):
            self.git(repo, "config", "user.email", "fixture@example.invalid")
            self.git(repo, "config", "user.name", "Fixture")
        shutil.copyfile(FIXTURES / "base.txt", self.seed / "base.txt")
        self.git(self.seed, "add", "base.txt")
        self.git(self.seed, "commit", "-m", "fixture base")
        self.git(self.seed, "push", "origin", "main")
        self.git(self.directory, "clone", str(self.remote), str(self.clone))
        subprocess.run(["python3", str(ROOT / "scripts/install-checkout-guard.py"), "--repo", str(self.clone)], check=True, capture_output=True)
        shutil.copyfile(FIXTURES / "update.txt", self.seed / "update.txt")
        self.git(self.seed, "add", "update.txt")
        self.git(self.seed, "commit", "-m", "fixture update")
        self.git(self.seed, "push", "origin", "main")

    def git(self, repo, *args, check=True):
        return subprocess.run(["git", "-C", str(repo), *args], check=check, capture_output=True, text=True)

    def test_stale_worktree_creation_returns_failure_and_fetches_remote(self):
        worktree = self.directory / "stale"
        result = self.git(self.clone, "worktree", "add", "-b", "stale", str(worktree), "main", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("New checkout is stale", result.stderr)
        self.assertTrue(worktree.exists())
        self.assertEqual(self.git(self.clone, "rev-parse", "origin/main").stdout, self.git(self.seed, "rev-parse", "main").stdout)

    def test_fresh_remote_base_passes(self):
        self.git(self.clone, "fetch", "origin")
        result = self.git(self.clone, "worktree", "add", "-b", "fresh", str(self.directory / "fresh"), "origin/main", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ordinary_branch_switch_does_not_fetch_or_fail(self):
        result = self.git(self.clone, "checkout", "-b", "existing-base", "main", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unreachable_remote_fails_new_creation(self):
        self.git(self.clone, "remote", "set-url", "origin", str(self.directory / "missing"))
        result = self.git(self.clone, "worktree", "add", "-b", "offline", str(self.directory / "offline"), "main", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fetching origin/main failed", result.stderr)

    def test_existing_hook_is_preserved_and_install_is_idempotent(self):
        hooks = self.clone / ".git/hooks"
        shutil.copyfile(FIXTURES / "previous-hook", hooks / "post-checkout")
        (hooks / "post-checkout").chmod(0o755)
        for _ in range(2):
            subprocess.run(["python3", str(ROOT / "scripts/install-checkout-guard.py"), "--repo", str(self.clone)], check=True, capture_output=True)
        self.assertEqual((hooks / "post-checkout.before-base-guard").read_bytes(), (FIXTURES / "previous-hook").read_bytes())
        self.git(self.clone, "fetch", "origin")
        result = self.git(self.clone, "worktree", "add", "-b", "preserved", str(self.directory / "preserved"), "origin/main", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PREVIOUS_HOOK_RAN", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
