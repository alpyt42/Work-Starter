#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Create, read and edit the actions of a brain's registers (`projects/**/state/actions.md`).

One tool for the agents (command line) and for the local web interface (tasks-web runs it for
every write), so that an action is always written the same way:

    - [ ] **DEM-101** — Owner — Title ⏫ ➕ 2026-10-13 📅 2026-10-20
        - source: [Minutes of 13/10](../sources/2026-10/2026-10-13-cr-demo.md)
        - created: 2026-10-13 14:32
        - updated: 2026-10-14 09:05
        - 14/10: history entry

`➕` carries the creation date for the Obsidian Tasks plugin, which reads dates only; the
`created:` sub-bullet keeps the creation date and time (Europe/Paris, to the minute). Both are
written once, at creation. `updated:` is rewritten by every change made through this tool
(fields, status, history). The due date stays `📅` on the line.

A group of tasks is a label, not a parent task: at most one `#group/<slug>` tag at the end
of the title, just before the Tasks emojis (`… Title #group/ingestion-workshop ➕ 2026-10-13`).
`--group SLUG` writes it (`--group ""` on `update` removes it, no option keeps it); a `--title`
that itself ends with a valid `#group/…` tag is refused (use `--group`).

A brain written with the earlier French labels is converted once with
`uv run tools/brain/migrate-english.py`.

Commands (from the Work root, `uv run tools/brain/action.py <command> --help` for details):

    list      [--project P] [--state open|closed|all] [--owner O] [--table]
    board     [--write [PATH]] [--watch]     complete view by project (terminal, VS Code preview)
    show      ID
    create    --project P --title T --owner O --source S [--state] [--priority] [--due]
              [--scheduled] [--due-note N] [--group SLUG] [--prefix XXX]
    update    ID [--title] [--owner] [--state] [--priority] [--due] [--scheduled] [--group SLUG]
              [--closed-on D]
    history   add ID --text T [--date D]  |  edit ID --index N --text T [--date D]  |  remove ID --index N
    move      ID --to P                      to another register of the same client, ID unchanged
    check     [--register R]                 format errors (exit 1) and warnings of the registers
    delete    ID
    sweep     [--write|--check] [--archive] [--register R]   put each action under its state's section
    archive   [--write|--check] [--days N] [--today D]       move old closures to actions-archive-YYYY.md

Every write accepts `--dry-run` (print the result, write nothing) and the optimistic-lock options
`--expect-version` (hash of the action line) and `--expect-details-version` (hash of the block)
used by the web interface. A status change moves the action to the section of its state (the
`sweep`, for this action only); a closure gets `✅`/`❌` with today's date, or
`--closed-on` for the date of the evidence; a reopening drops it.

Output is JSON on stdout. Exit codes: 0 done, 2 invalid request, 3 not found, 4 conflict.
`--brain PATH` or BRAIN_DIR selects another brain; ACTION_NOW (`YYYY-MM-DD HH:MM`) fixes the
clock for tests.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

WORK = Path(os.environ.get("WORK_DIR", Path(__file__).resolve().parents[2])).resolve()


def default_brain_dir() -> Path:
    """The default brain of WORK (rule of tools/machine/work_config.py); `WORK/brain` when there is none."""
    spec = importlib.util.spec_from_file_location("work_config", Path(__file__).resolve().parents[1] / "machine/work_config.py")
    assert spec and spec.loader
    work_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(work_config)
    try:
        return work_config.default_brain(WORK) or WORK / "brain"
    except work_config.ConfigError as error:
        raise SystemExit(f"work config error: {error}") from None
    except OSError:
        return WORK / "brain"


BRAIN = Path(os.environ["BRAIN_DIR"] if "BRAIN_DIR" in os.environ else default_brain_dir()).resolve()

# --- Registers: sections and archive (formerly manage-action.py) -------------------------------------

ACTION = re.compile(r"^- \[(.)\] \*\*([A-Z]{2,5}-\d{3})\*\*")
CLOSED_ON = re.compile(r"[✅❌]\s*(\d{4}-\d{2}-\d{2})\b")
H1_PROJECT = re.compile(r"^#\s+Actions\s*[—–-]\s*(.+?)\s*$")
DEFAULT_DAYS = 30

TITLES = {"open": "Open", "done": "Done", "cancelled": "Cancelled"}
SECTION_KEYS = {title.lower(): key for key, title in TITLES.items()}


def section_key(title: str) -> str | None:
    """`open`, `done` or `cancelled` for a section title, else None."""
    return SECTION_KEYS.get(title.strip().lower())


def history_prefix(day: str) -> str:
    """The `DD/MM: ` prefix of a history entry for an ISO day."""
    return f"{day[8:10]}/{day[5:7]}: "


class ArchiveError(Exception):
    """A register cannot be archived; nothing was written for it."""


@dataclass
class Block:
    """An action line with its indented sub-bullets (and the blank lines between them)."""

    start: int
    end: int  # exclusive
    action_id: str
    state: str
    closed: date | None
    invalid_date: str | None
    section: str  # lower-cased `## ` heading the block sits under


@dataclass
class Plan:
    register: Path
    moves: dict[int, list[Block]] = field(default_factory=dict)  # year -> blocks
    outputs: dict[Path, str] = field(default_factory=dict)  # file -> new text
    warnings: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(len(blocks) for blocks in self.moves.values())


def paris_today() -> date:
    return datetime.now(ZoneInfo("Europe/Paris")).date()


def parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date '{value}' (expected YYYY-MM-DD)") from None


def split_text(text: str) -> tuple[list[str], str]:
    """Lines (the last item is '' when the text ends with a newline) and the line ending."""
    eol = "\r\n" if "\r\n" in text else "\n"
    return text.split(eol), eol


def parse_blocks(lines: list[str]) -> list[Block]:
    blocks: list[Block] = []
    section = ""
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("## "):
            section = line[3:].strip().lower()
        match = ACTION.match(line)
        if not match:
            index += 1
            continue
        state, action_id = match.groups()
        end = index + 1
        while end < len(lines):
            probe = end
            while probe < len(lines) and not lines[probe].strip():
                probe += 1
            if probe < len(lines) and lines[probe].startswith("    ") and lines[probe].strip():
                end = probe + 1
            else:
                break
        closed = None
        invalid = None
        found = CLOSED_ON.findall(line)
        if found:
            try:
                closed = date.fromisoformat(found[-1])
            except ValueError:
                invalid = found[-1]
        blocks.append(Block(index, end, action_id, state, closed, invalid, section))
        index = end
    return blocks


def project_name(register_lines: list[str], register: Path) -> str:
    for line in register_lines:
        if line.startswith("# "):
            found = H1_PROJECT.match(line)
            if found:
                return found.group(1)
            break
    return register.parent.parent.name


def new_archive(project: str, year: int) -> list[str]:
    title = f"# Actions archive {year} — {project}"
    quote = f"> Closed actions of {project} archived for {year}; the live register is [actions.md](actions.md). IDs stay reserved."
    return [title, "", quote, "", f"## {TITLES['done']}", "", f"## {TITLES['cancelled']}", ""]


def section_bounds(lines: list[str], key: str) -> tuple[int, int] | None:
    """Heading index and end (exclusive) of the `open`, `done` or `cancelled` section, or None."""
    for index, line in enumerate(lines):
        if line.startswith("## ") and section_key(line[3:]) == key:
            end = index + 1
            while end < len(lines) and not lines[end].startswith("## "):
                end += 1
            return index, end
    return None


def insert_block(lines: list[str], key: str, block: list[str], closed: date) -> None:
    """Insert in the `key` section, before the first dated item that closed strictly earlier."""
    bounds = section_bounds(lines, key)
    if bounds is None:
        while lines and lines[-1] == "":
            lines.pop()
        lines.extend(["", f"## {TITLES[key]}", ""])
        bounds = section_bounds(lines, key)
    assert bounds is not None
    heading, end = bounds
    items = parse_blocks(lines[heading:end])
    position = None
    for item in items:
        if item.closed is not None and item.closed < closed:
            position = heading + item.start
            break
    if position is None:
        position = heading + items[-1].end if items else heading + 1
    lines[position:position] = block
    after = position + len(block)
    if after < len(lines) and lines[after].startswith("## "):
        lines.insert(after, "")


def tidy_junctions(lines: list[str], junctions: list[int]) -> list[str]:
    """Repair the blank lines where blocks were removed (positions index the kept lines)."""
    for position in sorted(set(junctions), reverse=True):
        if position >= len(lines):
            while len(lines) > 1 and lines[-1] == "" and lines[-2] == "":
                lines.pop()
            continue
        before = lines[position - 1] if position else ""
        if position and before == "" and lines[position] == "":
            del lines[position]
        elif before.startswith("## ") and lines[position] == "":
            probe = position
            while probe < len(lines) and lines[probe] == "":
                probe += 1
            if probe < len(lines) and not lines[probe].startswith("#"):
                del lines[position:probe]
    return lines


def plan_register(register: Path, today: date, days: int) -> Plan:
    plan = Plan(register)
    raw = register.read_bytes().decode("utf-8")
    lines, eol = split_text(raw)
    cutoff = today - timedelta(days=days)
    blocks = parse_blocks(lines)

    selected: list[Block] = []
    for block in blocks:
        if block.state not in STATE_SECTION or STATE_SECTION[block.state] == "open":
            continue
        if block.invalid_date:
            plan.warnings.append(f"{block.action_id}: invalid closing date {block.invalid_date}, left in the register")
            continue
        if block.closed is None or block.closed >= cutoff:
            continue
        if section_key(block.section) not in {"done", "cancelled"}:
            plan.warnings.append(f"{block.action_id} closed on {block.closed.isoformat()} but filed under '{block.section or 'no section'}': file it under {TITLES['done']} or {TITLES['cancelled']} first, not moved")
            continue
        selected.append(block)
    if not selected:
        return plan

    seen: set[str] = set()
    for block in selected:
        if block.action_id in seen:
            raise ArchiveError(f"ID {block.action_id} appears several times in the register")
        seen.add(block.action_id)
    for archive in sorted(register.parent.glob("actions-archive-*.md")):
        if archive.is_symlink():
            raise ArchiveError(f"{archive.name} is a symbolic link")
        known = {m.group(2) for m in map(ACTION.match, archive.read_text(encoding="utf-8").splitlines()) if m}
        clash = sorted(seen & known)
        if clash:
            raise ArchiveError(f"ID already in {archive.name}: {', '.join(clash)} (nothing is written for this register)")

    project = project_name(lines, register)
    by_year: dict[int, list[Block]] = {}
    for block in selected:
        assert block.closed is not None
        by_year.setdefault(block.closed.year, []).append(block)
    for year, year_blocks in sorted(by_year.items()):
        target = register.parent / f"actions-archive-{year}.md"
        if target.is_symlink():
            raise ArchiveError(f"{target.name} is a symbolic link")
        if target.exists():
            archive_lines, archive_eol = split_text(target.read_bytes().decode("utf-8"))
        else:
            archive_lines, archive_eol = new_archive(project, year), eol
        # Stable sort newest first: equal dates keep register order, after existing ones.
        for block in sorted(year_blocks, key=lambda item: item.closed, reverse=True):  # type: ignore[arg-type, return-value]
            assert block.closed is not None
            insert_block(archive_lines, STATE_SECTION[block.state], lines[block.start:block.end], block.closed)
        plan.outputs[target] = archive_eol.join(archive_lines)
        plan.moves[year] = year_blocks

    removed = {i for block in selected for i in range(block.start, block.end)}
    kept: list[str] = []
    junctions: list[int] = []
    for index, line in enumerate(lines):
        if index in removed:
            if index - 1 not in removed:
                junctions.append(len(kept))
            continue
        kept.append(line)
    tidy = tidy_junctions(kept, junctions)
    if raw and not raw.endswith(eol):
        while tidy and tidy[-1] == "":
            tidy.pop()
    plan.outputs[register] = eol.join(tidy)
    return plan


def atomic_write_text(path: Path, text: str) -> None:
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with open(temp, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def apply_plan(plan: Plan) -> None:
    """Archives first, register last; restore the archives if any write fails."""
    snapshots: dict[Path, bytes | None] = {}
    order = [path for path in plan.outputs if path != plan.register] + [plan.register]
    try:
        for path in order:
            snapshots[path] = path.read_bytes() if path.exists() else None
            atomic_write_text(path, plan.outputs[path])
    except Exception:
        for path, previous in snapshots.items():
            try:
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write_text(path, previous.decode("utf-8"))
            except OSError:
                pass
        raise


def registers_of(brain: Path) -> list[Path]:
    found = []
    for register in sorted((brain / "projects").glob("**/state/actions.md")):
        if register.is_symlink() or register.resolve() != register or not register.is_file():
            continue
        if brain not in register.parents:
            continue
        found.append(register)
    return found


def display(path: Path) -> str:
    try:
        return path.relative_to(WORK).as_posix()
    except ValueError:
        return path.as_posix()


OPEN_STATES = {" ", "/", "w"}
DONE_STATES = {"x", "X"}
CANCELLED_STATES = {"-"}
STATE_SECTION = {**{s: "done" for s in DONE_STATES}, **{s: "cancelled" for s in CANCELLED_STATES}, **{s: "open" for s in OPEN_STATES}}


@dataclass
class SweepPlan:
    register: Path
    moves: list[tuple[str, str, str]] = field(default_factory=list)  # (id, from, to)
    warnings: list[str] = field(default_factory=list)
    output: str | None = None


def insert_open(lines: list[str], block: list[str]) -> None:
    """Append at the end of the `open` section."""
    bounds = section_bounds(lines, "open")
    assert bounds is not None
    heading, end = bounds
    items = parse_blocks(lines[heading:end])
    position = heading + items[-1].end if items else heading + 1
    lines[position:position] = block
    after = position + len(block)
    if after < len(lines) and lines[after].startswith("## "):
        lines.insert(after, "")


def plan_sweep(register: Path, today: date) -> SweepPlan:
    return sweep_text(register.read_bytes().decode("utf-8"), today, register)


def sweep_text(raw: str, today: date, register: Path, only: set[str] | None = None) -> SweepPlan:
    """Plan the sweep of a register text; `only` restricts it to those action IDs."""
    plan = SweepPlan(register)
    lines, eol = split_text(raw)
    blocks = parse_blocks(lines)

    seen: set[str] = set()
    for block in blocks:
        if block.action_id in seen:
            raise ArchiveError(f"ID {block.action_id} appears several times in the register")
        seen.add(block.action_id)

    selected = []
    for block in blocks:
        if only is not None and block.action_id not in only:
            continue
        target = STATE_SECTION.get(block.state)
        if target is None:
            plan.warnings.append(f"{block.action_id}: unknown state [{block.state}], left in place")
            continue
        if section_key(block.section) is None:
            plan.warnings.append(f"{block.action_id}: filed under '{block.section or 'no section'}', unknown section, left in place")
            continue
        if section_key(block.section) == target:
            continue
        if section_bounds(lines, target) is None:
            plan.warnings.append(f"{block.action_id}: section '{TITLES[target]}' missing from the register, left in place")
            continue
        if target != "open" and block.closed is None and not block.invalid_date:
            plan.warnings.append(f"{block.action_id}: closed without a ✅/❌ date, to date with the evidence")
        if block.invalid_date:
            plan.warnings.append(f"{block.action_id}: invalid closing date {block.invalid_date}")
        if target == "open" and (block.closed or block.invalid_date):
            plan.warnings.append(f"{block.action_id}: reopened but a ✅/❌ date remains on the line, to remove")
        selected.append((block, target))
    if not selected:
        return plan

    removed = {i for block, _ in selected for i in range(block.start, block.end)}
    kept: list[str] = []
    junctions: list[int] = []
    for index, line in enumerate(lines):
        if index in removed:
            if index - 1 not in removed:
                junctions.append(len(kept))
            continue
        kept.append(line)
    tidy = tidy_junctions(kept, junctions)

    # Open actions keep register order; closed ones go newest first (no date = newest).
    ordered = sorted(
        selected,
        key=lambda item: (item[1] != "open", -(item[0].closed or today).toordinal() if item[1] != "open" else item[0].start),
    )
    for block, target in ordered:
        text = lines[block.start:block.end]
        while text and not text[-1].strip():
            text.pop()
        if target == "open":
            insert_open(tidy, text)
        else:
            insert_block(tidy, target, text, block.closed or today)
        plan.moves.append((block.action_id, block.section, TITLES[target].lower()))

    if raw and not raw.endswith(eol):
        while tidy and tidy[-1] == "":
            tidy.pop()
    plan.output = eol.join(tidy)
    return plan


def run_archive(register: Path, name: str, today: date, args: argparse.Namespace) -> tuple[int, int]:
    """Returns (actions moved or to move, errors)."""
    try:
        plan = plan_register(register, today, args.days)
        if plan.count and args.write:
            apply_plan(plan)
    except (ArchiveError, OSError, UnicodeDecodeError) as error:
        print(f"ERROR {name}: {error}", file=sys.stderr)
        return 0, 1
    if not args.quiet:
        for warning in plan.warnings:
            print(f"WARNING {name}: {warning}")
        if plan.count:
            targets = " ; ".join(f"actions-archive-{year}.md ({', '.join(b.action_id for b in blocks)})" for year, blocks in sorted(plan.moves.items()))
            print(f"{name}: archive {plan.count} action(s){' moved' if args.write else ''} → {targets}")
    return plan.count, 0


def run_sweep(register: Path, name: str, today: date, args: argparse.Namespace) -> tuple[int, int]:
    try:
        plan = plan_sweep(register, today)
        if plan.output is not None and args.write:
            atomic_write_text(register, plan.output)
    except (ArchiveError, OSError, UnicodeDecodeError) as error:
        print(f"ERROR {name}: {error}", file=sys.stderr)
        return 0, 1
    if not args.quiet:
        for warning in plan.warnings:
            print(f"WARNING {name}: {warning}")
        for action_id, origin, target in plan.moves:
            print(f"{name}: sweep {action_id} {origin or 'no section'} → {target}")
    return len(plan.moves), 0


# --- Single actions ------------------------------------------------------------------------------

ACTION_RE = re.compile(r"^- \[([ /wx-])\] \*\*([A-Z]{2,5}-\d{3})\*\* — ([^—]+?) — (.+)$")
ID_RE = re.compile(r"\b([A-Z]{2,5})-(\d{3})\b")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CLOSURE_RE = re.compile(r"\s+[✅❌]\s+(\d{4}-\d{2}-\d{2})$")
CREATED_RE = re.compile(r"\s+➕\s+(\d{4}-\d{2}-\d{2})")
DUE_RE = re.compile(r"\s+📅\s+(\d{4}-\d{2}-\d{2})")
SCHEDULED_RE = re.compile(r"\s+⏳\s+(\d{4}-\d{2}-\d{2})")
PRIORITY_RE = re.compile(r"\s+(⏫|🔼|🔽)")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
SOURCE_RE = re.compile(r"-\s*source\s*:", re.IGNORECASE)
CREATED_AT_RE = re.compile(r"-\s*created\s*:\s*(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}))?", re.IGNORECASE)
UPDATED_AT_RE = re.compile(r"-\s*updated\s*:\s*(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}))?", re.IGNORECASE)
HISTORY_DATE_RE = re.compile(r"^    - (\d{2}/\d{2}: )")
MD_LINK_RE = re.compile(r"(\]\()([^)\s]+)(\))")
LOOSE_ACTION_RE = re.compile(r"^\s*[-*] \[.?\]\s*\*\*([A-Z]{2,5}-\d{3})\*\*")
PROTECTED_RE = re.compile(r"-\s*(source|created|updated)\s*:", re.IGNORECASE)
STATUS = {" ", "/", "w", "x", "-"}
PRIORITY = {"", "⏫", "🔼", "🔽"}
STATE_LABELS = {" ": "To do", "/": "In progress", "w": "Waiting", "x": "Done", "-": "Cancelled"}
STATE_ALIASES = {
    " ": " ", "todo": " ", "open": " ",
    "/": "/", "doing": "/", "in-progress": "/",
    "w": "w", "waiting": "w",
    "x": "x", "done": "x",
    "-": "-", "cancelled": "-", "canceled": "-",
}
PRIORITY_ALIASES = {
    "": "", "none": "", "normal": "",
    "⏫": "⏫", "high": "⏫",
    "🔼": "🔼", "medium": "🔼",
    "🔽": "🔽", "low": "🔽",
}
RESERVED = ("➕", "📅", "⏳", "⏫", "🔼", "🔽", "✅", "❌")
GROUP_LIMIT = 40
GROUP_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
GROUP_RE = re.compile(GROUP_SLUG)
GROUP_TAG_RE = re.compile(r"(?<!\S)#group/(\S*)")
TRAILING_GROUP_RE = re.compile(rf"\s+#group/({GROUP_SLUG})$")
EXIT = {"bad_request": 2, "not_found": 3, "conflict": 4}
TZ = ZoneInfo("Europe/Paris")


class ActionError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        self.message = message
        super().__init__(message)


# --- Clock and validation ------------------------------------------------------------------------


def now() -> datetime:
    fixed = os.environ.get("ACTION_NOW", "").strip()
    if fixed:
        return datetime.strptime(fixed, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    return datetime.now(TZ).replace(second=0, microsecond=0)


def today() -> str:
    return now().date().isoformat()


def parse_date(value: object, field: str) -> str:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise ActionError("bad_request", f"{field} must use the format YYYY-MM-DD.")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ActionError("bad_request", f"{field} is not a valid date.") from None
    return value


def optional_date(value: object, field: str) -> str:
    return "" if value in ("", None, "none") else parse_date(value, field)


def clean_text(value: object, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ActionError("bad_request", f"{field} is required.")
    value = value.strip()
    if not value or len(value) > limit or any(char in value for char in "\r\n\x00"):
        raise ActionError("bad_request", f"{field} must be 1 to {limit} characters on one line.")
    if (field == "Owner" and " — " in value) or any(marker in value for marker in RESERVED):
        raise ActionError("bad_request", f"{field} contains a separator reserved for registers.")
    return value


def valid_group(slug: str) -> bool:
    return len(slug) <= GROUP_LIMIT and GROUP_RE.fullmatch(slug) is not None


def clean_group(value: object) -> str:
    """A group slug, or '' for none."""
    slug = value.strip() if isinstance(value, str) else None
    if slug is None or (slug and not valid_group(slug)):
        raise ActionError("bad_request", f"Invalid group: lowercase letters, digits and hyphens (ingestion-workshop), {GROUP_LIMIT} characters at most.")
    return slug


def split_group(title: str) -> tuple[str, str]:
    """(title without its trailing `#group/<slug>` tag, slug); the title unchanged and '' when it has none."""
    match = TRAILING_GROUP_RE.search(title)
    if match and len(match.group(1)) <= GROUP_LIMIT:
        return title[:match.start()].rstrip(), match.group(1)
    return title, ""


def clean_title(value: object) -> str:
    title = clean_text(value, "Title", 300)
    if split_group(title)[1]:
        raise ActionError("bad_request", "The title must not end with a #group/… tag: use the Group field (--group).")
    return title


def clean_note(value: object) -> str:
    if not isinstance(value, str):
        raise ActionError("bad_request", "Invalid note.")
    note = value.strip()
    if not note or len(note) > 1000 or note.splitlines() != [note] or "\x00" in note:
        raise ActionError("bad_request", "The note must be 1 to 1000 characters on one line.")
    return note


def state_of(value: str) -> str:
    key = value if value in STATUS else value.strip().lower()
    if key not in STATE_ALIASES:
        raise ActionError("bad_request", "Invalid status or priority.")
    return STATE_ALIASES[key]


def priority_of(value: str) -> str:
    key = value.strip().lower() if value not in PRIORITY else value
    if key not in PRIORITY_ALIASES:
        raise ActionError("bad_request", "Invalid status or priority.")
    return PRIORITY_ALIASES[key]


# --- Reading -------------------------------------------------------------------------------------


def registers(brain: Path) -> list[Path]:
    root = (brain / "projects").resolve()
    found = []
    for path in sorted(root.glob("**/state/actions.md")):
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            continue
        found.append(path)
    return found


def project_label(register: Path, brain: Path) -> str:
    parts = register.relative_to(brain / "projects").parts[:-2]
    return f"{parts[1]} / {parts[3]}" if parts[0] == "clients" and len(parts) >= 4 else parts[-1]


def line_version(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()[:16]


def parse_action(line: str, register: Path, brain: Path, number: int) -> dict | None:
    match = ACTION_RE.match(line)
    if not match:
        return None
    state, action_id, owner, rest = match.groups()
    closure = CLOSURE_RE.search(rest)
    done = closure.group(1) if closure else ""
    rest = CLOSURE_RE.sub("", rest)
    created = CREATED_RE.search(rest)
    due = DUE_RE.search(rest)
    scheduled = SCHEDULED_RE.search(rest)
    priority = PRIORITY_RE.search(rest)
    title, group = split_group(PRIORITY_RE.sub("", SCHEDULED_RE.sub("", CREATED_RE.sub("", DUE_RE.sub("", rest)))).strip())
    return {
        "id": action_id,
        "state": state,
        "owner": owner.strip(),
        "title": LINK_RE.sub(r"\1", title),
        "raw_title": title,  # without the group tag, which is `group`: both go back to `update` as they are
        "group": group,
        "priority": priority.group(1) if priority else "",
        "created": created.group(1) if created else "",
        "created_at": created.group(1) if created else "",
        "updated_at": created.group(1) if created else "",
        "due": due.group(1) if due else "",
        "scheduled": scheduled.group(1) if scheduled else "",
        "done": done,
        "project": project_label(register, brain),
        "register": register.relative_to(brain).as_posix(),
        "line": number,
        "version": line_version(line),
    }


def last_detail(lines: list[str], index: int) -> int:
    """Index of the last indented line of the action's block (``index`` when it has none)."""
    last = index
    position = index + 1
    while position < len(lines) and (lines[position].startswith("    ") or not lines[position].strip()):
        if lines[position].strip():
            last = position
        position += 1
    return last


def items(lines: list[str], index: int, last: int) -> list[tuple[int, int]]:
    """Line ranges (start, end excluded) of the top-level sub-bullets of the action's block."""
    found = []
    position = index + 1
    while position <= last:
        if not lines[position].startswith("    - "):
            position += 1
            continue
        end = position + 1
        stop = end
        while end <= last and (lines[end].startswith("     ") or not lines[end].strip()):
            end += 1
            if lines[end - 1].strip():
                stop = end
        found.append((position, stop))
        position = stop
    return found


def item_text(lines: list[str], start: int, end: int) -> str:
    return "\n".join(line[4:] if line.strip() else "" for line in lines[start:end])


def stamp_of(lines: list[str], index: int, pattern: re.Pattern, fallback: str) -> str:
    for start, end in items(lines, index, last_detail(lines, index)):
        match = pattern.match(item_text(lines, start, end))
        if match:
            return f"{match.group(1)} {match.group(2)}" if match.group(2) else match.group(1)
    return fallback


def with_stamps(action: dict, lines: list[str], index: int) -> dict:
    action["created_at"] = stamp_of(lines, index, CREATED_AT_RE, action["created"])
    action["updated_at"] = stamp_of(lines, index, UPDATED_AT_RE, action["created_at"])
    return action


def stamp_updated(lines: list[str], index: int, moment: str) -> None:
    """Set the `updated:` sub-bullet of the action at ``index`` (after `created:` when it is added)."""
    stamp = f"    - updated: {moment}"
    found = items(lines, index, last_detail(lines, index))
    for start, end in found:
        if UPDATED_AT_RE.match(item_text(lines, start, end)):
            lines[start:end] = [stamp]
            return
    after = next((end for start, end in found if CREATED_AT_RE.match(item_text(lines, start, end))), None)
    if after is None:
        after = next((end for start, end in found if SOURCE_RE.match(item_text(lines, start, end))), last_detail(lines, index) + 1)
    lines.insert(after, stamp)


def load(register: Path, brain: Path) -> list[dict]:
    lines = register.read_text(encoding="utf-8").splitlines()
    found = []
    for index, line in enumerate(lines):
        action = parse_action(line, register, brain, index + 1)
        if action:
            found.append(with_stamps(action, lines, index))
    return found


def find(brain: Path, action_id: str) -> tuple[Path, list[str], int, dict]:
    found = []
    for path in registers(brain):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            action = parse_action(line, path, brain, index + 1)
            if action and action["id"] == action_id:
                found.append((path, lines, index, with_stamps(action, lines, index)))
    if len(found) != 1:
        raise ActionError("not_found" if not found else "conflict", "Action not found or duplicate ID.")
    return found[0]


def details(brain: Path, action_id: str) -> dict:
    _, lines, index, action = find(brain, action_id)
    last = last_detail(lines, index)
    block = lines[index + 1:last + 1]
    while block and not block[0].strip():
        block.pop(0)
    notes = [{"index": number, "text": (text := item_text(lines, start, end)), "deletable": not PROTECTED_RE.match(text)}
             for number, (start, end) in enumerate(items(lines, index, last))]
    version = hashlib.sha256("\n".join([lines[index], *lines[index + 1:last + 1]]).encode("utf-8")).hexdigest()[:16]
    return {**action, "details": [line[4:] if line.strip() else "" for line in block], "notes": notes, "details_version": version}


def resolve_register(brain: Path, project: str) -> Path:
    """A register from its path (brain- or Work-relative), its project folder, `client/mission` or label."""
    wanted = project.strip().strip("/")
    if not wanted:
        raise ActionError("bad_request", "Invalid project.")
    matches = []
    for path in registers(brain):
        relative = path.relative_to(brain).as_posix()
        folder = path.parent.parent.relative_to(brain / "projects").parts
        short = f"{folder[1]}/{folder[3]}" if folder[0] == "clients" and len(folder) >= 4 else folder[-1]
        candidates = {relative, f"{brain.name}/{relative}", path.parent.parent.relative_to(brain).as_posix(),
                      "/".join(folder), short, project_label(path, brain)}
        if wanted in candidates:
            matches.append(path)
    if len(matches) != 1:
        raise ActionError("bad_request", "Unknown project." if not matches else "Ambiguous project: give the register path.")
    return matches[0]


# --- Writing -------------------------------------------------------------------------------------


def action_line(action_id: str, title: str, owner: str, state: str, priority: str, created: str, due: str, scheduled: str, closure: str,
                group: str = "") -> str:
    return (f"- [{state}] **{action_id}** — {owner} — {title}"
            + (f" #group/{group}" if group else "")
            + (f" {priority}" if priority else "")
            + (f" ➕ {created}" if created else "")
            + (f" 📅 {due}" if due else "")
            + (f" ⏳ {scheduled}" if scheduled else "")
            + (f" {'✅' if state == 'x' else '❌'} {closure}" if state in {"x", "-"} and closure else ""))


def atomic_write(path: Path, data: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".actions-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def write(path: Path, existing: str, lines: list[str], dry_run: bool) -> str:
    text = "\n".join(lines) + ("\n" if existing.endswith("\n") else "")
    if path.read_text(encoding="utf-8") != existing:
        raise ActionError("conflict", "The register changed. Refresh before retrying.")
    if not dry_run:
        atomic_write(path, text.encode("utf-8"))
    return text


def check_versions(brain: Path, action_id: str, line_v: str | None, details_v: str | None) -> None:
    if line_v is not None and find(brain, action_id)[3]["version"] != line_v:
        raise ActionError("conflict", "The action changed in the register. Refresh before retrying.")
    if details_v is not None and details(brain, action_id)["details_version"] != details_v:
        raise ActionError("conflict", "The history changed in the register. Reopen the action before retrying.")


def next_id(brain: Path, register: Path, lines: list[str], prefix: str | None) -> str:
    own = {match.group(2).split("-")[0] for match in map(ACTION_RE.match, lines) if match}
    if prefix:
        prefix = prefix.strip().upper()
        if not re.fullmatch(r"[A-Z]{2,5}", prefix) or (own and own != {prefix}):
            raise ActionError("bad_request", "Invalid ID prefix for this register.")
    elif len(own) == 1:
        prefix = next(iter(own))
    else:
        raise ActionError("conflict", "Set an ID prefix in the register before creating actions.")
    parts = register.relative_to(brain / "projects").parts
    scope = brain / "projects" / parts[0] / parts[1]
    highest = 0
    for md in scope.rglob("*.md"):
        if md.is_symlink() or not md.resolve().is_relative_to(scope.resolve()):
            continue
        for match in ID_RE.finditer(md.read_text(encoding="utf-8")):
            if match.group(1) == prefix:
                highest = max(highest, int(match.group(2)))
    if highest >= 999:
        raise ActionError("conflict", "The ID series is exhausted.")
    return f"{prefix}-{highest + 1:03d}"


def create(brain: Path, project: str, title: str, owner: str, source: str, state: str = " ", priority: str = "",
           due: str = "", scheduled: str = "", due_note: str = "", prefix: str | None = None, dry_run: bool = False,
           group: str = "") -> dict:
    path = resolve_register(brain, project)
    title = clean_title(title)
    group = clean_group(group)
    owner = clean_text(owner, "Owner", 120)
    source = clean_note(source)
    state, priority = state_of(state), priority_of(priority)
    if state not in {" ", "/", "w"}:
        raise ActionError("bad_request", "A new action must be to do, in progress or waiting.")
    due, scheduled = optional_date(due, "Due date"), optional_date(scheduled, "Scheduled date")
    existing = path.read_text(encoding="utf-8")
    lines = existing.splitlines()
    action_id = next_id(brain, path, lines, prefix)
    moment = now()
    block = [action_line(action_id, title, owner, state, priority, moment.date().isoformat(), due, scheduled, "", group)]
    if due_note:
        block.append(f"    - due: {clean_note(due_note)}")
    block += [f"    - source: {source}", f"    - created: {moment:%Y-%m-%d %H:%M}", f"    - updated: {moment:%Y-%m-%d %H:%M}"]
    bounds = section_bounds(lines, "open")
    if bounds:
        heading, end = bounds
        found = parse_blocks(lines[heading:end])
        insert = heading + found[-1].end if found else heading + 1
    else:
        insert = next((index for index, line in enumerate(lines) if line.startswith("## ") and section_key(line[3:]) == "done"), len(lines))
        while insert > 0 and not lines[insert - 1].strip():
            insert -= 1
    lines[insert:insert] = block
    if insert + len(block) < len(lines) and lines[insert + len(block)].startswith("## "):
        lines.insert(insert + len(block), "")
    write(path, existing, lines, dry_run)
    return {"id": action_id, "register": path.relative_to(brain).as_posix(), "label": f"creation of {action_id}",
            "line": block[0], "created_at": f"{moment:%Y-%m-%d %H:%M}", "dry_run": dry_run}


def update(brain: Path, action_id: str, *, title: str | None = None, owner: str | None = None, state: str | None = None,
           priority: str | None = None, due: str | None = None, scheduled: str | None = None, closed_on: str | None = None,
           expect_version: str | None = None, dry_run: bool = False, group: str | None = None) -> dict:
    path, lines, index, current = find(brain, action_id)
    if expect_version is not None and current["version"] != expect_version:
        raise ActionError("conflict", "The action changed in the register. Refresh before retrying.")
    existing = path.read_text(encoding="utf-8")
    if existing.splitlines() != lines:
        raise ActionError("conflict", "The register changed. Refresh before retrying.")
    new = {
        "title": current["raw_title"] if title is None else clean_title(title),
        "owner": current["owner"] if owner is None else clean_text(owner, "Owner", 120),
        "state": current["state"] if state is None else state_of(state),
        "priority": current["priority"] if priority is None else priority_of(priority),
        "due": current["due"] if due is None else optional_date(due, "Due date"),
        "scheduled": current["scheduled"] if scheduled is None else optional_date(scheduled, "Scheduled date"),
        "group": current["group"] if group is None else clean_group(group),
    }
    if closed_on is not None:
        closed_on = parse_date(closed_on, "Closing date")
        if new["state"] not in {"x", "-"}:
            raise ActionError("bad_request", "A closing date requires the state x or -.")
    if new["state"] == current["state"]:
        closure = closed_on or current["done"]
    else:
        closure = closed_on or today()
    lines[index] = action_line(action_id, new["title"], new["owner"], new["state"], new["priority"], current["created"],
                               new["due"], new["scheduled"], closure, new["group"])
    stamp_updated(lines, index, f"{now():%Y-%m-%d %H:%M}")
    text = "\n".join(lines) + ("\n" if existing.endswith("\n") else "")
    swept = sweep_text(text, now().date(), path, only={action_id}).output
    if swept is not None:
        lines = swept.split("\n")
        if existing.endswith("\n") and lines and lines[-1] == "":
            lines.pop()
    keys = ("title", "owner", "priority", "due", "scheduled", "group")
    only_state = new["state"] != current["state"] and all(new[k] == (current["raw_title"] if k == "title" else current[k]) for k in keys)
    label = f"status of {action_id} → {STATE_LABELS[new['state']]}" if only_state else f"edit of {action_id}"
    write(path, existing, lines, dry_run)
    return {"id": action_id, "register": path.relative_to(brain).as_posix(), "label": label,
            "line": next(line for line in lines if f"**{action_id}**" in line and ACTION_RE.match(line)), "dry_run": dry_run}


def add_history(brain: Path, action_id: str, text: str, when: str | None = None, expect_details_version: str | None = None,
                dry_run: bool = False) -> dict:
    note = clean_note(text)
    day = parse_date(when, "Date") if when else today()
    check_versions(brain, action_id, None, expect_details_version)
    path, lines, index, _ = find(brain, action_id)
    existing = path.read_text(encoding="utf-8")
    lines.insert(last_detail(lines, index) + 1, f"    - {history_prefix(day)}{note}")
    stamp_updated(lines, index, f"{now():%Y-%m-%d %H:%M}")
    write(path, existing, lines, dry_run)
    return {"id": action_id, "register": path.relative_to(brain).as_posix(), "label": f"note added to {action_id}", "dry_run": dry_run}


def remove_history(brain: Path, action_id: str, number: int, expect_text: str | None = None,
                   expect_details_version: str | None = None, dry_run: bool = False) -> dict:
    check_versions(brain, action_id, None, expect_details_version)
    path, lines, index, _ = find(brain, action_id)
    existing = path.read_text(encoding="utf-8")
    found = items(lines, index, last_detail(lines, index))
    if not 0 <= number < len(found):
        raise ActionError("bad_request", "Note not found.")
    start, end = found[number]
    text = item_text(lines, start, end)
    if expect_text is not None and text != expect_text:
        raise ActionError("conflict", "The note changed in the register. Reopen the action before retrying.")
    if PROTECTED_RE.match(text):
        raise ActionError("bad_request", "The source, created and updated lines cannot be deleted.")
    del lines[start:end]
    while start < len(lines) and not lines[start].strip() and not lines[start - 1].strip():
        del lines[start]
    stamp_updated(lines, index, f"{now():%Y-%m-%d %H:%M}")
    write(path, existing, lines, dry_run)
    return {"id": action_id, "register": path.relative_to(brain).as_posix(), "label": f"note deleted from {action_id}",
            "removed": text, "dry_run": dry_run}


def edit_history(brain: Path, action_id: str, number: int, text: str, when: str | None = None, expect_text: str | None = None,
                 expect_details_version: str | None = None, dry_run: bool = False) -> dict:
    """Rewrite one history entry (its first line); its date is kept unless ``when`` is given, its sub-lines stay."""
    note = clean_note(text)
    check_versions(brain, action_id, None, expect_details_version)
    path, lines, index, _ = find(brain, action_id)
    existing = path.read_text(encoding="utf-8")
    found = items(lines, index, last_detail(lines, index))
    if not 0 <= number < len(found):
        raise ActionError("bad_request", "Note not found.")
    start, end = found[number]
    current = item_text(lines, start, end)
    if expect_text is not None and current != expect_text:
        raise ActionError("conflict", "The note changed in the register. Reopen the action before retrying.")
    if PROTECTED_RE.match(current):
        raise ActionError("bad_request", "The source, created and updated lines cannot be edited.")
    dated = HISTORY_DATE_RE.match(lines[start])
    if when:
        prefix = history_prefix(parse_date(when, "Date"))
    else:
        prefix = dated.group(1) if dated else ""
    lines[start] = f"    - {prefix}{note}"
    stamp_updated(lines, index, f"{now():%Y-%m-%d %H:%M}")
    write(path, existing, lines, dry_run)
    return {"id": action_id, "register": path.relative_to(brain).as_posix(), "label": f"note edited on {action_id}",
            "before": current, "dry_run": dry_run}


def relink(text: str, old_dir: Path, new_dir: Path) -> str:
    """Rewrite the relative Markdown links of ``text`` written in ``old_dir`` so they work from ``new_dir``."""
    def fix(match: re.Match) -> str:
        target = match.group(2)
        if re.match(r"^(<|[a-z][a-z0-9+.-]*:|#|/)", target):
            return match.group(0)
        path, sep, anchor = target.partition("#")
        moved = os.path.relpath(os.path.normpath(old_dir / path), new_dir).replace(os.sep, "/")
        return f"{match.group(1)}{moved}{sep}{anchor}{match.group(3)}"
    return MD_LINK_RE.sub(fix, text)


def move(brain: Path, action_id: str, project: str, dry_run: bool = False) -> dict:
    """Move an action, with its block, to another register of the same client (or internal project); ID unchanged."""
    source, lines, index, current = find(brain, action_id)
    target = resolve_register(brain, project)
    if target == source:
        raise ActionError("bad_request", "The action is already in this register.")
    scope = lambda path: path.relative_to(brain / "projects").parts[:2]  # noqa: E731
    if scope(target) != scope(source):
        raise ActionError("bad_request", "A move is limited to registers of the same client or project (IDs depend on it).")
    existing, target_existing = source.read_text(encoding="utf-8"), target.read_text(encoding="utf-8")
    end = last_detail(lines, index) + 1
    block = [relink(line, source.parent, target.parent) for line in lines[index:end]]
    while block and not block[-1].strip():
        block.pop()
    day = now()
    target_lines = target_existing.splitlines()
    block.insert(last_detail(block, 0) + 1, f"    - {history_prefix(day.date().isoformat())}moved from {project_label(source, brain)}")
    stamp_updated(block, 0, f"{day:%Y-%m-%d %H:%M}")
    del lines[index:end]
    if index and not lines[index - 1].strip():
        while index < len(lines) and not lines[index].strip():
            del lines[index]
    key = STATE_SECTION[current["state"]]
    if section_bounds(target_lines, key) is None:
        raise ActionError("bad_request", f"Section \"{TITLES[key]}\" is missing from the target register.")
    if key == "open":
        insert_open(target_lines, block)
    else:
        insert_block(target_lines, key, block, date.fromisoformat(current["done"]) if current["done"] else day.date())
    if dry_run:
        return {"id": action_id, "from": source.relative_to(brain).as_posix(), "register": target.relative_to(brain).as_posix(),
                "label": f"move of {action_id}", "dry_run": True}
    if source.read_text(encoding="utf-8") != existing or target.read_text(encoding="utf-8") != target_existing:
        raise ActionError("conflict", "The register changed. Refresh before retrying.")
    atomic_write(target, ("\n".join(target_lines) + ("\n" if target_existing.endswith("\n") else "")).encode("utf-8"))
    try:
        atomic_write(source, ("\n".join(lines) + ("\n" if existing.endswith("\n") else "")).encode("utf-8"))
    except OSError:
        atomic_write(target, target_existing.encode("utf-8"))
        raise
    return {"id": action_id, "from": source.relative_to(brain).as_posix(), "register": target.relative_to(brain).as_posix(),
            "label": f"move of {action_id}", "dry_run": False}


def check(brain: Path, only: set[Path] | None = None) -> dict:
    """Format errors (blocking) and warnings of the action registers; IDs are checked across each client folder."""
    errors: list[str] = []
    warnings: list[str] = []
    seen: dict[tuple, dict[str, str]] = {}
    for path in registers(brain):
        scope = path.relative_to(brain / "projects").parts[:2]
        bucket = seen.setdefault(scope, {})
        files = [path] + sorted(path.parent.glob("actions-archive-*.md"))
        for file in files:
            lines = file.read_text(encoding="utf-8").splitlines()
            name = file.relative_to(brain).as_posix()
            for number, line in enumerate(lines, 1):
                loose = LOOSE_ACTION_RE.match(line)
                if not loose:
                    continue
                action_id = loose.group(1)
                where = f"{name}:{number}"
                if action_id in bucket:
                    errors.append(f"{where}: {action_id} already present ({bucket[action_id]})")
                else:
                    bucket[action_id] = where
                if file != path or (only is not None and path not in only):
                    continue
                match = ACTION_RE.match(line)
                if not match:
                    errors.append(f"{where}: malformed action line (expected `- [state] **ID** — owner — title`)")
                    continue
                for marker, value in re.findall(r"(➕|📅|⏳|✅|❌)\s*(\S+)", line):
                    try:
                        date.fromisoformat(value)
                    except ValueError:
                        errors.append(f"{where}: {action_id} invalid {marker} date '{value}'")
                tags = GROUP_TAG_RE.findall(line)
                if any(not valid_group(tag) for tag in tags):
                    warnings.append(f"{where}: {action_id} invalid group slug #group/ (lowercase, digits, hyphens; {GROUP_LIMIT} characters at most)")
                elif len(tags) > 1:
                    warnings.append(f"{where}: {action_id} several #group/ tags (only one expected)")
                elif tags and not parse_action(line, path, brain, number)["group"]:
                    warnings.append(f"{where}: {action_id} tag #group/{tags[0]} not at the end of the title, group ignored")
                state = match.group(1)
                closed = re.search(r"[✅❌]\s*\d{4}-\d{2}-\d{2}", line)
                if state in {"x", "-"} and not closed:
                    warnings.append(f"{where}: {action_id} closed without a ✅/❌ date")
                if state not in {"x", "-"} and closed:
                    errors.append(f"{where}: {action_id} open but carries a closing date")
                if state == "x" and "❌" in line or state == "-" and "✅" in line:
                    errors.append(f"{where}: {action_id} closing mark inconsistent with the state")
                block = [item_text(lines, a, b) for a, b in items(lines, number - 1, last_detail(lines, number - 1))]
                if not any(re.match(r"-\s*(\[?source|\[)", entry, re.IGNORECASE) for entry in block):
                    warnings.append(f"{where}: {action_id} without a source sub-bullet")
    return {"errors": errors, "warnings": warnings}


def delete(brain: Path, action_id: str, expect_version: str | None = None, expect_details_version: str | None = None,
           dry_run: bool = False) -> dict:
    check_versions(brain, action_id, expect_version, expect_details_version)
    path, lines, index, _ = find(brain, action_id)
    existing = path.read_text(encoding="utf-8")
    del lines[index:last_detail(lines, index) + 1]
    if index and not lines[index - 1].strip():
        while index < len(lines) and not lines[index].strip():
            del lines[index]
        if index == len(lines):
            while lines and not lines[-1].strip():
                lines.pop()
    write(path, existing, lines, dry_run)
    return {"deleted": action_id, "register": path.relative_to(brain).as_posix(), "label": f"deletion of {action_id}", "dry_run": dry_run}


def listing(brain: Path, project: str | None, state: str, owner: str | None) -> list[dict]:
    paths = [resolve_register(brain, project)] if project else registers(brain)
    found = [action for path in paths for action in load(path, brain)]
    if state == "open":
        found = [a for a in found if a["state"] in {" ", "/", "w"}]
    elif state == "closed":
        found = [a for a in found if a["state"] in {"x", "-"}]
    if owner:
        found = [a for a in found if owner.lower() in a["owner"].lower()]
    return found


# --- Board (formerly tasks-board.py) -------------------------------------------------------------
# Complete read-only view by project: the owner's To do, everyone's In progress and Waiting,
# sorted by ID, then the 15 most recent closures, whoever the owner.

BOARD_DONE = re.compile(r"\s*[✅❌]\s*(\d{4}-\d{2}-\d{2})")
BOARD_LIMIT = 15
BOARD_STATES = ((" ", "To do"), ("/", "In progress"), ("w", "Waiting"))


@dataclass(frozen=True)
class BoardItem:
    state: str
    action_id: str
    owner: str
    title: str
    done: str | None
    register: Path
    line: int
    project: str


def board_owner(brain: Path) -> str:
    name = os.environ.get("BRAIN_OWNER", "").strip()
    config = brain / ".data/doctor.json"
    if not name and config.is_file():
        name = str(json.loads(config.read_text(encoding="utf-8")).get("owner", "")).strip()
    if not name:
        raise SystemExit(f"unknown owner: set BRAIN_OWNER or 'owner' in {brain.name}/.data/doctor.json")
    return name


def board_load(brain: Path) -> list[BoardItem]:
    found = []
    for register in sorted((brain / "projects").glob("**/state/actions.md")):
        for number, text in enumerate(register.read_text(encoding="utf-8").splitlines(), start=1):
            match = re.match(r"^- \[(.)\] \*\*([A-Z]{2,5}-\d{3})\*\* — ([^—]+?) — (.*)$", text)
            if not match:
                continue
            state, action_id, owner, rest = match.groups()
            done = BOARD_DONE.search(rest)
            # Links in a title are relative to the register: keep their text only.
            title = LINK_RE.sub(r"\1", BOARD_DONE.sub("", rest)).strip()
            found.append(BoardItem(state, action_id, owner.strip(), title, done.group(1) if done else None, register, number,
                                   project_label(register, brain)))
    return found


def board_groups(found: list[BoardItem], owner: str) -> tuple[list, list[str], list[BoardItem]]:
    """(projects with their state groups, projects with nothing to show, recent closures)."""
    def shown(a: BoardItem) -> bool:
        return a.state in "/w" or (a.state == " " and owner in a.owner)
    projects, empty = [], []
    for project in sorted({a.project for a in found}):
        listed = [a for a in found if a.project == project and shown(a)]
        groups = [(label, sorted((a for a in listed if a.state == symbol), key=lambda a: a.action_id)) for symbol, label in BOARD_STATES]
        groups = [(label, group) for label, group in groups if group]
        (projects.append((project, groups)) if groups else empty.append(project))
    done = sorted((a for a in found if a.state in "xX-" and a.done), key=lambda a: (a.done, a.action_id), reverse=True)
    return projects, empty, done[:BOARD_LIMIT]


def board_render(found: list[BoardItem], owner: str, base: Path) -> str:
    def item(a: BoardItem, dated: bool = False) -> str:
        target = os.path.relpath(a.register, base).replace(os.sep, "/")
        when = f" — {'cancelled' if a.state == '-' else 'done'} on {a.done}" if dated else ""
        return f"- `[{a.state}]` **{a.action_id}** — {a.owner} — {a.title}{when} — [register]({target}#L{a.line})"

    projects, empty, done = board_groups(found, owner)
    out = ["# Tasks", "", "> Snapshot of the `state/actions.md` registers, generated by `uv run tools/brain/action.py board --write`. Do not edit: change an action's state in its register, then run it again.", ""]
    for project, groups in projects:
        out += [f"## {project} ({sum(len(g) for _, g in groups)})", ""]
        for label, group in groups:
            out += [f"**{label}** ({len(group)})", ""] + [item(a) for a in group] + [""]
    if empty:
        out += ["_Nothing in progress, waiting or to do: " + ", ".join(empty) + "._", ""]
    out += [f"## Recently done ({len(done)})", ""]
    out += [item(a, dated=True) for a in done] if done else ["_None._"]
    out.append("")
    return "\n".join(out)


def board_write(brain: Path, target: Path) -> bool:
    """Write the board to target; return True when its content changed."""
    content = board_render(board_load(brain), board_owner(brain), target.parent)
    if target.is_file() and target.read_text(encoding="utf-8") == content:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return True


def board_watch(brain: Path, target: Path, interval: float) -> None:
    """Rewrite the board whenever a register changes; the VS Code preview follows the file."""
    def signature() -> tuple:
        files = sorted((brain / "projects").glob("**/state/actions.md")) + [brain / ".data/doctor.json"]
        return tuple((str(f), f.stat().st_mtime_ns) for f in files if f.is_file())
    print(f"Watching the registers; board: {os.path.relpath(target, Path.cwd())} (Ctrl+C to stop)", flush=True)
    last = None
    try:
        while True:
            current = signature()
            if current != last:
                if board_write(brain, target):
                    print(f"Board updated ({datetime.now():%H:%M:%S})", flush=True)
                last = current
            time.sleep(interval)
    except KeyboardInterrupt:
        pass


def board(args: argparse.Namespace) -> int:
    brain = (args.brain[0] if args.brain else BRAIN).expanduser().resolve()
    if not (brain / "projects").is_dir():
        raise SystemExit(f"brain not found: {brain}")
    if args.watch:
        if not args.write:
            raise SystemExit("--watch needs --write")
        board_watch(brain, Path(args.write).resolve(), interval=1.5)
        return 0
    print(board_render(board_load(brain), board_owner(brain), Path.cwd()))
    if args.write:
        target = Path(args.write).resolve()
        board_write(brain, target)
        print(f"\nWritten: {os.path.relpath(target, Path.cwd())}")
    return 0


# --- Command line --------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create, read and edit the actions of the brain's registers (JSON output).")
    parser.add_argument("--brain", action="append", type=Path, metavar="PATH", help="brain to process (default: BRAIN_DIR, else the default brain of Work; repeatable for sweep and archive)")
    sub = parser.add_subparsers(dest="command", required=True)

    def writable(p: argparse.ArgumentParser) -> None:
        p.add_argument("--dry-run", action="store_true", help="print the result, write nothing")

    p = sub.add_parser("list", help="list the actions")
    p.add_argument("--project", help="register, project folder, client/mission or label")
    p.add_argument("--state", choices=("open", "closed", "all"), default="open")
    p.add_argument("--owner")
    p.add_argument("--table", action="store_true", help="one line per action instead of JSON")

    p = sub.add_parser("board", help="complete view by project, for the terminal or a Markdown preview (read-only)")
    p.add_argument("--write", nargs="?", const=str(WORK / "agents/tasks-board.md"), metavar="PATH",
                   help="also write the board to PATH (default: agents/tasks-board.md)")
    p.add_argument("--watch", action="store_true", help="with --write: keep the file up to date when the registers change")

    p = sub.add_parser("show", help="show an action and its history")
    p.add_argument("id")

    p = sub.add_parser("create", help="create an action at the end of the Open section")
    p.add_argument("--project", required=True, help="register, project folder, client/mission or label")
    p.add_argument("--title", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--source", required=True, help="text of the source sub-bullet (Markdown link relative to the register)")
    p.add_argument("--state", default=" ", help="todo, in-progress or waiting (default: todo)")
    p.add_argument("--priority", default="", help="high, medium, low or normal")
    p.add_argument("--due", default="", help="precise due date YYYY-MM-DD")
    p.add_argument("--scheduled", default="", help="chosen work date YYYY-MM-DD")
    p.add_argument("--due-note", default="", help="qualified due date, as a sub-bullet ('before…')")
    p.add_argument("--group", default="", help="task group: lowercase-and-hyphens slug, 40 characters at most, written #group/<slug>")
    p.add_argument("--prefix", help="ID prefix, only for a register that is still empty")
    writable(p)

    p = sub.add_parser("update", help="change the fields of an action (only those given)")
    p.add_argument("id")
    for name in ("title", "owner", "state", "priority", "due", "scheduled", "group"):
        p.add_argument(f"--{name}", help="empty value clears a date" if name in {"due", "scheduled"}
                       else "group slug (#group/<slug>), empty value removes it; absent: unchanged" if name == "group" else None)
    p.add_argument("--closed-on", help="date of the closing evidence YYYY-MM-DD (default: today)")
    p.add_argument("--expect-version")
    writable(p)

    p = sub.add_parser("history", help="add, edit or remove a history entry")
    hist = p.add_subparsers(dest="operation", required=True)
    h = hist.add_parser("add")
    h.add_argument("id")
    h.add_argument("--text", required=True)
    h.add_argument("--date", help="date of the event YYYY-MM-DD (default: today)")
    h.add_argument("--expect-details-version")
    writable(h)
    h = hist.add_parser("edit")
    h.add_argument("id")
    h.add_argument("--index", type=int, required=True, help="rank of the sub-bullet (see show)")
    h.add_argument("--text", required=True, help="new text (the existing DD/MM date is kept)")
    h.add_argument("--date", help="new date of the entry YYYY-MM-DD")
    h.add_argument("--expect-text")
    h.add_argument("--expect-details-version")
    writable(h)
    h = hist.add_parser("remove")
    h.add_argument("id")
    h.add_argument("--index", type=int, required=True, help="rank of the sub-bullet (see show)")
    h.add_argument("--expect-text")
    h.add_argument("--expect-details-version")
    writable(h)

    for name, text in (("sweep", "put each action under the section of its state (Open, Done, Cancelled)"),
                       ("archive", "move the actions closed for more than --days days to state/actions-archive-YYYY.md")):
        p = sub.add_parser(name, help=text)
        mode = p.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="write nothing (default behavior)")
        mode.add_argument("--write", action="store_true", help="apply the moves")
        mode.add_argument("--check", action="store_true", help="dry run that exits with code 1 when an action has to move (pre-commit)")
        p.add_argument("--register", action="append", type=Path, metavar="PATH", help="limit the processing to these state/actions.md (repeatable)")
        p.add_argument("--days", type=int, default=DEFAULT_DAYS, help=f"minimum age of the closure for archive (default {DEFAULT_DAYS})")
        p.add_argument("--today", type=parse_day, help="today's date YYYY-MM-DD (default: ARCHIVE_TODAY, else the Europe/Paris date)")
        p.add_argument("--quiet", action="store_true", help="print only the totals (and the errors)")
        if name == "sweep":
            p.add_argument("--archive", action="store_true", help="also archive, after the sweep")

    p = sub.add_parser("move", help="move an action to another register of the same client (ID unchanged)")
    p.add_argument("id")
    p.add_argument("--to", required=True, help="target register: path, folder, client/mission or label")
    writable(p)

    p = sub.add_parser("check", help="check the format of the registers (exit code 1 on error)")
    p.add_argument("--register", action="append", type=Path, metavar="PATH", help="limit the format check to these registers (IDs are still checked across the whole client)")
    p.add_argument("--quiet", action="store_true", help="print only the errors")

    p = sub.add_parser("delete", help="delete an action and its block")
    p.add_argument("id")
    p.add_argument("--expect-version")
    p.add_argument("--expect-details-version")
    writable(p)
    return parser


def maintain(args: argparse.Namespace) -> int:
    """`sweep` and `archive`: same report and exit codes as the former manage-action.py."""
    operations = {"sweep": args.command == "sweep", "archive": args.command == "archive" or getattr(args, "archive", False)}
    if args.days < 0:
        print("--days must be zero or positive", file=sys.stderr)
        return 2
    today_ = args.today or (parse_day(os.environ["ARCHIVE_TODAY"]) if os.environ.get("ARCHIVE_TODAY") else paris_today())
    brains = [path.expanduser().resolve() for path in (args.brain or [BRAIN])]
    only_registers = {path.expanduser().resolve() for path in args.register} if args.register else None
    totals = {"sweep": 0, "archive": 0}
    hits = {"sweep": 0, "archive": 0}
    errors = 0
    for brain in brains:
        if not brain.is_dir():
            print(f"ERROR {brain.as_posix()}: brain not found", file=sys.stderr)
            errors += 1
            continue
        for register in registers_of(brain):
            if only_registers is not None and register not in only_registers:
                continue
            name = display(register)
            for operation, runner in (("sweep", run_sweep), ("archive", run_archive)):
                if not operations[operation]:
                    continue
                count, failed = runner(register, name, today_, args)
                totals[operation] += count
                hits[operation] += 1 if count else 0
                errors += failed
                if failed:
                    break  # a register in error is left alone by the next operation
    verb = "moved" if args.write else "to move"
    for operation, label in (("sweep", "sweep"), ("archive", "archive")):
        if operations[operation]:
            print(f"Total {label}: {totals[operation]} action(s) {verb} in {hits[operation]} register(s)")
    pending = any(totals.values())
    if args.check and pending:
        print(f"Misfiled actions: run `uv run tools/brain/action.py {args.command} --write` (then stage again).")
    elif not args.write and pending:
        print("(dry run: nothing is written, run again with --write)")
    if errors:
        print(f"{errors} error(s)")
    return 1 if errors or (args.check and pending) else 0


def run(args: argparse.Namespace) -> object:
    brain = (args.brain[0] if args.brain else BRAIN).expanduser().resolve()
    if not (brain / "projects").is_dir():
        raise ActionError("not_found", f"Registers not found under {brain / 'projects'}")
    if args.command == "list":
        return listing(brain, args.project, args.state, args.owner)
    if args.command == "show":
        return details(brain, args.id)
    if args.command == "create":
        return create(brain, args.project, args.title, args.owner, args.source, args.state, args.priority, args.due,
                      args.scheduled, args.due_note, args.prefix, args.dry_run, args.group)
    if args.command == "update":
        return update(brain, args.id, title=args.title, owner=args.owner, state=args.state, priority=args.priority,
                      due=args.due, scheduled=args.scheduled, closed_on=args.closed_on,
                      expect_version=args.expect_version, dry_run=args.dry_run, group=args.group)
    if args.command == "history" and args.operation == "add":
        return add_history(brain, args.id, args.text, args.date, args.expect_details_version, args.dry_run)
    if args.command == "history" and args.operation == "edit":
        return edit_history(brain, args.id, args.index, args.text, args.date, args.expect_text, args.expect_details_version, args.dry_run)
    if args.command == "move":
        return move(brain, args.id, args.to, args.dry_run)
    if args.command == "history":
        return remove_history(brain, args.id, args.index, args.expect_text, args.expect_details_version, args.dry_run)
    return delete(brain, args.id, args.expect_version, args.expect_details_version, args.dry_run)


def main() -> int:
    args = build_parser().parse_args()
    if args.command in {"sweep", "archive"}:
        return maintain(args)
    if args.command == "board":
        return board(args)
    if args.command == "check":
        brain = (args.brain[0] if args.brain else BRAIN).expanduser().resolve()
        result = check(brain, {path.expanduser().resolve() for path in args.register} if args.register else None)
        for error in result["errors"]:
            print(f"ERROR {error}")
        if not args.quiet:
            for warning in result["warnings"]:
                print(f"WARNING {warning}")
        print(f"Action check: {len(result['errors'])} error(s), {len(result['warnings'])} warning(s)")
        return 1 if result["errors"] else 0
    try:
        result = run(args)
    except ActionError as error:
        print(json.dumps({"error": error.message, "kind": error.kind}, ensure_ascii=False))
        return EXIT[error.kind]
    except (OSError, UnicodeDecodeError) as error:
        print(json.dumps({"error": str(error), "kind": "conflict"}, ensure_ascii=False))
        return EXIT["conflict"]
    if args.command == "list" and args.table:
        for action in result:  # type: ignore[union-attr]
            extra = " ".join(part for part in (f"[group: {action['group']}]" if action["group"] else "", action["priority"],
                                               f"📅 {action['due']}" if action["due"] else "") if part)
            print(f"[{action['state']}] {action['id']} — {action['owner']} — {action['title']} {extra}".rstrip() + f"  ({action['project']})")
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
