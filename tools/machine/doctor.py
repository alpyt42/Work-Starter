#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read-only check that this machine can run the Work workspace.

Checks the required commands, the default brain (work_config.py) and the brains expected by its
.data/local-paths.json (present, Git repository, upstream, unpushed commits), the local input folders
named there, the JSON state files of every brain, and the local artifacts folder.
It also checks the skill configuration (valid layers, changed since the last
update.sh, skills of skills-lock.json no layer knows, enabled third-party skills not
installed, broken or orphan links in .agents/skills and .claude/skills, real folders of
.agents/skills that are neither an enabled third-party skill nor a generated copy) and, for each
brain, its boundary declaration .data/brain.json (fields filled in; Git remote and
effective user.email matching the declared patterns).
It never fetches, pulls, writes, or prints the configured paths; the skill links
themselves are checked by tools/machine/check-links.sh.

Run from the Work root with `uv run tools/machine/doctor.py`. Set WORK_DIR to check
another workspace. Exit status is 1 when an ERROR is found.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import work_config  # next to this script; shares WORK_DIR and the configuration rules


WORK = Path(os.environ.get("WORK_DIR", Path(__file__).resolve().parents[2])).resolve()
BRAIN_NAME = re.compile(r"^brain(-[a-z0-9][a-z0-9-]*)?$")
COMMANDS = ("git", "uv")  # node and npx are only needed when third-party skills are enabled
BRAIN_FIELDS = ("scope", "description", "remote", "email")
MANAGED_LINK = re.compile(r"\.\./\.\./(brain(-[a-z0-9][a-z0-9-]*)?|\.agents)/skills/[^/]+")
findings: list[tuple[str, str]] = []


def report(level: str, detail: str) -> None:
    findings.append((level, detail))


def git(repo: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def command_checks() -> None:
    for name in COMMANDS:
        if shutil.which(name) is None:
            report("ERROR", f"command not found: {name}")


def repo_checks(repo: Path) -> None:
    label = repo.name if repo != WORK else "Work"
    if not (repo / ".git").exists():
        report("ERROR", f"{label}: not a Git repository")
        return
    dirty = git(repo, "status", "--porcelain")
    if dirty:
        report("INFO", f"{label}: {len(dirty.splitlines())} modified file(s) not committed")
    if git(repo, "rev-parse", "--abbrev-ref", "@{upstream}") is None:
        report("WARN", f"{label}: no upstream branch tracked, nothing is backed up remotely")
        return
    # Counts against the last fetched state; no network access.
    ahead = git(repo, "rev-list", "--count", "@{upstream}..HEAD")
    if ahead and ahead != "0":
        report("WARN", f"{label}: {ahead} local commit(s) not pushed")


def load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        report("ERROR", f"{path.relative_to(WORK)}: unreadable JSON ({error.__class__.__name__})")
        return None


def boundary_checks(brain: Path) -> None:
    """The brain's .data/brain.json declares its trust boundary: Git remote and identity must match it."""
    path = brain / ".data/brain.json"
    if not path.is_file():
        report("WARN", f"{brain.name}/.data/brain.json missing: declare the trust boundary of the brain (scope, remote, email)")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return  # reported as unreadable JSON with the other state files
    if not isinstance(data, dict):
        report("WARN", f"{brain.name}/.data/brain.json: a JSON object is expected")
        return
    declared = {field: data[field].strip() for field in BRAIN_FIELDS if isinstance(data.get(field), str) and data[field].strip()}
    empty = [field for field in BRAIN_FIELDS if field not in declared]
    if empty:
        report("WARN", f"{brain.name}/.data/brain.json: field(s) not filled in: {', '.join(empty)}")
    if not (brain / ".git").exists():
        return
    actual = {"remote": git(brain, "remote", "get-url", "origin"), "email": git(brain, "config", "user.email")}
    names = {"remote": "remote origin", "email": "effective user.email"}
    for field in ("remote", "email"):
        if field not in declared:
            continue
        if not actual[field]:
            report("WARN", f"{brain.name}: {names[field]} not set although brain.json declares one")
        elif not fnmatch.fnmatchcase(actual[field], declared[field]):
            report("ERROR", f"{brain.name}: {names[field]} does not match the \"{field}\" pattern of brain.json (trust boundary)")


def brain_checks() -> None:
    default = None
    invalid = False
    try:
        default = work_config.default_brain(WORK)
    except work_config.ConfigError as error:
        invalid = True
        report("ERROR", str(error))
    if default is None and not invalid:
        brains = [brain.name for brain in work_config.find_brains(WORK)]
        if not brains:
            report("ERROR", "no brain at the Work root: run tools/machine/install.sh")
        else:
            report("WARN", f"several brains ({', '.join(brains)}) and no default brain: set \"defaultBrain\" in work-config.local.json")

    # The shared settings (input folders, expected brains) live in the default brain.
    shared = f"{default.name}/.data/local-paths.json" if default else "local-paths.json"
    config: dict | list | None = {}
    if default is not None:
        config_file = default / ".data/local-paths.json"
        config = load_json(config_file) if config_file.is_file() else {}
        if not config_file.is_file():
            report("WARN", f"{shared} missing: input folders and expected brains unknown")
    config = config if isinstance(config, dict) else {}

    present = sorted(p.name for p in WORK.iterdir() if p.is_dir() and BRAIN_NAME.fullmatch(p.name))
    expected = config.get("brains", [default.name] if default else [])
    for name in expected:
        if name not in present:
            report("ERROR", f"expected brain missing: {name}/ (clone it by hand, see the README section \"Set up a new machine\")")
    for name in present:
        brain = WORK / name
        if not (brain / "AGENTS.md").is_file() or not (brain / ".data").is_dir():
            report("WARN", f"{name}/ has no AGENTS.md or .data/: ignored by the tools")
            continue
        if default is not None and name not in expected:
            report("INFO", f"{name}/ is present but not in the \"brains\" list of local-paths.json")
        repo_checks(brain)
        boundary_checks(brain)
        for state in sorted((brain / ".data").rglob("*.json")):
            load_json(state)

    # Input folders are relative to the home directory (as in tools/brain/brain-state.py)
    # and differ per machine; report the key, never the path.
    for key, value in sorted(config.items()):
        if not key.endswith("_dir") or not isinstance(value, str):
            continue
        folder = Path.home() / value
        if not folder.is_dir():
            report("WARN", f"input folder \"{key}\" not found on this machine: adjust {shared}")


def skills_checks() -> None:
    try:
        config = work_config.resolve()
    except (work_config.ConfigError, OSError) as error:
        report("ERROR", f"invalid skills configuration: {error}")
        return
    state = work_config.stamp_state(config)
    if state == "missing":
        report("WARN", "no .work-state.json: run tools/machine/update.sh")
    elif state == "changed":
        report("WARN", "configuration changed since the last update.sh")

    try:
        unadopted = sorted(work_config.unknown_lock_entries(config))
    except (work_config.ConfigError, OSError) as error:
        report("ERROR", f"skills-lock.json unreadable: {error}")
        unadopted = []
    for name in unadopted:
        report("WARN", f"skill installed but not adopted: {name} — run uv run tools/machine/work_config.py adopt")

    third_party = work_config.enabled_third_party(config)
    if third_party and shutil.which("npx") is None:
        report("ERROR", "command not found: npx (needed by the enabled third-party skills)")
    for name in third_party:
        if not (WORK / ".agents/skills" / name / "SKILL.md").is_file():
            report("WARN", f"enabled third-party skill not installed: {name} — run tools/machine/update.sh")

    expected = {
        (agent, name, f"../../{skill['brain']}/skills/{name}")
        for name, skill in work_config.enabled_own(config).items()
        if skill["mode"] == "link"
        for agent in (".agents", ".claude")
    } | {(".claude", name, f"../../.agents/skills/{name}") for name in third_party}
    for agent in (".agents", ".claude"):
        folder = WORK / agent / "skills"
        for entry in sorted(folder.iterdir()) if folder.is_dir() else []:
            if not entry.is_symlink():
                continue
            target = os.readlink(entry)
            if not entry.exists():
                report("WARN", f"broken link: {agent}/skills/{entry.name} — run tools/machine/update.sh")
            elif MANAGED_LINK.fullmatch(target) and (agent, entry.name, target) not in expected and entry.name not in unadopted:
                report("WARN", f"orphan link: {agent}/skills/{entry.name} (skill not enabled) — run tools/machine/update.sh")
    leftover_checks(third_party, unadopted)


def leftover_checks(third_party: dict, unadopted: list[str]) -> None:
    """A real folder of .agents/skills must be an enabled third-party skill or a generated copy."""
    folder = WORK / ".agents/skills"
    for entry in sorted(folder.iterdir()) if folder.is_dir() else []:
        if entry.is_symlink() or not entry.is_dir() or entry.name in third_party or entry.name in unadopted:
            continue  # links are checked above; a skill installed but not adopted is reported on its own
        if not work_config.is_generated_copy(entry):
            report("WARN", f"orphan folder: .agents/skills/{entry.name} (neither an enabled third-party skill nor a generated copy) "
                           "— left over from a failed cleanup? remove it, or run tools/machine/update.sh if it is disabled")


def artifacts_checks() -> None:
    artifacts = WORK / "artifacts"
    if not artifacts.is_dir():
        report("WARN", "artifacts/ missing")
        return
    files = sum(1 for p in artifacts.rglob("*") if p.is_file() and p.name not in {".DS_Store", "README.md"})
    report("INFO", f"artifacts/: {files} local file(s), backed up by no repository — plan a backup")


def main() -> None:
    command_checks()
    repo_checks(WORK)
    brain_checks()
    skills_checks()
    artifacts_checks()
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    for level, detail in sorted(findings, key=lambda item: order[item[0]]):
        print(f"{level}: {detail}")
    errors = sum(level == "ERROR" for level, _ in findings)
    warnings = sum(level == "WARN" for level, _ in findings)
    print(f"Summary: {errors} error(s), {warnings} warning(s). Skill links: ./tools/machine/check-links.sh")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
