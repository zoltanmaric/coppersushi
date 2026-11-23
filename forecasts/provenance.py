"""Record the Python source used to fit and issue a forecast."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_hashes(package: Path) -> dict[str, str]:
    """Hash implementation files by package-relative path, including nested components."""
    return {
        path.relative_to(package).as_posix(): digest(path)
        for path in sorted(package.rglob("*.py"))
        if "tests" not in path.relative_to(package).parts
    }


def digest(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()
