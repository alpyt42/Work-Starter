#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Merge skill states across every brain of the workspace.

A brain is a directory at the Work root named `brain` or `brain-*` that holds
an AGENTS.md and a .data/ folder. Each transcript belongs to exactly one brain:
its state lives only in that brain's .data/transcripts.json. A transcript is
new when no brain lists it.

`brain/` is the default brain and holds the shared configuration: the input
folders in .data/local-paths.json and, optionally, the list of brains expected
on every machine (`"brains": ["brain", "brain-perso"]`). A missing expected
brain stops the tool, so its transcripts never come back as new elsewhere.

Each brain is a trust boundary declared in its own .data/brain.json (`scope`,
`description`, ...). `brains` prints the scope and the description next to each
brain, so that an agent can pick the brain where new content belongs.

Run from the Work root with `uv run tools/brain/brain-state.py`. Set WORK_DIR to use
another workspace and TRANSCRIPTS_DIR to override the transcript folder.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


WORK = Path(os.environ.get("WORK_DIR", Path(__file__).resolve().parents[2])).resolve()
DEFAULT = "brain"
NAME = re.compile(r"^brain(-[a-z0-9][a-z0-9-]*)?$")


def is_brain(path: Path) -> bool:
    return NAME.fullmatch(path.name) is not None and (path / "AGENTS.md").is_file() and (path / ".data").is_dir()


def discover() -> list[Path]:
    """Brains present at the Work root, the default brain first."""
    found = sorted((p for p in WORK.iterdir() if p.is_dir() and is_brain(p)), key=lambda p: (p.name != DEFAULT, p.name))
    return found


def shared_config() -> dict:
    path = WORK / DEFAULT / ".data/local-paths.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def check_expected(brains: list[Path]) -> None:
    expected = shared_config().get("brains", [])
    missing = [name for name in expected if not (WORK / name).is_dir() or not is_brain(WORK / name)]
    if missing:
        raise SystemExit(
            "brain(s) attendu(s) absent(s) : " + ", ".join(missing)
            + " — cloner ou restaurer avant de traiter des transcripts"
        )
    if not brains:
        raise SystemExit(f"aucun brain trouvé dans {WORK}")


def load_transcripts(brains: list[Path]) -> dict[str, tuple[str, dict]]:
    """Union of transcript states, keyed by file name; refuses a file listed by two brains."""
    merged: dict[str, tuple[str, dict]] = {}
    conflicts: list[str] = []
    for brain in brains:
        state = brain / ".data/transcripts.json"
        if not state.is_file():
            continue
        for key, record in json.loads(state.read_text(encoding="utf-8")).items():
            if key in merged:
                conflicts.append(f"{key} ({merged[key][0]}, {brain.name})")
            else:
                merged[key] = (brain.name, record)
    if conflicts:
        raise SystemExit("transcript présent dans plusieurs brains : " + "; ".join(conflicts))
    return merged


def transcripts_dir() -> Path:
    if "TRANSCRIPTS_DIR" in os.environ:
        return Path(os.environ["TRANSCRIPTS_DIR"])
    relative = shared_config().get("transcripts_dir")
    if not relative:
        raise SystemExit(f"transcripts_dir absent de {DEFAULT}/.data/local-paths.json")
    return Path.home() / relative


def boundary(brain: Path) -> dict:
    """The brain's .data/brain.json, or {} when it has none."""
    path = brain / ".data/brain.json"
    if not path.is_file():
        return {}
    try:
        declared = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"{brain.name}/.data/brain.json illisible : {error}") from None
    return declared if isinstance(declared, dict) else {}


def one_line(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def cmd_brains(brains: list[Path]) -> int:
    """One line per brain: name, tracked transcripts, scope, description (tab-separated)."""
    for brain in brains:
        state = brain / ".data/transcripts.json"
        count = len(json.loads(state.read_text(encoding="utf-8"))) if state.is_file() else 0
        declared = boundary(brain)
        print(f"{brain.name}\t{count} transcript(s) suivis\t{one_line(declared.get('scope'))}\t{one_line(declared.get('description'))}")
    return 0


def cmd_transcripts(brains: list[Path], new: bool, where: str | None) -> int:
    merged = load_transcripts(brains)
    if where:
        if where not in merged:
            print(f"{where}\tnon suivi")
            return 1
        owner, record = merged[where]
        print(f"{where}\t{owner}\t{record.get('status', '?')}")
        return 0
    if new:
        folder = transcripts_dir()
        try:
            names = sorted(p.name for p in folder.iterdir() if p.suffix == ".txt")
        except (FileNotFoundError, NotADirectoryError):
            raise SystemExit(f"dossier des transcripts introuvable : {folder}") from None
        except PermissionError:
            raise SystemExit(
                f"Accès refusé au dossier des transcripts : {folder}. "
                "Vérifie les autorisations macOS et la disponibilité du dossier OneDrive, puis relance."
            ) from None
        except OSError as error:
            raise SystemExit(f"impossible de lire le dossier des transcripts : {folder} ({error.strerror})") from None
        for name in names:
            if name not in merged:
                print(name)
        return 0
    for key in sorted(merged):
        owner, record = merged[key]
        print(f"{record.get('status', '?')}\t{owner}\t{key}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("brains", help="list the brains found, their tracked transcripts, scope and description")
    tr = sub.add_parser("transcripts", help="merged transcript states (status, brain, file)")
    group = tr.add_mutually_exclusive_group()
    group.add_argument("--new", action="store_true", help="transcripts listed by no brain")
    group.add_argument("--where", metavar="FILE", help="which brain owns FILE, and its status")
    args = parser.parse_args()

    brains = discover()
    check_expected(brains)
    if args.command == "brains":
        return cmd_brains(brains)
    return cmd_transcripts(brains, args.new, args.where)


if __name__ == "__main__":
    sys.exit(main())
