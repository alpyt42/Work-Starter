#!/usr/bin/env python3
"""Resolve the Work skill configuration and keep the generated files in sync.

Work-Starter ships no skill. Every brain (`brain/`, `brain-perso/`, `brain-<name>/`
holding an AGENTS.md and a .data/ folder) is a trust boundary that can hold:

- its own skills, `<brain>/skills/<name>/SKILL.md`; a skill folder containing an
  empty `.install-as-copy` file is installed as a real copy instead of a link;
- its configuration, `<brain>/.data/work-config.json`:
  `{"version": 1, "skills": {"thirdParty": {"<name>": {"source": ..., "sourceType": ...,
  "skillPath": ..., "computedHash": ...}}, "disabled": []}}`.

Layers, the later one wins: (1) `work-config.example.json` (public defaults),
(2) each brain's work-config.json, `brain/` first then the others by name,
(3) the ignored `work-config.local.json` (same schema, machine-specific).
A third-party name defined in two layers must have identical entries, except that
the local layer may override. An own-skill name found in two brains is an error.
`disabled` names, unioned over all layers, are not exposed to agents.

Commands: check, list-brains, list-own, list-third-party, list-catalog, lock, adopt,
stamp, status. `lock` writes the ignored skills-lock.json and refuses to overwrite
entries that no layer knows (installed with `npx skills add`): `adopt` records them
in a brain first. `stamp` writes .work-state.json with a hash of the resolved
configuration (third-party entries, disabled names, own skills with brain and mode);
`status` tells whether it changed since. Set WORK_DIR to use another workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("WORK_DIR", Path(__file__).resolve().parents[2])).resolve()
EXAMPLE = ROOT / "work-config.example.json"
LOCAL = ROOT / "work-config.local.json"
LOCK = ROOT / "skills-lock.json"
STATE = ROOT / ".work-state.json"
DEFAULT_BRAIN = "brain"
BRAIN_NAME = re.compile(r"^brain(-[a-z0-9][a-z0-9-]*)?$")
SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ENTRY_KEYS = ("source", "sourceType", "skillPath", "computedHash")
COPY_MARKER = ".install-as-copy"
EMPTY_LAYER: dict[str, Any] = {"version": 1, "skills": {"thirdParty": {}, "disabled": []}}


class ConfigError(ValueError):
    """A Work configuration is invalid."""


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"invalid JSON in {rel(path)}: {error}") from error
    except OSError as error:
        raise ConfigError(f"cannot read {rel(path)}: {error.strerror}") from error


def write_json(path: Path, value: Any) -> None:
    """Write deterministic JSON (sorted keys, 2 spaces, trailing newline) so merges stay clean."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def emit(lines: list[str]) -> None:
    """Print one item per line, nothing at all for an empty list."""
    if lines:
        print("\n".join(lines))


def discover_brains() -> list[Path]:
    """Brains at the Work root (same rule as tools/brain/brain-state.py), `brain/` first."""
    found = [
        path
        for path in ROOT.iterdir()
        if path.is_dir() and BRAIN_NAME.fullmatch(path.name) and (path / "AGENTS.md").is_file() and (path / ".data").is_dir()
    ]
    return sorted(found, key=lambda path: (path.name != DEFAULT_BRAIN, path.name))


def check_name(name: Any, label: str) -> str:
    if not isinstance(name, str) or not SKILL_NAME.fullmatch(name):
        raise ConfigError(f"{label}: invalid skill name {name!r} (lowercase letters, digits, - and _)")
    return name


def check_entry(entry: Any, label: str) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ConfigError(f"{label} must be an object")
    for key in ENTRY_KEYS:
        if not isinstance(entry.get(key), str) or not entry[key]:
            raise ConfigError(f"{label} needs a non-empty string {key}")
    return entry


def parse_layer(data: Any, label: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Validate one layer; return its third-party entries and disabled names."""
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ConfigError(f"{label}: must be an object with version 1")
    unknown = sorted(set(data) - {"version", "skills"})
    if unknown:
        raise ConfigError(f"{label}: unknown key(s): {', '.join(unknown)}")
    skills = data.get("skills", {})
    if not isinstance(skills, dict):
        raise ConfigError(f"{label}: skills must be an object")
    unknown = sorted(set(skills) - {"thirdParty", "disabled"})
    if unknown:
        raise ConfigError(f"{label}: unknown key(s) in skills: {', '.join(unknown)}")

    third_party = skills.get("thirdParty", {})
    if not isinstance(third_party, dict):
        raise ConfigError(f"{label}: skills.thirdParty must be an object of skill entries")
    for name, entry in third_party.items():
        check_name(name, f"{label}: skills.thirdParty")
        check_entry(entry, f"{label}: skills.thirdParty.{name}")

    disabled = skills.get("disabled", [])
    if not isinstance(disabled, list):
        raise ConfigError(f"{label}: skills.disabled must be a list of skill names")
    for name in disabled:
        check_name(name, f"{label}: skills.disabled")
    if len(disabled) != len(set(disabled)):
        raise ConfigError(f"{label}: skills.disabled contains duplicates")
    return third_party, disabled


def layer_files() -> list[tuple[str, Path]]:
    """Existing configuration files in precedence order (the last one wins)."""
    files = [(rel(EXAMPLE), EXAMPLE)]
    files += [(rel(b / ".data/work-config.json"), b / ".data/work-config.json") for b in discover_brains()]
    files.append((rel(LOCAL), LOCAL))
    return [(label, path) for label, path in files if path.is_file()]


def own_skills() -> dict[str, dict[str, Any]]:
    """Skills found in `<brain>/skills/`, by name; the same name in two brains is an error."""
    own: dict[str, dict[str, Any]] = {}
    for brain in discover_brains():
        folder = brain / "skills"
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if path.name.startswith(".") or not path.is_dir() or not (path / "SKILL.md").is_file():
                continue
            name = check_name(path.name, rel(path))
            if name in own:
                raise ConfigError(f"own skill {name} exists in two brains: {rel(own[name]['path'])} and {rel(path)}")
            own[name] = {"brain": brain.name, "path": path, "mode": "copy" if (path / COPY_MARKER).is_file() else "link"}
    return own


def resolve() -> dict[str, Any]:
    """Merge every layer and the own skills; raise ConfigError on any problem."""
    third_party: dict[str, dict[str, Any]] = {}
    origin: dict[str, str] = {}
    disabled: set[str] = set()
    for label, path in layer_files():
        layer_third_party, layer_disabled = parse_layer(read_json(path), label)
        for name, entry in layer_third_party.items():
            if name in third_party and third_party[name] != entry and path != LOCAL:
                raise ConfigError(f"third-party skill {name} is defined differently in {origin[name]} and {label}")
            third_party[name], origin[name] = entry, label
        disabled.update(layer_disabled)
    own = own_skills()
    clash = sorted(set(own) & set(third_party))
    if clash:
        raise ConfigError(f"skill(s) both own and third-party: {', '.join(clash)}")
    return {"thirdParty": third_party, "disabled": sorted(disabled), "own": own}


def enabled_own(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: skill for name, skill in sorted(config["own"].items()) if name not in config["disabled"]}


def enabled_third_party(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: entry for name, entry in sorted(config["thirdParty"].items()) if name not in config["disabled"]}


def config_hash(config: dict[str, Any]) -> str:
    canonical = {
        "disabled": config["disabled"],
        "own": {name: {"brain": skill["brain"], "mode": skill["mode"]} for name, skill in config["own"].items()},
        "thirdParty": config["thirdParty"],
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def lock_entries() -> dict[str, Any]:
    """Skills listed by the existing skills-lock.json (none when it is absent)."""
    if not LOCK.is_file():
        return {}
    data = read_json(LOCK)
    if not isinstance(data, dict) or not isinstance(data.get("skills"), dict):
        raise ConfigError(f"{rel(LOCK)} needs a skills object")
    return data["skills"]


def unknown_lock_entries(config: dict[str, Any]) -> dict[str, Any]:
    """Lock entries that no configuration layer knows: they come from `npx skills add`."""
    return {name: entry for name, entry in lock_entries().items() if name not in config["thirdParty"]}


def lock(config: dict[str, Any]) -> None:
    unknown = unknown_lock_entries(config)
    if unknown:
        raise ConfigError(
            f"{rel(LOCK)} lists skills that are in no work config: {', '.join(sorted(unknown))}. "
            "Run `uv run tools/machine/work_config.py adopt [--brain NAME]` to record them in a brain, "
            f"or remove these entries from {rel(LOCK)}"
        )
    skills = enabled_third_party(config)
    write_json(LOCK, {"version": 1, "skills": skills})
    print(f"{rel(LOCK)} written: {len(skills)} third-party skill(s)")


def adopt(config: dict[str, Any], brain_name: str) -> None:
    brains = {brain.name: brain for brain in discover_brains()}
    if brain_name not in brains:
        raise ConfigError(f"no brain named {brain_name} (found: {', '.join(brains) or 'none'})")
    unknown = unknown_lock_entries(config)
    if not unknown:
        print("Nothing to adopt: every skill of the lock is already in a work config")
        return
    for name, entry in unknown.items():
        check_name(name, rel(LOCK))
        check_entry(entry, f"{rel(LOCK)}: {name}")
    path = brains[brain_name] / ".data/work-config.json"
    data = read_json(path) if path.is_file() else json.loads(json.dumps(EMPTY_LAYER))
    parse_layer(data, rel(path))
    data.setdefault("skills", {}).setdefault("thirdParty", {}).update(unknown)
    write_json(path, data)
    for name in sorted(unknown):
        print(f"Adopted {name} into {rel(path)}")


def stamp_state(config: dict[str, Any]) -> str:
    """`current`, `changed` or `missing` (no usable .work-state.json) against the last stamp."""
    try:
        stamp = read_json(STATE).get("configHash") if STATE.is_file() else None
    except (ConfigError, AttributeError):
        stamp = None
    if stamp is None:
        return "missing"
    return "current" if stamp == config_hash(config) else "changed"


def status(config: dict[str, Any]) -> bool:
    state = stamp_state(config)
    if state == "missing":
        print(f"No valid {rel(STATE)}: run tools/machine/update.sh")
    elif state == "changed":
        print("Work configuration changed since the last update.sh: run tools/machine/update.sh")
    else:
        print("Work configuration unchanged since the last update.sh")
    return state == "current"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("check", "validate every layer and the skill names"),
        ("list-brains", "brains present at the Work root"),
        ("list-own", "enabled own skills: name, brain, link|copy"),
        ("list-third-party", "enabled third-party skills"),
        ("list-catalog", "every known third-party skill, enabled or not"),
        ("lock", "write skills-lock.json from the resolved third-party skills"),
        ("stamp", "record the resolved configuration in .work-state.json"),
        ("status", "exit 1 when the configuration changed since the last stamp"),
    ):
        sub.add_parser(name, help=text)
    adopt_parser = sub.add_parser("adopt", help="record the skills of skills-lock.json unknown to every layer")
    adopt_parser.add_argument("--brain", default=DEFAULT_BRAIN, help="brain that receives them (default: brain)")
    args = parser.parse_args()

    try:
        if args.command == "list-brains":
            emit([brain.name for brain in discover_brains()])
            return 0
        config = resolve()
        if args.command == "check":
            print(
                f"Work configuration OK: {len(config['own'])} own, {len(config['thirdParty'])} third-party, "
                f"{len(config['disabled'])} disabled"
            )
        elif args.command == "list-own":
            emit([f"{n}\t{s['brain']}\t{s['mode']}" for n, s in enabled_own(config).items()])
        elif args.command == "list-third-party":
            emit(list(enabled_third_party(config)))
        elif args.command == "list-catalog":
            emit(sorted(config["thirdParty"]))
        elif args.command == "lock":
            lock(config)
        elif args.command == "adopt":
            adopt(config, args.brain)
        elif args.command == "stamp":
            write_json(STATE, {"configHash": config_hash(config)})
            print(f"{rel(STATE)} written")
        elif args.command == "status":
            return 0 if status(config) else 1
        return 0
    except (ConfigError, OSError) as error:
        print(f"work config error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
