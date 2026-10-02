#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""List, check, or clone client repositories from the private brain catalog.

Run from the Work root: brain/ is found next to tools/. Set WORK_DIR or
BRAIN_DIR only to use another location. The catalog contains URLs only;
credentials and key paths stay local.

Author and SSH key come from the user's ~/.gitconfig rules (by folder and by
remote URL, see machine/gitconfig.example); `check` shows what each clone gets.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path


WORK = Path(os.environ.get("WORK_DIR", Path(__file__).resolve().parents[1])).resolve()
BRAIN = Path(os.environ.get("BRAIN_DIR", WORK / "brain")).resolve()
CATALOG = BRAIN / ".data/client-repos.json"
PART = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SSH_URL = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[A-Za-z0-9._/-]+\.git$")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def catalog() -> list[dict[str, str]]:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("repositories"), list):
        raise ValueError("unsupported client repository catalog")
    repositories: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in data["repositories"]:
        if not isinstance(item, dict) or set(item) != {"path", "url"}:
            raise ValueError("catalog entries must contain only path and url")
        path, url = item["path"], item["url"]
        if not isinstance(path, str) or not isinstance(url, str):
            raise ValueError("catalog path and url must be strings")
        parts = path.split("/")
        if len(parts) != 3 or parts[0] != "repos" or not all(PART.fullmatch(p) for p in parts[1:]):
            raise ValueError(f"unsafe repository path: {path}")
        if path in seen:
            raise ValueError(f"duplicate repository path: {path}")
        if not SSH_URL.fullmatch(url) or ".." in url:
            raise ValueError(f"unsafe or non-SSH URL for {path}")
        seen.add(path)
        repositories.append(item)
    return repositories


def selected(items: list[dict[str, str]], selector: str | None) -> list[dict[str, str]]:
    if selector is None:
        return items
    matches = [item for item in items if item["path"] == selector or item["path"].split("/")[1] == selector]
    if not matches:
        raise ValueError(f"unknown client or repository: {selector}")
    return matches


def destination(relative: str) -> Path:
    repos = WORK / "repos"
    if repos.is_symlink() or not repos.resolve().is_relative_to(WORK):
        raise ValueError("repos/ must be inside the Work checkout")
    target = WORK / relative
    if target.is_symlink() or not target.parent.resolve().is_relative_to(repos.resolve()):
        raise ValueError(f"repository destination escapes Work: {relative}")
    return target


def existing_remote(target: Path) -> str:
    if not (target / ".git").exists():
        raise ValueError(f"destination exists but is not a Git clone: {target}")
    if Path(git(target, "rev-parse", "--show-toplevel")).resolve() != target.resolve():
        raise ValueError(f"destination is not its own Git repository: {target}")
    return git(target, "remote", "get-url", "origin")


def effective(repo: Path, key: str) -> tuple[str, str]:
    """Effective value of a Git setting in repo and the file it comes from."""
    result = subprocess.run(
        ["git", "-C", str(repo), "config", "--show-origin", "--get", key], capture_output=True, text=True
    )
    if result.returncode or "\t" not in result.stdout:
        return "", ""
    origin, value = result.stdout.rstrip("\n").split("\t", 1)
    origin = origin.removeprefix("file:")
    local = bool(origin) and (repo / origin).resolve() == (repo / ".git/config").resolve()
    return value, "clone local" if local else Path(origin).name


def identity_summary(repo: Path) -> tuple[str, bool]:
    """Human-readable author and key applied in repo, and whether an author exists."""
    email, email_origin = effective(repo, "user.email")
    command, command_origin = effective(repo, "core.sshCommand")
    key = re.search(r"-i\s+(\S+)", command)
    key_text = f"{key.group(1)} ({command_origin})" if key else "choisie par ~/.ssh/config"
    author = f"{email} ({email_origin})" if email else "aucun"
    return f"auteur={author} · clé={key_text}", bool(email)


def check(items: list[dict[str, str]]) -> int:
    mismatches = 0
    for item in items:
        target = destination(item["path"])
        if not target.exists():
            print(f"ABSENT    {item['path']}")
            continue
        try:
            actual = existing_remote(target)
        except (ValueError, subprocess.CalledProcessError) as exc:
            print(f"ERREUR    {item['path']}: {exc}")
            mismatches += 1
            continue
        if actual != item["url"]:
            visible = actual if SSH_URL.fullmatch(actual) and ".." not in actual else "<URL non SSH masquée>"
            print(f"DIFFÉRENT {item['path']}: origin={visible}; catalogue={item['url']}")
            mismatches += 1
            continue
        summary, has_author = identity_summary(target)
        if has_author:
            print(f"OK        {item['path']}  {summary}")
        else:
            print(f"IDENTITÉ  {item['path']}  {summary} : aucun user.email (règle ~/.gitconfig absente ou incomplète)")
            mismatches += 1
    return 1 if mismatches else 0


def ssh_command(identity_arg: str) -> str:
    identity = Path(identity_arg)
    if not identity.is_absolute() or not identity.is_file():
        raise ValueError("--identity must name an existing absolute key path")
    identity = identity.resolve()
    if identity.is_relative_to(WORK):
        raise ValueError("SSH keys must stay outside Work")
    if stat.S_IMODE(identity.stat().st_mode) & 0o077:
        raise ValueError("SSH key permissions must be owner-only")
    return shlex.join([
        "ssh", "-F", "/dev/null", "-i", str(identity),
        "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes",
    ])


def home_rules_cover(target: Path, url: str) -> str:
    """Author email the home rules would give a clone of url at target ("" if none).

    Evaluated in a throwaway repository at the destination so that both
    `gitdir:` and `hasconfig:remote.*.url:` conditions apply; target is left empty.
    """
    target.mkdir(parents=True)
    try:
        subprocess.run(["git", "init", "-q", str(target)], check=True)
        subprocess.run(["git", "-C", str(target), "remote", "add", "origin", url], check=True)
        return effective(target, "user.email")[0]
    finally:
        shutil.rmtree(target / ".git", ignore_errors=True)


def clone(items: list[dict[str, str]], identity: str | None, author_name: str | None, author_email: str | None) -> int:
    override = identity or author_name or author_email
    environment = os.environ.copy()
    if override:
        if not (identity and author_name and author_name.strip() and author_email and "@" in author_email):
            raise ValueError("an override needs --identity, --author-name and --author-email together")
        command = ssh_command(identity)
        environment.pop("GIT_SSH", None)
        environment["GIT_SSH_COMMAND"] = command
    for item in items:
        target = destination(item["path"])
        if target.exists():
            if existing_remote(target) != item["url"]:
                raise ValueError(f"existing clone has a different origin: {item['path']}")
            print(f"DÉJÀ PRÉSENT {item['path']}  {identity_summary(target)[0]}")
            continue
        if not override and not home_rules_cover(target, item["url"]):
            target.rmdir()
            raise ValueError(
                f"no ~/.gitconfig rule gives an author for {item['path']}: add a folder or "
                "remote URL rule (machine/gitconfig.example) or pass an explicit override"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", item["url"], str(target)], env=environment, check=True)
        if override:
            for key, value in (
                ("user.name", author_name.strip()),
                ("user.email", author_email.strip()),
                ("user.useConfigOnly", "true"),
                ("core.sshCommand", command),
            ):
                subprocess.run(["git", "-C", str(target), "config", "--local", key, value], check=True)
        print(f"CLONÉ       {item['path']}  {identity_summary(target)[0]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "check"):
        commands.add_parser(name).add_argument("selector", nargs="?", help="client or repos/client/name")
    clone_parser = commands.add_parser("clone")
    clone_parser.add_argument("selector", help="one client or repos/client/name")
    clone_parser.add_argument("--identity", help="one-off override: absolute path to an approved SSH key")
    clone_parser.add_argument("--author-name", help="one-off override, with --identity")
    clone_parser.add_argument("--author-email", help="one-off override, with --identity")
    args = parser.parse_args()
    try:
        items = selected(catalog(), args.selector)
        if args.command == "list":
            for item in items:
                print(f"{item['path']}  {item['url']}")
            return 0
        if args.command == "check":
            return check(items)
        return clone(items, args.identity, args.author_name, args.author_email)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
