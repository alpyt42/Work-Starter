#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read-only check that this machine can run the Work workspace.

Checks the required commands, the brains expected by brain/.data/local-paths.json
(present, Git repository, upstream, unpushed commits), the local input folders
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
            report("ERROR", f"commande absente : {name}")


def repo_checks(repo: Path) -> None:
    label = repo.name if repo != WORK else "Work"
    if not (repo / ".git").exists():
        report("ERROR", f"{label} : pas un dépôt Git")
        return
    dirty = git(repo, "status", "--porcelain")
    if dirty:
        report("INFO", f"{label} : {len(dirty.splitlines())} fichier(s) modifié(s) non commités")
    if git(repo, "rev-parse", "--abbrev-ref", "@{upstream}") is None:
        report("WARN", f"{label} : aucune branche distante suivie, rien n'est sauvegardé à distance")
        return
    # Counts against the last fetched state; no network access.
    ahead = git(repo, "rev-list", "--count", "@{upstream}..HEAD")
    if ahead and ahead != "0":
        report("WARN", f"{label} : {ahead} commit(s) local(aux) non poussé(s)")


def load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        report("ERROR", f"{path.relative_to(WORK)} : JSON illisible ({error.__class__.__name__})")
        return None


def boundary_checks(brain: Path) -> None:
    """The brain's .data/brain.json declares its trust boundary: Git remote and identity must match it."""
    path = brain / ".data/brain.json"
    if not path.is_file():
        report("WARN", f"{brain.name}/.data/brain.json absent : déclarer la frontière du brain (scope, remote, email)")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return  # reported as unreadable JSON with the other state files
    if not isinstance(data, dict):
        report("WARN", f"{brain.name}/.data/brain.json : un objet JSON est attendu")
        return
    declared = {field: data[field].strip() for field in BRAIN_FIELDS if isinstance(data.get(field), str) and data[field].strip()}
    empty = [field for field in BRAIN_FIELDS if field not in declared]
    if empty:
        report("WARN", f"{brain.name}/.data/brain.json : champ(s) non renseigné(s) : {', '.join(empty)}")
    if not (brain / ".git").exists():
        return
    actual = {"remote": git(brain, "remote", "get-url", "origin"), "email": git(brain, "config", "user.email")}
    names = {"remote": "remote origin", "email": "user.email effectif"}
    for field in ("remote", "email"):
        if field not in declared:
            continue
        if not actual[field]:
            report("WARN", f"{brain.name} : {names[field]} non défini alors que brain.json en déclare un")
        elif not fnmatch.fnmatchcase(actual[field], declared[field]):
            report("ERROR", f"{brain.name} : {names[field]} ne correspond pas au motif « {field} » de brain.json (frontière du brain)")


def brain_checks() -> None:
    config_file = WORK / "brain/.data/local-paths.json"
    if not (WORK / "brain").is_dir():
        report("ERROR", "brain/ absent : lancer tools/machine/bootstrap.sh avec BRAIN_REMOTE")
        return
    config = load_json(config_file) if config_file.is_file() else {}
    if not config_file.is_file():
        report("WARN", "brain/.data/local-paths.json absent : dossiers d'entrée et brains attendus inconnus")
    config = config if isinstance(config, dict) else {}

    present = sorted(p.name for p in WORK.iterdir() if p.is_dir() and BRAIN_NAME.fullmatch(p.name))
    expected = config.get("brains", ["brain"])
    for name in expected:
        if name not in present:
            report("ERROR", f"brain attendu absent : {name}/ (à cloner à la main, voir README « Set up a new machine »)")
    for name in present:
        brain = WORK / name
        if not (brain / "AGENTS.md").is_file() or not (brain / ".data").is_dir():
            report("WARN", f"{name}/ sans AGENTS.md ou .data/ : ignoré par les outils")
            continue
        if name not in expected:
            report("INFO", f"{name}/ présent mais absent de la liste « brains » de local-paths.json")
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
            report("WARN", f"dossier d'entrée « {key} » introuvable sur cette machine : adapter brain/.data/local-paths.json")


def skills_checks() -> None:
    try:
        config = work_config.resolve()
    except (work_config.ConfigError, OSError) as error:
        report("ERROR", f"configuration des skills invalide : {error}")
        return
    state = work_config.stamp_state(config)
    if state == "missing":
        report("WARN", "aucun .work-state.json : lancer tools/machine/update.sh")
    elif state == "changed":
        report("WARN", "config modifiée depuis le dernier update.sh")

    try:
        unadopted = sorted(work_config.unknown_lock_entries(config))
    except (work_config.ConfigError, OSError) as error:
        report("ERROR", f"skills-lock.json illisible : {error}")
        unadopted = []
    for name in unadopted:
        report("WARN", f"skill installé mais non adopté : {name} — lancer uv run tools/machine/work_config.py adopt")

    third_party = work_config.enabled_third_party(config)
    if third_party and shutil.which("npx") is None:
        report("ERROR", "commande absente : npx (nécessaire aux skills tiers activés)")
    for name in third_party:
        if not (WORK / ".agents/skills" / name / "SKILL.md").is_file():
            report("WARN", f"skill tiers activé mais non installé : {name} — lancer tools/machine/update.sh")

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
                report("WARN", f"lien cassé : {agent}/skills/{entry.name} — lancer tools/machine/update.sh")
            elif MANAGED_LINK.fullmatch(target) and (agent, entry.name, target) not in expected and entry.name not in unadopted:
                report("WARN", f"lien orphelin : {agent}/skills/{entry.name} (skill non activé) — lancer tools/machine/update.sh")
    leftover_checks(third_party, unadopted)


def leftover_checks(third_party: dict, unadopted: list[str]) -> None:
    """A real folder of .agents/skills must be an enabled third-party skill or a generated copy."""
    folder = WORK / ".agents/skills"
    for entry in sorted(folder.iterdir()) if folder.is_dir() else []:
        if entry.is_symlink() or not entry.is_dir() or entry.name in third_party or entry.name in unadopted:
            continue  # links are checked above; a skill installed but not adopted is reported on its own
        if not work_config.is_generated_copy(entry):
            report("WARN", f"dossier orphelin : .agents/skills/{entry.name} (ni skill tiers activé, ni copie générée) "
                           "— reste d'un nettoyage raté ? le retirer, ou lancer tools/machine/update.sh s'il est désactivé")


def artifacts_checks() -> None:
    artifacts = WORK / "artifacts"
    if not artifacts.is_dir():
        report("WARN", "artifacts/ absent")
        return
    files = sum(1 for p in artifacts.rglob("*") if p.is_file() and p.name not in {".DS_Store", "README.md"})
    report("INFO", f"artifacts/ : {files} fichier(s) locaux, sauvegardés par aucun dépôt — prévoir une sauvegarde")


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
    print(f"Bilan : {errors} erreur(s), {warnings} avertissement(s). Liens des skills : ./tools/machine/check-links.sh")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
