#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Map the brains of the workspace and merge their skill states.

A brain is a directory at the Work root named `brain` or `brain-*` that holds
an AGENTS.md and a .data/ folder. Each transcript belongs to exactly one brain:
its state lives only in that brain's .data/transcripts.json. A transcript is
new when no brain lists it.

The default brain (`brain/`, else the only brain, or the one named by `defaultBrain`
in work-config.local.json: see tools/machine/work_config.py) holds the shared
configuration: the input folders in .data/local-paths.json and, optionally, the
list of brains expected on every machine (`"brains": ["brain", "brain-perso"]`).
A missing expected brain stops the tool, so its transcripts never come back as new elsewhere.

Each brain is a trust boundary declared in its own .data/brain.json (`scope`,
`description`, ...). `brains` prints the scope and the description next to each
brain, so that an agent can pick the brain where new content belongs.

Commands (from the Work root, `uv run tools/brain/brain-state.py <command> --help` for details):

    map [--json] [--brain NAME] [--all]   where everything is: brains, clients, projects, pages, registers
    brains                                the brains found, with their scope and description
    transcripts [--new | --where FILE]    merged transcript states

`map` is the first command of a session: it replaces the exploration calls that locate the
brain, client, mission and register to work in. One block per brain (name, scope, `default`
mark, number of people pages, lines waiting in `inbox/inbox.md`), then one line per project,
grouped by client (with the client index page) and `internal`. A project is a folder holding
`state/actions.md`; its line gives:

    name, register ID prefix, actions to do / in progress / waiting / done (by `[ ]` `[/]` `[w]`
    `[x]`), `late` = unfinished actions whose `📅` date is before today (Europe/Paris), `dec` =
    decisions still proposed in `state/decisions.md`, `last` = date of the latest `## Timeline`
    entry of the page, and the page path from the Work root (`<project>/<project>.md`, flagged
    when missing). Archived projects (`projects/archive/…`, `projects/clients/<client>/archive/…`)
    are hidden unless `--all`, which flags them `[archived]`. `--brain NAME` keeps one brain.
    `--json` prints the same data with stable keys (`today`, then per brain `name`, `default`,
    `scope`, `people`, `inbox_lines`, `clients`, `internal`; per project `label`, `name`, `kind`,
    `client`, `archived`, `page`, `register`, `prefix`, `actions`, `decisions_proposed`,
    `last_timeline`). Read-only, no network. `inbox_lines` counts the non-empty lines below the
    first `---` of `inbox/inbox.md`, else below its title and quote, ignoring triage log lines.

Run from the Work root with `uv run tools/brain/brain-state.py`. Set WORK_DIR to use
another workspace and TRANSCRIPTS_DIR to override the transcript folder; ACTION_NOW
(`YYYY-MM-DD HH:MM`) fixes the clock of `map`, as for `action.py`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path


WORK = Path(os.environ.get("WORK_DIR", Path(__file__).resolve().parents[2])).resolve()
_spec = importlib.util.spec_from_file_location("work_config", Path(__file__).resolve().parents[1] / "machine/work_config.py")
assert _spec and _spec.loader
work_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(work_config)  # owns the rule of what a brain is and which one is the default


def default_brain() -> Path | None:
    """The default brain of the Work root (None: no brain, or several and no `defaultBrain` setting)."""
    try:
        return work_config.default_brain(WORK)
    except work_config.ConfigError as error:
        raise SystemExit(f"work config error: {error}") from None


def discover() -> list[Path]:
    """Brains present at the Work root, the default brain first."""
    try:
        return work_config.discover_brains(WORK)
    except work_config.ConfigError as error:
        raise SystemExit(f"work config error: {error}") from None


def shared_config() -> dict:
    default = default_brain()
    path = default / ".data/local-paths.json" if default else None
    return json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else {}


def check_expected(brains: list[Path]) -> None:
    expected = shared_config().get("brains", [])
    missing = [name for name in expected if not (WORK / name).is_dir() or not work_config.is_brain(WORK / name)]
    if missing:
        raise SystemExit(
            "expected brain(s) missing: " + ", ".join(missing)
            + " — clone or restore them before processing transcripts"
        )
    if not brains:
        raise SystemExit(f"no brain found in {WORK}")


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
        raise SystemExit("transcript listed by several brains: " + "; ".join(conflicts))
    return merged


def transcripts_dir() -> Path:
    if "TRANSCRIPTS_DIR" in os.environ:
        return Path(os.environ["TRANSCRIPTS_DIR"])
    relative = shared_config().get("transcripts_dir")
    if not relative:
        default = default_brain()
        raise SystemExit(
            f"transcripts_dir missing from {default.name}/.data/local-paths.json" if default
            else "no default brain (several brains): set defaultBrain in work-config.local.json to read transcripts_dir"
        )
    return Path.home() / relative


def boundary(brain: Path) -> dict:
    """The brain's .data/brain.json, or {} when it has none."""
    path = brain / ".data/brain.json"
    if not path.is_file():
        return {}
    try:
        declared = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"{brain.name}/.data/brain.json is unreadable: {error}") from None
    return declared if isinstance(declared, dict) else {}


def one_line(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def cmd_brains(brains: list[Path]) -> int:
    """One line per brain: name, tracked transcripts, scope, description (tab-separated)."""
    for brain in brains:
        state = brain / ".data/transcripts.json"
        count = len(json.loads(state.read_text(encoding="utf-8"))) if state.is_file() else 0
        declared = boundary(brain)
        print(f"{brain.name}\t{count} transcript(s) tracked\t{one_line(declared.get('scope'))}\t{one_line(declared.get('description'))}")
    return 0


def cmd_transcripts(brains: list[Path], new: bool, where: str | None) -> int:
    merged = load_transcripts(brains)
    if where:
        if where not in merged:
            print(f"{where}\tnot tracked")
            return 1
        owner, record = merged[where]
        print(f"{where}\t{owner}\t{record.get('status', '?')}")
        return 0
    if new:
        folder = transcripts_dir()
        try:
            names = sorted(p.name for p in folder.iterdir() if p.suffix == ".txt")
        except (FileNotFoundError, NotADirectoryError):
            raise SystemExit(f"transcripts folder not found: {folder}") from None
        except PermissionError:
            raise SystemExit(
                f"Access denied to the transcripts folder: {folder}. "
                "Check the macOS permissions and that the synced folder (OneDrive, for example) is available, then run again."
            ) from None
        except OSError as error:
            raise SystemExit(f"cannot read the transcripts folder: {folder} ({error.strerror})") from None
        for name in names:
            if name not in merged:
                print(name)
        return 0
    for key in sorted(merged):
        owner, record = merged[key]
        print(f"{record.get('status', '?')}\t{owner}\t{key}")
    return 0


# --- map: where everything is ---------------------------------------------------------------------

STATE_KEYS = {" ": "open", "/": "in_progress", "w": "waiting", "x": "done"}
TIMELINE_ENTRY = re.compile(r"^[-*]\s+(\d{4}-\d{2}-\d{2})\s+[—–-]")
PREFIX_HINT = re.compile(r"(?i:pr[eé]fix\w*)[^`\n]{0,40}`([A-Z]{2,5})`")
INBOX_SEPARATOR = re.compile(r"^-{3,}$")
INBOX_LOG = re.compile(r"^[-*]\s+\d{4}-\d{2}-\d{2}\s+[—–-]\s+triage\b", re.IGNORECASE)


def load_tools() -> tuple:
    """action.py and decision.py, loaded as decision.py does (one copy of action.py in sys.modules)."""
    here = Path(__file__).resolve().parent
    modules = []
    for file, name in (("action.py", "brain_action"), ("decision.py", "brain_decision")):
        module = sys.modules.get(name)
        if module is None:
            spec = importlib.util.spec_from_file_location(name, here / file)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        modules.append(module)
    return tuple(modules)


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def last_timeline(page: Path) -> str | None:
    """Date of the most recent `- YYYY-MM-DD — …` entry under the page's `## Timeline`."""
    if not page.is_file():
        return None
    inside, found = False, []
    for line in read_lines(page):
        if line.startswith("## "):
            inside = line[3:].strip().lower() == "timeline"
        elif inside and (entry := TIMELINE_ENTRY.match(line)):
            found.append(entry.group(1))
    return max(found) if found else None


def inbox_lines(brain: Path) -> int:
    """Non-empty lines of inbox/inbox.md left to triage: below the first `---`, else below the title and quote."""
    path = brain / "inbox/inbox.md"
    if not path.is_file():
        return 0
    lines = [line.strip() for line in read_lines(path)]
    separator = next((index for index, line in enumerate(lines) if INBOX_SEPARATOR.match(line)), None)
    if separator is not None:
        lines = lines[separator + 1:]
    else:
        start = 0
        while start < len(lines) and (not lines[start] or lines[start].startswith(("#", ">"))):
            start += 1
        lines = lines[start:]
    return sum(1 for line in lines if line and not INBOX_LOG.match(line))


def people_pages(brain: Path) -> int:
    folder = brain / "people"
    if not folder.is_dir():
        return 0
    return sum(1 for page in folder.glob("*.md") if page.is_file() and not page.is_symlink() and page.name.lower() != "readme.md")


def project_entry(brain: Path, name: str, register: Path, today: str, tools: tuple) -> dict:
    """One project (a folder holding state/actions.md) of the resolved `brain`, displayed under the brain's `name`."""
    action, decision = tools
    folder = register.parent.parent
    parts = register.relative_to(brain / "projects").parts[:-2]
    kind = "client" if parts[0] == "clients" else "internal"
    client = parts[1] if kind == "client" and len(parts) > 1 else None
    archived = parts[0] == "archive" or (kind == "client" and len(parts) > 2 and parts[2] == "archive")
    base = f"{name}/projects/{'/'.join(parts)}"
    page = folder / f"{folder.name}.md"

    lines = read_lines(register)
    counts = {"open": 0, "in_progress": 0, "waiting": 0, "done": 0, "overdue": 0}
    prefixes: Counter = Counter()
    for number, line in enumerate(lines, 1):
        if not line.startswith("- ["):
            continue
        parsed = action.parse_action(line, register, brain, number)
        if parsed is None:
            continue
        if parsed["state"] in STATE_KEYS:
            counts[STATE_KEYS[parsed["state"]]] += 1
        if parsed["state"] in action.OPEN_STATES and parsed["due"] and parsed["due"] < today:
            counts["overdue"] += 1
        prefixes[parsed["id"].split("-")[0]] += 1
    prefix = prefixes.most_common(1)[0][0] if prefixes else None
    if prefix is None:
        header = next((index for index, line in enumerate(lines) if line.startswith("## ")), len(lines))
        found = PREFIX_HINT.search("\n".join(lines[:header]))
        prefix = found.group(1) if found else None

    decisions = folder / "state/decisions.md"
    proposed = None
    if decisions.is_file() and not decisions.is_symlink():
        proposed = sum(1 for item in decision.parse(read_lines(decisions)) if item.state == "proposed")

    return {
        "label": action.project_label(register, brain),
        "name": folder.name,
        "kind": kind,
        "client": client,
        "archived": archived,
        "page": f"{base}/{folder.name}.md" if page.is_file() else None,
        "register": f"{base}/state/actions.md",
        "prefix": prefix,
        "actions": counts,
        "decisions_proposed": proposed,
        "last_timeline": last_timeline(page),
    }


def brain_map(brain: Path, default: Path | None, include_archived: bool, today: str, tools: tuple) -> dict:
    name = brain.name
    declared = boundary(brain)
    brain = brain.resolve()
    action = tools[0]
    registers = [register for register in action.registers(brain) if len(register.relative_to(brain / "projects").parts) > 2]
    projects = [project_entry(brain, name, register, today, tools) for register in registers]
    if not include_archived:
        projects = [project for project in projects if not project["archived"]]
    projects.sort(key=lambda project: (project["archived"], project["name"]))

    clients: dict[str, dict] = {}
    root = brain / "projects/clients"
    if root.is_dir():
        for folder in sorted(root.iterdir()):
            if folder.is_dir() and not folder.is_symlink() and not folder.name.startswith("."):
                index = folder / f"{folder.name}.md"
                page = f"{name}/projects/clients/{folder.name}/{folder.name}.md" if index.is_file() else None
                clients[folder.name] = {"name": folder.name, "page": page, "projects": []}
    for project in projects:
        if project["client"] is not None:
            clients.setdefault(project["client"], {"name": project["client"], "page": None, "projects": []})["projects"].append(project)
    return {
        "name": name,
        "default": default is not None and brain == default.resolve(),
        "scope": one_line(declared.get("scope")),
        "people": people_pages(brain),
        "inbox_lines": inbox_lines(brain),
        "clients": [clients[key] for key in sorted(clients)],
        "internal": [project for project in projects if project["client"] is None],
    }


def render_map(data: dict) -> str:
    """The map as text: a header per brain, then one aligned line per project, grouped by client."""
    out: list[str] = []
    for brain in data["brains"]:
        tags = ", ".join(tag for tag in (brain["scope"], "default" if brain["default"] else "") if tag)
        inbox = f"inbox {brain['inbox_lines']} to triage" if brain["inbox_lines"] else "inbox empty"
        out.append(f"{brain['name']}" + (f" ({tags})" if tags else "") + f" — people {brain['people']} — {inbox}")
        groups = [(f"client {client['name']}  {client['page'] or '(no index page)'}", client["projects"]) for client in brain["clients"]]
        if brain["internal"]:
            groups.append(("internal", brain["internal"]))
        shown = [project for _, projects in groups for project in projects]
        names = {id(project): project["name"] + (" [archived]" if project["archived"] else "") for project in shown}
        name_width = max(map(len, names.values()), default=0)
        prefix_width = max((len(project["prefix"] or "-") for project in shown), default=1)
        numbers = [value for project in shown for value in (*project["actions"].values(), project["decisions_proposed"]) if value is not None]
        digits = max((len(str(value)) for value in numbers), default=1)
        for title, projects in groups:
            out.append(f"  {title}")
            for project in projects:
                actions = project["actions"]
                proposed = "-" if project["decisions_proposed"] is None else str(project["decisions_proposed"])
                page = project["page"] or project["register"].removesuffix("/state/actions.md") + f"/{project['name']}.md (missing)"
                out.append(
                    f"    {names[id(project)]:<{name_width}}  {project['prefix'] or '-':<{prefix_width}}"
                    f"  open {actions['open']:>{digits}}  doing {actions['in_progress']:>{digits}}  wait {actions['waiting']:>{digits}}"
                    f"  done {actions['done']:>{digits}}  late {actions['overdue']:>{digits}}  dec {proposed:>{digits}}"
                    f"  last {project['last_timeline'] or '-':<10}  {page}"
                )
    out.append("")
    out.append("open/doing/wait/done: actions by state; late: unfinished actions past their due date; dec: proposed decisions; last: latest Timeline entry.")
    return "\n".join(out)


def cmd_map(brains: list[Path], only: str | None, as_json: bool, include_archived: bool) -> int:
    if only is not None:
        brains = [brain for brain in brains if brain.name == only]
        if not brains:
            raise SystemExit(f"unknown brain {only}: choose one of " + ", ".join(brain.name for brain in discover()))
    tools = load_tools()
    today = tools[0].now().date().isoformat()
    default = default_brain()
    data = {"today": today, "brains": [brain_map(brain, default, include_archived, today, tools) for brain in brains]}
    print(json.dumps(data, ensure_ascii=False, indent=2) if as_json else render_map(data))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("brains", help="list the brains found, their tracked transcripts, scope and description")
    mp = sub.add_parser("map", help="where everything is: brains, clients, projects, pages, registers and their state (read-only)")
    mp.add_argument("--json", action="store_true", help="structured output with stable keys instead of text")
    mp.add_argument("--brain", metavar="NAME", help="only this brain (as listed by `brains`)")
    mp.add_argument("--all", action="store_true", help="also show the archived projects, flagged [archived]")
    tr = sub.add_parser("transcripts", help="merged transcript states (status, brain, file)")
    group = tr.add_mutually_exclusive_group()
    group.add_argument("--new", action="store_true", help="transcripts listed by no brain")
    group.add_argument("--where", metavar="FILE", help="which brain owns FILE, and its status")
    args = parser.parse_args()

    brains = discover()
    check_expected(brains)
    if args.command == "brains":
        return cmd_brains(brains)
    if args.command == "map":
        return cmd_map(brains, args.brain, args.json, args.all)
    return cmd_transcripts(brains, args.new, args.where)


if __name__ == "__main__":
    sys.exit(main())
