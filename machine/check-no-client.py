#!/usr/bin/env python3
"""Reject known client and person names in publishable repository files."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def brain_path() -> Path:
    if "BRAIN_DIR" in os.environ:
        return Path(os.environ["BRAIN_DIR"]).resolve()
    for directory in (ROOT, *ROOT.parents):
        candidate = directory / "brain"
        if (candidate / "projects/clients").is_dir() and (candidate / "people").is_dir():
            return candidate
    return ROOT / "brain"


BRAIN = brain_path()


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def names() -> set[str]:
    roots = (BRAIN / "projects/clients", BRAIN / "people")
    if not all(root.is_dir() for root in roots):
        raise RuntimeError("private brain with projects/clients/ and people/ is required")
    found: set[str] = set()
    for path in roots[0].iterdir():
        if path.is_dir() and not path.name.startswith("_"):
            found.add(path.name)
            found.add(path.name.replace("-", " "))
    for path in roots[1].glob("*.md"):
        if not path.name.startswith("_"):
            found.add(path.stem)
            found.add(path.stem.replace("-", " "))
    return {name.casefold() for name in found if len(name) >= 4}


def files(mode: str) -> list[str]:
    if mode == "--staged":
        raw = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    else:
        raw = git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return [os.fsdecode(item) for item in raw.split(b"\0") if item]


def contents(path: str, mode: str) -> bytes:
    if mode == "--staged":
        return git("show", f":{path}")
    file = ROOT / path
    if file.is_symlink():
        return os.readlink(file).encode()
    return file.read_bytes()


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"--staged", "--worktree"}:
        print("usage: check-no-client.sh [--staged|--worktree]", file=sys.stderr)
        return 2
    try:
        blocked = names()
        candidates = files(sys.argv[1])
        violations = []
        for path in candidates:
            if not (ROOT / path).exists() and sys.argv[1] == "--worktree":
                continue
            body = contents(path, sys.argv[1]).decode("utf-8", errors="ignore")
            haystack = f"{path}\n{body}".casefold()
            for name in blocked:
                if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", haystack):
                    violations.append((path, name))
        if violations:
            for path, name in sorted(set(violations)):
                print(f"Blocked known name in {path}: {name}", file=sys.stderr)
            return 1
        print(f"Known-name scan OK ({len(candidates)} files, {len(blocked)} names)")
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Known-name scan could not run: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
