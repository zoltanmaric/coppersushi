#!/usr/bin/env python3
"""Install the stale-base guard in shared Git metadata, preserving an existing hook."""
import argparse
from pathlib import Path
import shutil
import subprocess


def install(repo):
    configured = subprocess.run(["git", "-C", str(repo), "config", "--get", "core.hooksPath"], capture_output=True, text=True)
    if configured.returncode == 0:
        raise RuntimeError("core.hooksPath is configured; preserve that hook setup and install the guard there manually")
    if configured.returncode != 1:
        raise RuntimeError("Cannot read the repository hook configuration")
    common = Path(subprocess.check_output(["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"], text=True).strip())
    hooks = common / "hooks"
    hooks.mkdir(exist_ok=True)
    target = hooks / "post-checkout"
    backup = hooks / "post-checkout.before-base-guard"
    marker = b"# Copper Sushi stale-base guard"
    if target.exists() and marker not in target.read_bytes():
        if backup.exists():
            raise RuntimeError("An earlier hook backup exists; refusing to overwrite it")
        shutil.copy2(target, backup)
    source = Path(__file__).parent / "hooks/post-checkout"
    temporary = hooks / "post-checkout.installing"
    shutil.copyfile(source, temporary)
    temporary.chmod(0o755)
    temporary.replace(target)
    print("Installed checkout base guard; existing hook preserved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    install(parser.parse_args().repo.resolve())
