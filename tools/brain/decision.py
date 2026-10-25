#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Propose, read and settle the decisions of a brain's registers (`projects/**/state/decisions.md`).

The register sits next to the project's `actions.md` and has three sections: `## Proposed`,
`## Accepted` and `## Rejected / superseded`. Each decision is a block:

    ### Title (2026-10-13, status: proposed)
    - **Context:** …
    - **Decision:** …
    - **Consequences:** …
    - **Source:** [Minutes of 13/10](../sources/2026-10/2026-10-13-cr-daily-migration.md)
    - **Accepted:** Owner, 2026-10-14.

Existing blocks vary (status missing from the title, `active`, optional `Follow-up`, `Superseded by`):
the parser tolerates all of it and a write only touches the block it moves or completes. Accepted
and rejected decisions are newest first. A brain written with the earlier French labels is converted
once with `uv run tools/brain/migrate-english.py`.

Commands (from the Work root, `uv run tools/brain/decision.py <command> --help` for details):

    list       [--project P] [--status proposed|accepted|rejected|all] [--table]
    show       REF --project P
    propose    --project P --title T --decision D --source S [--context C] [--consequences C] [--date D]
    accept     REF --project P [--on D] [--by NAME] [--note TEXT]
    reject     REF --project P [--on D] [--by NAME] [--reason TEXT]
    supersede  OLD --by NEW --project P [--on D]

REF is the number given by `list` for that project (rank in the register, 1..n) or a unique
substring of the title (case-insensitive). Numbers change when a decision moves: list again.
Every write accepts `--dry-run`. Output is JSON on stdout. Exit codes: 0 done, 2 invalid request,
3 not found, 4 conflict or ambiguous reference. `--brain PATH` or BRAIN_DIR selects another brain;
ACTION_NOW (`YYYY-MM-DD HH:MM`) fixes the clock for tests.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_ACTION = Path(__file__).resolve().with_name("action.py")
action = sys.modules.get("brain_action")
if action is None:
    _spec = importlib.util.spec_from_file_location("brain_action", _ACTION)
    assert _spec and _spec.loader
    action = importlib.util.module_from_spec(_spec)
    sys.modules["brain_action"] = action
    _spec.loader.exec_module(action)

ActionError = action.ActionError
EXIT = action.EXIT

STATES = ("proposed", "accepted", "rejected")
SECTIONS = {"proposed": "Proposed", "accepted": "Accepted", "rejected": "Rejected / superseded"}
STATUS = {"proposed": "proposed", "accepted": "accepted", "rejected": "rejected", "superseded": "superseded"}
FIELDS = {"context": "Context", "decision": "Decision", "consequences": "Consequences", "source": "Source",
          "accepted": "Accepted", "rejected": "Rejected", "superseded": "Superseded by"}
HEADER_RE = re.compile(r"^### (.+) \((\d{4}-\d{2}-\d{2})(?:, status\s*:\s*([^()]*))?\)\s*$")
FIELD_RE = re.compile(r"^- \*\*([^*]+?)\s*:\*\*\s*(.*)$")
QUOTE = "> Keep the source and status of each decision; an accepted decision is never rewritten: a new one supersedes it."


# --- Reading -------------------------------------------------------------------------------------


@dataclass
class Decision:
    start: int
    end: int  # exclusive, trailing blank lines excluded
    title: str
    date: str
    status: str  # as written in the title ("" when absent)
    section: str  # heading text
    state: str  # proposed | accepted | rejected | "" (unknown section)
    number: int


def section_state(heading: str) -> str:
    return {title.lower(): state for state, title in SECTIONS.items()}.get(heading.strip().lower(), "")


def parse(lines: list[str]) -> list[Decision]:
    found: list[Decision] = []
    section = ""
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("## "):
            section = line[3:].strip()
        if not line.startswith("### "):
            index += 1
            continue
        end = index + 1
        while end < len(lines) and not lines[end].startswith("#"):
            end += 1
        stop = end
        while stop > index + 1 and not lines[stop - 1].strip():
            stop -= 1
        match = HEADER_RE.match(line)
        if match:
            title, date, status = match.group(1).strip(), match.group(2), (match.group(3) or "").strip()
        else:
            title, date, status = line[4:].strip(), "", ""
        found.append(Decision(index, stop, title, date, status, section, section_state(section), len(found) + 1))
        index = end
    return found


def fields_of(lines: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in lines:
        match = FIELD_RE.match(line)
        if match and match.group(1) not in found:
            found[match.group(1)] = match.group(2).strip()
    return found


def decisions_path(brain: Path, project: str) -> Path:
    path = action.resolve_register(brain, project).parent / "decisions.md"
    if path.is_symlink():
        raise ActionError("bad_request", "decisions.md is a symbolic link.")
    return path


def read(path: Path) -> tuple[str, list[str]]:
    text = path.read_bytes().decode("utf-8")
    return text, text.splitlines()


def public(decision: Decision, project: str, register: str) -> dict:
    return {"project": project, "register": register, "number": decision.number, "section": decision.section,
            "state": decision.state, "title": decision.title, "date": decision.date, "status": decision.status}


def listing(brain: Path, project: str | None, status: str) -> list[dict]:
    actions = [action.resolve_register(brain, project)] if project else action.registers(brain)
    found = []
    for register in actions:
        path = register.parent / "decisions.md"
        if not path.is_file() or path.is_symlink():
            continue
        label, relative = action.project_label(register, brain), path.relative_to(brain).as_posix()
        for decision in parse(read(path)[1]):
            if status == "all" or decision.state == status:
                found.append(public(decision, label, relative))
    return found


def pick(found: list[Decision], ref: str) -> Decision:
    ref = ref.strip()
    if not ref:
        raise ActionError("bad_request", "Invalid decision reference.")
    if ref.isdigit():
        for decision in found:
            if decision.number == int(ref):
                return decision
        raise ActionError("not_found", f"No decision number {ref}.")
    wanted = ref.casefold()
    exact = [d for d in found if d.title.casefold() == wanted]
    matches = exact or [d for d in found if wanted in d.title.casefold()]
    if not matches:
        raise ActionError("not_found", f"No decision title contains “{ref}”.")
    if len(matches) > 1:
        names = "; ".join(f"no. {d.number} {d.title}" for d in matches[:5])
        raise ActionError("conflict", f"Ambiguous reference “{ref}” ({len(matches)} decisions): {names}. Use the number.")
    return matches[0]


def locate(brain: Path, project: str, ref: str) -> tuple[Path, str, list[str], list[Decision], Decision]:
    path = decisions_path(brain, project)
    if not path.is_file():
        raise ActionError("not_found", "This project has no decision register.")
    text, lines = read(path)
    found = parse(lines)
    return path, text, lines, found, pick(found, ref)


def show(brain: Path, project: str, ref: str) -> dict:
    path, _, lines, found, decision = locate(brain, project, ref)
    block = lines[decision.start:decision.end]
    return {**public(decision, action.project_label(action.resolve_register(brain, project), brain), path.relative_to(brain).as_posix()),
            "fields": fields_of(block), "block": block, "line": decision.start + 1}


# --- Writing -------------------------------------------------------------------------------------


def commit(path: Path, existing: str | None, lines: list[str], dry_run: bool) -> str:
    """Write the lines unless the file changed since it was read (None = it did not exist)."""
    eol = "\r\n" if existing and "\r\n" in existing else "\n"
    text = eol.join(lines) + eol
    if existing is not None and not existing.endswith(("\n", "\r\n")):
        text = text[:-len(eol)]
    current = path.read_bytes().decode("utf-8") if path.exists() else None
    if current != existing:
        raise ActionError("conflict", "The decision register has changed. Refresh before trying again.")
    if not dry_run:
        action.atomic_write(path, text.encode("utf-8"))
    return text


def header(title: str, date: str, status: str) -> str:
    return f"### {title} ({date}, status: {status})" if date else f"### {title} (status: {status})"


def with_status(line: str, status: str) -> str:
    match = HEADER_RE.match(line)
    if match:
        return header(match.group(1).strip(), match.group(2), status)
    return f"{line.rstrip()} (status: {status})"


def field(name: str, value: str) -> str:
    """A `- **Label:** value` line."""
    return f"- **{FIELDS[name]}:** {value}"


def section_range(lines: list[str], state: str) -> tuple[int, int] | None:
    for index, line in enumerate(lines):
        if line.startswith("## ") and section_state(line[3:]) == state:
            end = index + 1
            while end < len(lines) and not lines[end].startswith("## "):
                end += 1
            return index, end
    return None


def ensure_section(lines: list[str], state: str) -> tuple[int, int]:
    found = section_range(lines, state)
    if found is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines.extend(["", f"## {SECTIONS[state]}"])
        found = section_range(lines, state)
    assert found is not None
    return found


def remove(lines: list[str], start: int, end: int) -> None:
    del lines[start:end]
    while start < len(lines) and not lines[start].strip():
        del lines[start]
    if start >= len(lines):
        while lines and not lines[-1].strip():
            lines.pop()
    elif start > 0 and lines[start - 1].strip():
        lines.insert(start, "")


def insert_top(lines: list[str], state: str, block: list[str]) -> None:
    heading, _ = ensure_section(lines, state)
    probe = heading + 1
    while probe < len(lines) and not lines[probe].strip():
        probe += 1
    lines[heading + 1:probe] = ["", *block, ""] if probe < len(lines) else ["", *block]


def append_last(lines: list[str], state: str, block: list[str]) -> None:
    heading, end = ensure_section(lines, state)
    last = end
    while last > heading + 1 and not lines[last - 1].strip():
        last -= 1
    if last == heading + 1:  # empty section
        lines[heading + 1:end] = ["", *block, ""] if end < len(lines) else ["", *block]
        return
    lines[last:last] = ["", *block]
    after = last + 1 + len(block)
    if after < len(lines) and lines[after].strip():
        lines.insert(after, "")


def sentence(parts: str, note: str = "") -> str:
    return f"{parts}{f' ({note})' if note else ''}."


def propose(brain: Path, project: str, title: str, decision: str, source: str, context: str = "",
            consequences: str = "", date: str = "", dry_run: bool = False) -> dict:
    register = action.resolve_register(brain, project)
    path = decisions_path(brain, project)
    title = action.clean_text(title, "Title", 300)
    decision = action.clean_text(decision, "Decision", 1500)
    source = action.clean_note(source)
    context = action.clean_text(context, "Context", 1500) if context else ""
    consequences = action.clean_text(consequences, "Consequences", 1500) if consequences else ""
    day = action.parse_date(date, "Date") if date else action.today()
    if path.exists():
        existing, lines = read(path)
        if any(d.title.casefold() == title.casefold() for d in parse(lines)):
            raise ActionError("conflict", "A decision already has this title in this register.")
    else:
        existing = None
        name = action.project_name(register.read_text(encoding="utf-8").splitlines(), register)
        lines = [f"# Decisions — {name}", "", QUOTE, ""]
        for title_ in SECTIONS.values():
            lines += [f"## {title_}", ""]
        lines.pop()
    block = [header(title, day, STATUS["proposed"])]
    if context:
        block.append(field("context", context))
    block.append(field("decision", decision))
    if consequences:
        block.append(field("consequences", consequences))
    block.append(field("source", source))
    append_last(lines, "proposed", block)
    number = next(d.number for d in parse(lines) if d.title == title and d.state == "proposed")
    commit(path, existing, lines, dry_run)
    return {"register": path.relative_to(brain).as_posix(), "number": number, "title": title, "date": day,
            "label": f"proposal “{title}”", "block": block, "created_file": existing is None, "dry_run": dry_run}


def settle(brain: Path, project: str, ref: str, target: str, closing: str, *, note: str, verb: str, dry_run: bool) -> dict:
    """Move a proposed decision to the top of ``target`` (accepted or rejected) with its closing line."""
    path, existing, lines, _, decision = locate(brain, project, ref)
    if decision.state != "proposed":
        raise ActionError("bad_request", f"“{decision.title}” is already in “{decision.section or 'no section'}”: cannot {verb} it.")
    block = lines[decision.start:decision.end]
    block[0] = with_status(block[0], STATUS[target])
    block.append(field(target, sentence(closing, note)))
    remove(lines, decision.start, decision.end)
    insert_top(lines, target, block)
    commit(path, existing, lines, dry_run)
    return {"register": path.relative_to(brain).as_posix(), "title": decision.title, "from": decision.section,
            "to": SECTIONS[target], "label": f"{verb} “{decision.title}”", "block": block, "dry_run": dry_run}


def decision_owner(brain: Path, by: str = "") -> str:
    if by.strip():
        return action.clean_text(by, "Name", 120)
    try:
        return action.clean_text(action.board_owner(brain), "Name", 120)
    except (OSError, json.JSONDecodeError, SystemExit):
        raise ActionError(
            "bad_request",
            f"Unknown owner: use --by, BRAIN_OWNER or “owner” in {brain.name}/.data/doctor.json.",
        ) from None


def accept(brain: Path, project: str, ref: str, on: str = "", by: str = "", note: str = "", dry_run: bool = False) -> dict:
    day = action.parse_date(on, "Date") if on else action.today()
    who = decision_owner(brain, by)
    extra = action.clean_note(note) if note else ""
    return settle(brain, project, ref, "accepted", f"{who}, {day}", note=extra, verb="accept", dry_run=dry_run)


def reject(brain: Path, project: str, ref: str, on: str = "", by: str = "", reason: str = "", dry_run: bool = False) -> dict:
    day = action.parse_date(on, "Date") if on else action.today()
    who = decision_owner(brain, by)
    extra = action.clean_note(reason) if reason else ""
    return settle(brain, project, ref, "rejected", f"{who}, {day}", note=extra, verb="reject", dry_run=dry_run)


def supersede(brain: Path, project: str, old: str, new: str, on: str = "", dry_run: bool = False) -> dict:
    day = action.parse_date(on, "Date") if on else action.today()
    path, existing, lines, found, target = locate(brain, project, new)
    previous = pick(found, old)
    if previous.number == target.number:
        raise ActionError("bad_request", "A decision cannot supersede itself.")
    if target.state == "rejected":
        raise ActionError("bad_request", f"“{target.title}” is rejected or superseded: it cannot supersede another decision.")
    if previous.state not in {"proposed", "accepted"}:
        raise ActionError("bad_request", f"“{previous.title}” is already in “{previous.section or 'no section'}”: cannot supersede it.")
    block = lines[previous.start:previous.end]
    block[0] = with_status(block[0], STATUS["superseded"])
    block.append(field("superseded", f"“{target.title}” ({day})."))
    remove(lines, previous.start, previous.end)
    insert_top(lines, "rejected", block)
    commit(path, existing, lines, dry_run)
    return {"register": path.relative_to(brain).as_posix(), "title": previous.title, "superseded_by": target.title,
            "from": previous.section, "to": SECTIONS["rejected"], "label": f"supersede “{previous.title}”",
            "block": block, "dry_run": dry_run}


# --- Command line --------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Propose, read and settle the decisions of the brain's registers (JSON output).")
    parser.add_argument("--brain", action="append", type=Path, metavar="PATH", help="brain to use (default: BRAIN_DIR, else the default brain of Work)")
    sub = parser.add_subparsers(dest="command", required=True)
    project_help = "register, project folder, client/mission or label"

    def writable(p: argparse.ArgumentParser) -> None:
        p.add_argument("--dry-run", action="store_true", help="print the result without writing")

    p = sub.add_parser("list", help="list the decisions")
    p.add_argument("--project", help=project_help)
    p.add_argument("--status", choices=(*STATES, "all"), default="all", metavar="{proposed,accepted,rejected,all}")
    p.add_argument("--table", action="store_true", help="one line per decision instead of JSON")

    p = sub.add_parser("show", help="show a decision")
    p.add_argument("ref", help="number from list or unique substring of the title")
    p.add_argument("--project", required=True, help=project_help)

    p = sub.add_parser("propose", help="add a decision at the end of “Proposed”")
    p.add_argument("--project", required=True, help=project_help)
    p.add_argument("--title", required=True)
    p.add_argument("--decision", required=True)
    p.add_argument("--source", required=True, help="text of the Source line (Markdown link relative to the register)")
    p.add_argument("--context", default="")
    p.add_argument("--consequences", default="")
    p.add_argument("--date", default="", help="date of the decision YYYY-MM-DD (default: today)")
    writable(p)

    p = sub.add_parser("accept", help="move a proposed decision to the top of “Accepted”")
    p.add_argument("ref")
    p.add_argument("--project", required=True, help=project_help)
    p.add_argument("--on", default="", help="date of the acceptance YYYY-MM-DD (default: today)")
    p.add_argument("--by", default="", help="person who accepts (default: the brain owner)")
    p.add_argument("--note", default="")
    writable(p)

    p = sub.add_parser("reject", help="move a proposed decision to the top of “Rejected / superseded”")
    p.add_argument("ref")
    p.add_argument("--project", required=True, help=project_help)
    p.add_argument("--on", default="")
    p.add_argument("--by", default="", help="person who rejects (default: the brain owner)")
    p.add_argument("--reason", default="")
    writable(p)

    p = sub.add_parser("supersede", help="mark a decision as superseded by another one")
    p.add_argument("old")
    p.add_argument("--by", required=True, dest="new", help="decision that supersedes it (number or title)")
    p.add_argument("--project", required=True, help=project_help)
    p.add_argument("--on", default="")
    writable(p)
    return parser


def run(args: argparse.Namespace) -> object:
    brain = (args.brain[0] if args.brain else action.BRAIN).expanduser().resolve()
    if not (brain / "projects").is_dir():
        raise ActionError("not_found", f"No registers under {brain / 'projects'}")
    if args.command == "list":
        return listing(brain, args.project, args.status)
    if args.command == "show":
        return show(brain, args.project, args.ref)
    if args.command == "propose":
        return propose(brain, args.project, args.title, args.decision, args.source, args.context, args.consequences,
                       args.date, args.dry_run)
    if args.command == "accept":
        return accept(brain, args.project, args.ref, args.on, args.by, args.note, args.dry_run)
    if args.command == "reject":
        return reject(brain, args.project, args.ref, args.on, args.by, args.reason, args.dry_run)
    return supersede(brain, args.project, args.old, args.new, args.on, args.dry_run)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run(args)
    except ActionError as error:
        print(json.dumps({"error": error.message, "kind": error.kind}, ensure_ascii=False))
        return EXIT[error.kind]
    except (OSError, UnicodeDecodeError) as error:
        print(json.dumps({"error": str(error), "kind": "conflict"}, ensure_ascii=False))
        return EXIT["conflict"]
    if args.command == "list" and args.table:
        for item in result:  # type: ignore[union-attr]
            status = item["status"] or item["state"] or "?"
            print(f"{item['number']:>3}. [{status}] {item['date'] or '----------'} — {item['title']}  ({item['project']})")
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
