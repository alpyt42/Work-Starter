#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write the `## Timeline` of a project page and roll its past months into `journal/YYYY-MM.md`.

A project page keeps one line per event of the current month, most recent first:

    ## Timeline
    Previous months: [2026-09](journal/2026-09.md) · [2026-08](journal/2026-08.md)

    - 2026-10-14 — Demo recorded and shared with the client (Sonnet 5)

Older entries live in `<project>/journal/YYYY-MM.md` (title, back link, `> Journal archive of …`
line, then the entries). This tool does both moves so that agents never edit them by hand.

Commands (from the Work root, `uv run tools/brain/timeline.py <command> --help` for details):

    add   --project P --model M [--date D] TEXT   write `- D — TEXT (M)` at its date; rolls past months first
    roll  [--project P] [--write]                 move the entries of past months into journal/YYYY-MM.md

PROJECT is the register path, the project folder, `client/mission`, the name of an internal project or
the board label (as in `action.py`), or `clients/<client>` for a client index page. `roll` without
`--project` processes every project page of the brain (and the client index pages that have a timeline).
`roll` is a dry run unless `--write` is given; `add` accepts `--dry-run`.

The previous-months line and the journal headers keep the wording they already have (English or
French); a new one follows the wording of the project, else of the brain, else English. Only the
`## Timeline` section of the page and the journal files are written, atomically; a file that changed
since it was read is refused. Output is JSON on stdout. Exit codes: 0 done, 2 invalid request, 3 not
found, 4 conflict. `--brain PATH` or BRAIN_DIR selects another brain; ACTION_NOW (`YYYY-MM-DD HH:MM`)
fixes the clock for tests.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
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

ENTRY_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2})(?:\s+[—–-](?:\s|$)|$)")
TIMELINE_RE = re.compile(r"^##\s+Timeline\s*#*\s*$", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}(?:\s|$)")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
PREVIOUS_RE = re.compile(r"^(?P<label>(?:Previous months|Mois précédents|Mois precedents)\s*:)\s*(?P<rest>.*?)\s*$", re.IGNORECASE)
MONTH_LINK_RE = re.compile(r"\[(\d{4}-\d{2})\]\([^)]*\)")
PLACEHOLDER_RE = re.compile(r"^- \(no entries yet\)\s*$", re.IGNORECASE)
JOURNAL_FILE_RE = re.compile(r"^(\d{4}-\d{2})\.md$")
CLIENT_RE = re.compile(r"(?:projects/)?clients/([^/]+)")
H1_PREFIX_RE = re.compile(r"^(?:Mission|Project|Projet|Client)\s*:\s*", re.IGNORECASE)
JOURNAL_TITLE_RE = re.compile(r"^# Journal — (\d{4}-\d{2}) — ")
LINK_RE = re.compile(r"(\]\()(<[^>\n]*>|[^)\s]+)")
CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
ENTRY_LIMIT = 2000
MODEL_LIMIT = 80

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
}
WORDING = {
    "en": {"previous": "Previous months:", "back": "Back to project",
           "quote": "Journal archive of {name} for {month} {year}: entries moved from the project page on {day}. The current month stays on the page.",
           "markers": ("previous months", "back to project", "journal archive of")},
    "fr": {"previous": "Mois précédents :", "back": "Retour au projet",
           "quote": "Archive du journal de {name} pour {month} {year} : entrées déplacées depuis la fiche le {day}. Les mois en cours restent dans la fiche.",
           "markers": ("mois précédents", "mois precedents", "retour au projet", "archive du journal")},
}


# --- Reading -------------------------------------------------------------------------------------


@dataclass
class Entry:
    start: int
    end: int  # exclusive: the entry line and its indented continuation lines
    day: str


@dataclass
class Section:
    heading: int  # -1 for a whole journal file, which has no heading to look for
    end: int  # exclusive
    entries: list[Entry]
    previous: list[int]  # indexes of the previous-months lines


@dataclass
class Doc:
    """A Markdown file held in memory; `original` is None while the file does not exist."""

    path: Path
    lines: list[str]
    eol: str = "\n"
    final: bool = True
    original: str | None = None

    @classmethod
    def load(cls, path: Path) -> Doc:
        if path.is_symlink():
            raise ActionError("bad_request", f"{path.name} is a symbolic link.")
        if not path.exists():
            return cls(path, [])
        text = path.read_bytes().decode("utf-8")
        eol = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(eol)
        final = lines[-1] == ""
        if final:
            lines.pop()
        return cls(path, lines, eol, final, text)

    def render(self) -> str:
        return self.eol.join(self.lines) + (self.eol if self.final and self.lines else "")

    @property
    def dirty(self) -> bool:
        return self.render() != (self.original or "") if self.original is not None else bool(self.lines)


@dataclass
class Plan:
    """Everything one command reads and writes, held in memory until `commit`."""

    brain: Path
    page: Path
    today: date
    docs: dict[Path, Doc] = field(default_factory=dict)
    _style: tuple[str, bool] | None = None

    def doc(self, path: Path) -> Doc:
        if path not in self.docs:
            self.docs[path] = Doc.load(path)
        return self.docs[path]

    def journal(self, month: str) -> Doc:
        folder = self.page.parent / "journal"
        if folder.is_symlink():
            raise ActionError("bad_request", "journal is a symbolic link.")
        return self.doc(folder / f"{month}.md")

    def style(self) -> tuple[str, bool]:
        """(language, month-first journal title) for the files this plan creates."""
        if self._style is None:
            self._style = detect_style(self.brain, self.page)
        return self._style


def valid_day(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def fenced(lines: list[str]) -> list[bool]:
    """For each line, whether it belongs to a fenced code block (fences included)."""
    flags: list[bool] = []
    marker = ""
    for line in lines:
        found = FENCE_RE.match(line)
        if not marker:
            flags.append(bool(found))
            if found:
                marker = found.group(1)
        else:
            flags.append(True)
            if found and found.group(1)[0] == marker[0] and len(found.group(1)) >= len(marker) and not found.group(2).strip():
                marker = ""
    return flags


def scan(lines: list[str], start: int, end: int, flags: list[bool]) -> tuple[list[Entry], list[int]]:
    """Timeline entries and previous-months lines between two lines."""
    entries: list[Entry] = []
    previous: list[int] = []
    index = start
    while index < end:
        line = lines[index]
        found = ENTRY_RE.match(line)
        if flags[index]:
            index += 1
        elif found and valid_day(found.group(1)):
            stop = index + 1
            while stop < end and lines[stop].strip() and lines[stop][0] in " \t" and not flags[stop]:
                stop += 1
            entries.append(Entry(index, stop, found.group(1)))
            index = stop
        else:
            if PREVIOUS_RE.match(line):
                previous.append(index)
            index += 1
    return entries, previous


def find_section(lines: list[str]) -> Section | None:
    flags = fenced(lines)
    heading = next((i for i, line in enumerate(lines) if not flags[i] and TIMELINE_RE.match(line)), None)
    if heading is None:
        return None
    end = next((i for i in range(heading + 1, len(lines)) if not flags[i] and HEADING_RE.match(lines[i])), len(lines))
    return Section(heading, end, *scan(lines, heading + 1, end, flags))


def whole(lines: list[str]) -> Section:
    return Section(-1, len(lines), *scan(lines, 0, len(lines), fenced(lines)))


def project_name(lines: list[str], page: Path) -> str:
    for line in lines:
        if line.startswith("# "):
            return H1_PREFIX_RE.sub("", line[2:].strip()) or page.parent.name
    return page.parent.name


def language_of(text: str) -> str | None:
    lowered = text.casefold()
    for code, wording in WORDING.items():
        if any(marker in lowered for marker in wording["markers"]):
            return code
    return None


def read_lines(path: Path, limit: int | None = None) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    return lines[:limit] if limit else lines


def wording_of(page: Path) -> tuple[list[str], bool | None]:
    """Languages found in the page's previous-months line and in its journals' headers, and the title order of the newest journal."""
    votes: list[str] = []
    lines = read_lines(page)
    section = find_section(lines)
    for index in section.previous if section else []:
        if language := language_of(lines[index]):
            votes.append(language)
    month_first: bool | None = None
    journals = sorted((page.parent / "journal").glob("*.md"), reverse=True) if (page.parent / "journal").is_dir() else []
    for journal in journals:
        head = read_lines(journal, 8)
        if language := language_of("\n".join(head)):
            votes.append(language)
        if month_first is None and head and head[0].startswith("# Journal — "):
            month_first = bool(JOURNAL_TITLE_RE.match(head[0]))
    return votes, month_first


def detect_style(brain: Path, page: Path) -> tuple[str, bool]:
    votes, month_first = wording_of(page)
    if not votes:
        for other, _ in project_pages(brain):
            votes += wording_of(other)[0]
    counts = Counter(votes)
    language = max(("en", "fr"), key=lambda code: (counts[code], code == "en"))
    return language, bool(month_first)


# --- Projects ------------------------------------------------------------------------------------


def locate(brain: Path, project: str) -> tuple[Path, str]:
    """The project page and its label: `<folder>/<folder name>.md` or a client index page."""
    wanted = project.strip().strip("/")
    client = CLIENT_RE.fullmatch(wanted)
    if client:
        folder = brain / "projects/clients" / client.group(1)
        if not folder.is_dir():
            raise ActionError("bad_request", "Unknown project.")
        page, label = folder / f"{folder.name}.md", f"clients/{folder.name}"
    else:
        register = action.resolve_register(brain, wanted)
        folder = register.parent.parent
        page, label = folder / f"{folder.name}.md", action.project_label(register, brain)
    if page.is_symlink() or not page.resolve().is_relative_to(brain):
        raise ActionError("bad_request", "The project page is a symbolic link or lies outside the brain.")
    if not page.is_file():
        raise ActionError("not_found", f"Project page not found: {page.relative_to(brain).as_posix()}")
    return page, label


def project_pages(brain: Path) -> list[tuple[Path, str]]:
    """Every project page (archived projects left alone) and every client index page of the brain."""
    found: list[tuple[Path, str]] = []
    for register in action.registers(brain):
        folder = register.parent.parent
        page = folder / f"{folder.name}.md"
        if "archive" not in register.relative_to(brain / "projects").parts and page.is_file() and not page.is_symlink():
            found.append((page, action.project_label(register, brain)))
    clients = brain / "projects/clients"
    for folder in sorted(clients.iterdir()) if clients.is_dir() else []:
        page = folder / f"{folder.name}.md"
        if folder.is_dir() and not folder.is_symlink() and page.is_file() and not page.is_symlink():
            found.append((page, f"clients/{folder.name}"))
    return found


# --- Editing -------------------------------------------------------------------------------------


def shift_target(target: str) -> str:
    """A relative link target seen from `journal/` instead of the project folder; others are left alone."""
    wrapped = target.startswith("<")
    inner = target[1:-1] if wrapped else target
    if not inner or inner.startswith(("#", "/")) or SCHEME_RE.match(inner):
        return target
    inner = "../" + inner.removeprefix("./")
    return f"<{inner}>" if wrapped else inner


def shift_links(line: str) -> str:
    """Add one `../` to the relative Markdown links of a line (code spans untouched)."""
    def shift(text: str) -> str:
        return LINK_RE.sub(lambda found: found.group(1) + shift_target(found.group(2)), text)

    pieces, last = [], 0
    for span in CODE_SPAN_RE.finditer(line):
        pieces += [shift(line[last:span.start()]), span.group(0)]
        last = span.end()
    return "".join(pieces) + shift(line[last:])


def remove_range(lines: list[str], start: int, end: int) -> None:
    """Delete lines[start:end], then drop the blank line the removal would leave doubled or dangling."""
    del lines[start:end]
    while start > 0 and not lines[start - 1].strip() and (start >= len(lines) or not lines[start].strip()):
        del lines[start - 1]
        start -= 1


def find_slot(entries: list[Entry], day: str, below: bool) -> int | None:
    """Line where an entry dated `day` goes among the others (None: there are none).

    Most recent first. `below` False puts it above the entries of the same date (a new entry); `below`
    True puts it under the entries of the same or a later date (moved entries keep their order).
    """
    if not entries:
        return None
    if below:
        slot = [entry.end for entry in entries if entry.day >= day]
        return slot[-1] if slot else entries[0].start
    return next((entry.start for entry in entries if entry.day <= day), entries[-1].end)


def first_entry_slot(lines: list[str], section: Section) -> int:
    """Where the first entry of a section without entries goes: under the quote and previous-months line."""
    last, quoted = section.heading, False
    for index in range(section.heading + 1, section.end):
        if lines[index].startswith(">") or index in section.previous:
            last, quoted = index, quoted or lines[index].startswith(">")
        elif lines[index].strip():
            break
    slot = last + 1
    while slot < section.end and not lines[slot].strip():
        slot += 1
    if slot == last + 1 and last in section.previous and not quoted:
        lines.insert(slot, "")  # a blank line between the previous-months line and the entries
        slot += 1
    return slot


def place(lines: list[str], block: list[str], day: str, below: bool, page: bool) -> None:
    """Insert an entry block at its date in a page's timeline (`page`) or in a journal file."""
    section = find_section(lines) if page else whole(lines)
    assert section is not None
    slot = find_slot(section.entries, day, below)
    if slot is not None:
        lines[slot:slot] = block
    elif not page:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ([""] if lines else []) + block
    else:
        for index in reversed([i for i in range(section.heading + 1, section.end) if PLACEHOLDER_RE.match(lines[i])]):
            del lines[index]
        section = find_section(lines)
        assert section is not None
        slot = first_entry_slot(lines, section)
        lines[slot:slot] = block
        if slot + len(block) < len(lines) and lines[slot + len(block)].strip():
            lines.insert(slot + len(block), "")


def ensure_section(doc: Doc) -> None:
    if find_section(doc.lines) is None:
        while doc.lines and not doc.lines[-1].strip():
            doc.lines.pop()
        doc.lines += ["", "## Timeline", ""] if doc.lines else ["## Timeline", ""]


def set_previous(plan: Plan, months: set[str]) -> None:
    """Write the previous-months line of the page: the months it lists, the journals on disk and `months`."""
    doc = plan.doc(plan.page)
    section = find_section(doc.lines)
    assert section is not None
    folder = plan.page.parent / "journal"
    found = {m.group(1) for p in folder.glob("*.md") if (m := JOURNAL_FILE_RE.match(p.name))} if folder.is_dir() and not folder.is_symlink() else set()
    found |= {m.group(1) for path in plan.docs if path.parent == folder and (m := JOURNAL_FILE_RE.match(path.name))}
    label, listed = "", set()
    for index in section.previous:
        parsed = PREVIOUS_RE.match(doc.lines[index])
        assert parsed is not None
        label = label or parsed.group("label")
        listed |= set(MONTH_LINK_RE.findall(parsed.group("rest")))
    label = label or WORDING[plan.style()[0]]["previous"]
    text = f"{label} " + " · ".join(f"[{m}](journal/{m}.md)" for m in sorted(listed | found | months, reverse=True))
    head_end = section.entries[0].start if section.entries else section.end
    if len(section.previous) == 1 and section.previous[0] < head_end:
        doc.lines[section.previous[0]] = text
        return
    for index in reversed(section.previous):  # missing, doubled or stray among the entries: one line, under the heading
        del doc.lines[index]
        if index > head_end and index < len(doc.lines) and not doc.lines[index].strip():
            del doc.lines[index]  # the blank line that followed the stray line between two entries
    slot = section.heading + 1
    while slot < len(doc.lines) and doc.lines[slot].startswith(">"):
        slot += 1
    doc.lines.insert(slot, text)
    if slot == section.heading + 1 and slot + 1 < len(doc.lines) and doc.lines[slot + 1].strip():
        doc.lines.insert(slot + 1, "")


def new_journal(plan: Plan, month: str) -> list[str]:
    """Title, back link and archive line of a journal file that does not exist yet."""
    language, month_first = plan.style()
    name = project_name(plan.doc(plan.page).lines, plan.page)
    wording = WORDING[language]
    year, number = month.split("-")
    quote = wording["quote"].format(name=name, month=MONTHS[language][int(number) - 1], year=year, day=plan.today.isoformat())
    title = f"# Journal — {month} — {name}" if month_first else f"# Journal — {name} — {month}"
    return [title, "", f"[{wording['back']}](../{plan.page.name})", "", f"> {quote}"]


# --- Commands ------------------------------------------------------------------------------------


def roll_page(plan: Plan, label: str) -> dict | None:
    """Move the entries of past months of the page into their journals; None when there is nothing to move."""
    doc = plan.doc(plan.page)
    section = find_section(doc.lines)
    current = plan.today.isoformat()[:7]
    stale = [entry for entry in section.entries if entry.day[:7] < current] if section else []
    if not stale:
        return None
    moved: dict[str, list[tuple[str, list[str]]]] = {}
    for entry in stale:
        moved.setdefault(entry.day[:7], []).append((entry.day, [shift_links(line) for line in doc.lines[entry.start:entry.end]]))
    for entry in reversed(stale):
        remove_range(doc.lines, entry.start, entry.end)
    months = []
    for month in sorted(moved):
        journal = plan.journal(month)
        created = not journal.lines
        if created:
            journal.lines = new_journal(plan, month)
        known = {tuple(journal.lines[e.start:e.end]) for e in whole(journal.lines).entries}
        duplicates = 0
        for day, block in moved[month]:
            if tuple(block) in known:
                duplicates += 1
                continue
            known.add(tuple(block))
            place(journal.lines, block, day, True, False)
        months.append({"month": month, "count": len(moved[month]), "duplicates": duplicates,
                       "journal": journal.path.relative_to(plan.brain).as_posix(), "created": created})
    set_previous(plan, set(moved))
    return {"project": label, "page": plan.page.relative_to(plan.brain).as_posix(), "moved": len(stale), "months": months}


def commit(plan: Plan, dry_run: bool) -> None:
    """Write the changed files (journals first, the page last), unless one changed since it was read."""
    for doc in plan.docs.values():
        current = doc.path.read_bytes().decode("utf-8") if doc.path.exists() else None
        if current != doc.original:
            raise ActionError("conflict", f"{doc.path.name} changed since it was read. Refresh before trying again.")
    changed = [doc for doc in plan.docs.values() if doc.dirty]
    if dry_run or not changed:
        return
    changed.sort(key=lambda doc: doc.path == plan.page)
    snapshots: dict[Path, str | None] = {}
    made: list[Path] = []
    try:
        for doc in changed:
            snapshots[doc.path] = doc.original
            if not doc.path.parent.exists():
                doc.path.parent.mkdir(parents=True)
                made.append(doc.path.parent)
            action.atomic_write(doc.path, doc.render().encode("utf-8"))
    except Exception:
        for path, previous in snapshots.items():
            try:
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    action.atomic_write(path, previous.encode("utf-8"))
            except OSError:
                pass
        for folder in made:
            try:
                folder.rmdir()
            except OSError:
                pass
        raise


def today_date() -> date:
    return date.fromisoformat(action.today())


def clean_line(value: object, field_name: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ActionError("bad_request", f"{field_name} is required.")
    value = value.strip()
    if not value or len(value) > limit or any(char in value for char in "\r\n\x00"):
        raise ActionError("bad_request", f"{field_name} must be 1 to {limit} characters on one line.")
    return value


def add(brain: Path, project: str, model: str, text: str, day: str = "", dry_run: bool = False) -> dict:
    page, label = locate(brain, project)
    model = clean_line(model, "Model", MODEL_LIMIT)
    text = clean_line(text, "Text", ENTRY_LIMIT)
    when = action.parse_date(day, "Date") if day else action.today()
    line = f"- {when} — {text} ({model})"
    plan = Plan(brain, page, today_date())
    rolled = roll_page(plan, label) or {"project": label, "page": page.relative_to(brain).as_posix(), "moved": 0, "months": []}
    month = when[:7]
    if month < plan.today.isoformat()[:7]:
        journal = plan.journal(month)
        created = not journal.lines
        if created:
            journal.lines = new_journal(plan, month)
        place(journal.lines, [shift_links(line)], when, False, False)
        ensure_section(plan.doc(page))
        set_previous(plan, {month})
        target = journal.path
    else:
        ensure_section(plan.doc(page))
        place(plan.doc(page).lines, [line], when, False, True)
        created, target = False, page
    commit(plan, dry_run)
    return {"project": label, "page": page.relative_to(brain).as_posix(), "file": target.relative_to(brain).as_posix(),
            "date": when, "entry": line, "journal": target != page, "created_file": created, "rolled": rolled, "dry_run": dry_run}


def roll(brain: Path, project: str | None, write: bool) -> dict:
    pages = [locate(brain, project)] if project else project_pages(brain)
    moves, errors = [], []
    for page, label in pages:
        plan = Plan(brain, page, today_date())
        try:
            found = roll_page(plan, label)
            commit(plan, not write)
        except (ActionError, OSError, UnicodeDecodeError) as error:
            if project:
                raise
            errors.append({"project": label, "error": getattr(error, "message", str(error))})
            continue
        if found:
            moves.append(found)
    result = {"dry_run": not write, "checked": len(pages), "total": sum(move["moved"] for move in moves), "projects": moves}
    if errors:
        result["errors"] = errors
    return result


# --- Command line --------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write the timeline of a project page and roll its past months into journal/ (JSON output).")
    parser.add_argument("--brain", action="append", type=Path, metavar="PATH", help="brain to use (default: BRAIN_DIR, else the default brain of Work)")
    sub = parser.add_subparsers(dest="command", required=True)
    project_help = "register, project folder, client/mission or label; clients/<client> for a client index page"

    p = sub.add_parser("add", help="write a dated entry in the timeline (past months are rolled first)")
    p.add_argument("--project", required=True, help=project_help)
    p.add_argument("--model", required=True, help="model that writes the entry, shown in parentheses")
    p.add_argument("--date", default="", help="date of the event YYYY-MM-DD (default: today, Europe/Paris)")
    p.add_argument("--dry-run", action="store_true", help="print the result without writing")
    p.add_argument("text", help="text of the entry")

    p = sub.add_parser("roll", help="move the timeline entries of past months into journal/YYYY-MM.md")
    p.add_argument("--project", help=project_help + " (default: every project page of the brain)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="write nothing (default behavior)")
    mode.add_argument("--write", action="store_true", help="apply the moves")
    return parser


def run(args: argparse.Namespace) -> object:
    brain = (args.brain[0] if args.brain else action.BRAIN).expanduser().resolve()
    if not (brain / "projects").is_dir():
        raise ActionError("not_found", f"No projects under {brain / 'projects'}")
    if args.command == "add":
        return add(brain, args.project, args.model, args.text, args.date, args.dry_run)
    return roll(brain, args.project, args.write)


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
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT["conflict"] if isinstance(result, dict) and result.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
