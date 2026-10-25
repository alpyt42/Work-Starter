#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Create a blank brain at the Work root from kit/brain/seed/.

The seed holds only what belongs to one brain: its short AGENTS.md, profile,
inbox, task board, empty project and people folders, empty skill states, its
boundary declaration (.data/brain.json), its skill configuration
(.data/work-config.json) and a skills/ folder for private skills.
The shared conventions, guides and templates stay in kit/brain/ and are read
from there, so they follow Work updates instead of being copied.

`{{BRAIN}}` in the seed is replaced by the brain's folder name, which keeps the
Tasks queries of tasks.md scoped to that brain. The new folder gets a fresh Git
repository with no commit and no remote. An existing folder is never touched.

Every brain is a trust boundary declared in `.data/brain.json`. `--scope`,
`--description`, `--remote` and `--email` fill it at creation (the file is
written with sorted keys); otherwise the empty seed is kept and the owner fills it.

Run from the Work root with `uv run tools/brain/new-brain.py brain` (or
`brain-perso`, `brain-<name>`). Set WORK_DIR to use another workspace.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


WORK = Path(os.environ.get("WORK_DIR", Path(__file__).resolve().parents[2])).resolve()
SEED = Path(__file__).resolve().parents[2] / "kit/brain/seed"
NAME = re.compile(r"^brain(-[a-z0-9][a-z0-9-]*)?$")
PLACEHOLDER = "{{BRAIN}}"
TEXT = {".md", ".json"}
BOUNDARY = ".data/brain.json"
BOUNDARY_FIELDS = ("scope", "description", "remote", "email")


def write_boundary(target: Path, fields: dict[str, str]) -> None:
    """Fill the seed's .data/brain.json with the given fields (sorted keys, 2 spaces)."""
    path = target / BOUNDARY
    declaration = {"version": 1, "scope": "", "description": "", "remote": "", "email": "", "allow": []}
    if path.is_file():
        declaration.update(json.loads(path.read_text(encoding="utf-8")))
    declaration.update(fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(declaration, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def create(name: str, git: bool = True, boundary: dict[str, str] | None = None) -> Path:
    if NAME.fullmatch(name) is None:
        raise SystemExit(f"invalid brain name: {name} (expected: brain or brain-<name>)")
    target = WORK / name
    if target.exists():
        raise SystemExit(f"{name}/ already exists: nothing was changed")
    if not SEED.is_dir():
        raise SystemExit(f"seed not found: {SEED}")
    shutil.copytree(SEED, target)
    for path in target.rglob("*"):
        if path.is_file() and path.suffix in TEXT:
            text = path.read_text(encoding="utf-8")
            if PLACEHOLDER in text:
                path.write_text(text.replace(PLACEHOLDER, name), encoding="utf-8")
    fields = {key: value for key, value in (boundary or {}).items() if value}
    if fields:
        write_boundary(target, fields)
    if git:
        subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=target, check=True)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a blank brain from kit/brain/seed/.")
    parser.add_argument("name", nargs="?", default="brain", help="folder at the Work root (default: brain)")
    parser.add_argument("--no-git", action="store_true", help="do not run git init in the new brain")
    parser.add_argument("--scope", help="short label of the trust boundary, for example personal, employer, client")
    parser.add_argument("--description", help="what this brain holds and must never hold (agents route content with it)")
    parser.add_argument("--remote", help="fnmatch glob the brain's Git remote URL must match")
    parser.add_argument("--email", help="fnmatch glob the brain's commit e-mail must match")
    args = parser.parse_args(argv)
    boundary = {field: getattr(args, field) or "" for field in BOUNDARY_FIELDS}
    target = create(args.name, git=not args.no_git, boundary=boundary)
    note = "" if args.no_git else ", Git repository with no commit and no remote"
    print(f"{target.name}/ created from kit/brain/seed/{note}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
