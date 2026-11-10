"""Replay the review in an isolated temporary source copy, without editing the checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-draft", action="store_true")
    parser.add_argument("--existing-tests", action="store_true")
    args = parser.parse_args()
    review_dir = Path(__file__).resolve().parent
    root = review_dir.parents[2]
    baseline = json.loads((review_dir / "baseline-sha256.json").read_text(encoding="utf-8"))
    for name, expected in baseline.items():
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if actual != expected:
            parser.error(f"The reviewed baseline changed: {name}")
    tracked = subprocess.check_output(["git", "ls-files", "backend", "tests"], cwd=root, text=True).splitlines()
    with tempfile.TemporaryDirectory(prefix="easychat-access-draft-") as directory:
        isolated = Path(directory)
        for name in tracked:
            source = root / name
            if source.suffix not in {".py", ".sql"} or not source.is_file():
                continue
            target = isolated / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        shutil.copy2(root / "pyproject.toml", isolated / "pyproject.toml")
        shutil.copy2(review_dir / "test_access_draft.py", isolated / "test_access_draft.py")
        if args.apply_draft:
            patch = str(review_dir / "access-fixes.draft.patch")
            subprocess.run(["git", "apply", "--check", patch], cwd=isolated, check=True)
            subprocess.run(["git", "apply", patch], cwd=isolated, check=True)
        targets = ["test_access_draft.py"]
        if args.existing_tests:
            targets.extend(["tests/access", "tests/security"])
        result = subprocess.run([sys.executable, "-m", "pytest", *targets, "-q",
                                 "-m", "not integration and not resources", "--tb=short"], cwd=isolated)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
