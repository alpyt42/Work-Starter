#!/usr/bin/env python3
"""Reject known client and person names in publishable repository files.

Default mode: scan this Work repository (staged or worktree) against the names of
the default brain (clients and people).

Brain mode (`--brain DIR`): scan the Git repository of one brain against the
client names of the OTHER brains of the same Work root. A brain is a trust
boundary: the client folders of another brain (`<other>/projects/clients/<name>/`)
must not appear in its paths or content, except the names listed in the `allow`
field of its own `.data/brain.json`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAIN_NAME = re.compile(r"^brain(-[a-z0-9][a-z0-9-]*)?$")
USAGE = "usage: check-no-client.sh [--staged|--worktree] | check-no-client.py --brain DIR --staged|--worktree"


def brain_path() -> Path:
    if "BRAIN_DIR" in os.environ:
        return Path(os.environ["BRAIN_DIR"]).resolve()
    for directory in (ROOT, *ROOT.parents):
        candidate = directory / "brain"
        if (candidate / "projects/clients").is_dir() and (candidate / "people").is_dir():
            return candidate
    return ROOT / "brain"


BRAIN = brain_path()


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True).stdout


def forms(name: str) -> set[str]:
    """Casefolded spellings of a folder or file name: as written and with spaces for dashes."""
    return {name.casefold(), name.replace("-", " ").casefold()}


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
        if not path.name.startswith("_") and path.name.casefold() != "readme.md":
            found.add(path.stem)
            found.add(path.stem.replace("-", " "))
    return {name.casefold() for name in found if len(name) >= 4}


def other_brains(brain: Path) -> list[Path]:
    """Sibling brains of `brain` at the same Work root (folders named brain or brain-*)."""
    work = brain.parent
    own = brain.resolve()
    return sorted(
        path
        for path in work.iterdir()
        if BRAIN_NAME.fullmatch(path.name) and path.is_dir() and path.resolve() != own
    )


def client_names(brain: Path) -> dict[str, str]:
    """Client folder names of one brain, same normalisation as `names()`, mapped to the brain's name."""
    clients = brain / "projects/clients"
    found: dict[str, str] = {}
    if not clients.is_dir():
        return found
    for path in clients.iterdir():
        if path.is_dir() and not path.name.startswith("_"):
            for form in forms(path.name):
                if len(form) >= 4:
                    found[form] = brain.name
    return found


def allowed(brain: Path, mode: str) -> set[str]:
    """Names the brain may keep: the `allow` list of its .data/brain.json (staged version when staging)."""
    raw: bytes | None = None
    if mode == "--staged":
        try:
            raw = git(brain, "show", ":.data/brain.json")
        except subprocess.CalledProcessError:
            raw = None
    if raw is None:
        declaration = brain / ".data/brain.json"
        raw = declaration.read_bytes() if declaration.is_file() else None
    if raw is None:
        return set()
    try:
        allow = json.loads(raw).get("allow", [])
    except (json.JSONDecodeError, AttributeError) as error:
        raise RuntimeError(f"{brain.name}/.data/brain.json is not valid: {error}") from None
    if not isinstance(allow, list) or any(not isinstance(item, str) for item in allow):
        raise RuntimeError(f"{brain.name}/.data/brain.json: `allow` must be a list of names")
    return {form for item in allow for form in forms(item)}


def other_brains_names(brain: Path, mode: str) -> dict[str, str]:
    """Client names of the other brains that this brain must not mention, minus its `allow` list."""
    blocked: dict[str, str] = {}
    for other in other_brains(brain):
        blocked.update(client_names(other))
    for form in allowed(brain, mode):
        blocked.pop(form, None)
    return blocked


def files(repo: Path, mode: str) -> list[str]:
    if mode == "--staged":
        raw = git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    else:
        raw = git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return [os.fsdecode(item) for item in raw.split(b"\0") if item]


def contents(repo: Path, path: str, mode: str) -> bytes:
    if mode == "--staged":
        return git(repo, "show", f":{path}")
    file = repo / path
    if file.is_symlink():
        return os.readlink(file).encode()
    return file.read_bytes()


def scan(repo: Path, mode: str, blocked: dict[str, str]) -> tuple[list[str], list[tuple[str, str]]]:
    candidates = files(repo, mode)
    violations: list[tuple[str, str]] = []
    for path in candidates:
        if not (repo / path).exists() and mode == "--worktree":
            continue
        body = contents(repo, path, mode).decode("utf-8", errors="ignore")
        haystack = f"{path}\n{body}".casefold()
        for name in blocked:
            if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", haystack):
                violations.append((path, name))
    return candidates, violations


def parse(argv: list[str]) -> tuple[str, Path | None] | None:
    """Return (mode, brain directory or None), or None when the arguments are invalid."""
    modes: list[str] = []
    brain: Path | None = None
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg in {"--staged", "--worktree"}:
            modes.append(arg)
        elif arg == "--brain" and args and brain is None:
            brain = Path(args.pop(0)).resolve()
        else:
            return None
    return (modes[0], brain) if len(modes) == 1 else None


def main() -> int:
    parsed = parse(sys.argv[1:])
    if parsed is None:
        print(USAGE, file=sys.stderr)
        return 2
    mode, brain = parsed
    try:
        if brain is None:
            repo, blocked, label = ROOT, {name: "" for name in names()}, "known name"
        else:
            if not brain.is_dir():
                raise RuntimeError(f"brain not found: {brain}")
            if not other_brains(brain):
                print(f"Client-name scan of {brain.name}: no other brain at the Work root, nothing to check")
                return 0
            repo, blocked, label = brain, other_brains_names(brain, mode), "client name of another brain"
        candidates, violations = scan(repo, mode, blocked)
        if violations:
            for path, name in sorted(set(violations)):
                owner = f" ({blocked[name]})" if blocked[name] else ""
                print(f"Blocked {label}{owner} in {path}: {name}", file=sys.stderr)
            return 1
        subject = "Known-name scan" if brain is None else f"Client-name scan of {brain.name}"
        print(f"{subject} OK ({len(candidates)} files, {len(blocked)} names)")
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Known-name scan could not run: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
