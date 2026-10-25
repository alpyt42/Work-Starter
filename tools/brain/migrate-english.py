#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Convert a brain written with the French format labels to the English ones (dry run by default).

Only structural labels change, never written content: section titles, sub-bullet keys and statuses
of the action and decision registers, the `Previous months:` line of project pages, the front-matter
keys of person pages, the Tasks queries, button and seed labels of `tasks.md`, links to renamed kit
headings, and the French values of `.data/transcripts.json`, `.data/messages-state.json` and
`.data/brain.json`. Dated sources, journals, notes, workstreams, handoffs, `me/` and `skills/` are
never read for writing. What the script cannot convert safely (free variants, decisions written as
bullets, person pages without front matter) is listed, not changed.

    uv run tools/brain/migrate-english.py [--brain PATH] [--diff]   report what would change
    uv run tools/brain/migrate-english.py --write                   apply it
    uv run tools/brain/migrate-english.py --check                   exit 1 when something is left to convert

Running it again finds nothing: every rule only matches the French forms. `--write` refuses a file
with uncommitted changes (`--allow-dirty` to override); it never commits. `--no-tasks-labels`
keeps the French titles and help of `tasks.md` (its queries and button are still converted).
`--brain PATH` or BRAIN_DIR selects the brain (default: Work/brain).
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

WORK = Path(os.environ.get("WORK_DIR", Path(__file__).resolve().parents[2])).resolve()
BRAIN = Path(os.environ.get("BRAIN_DIR", WORK / "brain")).resolve()
NEVER = ("sources", "journal", "notes", "workstreams", "handoffs")  # project folders never written

# --- Action registers ----------------------------------------------------------------------------

ACTION_LINE = re.compile(r"^- \[.\] \*\*[A-Z]{2,5}-\d{3}\*\*")
ACTION_SECTIONS = {"Ouvertes": "Open", "Terminées": "Done", "Annulées": "Cancelled"}
ACTION_RULES = [  # (rule, pattern, replacement) on sub-bullets indented by four spaces
    ("created", re.compile(r"^    - créée\s*:\s*"), "    - created: "),
    ("updated", re.compile(r"^    - mise à jour\s*:\s*"), "    - updated: "),
    ("due", re.compile(r"^    - échéance\s*:\s*"), "    - due: "),
    ("done", re.compile(r"^    - faite?\s*:\s*"), "    - done: "),
    ("cancelled", re.compile(r"^    - annulée le (\d{4}-\d{2}-\d{2}) par "), r"    - cancelled: \1 by "),
    ("cancelled", re.compile(r"^    - annulée le (\d{4}-\d{2}-\d{2})"), r"    - cancelled: \1"),
    ("source", re.compile(r"^    - source\s+:\s*"), "    - source: "),
    ("history", re.compile(r"^    - (\d{2}/\d{2}) : "), r"    - \1: "),
]
ACTION_LEFT = [  # free variants reported, not converted
    (re.compile(r"^    - fait le \d{2}/\d{2}"), "« fait le DD/MM » kept as written"),
    (re.compile(r"^    - limite\s*:"), "« limite: » kept as written"),
    (re.compile(r"^    - \d{2}/\d{2}\b(?! : )[^:\n]*\s:\s"), "history line with a qualifier before « : », kept as written"),
]
ARCHIVE_TITLE = re.compile(r"^# Archive des actions (\d{4}) — (.+)$")
ARCHIVE_QUOTE = re.compile(r"^> Archive des actions closes de (.+) en (\d{4}) ; le registre vivant est \[actions\.md\]\(actions\.md\)\. Les ID restent réservés\.$")

# --- Decision registers --------------------------------------------------------------------------

DECISION_SECTIONS = {"Proposées": "Proposed", "Validées": "Accepted", "Refusées / remplacées": "Rejected / superseded"}
DECISION_STATUS = {"proposée": "proposed", "validée": "accepted", "refusée": "rejected", "remplacée": "superseded"}
DECISION_FIELDS = {"Contexte": "Context", "Décision": "Decision", "Conséquences": "Consequences", "Source": "Source",
                   "Validation": "Accepted", "Refus": "Rejected", "Remplacée par": "Superseded by"}
STATUS_TAIL = re.compile(r"(\((?:\d{4}-\d{2}-\d{2}, )?)statut\s*:\s*([^()]*)\)\s*$")
FIELD_LINE = re.compile(r"^- \*\*([^*]+?)\s*:\*\*")

# --- Pages, people, data -------------------------------------------------------------------------

PREVIOUS_MONTHS = re.compile(r"^Mois précédents\s*:\s*")
PERSON_KEYS = {"nom": "name", "organisation": "organization", "alias": "aliases", "derniere_maj": "updated"}
TRANSCRIPT_STATUS = {"traite": "processed", "ignore": "ignored", "decoupe": "split", "doublon": "duplicate", "a-decider": "undecided"}
MESSAGE_STATUS = {"traite": "processed", "ignore": "ignored"}
SCOPES = {"perso": "personal", "employeur": "employer"}

# Links to kit headings renamed in English (`kit/brain/AGENTS.md` and `kit/brain/docs/*.md`).
KIT_ANCHORS = {
    "AGENTS.md": {"sorienter-avant-décrire": "get-oriented-before-writing", "ce-qui-fait-foi": "source-of-truth",
                  "ranger-linformation": "where-information-goes", "plusieurs-brains": "several-brains",
                  "finir-le-travail": "finish-the-work", "références-à-ouvrir-au-bon-moment": "references-to-open-when-needed"},
    "docs/CONVENTIONS.md": {"dossiers-et-navigation": "folders-and-navigation", "sources-état-et-journal": "sources-state-and-journal",
                            "tableau-tasks-et-inbox": "tasks-board-and-inbox", "personnes-notes-et-voix": "people-notes-and-voice",
                            "liens-handoffs-et-archives": "links-handoffs-and-archives",
                            "ingestion-et-confidentialité": "ingestion-and-confidentiality", "forme": "form"},
    "docs/WORKFLOWS.md": {"les-fichiers-centraux": "the-central-files", "rythme--à-la-demande": "rhythm--on-demand",
                          "utiliser-la-liste-et-le-kanban-dans-obsidian": "use-the-list-and-the-kanban-in-obsidian",
                          "où-vivent-les-choses": "where-things-live", "exécuter-du-vrai-travail": "doing-real-work",
                          "gestes-de-maintenance-pour-lagent": "maintenance-gestures-for-the-agent"},
    "docs/GIT.md": {"identités-git-et-clés-ssh": "git-identities-and-ssh-keys", "publication-du-brain": "publishing-the-brain",
                    "repos-partagés-et-clones-client": "shared-repos-and-client-clones"},
}
LINK = re.compile(r"\]\(([^)\s#]*)#([^)\s]+)\)")

# --- tasks.md ------------------------------------------------------------------------------------

OLD_FORM = "kit/brain/templates/templater/nouvelle-action.md"
NEW_FORM = "kit/brain/templates/templater/new-action.md"
TASKS_LINES = {  # seed lines of tasks.md before the English formats → their English version
    "Les prochaines actions, la liste par projet et le kanban, au même endroit. Tant que le propriétaire n'est pas renseigné dans le starter, les vues montrent tous les responsables.":
        "Next actions, the list by project and the kanban, in one place. Until the owner is set in the starter, the views show every owner.",
    "> [Pilotage](#pilotage) · [Liste par projet](#liste-par-projet) · [Kanban](#kanban) · [Historique](#historique) · [Inbox](inbox.md)":
        "> [Focus](#focus) · [By project](#by-project) · [Kanban](#kanban) · [History](#history) · [Inbox](inbox.md)",
    "label: Nouvelle action": "label: New action",
    "tooltip: Ajouter une tâche dans le registre du projet choisi": "tooltip: Add a task to the register of the chosen project",
    "Choisis le projet, puis renseigne l'action. Le formulaire la range au bon endroit avec son ID, sa priorité et son échéance.":
        "Choose the project, then fill in the action. The form files it in the right place with its ID, priority and due date.",
    "> [!info]- Dans le navigateur": "> [!info]- In the browser",
    "> Depuis la racine de l'espace de travail, lance `uv run tools/tasks-web/tasks-web.py`, puis ouvre `http://127.0.0.1:8765/`. Cette [interface locale](../tools/tasks-web/README.md) lit et modifie les mêmes registres.":
        "> From the Work root, run `uv run tools/tasks-web/tasks-web.py`, then open `http://127.0.0.1:8765/`. This [local interface](../tools/tasks-web/README.md) reads and edits the same registers.",
    "## Pilotage": "## Focus",
    "> [!task-focus]+ Aujourd'hui": "> [!task-focus]+ Today",
    "> Choisis jusqu'à trois actions avec le crayon 📝 : **Scheduled / Planifiée = aujourd'hui**. Les échéances du jour, les retards et les actions planifiées non terminées remontent ici.":
        "> Pick up to three actions with the pencil 📝: **Scheduled = today**. Today's due dates, overdue actions and unfinished scheduled actions show up here.",
    "> > [!task-active]+ En cours": "> > [!task-active]+ In progress",
    "> > [!task-next]+ À lancer": "> > [!task-next]+ Up next",
    "> > Les 8 premières par priorité, puis échéance. La liste complète reste dans les projets.":
        "> > The first 8 by priority, then due date. The full list stays in the projects.",
    "> [!task-wait]+ À relancer": "> [!task-wait]+ Follow up",
    "> [!task-calendar]- Échéances · 7 prochains jours": "> [!task-calendar]- Due · next 7 days",
    "## Liste par projet": "## By project",
    "> [!task-project]- [Setup du système](projects/internal/setup/setup.md)": "> [!task-project]- [System setup](projects/internal/setup/setup.md)",
    "> [!task-project]- Autres projets": "> [!task-project]- Other projects",
    "Ajoute un encadré dédié quand un projet doit rester visible, puis exclus son registre d'« Autres projets ».":
        "Add a dedicated box when a project must stay visible, then exclude its register from “Other projects”.",
    "Pour déplacer une action, fais un clic droit sur sa case ou utilise le crayon 📝. Les colonnes lisent directement les registres.":
        "To move an action, right-click its checkbox or use the pencil 📝. The columns read the registers directly.",
    "> > [!column] À faire": "> > [!column] To do",
    "> > [!column] En cours": "> > [!column] In progress",
    "> > [!column] En attente": "> > [!column] Waiting",
    "> > [!column] Terminées récemment": "> > [!column] Recently done",
    "## Historique": "## History",
    "> [!task-history]- 15 dernières clôtures": "> [!task-history]- Last 15 closed",
    "> [!help]- Les gestes utiles": "> [!help]- How to",
    "> **Terminer** : cocher la case ; la date de fin est ajoutée au registre.": "> **Finish**: tick the checkbox; the done date is added to the register.",
    "> **Commencer ou mettre en attente** : clic droit sur la case, ou crayon 📝, puis choisir l'état.":
        "> **Start or put on hold**: right-click the checkbox, or use the pencil 📝, then choose the state.",
    "> **Prioriser** : choisir une priorité avec le crayon 📝. **Planifier** indique quand travailler ; **Due / Échéance** indique quand livrer.":
        "> **Prioritise**: choose a priority with the pencil 📝. **Scheduled** says when to work on it; **Due** says when to deliver.",
    "> **Capturer sans classer** : écrire dans l'[Inbox](inbox.md), puis trier plus tard.": "> **Capture without filing**: write in the [Inbox](inbox.md), then triage it later.",
    "> Les dates simples sont lues par Tasks. Les formulations vagues restent dans le registre. Voir les [conventions](../kit/brain/docs/CONVENTIONS.md).":
        "> Plain dates are read by Tasks. Vague wordings stay in the register. See the [conventions](../kit/brain/docs/CONVENTIONS.md).",
}
QUOTE_PREFIX = re.compile(r"^((?:> ?)*)(.*)$")
WAITING_EXCLUDED = "status.name does not include attente"
WAITING = "status.name includes attente"
OPEN_TYPES = "(status.type is TODO) OR (status.type is IN_PROGRESS)"


@dataclass
class Change:
    path: Path
    old: str
    new: str
    counts: dict[str, int] = field(default_factory=dict)
    left: list[str] = field(default_factory=list)  # « line N: reason », not converted


def count(change: Change, rule: str, n: int = 1) -> None:
    change.counts[rule] = change.counts.get(rule, 0) + n


def split(text: str) -> tuple[list[str], str]:
    eol = "\r\n" if "\r\n" in text else "\n"
    return text.split(eol), eol


# --- Converters (text in, text out; they record counts and what they leave) ------------------------


def convert_actions(change: Change) -> None:
    lines, eol = split(change.old)
    for number, line in enumerate(lines):
        heading = re.fullmatch(r"## (.+?)\s*", line)
        if heading and heading.group(1) in ACTION_SECTIONS:
            lines[number] = f"## {ACTION_SECTIONS[heading.group(1)]}"
            count(change, "section")
            continue
        if (found := ARCHIVE_TITLE.match(line)):
            lines[number] = f"# Actions archive {found.group(1)} — {found.group(2)}"
            count(change, "archive header")
            continue
        if (found := ARCHIVE_QUOTE.match(line)):
            lines[number] = (f"> Closed actions of {found.group(1)} archived for {found.group(2)}; the live register is "
                             "[actions.md](actions.md). IDs stay reserved.")
            count(change, "archive header")
            continue
        if ACTION_LINE.match(line):
            new, n = re.subn(r"(?<!\S)#lot/", "#group/", line)
            if n:
                lines[number] = new
                count(change, "group tag", n)
            continue
        if not line.startswith("    - "):
            continue
        for rule, pattern, replacement in ACTION_RULES:
            new, n = pattern.subn(replacement, line, count=1)
            if n:
                lines[number] = new
                count(change, rule)
                break
        else:
            for pattern, reason in ACTION_LEFT:
                if pattern.match(line):
                    change.left.append(f"line {number + 1}: {reason}")
                    break
    change.new = eol.join(lines)


def convert_decisions(change: Change) -> None:
    lines, eol = split(change.old)
    section_has_block = False
    for number, line in enumerate(lines):
        if line.startswith("# Décisions — "):
            lines[number] = "# Decisions — " + line[len("# Décisions — "):]
            count(change, "title")
            continue
        heading = re.fullmatch(r"## (.+?)\s*", line)
        if heading:
            section_has_block = False
            if heading.group(1) in DECISION_SECTIONS:
                lines[number] = f"## {DECISION_SECTIONS[heading.group(1)]}"
                count(change, "section")
            continue
        if line.startswith("### "):
            section_has_block = True
            found = STATUS_TAIL.search(line)
            if found:
                value = found.group(2).strip()
                status = DECISION_STATUS.get(value, value)
                if value not in DECISION_STATUS:
                    change.left.append(f"line {number + 1}: status « {value} » kept (not a known status)")
                lines[number] = f"{line[:found.start()]}{found.group(1)}status: {status})"
                count(change, "status")
            continue
        found = FIELD_LINE.match(line)
        if found:
            label = found.group(1).strip()
            if label in DECISION_FIELDS:
                new = f"- **{DECISION_FIELDS[label]}:**{line[found.end():]}"
                if new != line:  # `**Source:**` is already English
                    lines[number] = new
                    count(change, "field")
            elif label not in DECISION_FIELDS.values():
                change.left.append(f"line {number + 1}: field « {label} » kept as written")
            continue
        if line.startswith("- ") and not section_has_block:
            change.left.append(f"line {number + 1}: decision written as a bullet, not as a ### block: kept as written")
    change.new = eol.join(lines)


def convert_page(change: Change) -> None:
    lines, eol = split(change.old)
    for number, line in enumerate(lines):
        new, n = PREVIOUS_MONTHS.subn("Previous months: ", line, count=1)
        if n:
            lines[number] = new
            count(change, "previous months")
    change.new = eol.join(lines)


def convert_person(change: Change) -> None:
    lines, eol = split(change.old)
    if not lines or lines[0].strip() != "---":
        change.left.append("no front matter: nothing converted")
        change.new = change.old
        return
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        change.left.append("unterminated front matter: nothing converted")
        change.new = change.old
        return
    present = {m.group(1) for line in lines[1:end] if (m := re.match(r"^([A-Za-z_]+)\s*:", line))}
    for number in range(1, end):
        found = re.match(r"^([A-Za-z_]+)(\s*:)", lines[number])
        if found and found.group(1) in PERSON_KEYS:
            new_key = PERSON_KEYS[found.group(1)]
            if new_key in present:
                change.left.append(f"line {number + 1}: « {found.group(1)} » kept, « {new_key} » already present")
                continue
            lines[number] = new_key + lines[number][found.end(1):]
            count(change, "front matter")
    change.new = eol.join(lines)


def convert_tasks(change: Change, labels: bool) -> None:
    lines, eol = split(change.old)
    out: list[str] = []
    block: list[tuple[str, str]] | None = None  # (quote prefix, content) of the current ```tasks block

    # The waiting status `w` was a TODO named « En attente »; it becomes the type ON_HOLD, so every query keeps its
    # meaning. It is named in the queries only before the conversion: a converted page is not touched again.
    french = any(WAITING in line or WAITING_EXCLUDED in line for line in lines)

    def flush(rows: list[tuple[str, str]]) -> None:
        excludes = any(content.strip() == WAITING_EXCLUDED for _, content in rows)
        restricted = any(content.strip() in (OPEN_TYPES, "status.type is TODO") for _, content in rows)
        for prefix, content in rows:
            if not french:
                out.append(prefix + content)
                continue
            stripped = content.strip()
            if stripped == WAITING_EXCLUDED and restricted:
                count(change, "query")  # TODO and IN_PROGRESS no longer include the waiting actions
                continue
            if stripped == WAITING:
                content = "status.type is ON_HOLD"
                count(change, "query")
            elif not excludes and stripped == OPEN_TYPES:
                content = f"{OPEN_TYPES} OR (status.type is ON_HOLD)"
                count(change, "query")
            elif not excludes and stripped == "status.type is TODO":
                content = "(status.type is TODO) OR (status.type is ON_HOLD)"
                count(change, "query")
            elif WAITING in content or WAITING_EXCLUDED in content:  # inside a longer expression
                content = content.replace(WAITING_EXCLUDED, "status.type is not ON_HOLD").replace(WAITING, "status.type is ON_HOLD")
                count(change, "query")
            elif "attente" in stripped:
                change.left.append(f"query « {stripped} » kept: it names the French status")
            out.append(prefix + content)

    for line in lines:
        prefix, content = QUOTE_PREFIX.match(line).groups()
        if block is None:
            if content.strip() == "```tasks":
                block = []
                out.append(line)
                continue
            if OLD_FORM in line:
                line = line.replace(OLD_FORM, NEW_FORM)
                count(change, "button")
            elif labels and line.rstrip() in TASKS_LINES:
                line = TASKS_LINES[line.rstrip()]
                count(change, "label")
            out.append(line)
        elif content.strip() == "```":
            flush(block)
            block = None
            out.append(line)
        else:
            block.append((prefix, content))
    if block is not None:
        flush(block)
    change.new = eol.join(out)


def convert_anchors(change: Change, source: Path, brain: Path, kit: Path) -> None:
    def fix(found: re.Match) -> str:
        target, anchor = found.group(1), found.group(2)
        resolved = (source.parent / target).resolve() if target else source
        if source.name == "README.md" and source.parent.name == "inbox" and target == "../AGENTS.md" and anchor == "ranger-linformation":
            heading = re.search(r"^## Ranger l'information", (brain / "AGENTS.md").read_text(encoding="utf-8"), re.MULTILINE) if (brain / "AGENTS.md").is_file() else None
            if heading is None:  # the seed once pointed to the brain's AGENTS.md, which never had that section
                count(change, "kit anchor")
                return f"]({os.path.relpath(kit / 'AGENTS.md', source.parent)}#where-information-goes)"
        try:
            relative = resolved.relative_to(kit)
        except ValueError:
            return found.group(0)
        new = KIT_ANCHORS.get(relative.as_posix(), {}).get(anchor)
        if new is None:
            return found.group(0)
        count(change, "kit anchor")
        return f"]({target}#{new})"
    change.new = LINK.sub(fix, change.old)


def convert_json(change: Change, kind: str) -> None:
    """Rename the French keys and values of a .data JSON file in its text, so its layout is kept."""
    text = change.old
    if kind == "transcripts":
        text, n = re.subn(r'"date_traitement"(\s*:)', r'"processed_on"\1', text)
        if n:
            count(change, "key", n)
        mapping, key = TRANSCRIPT_STATUS, "status"
    elif kind == "messages":
        mapping, key = MESSAGE_STATUS, "status"
    else:
        mapping, key = SCOPES, "scope"
    for old, new in mapping.items():
        text, n = re.subn(rf'("{key}"\s*:\s*)"{re.escape(old)}"', rf'\1"{new}"', text)
        if n:
            count(change, "value", n)
    if text != change.old:  # the rewrite must be exactly the intended data change
        expected = rename_data(json.loads(change.old), kind)
        if json.loads(text) != expected:
            raise ValueError(f"{change.path}: unexpected JSON rewrite, nothing written")
    change.new = text


def rename_data(data: object, kind: str) -> object:
    if kind == "brain" and isinstance(data, dict):
        return {**data, "scope": SCOPES.get(data.get("scope"), data.get("scope"))} if "scope" in data else data
    mapping = TRANSCRIPT_STATUS if kind == "transcripts" else MESSAGE_STATUS

    def walk(value: object) -> object:
        if isinstance(value, dict):
            renamed = {("processed_on" if kind == "transcripts" and k == "date_traitement" else k): walk(v) for k, v in value.items()}
            if isinstance(renamed.get("status"), str):
                renamed["status"] = mapping.get(renamed["status"], renamed["status"])
            return renamed
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value
    return walk(data)


# --- Brain walk ----------------------------------------------------------------------------------


def project_files(brain: Path) -> list[Path]:
    """Markdown files of projects/ that may hold a format, outside the folders that are never written."""
    found = []
    for path in sorted((brain / "projects").rglob("*.md")):
        parts = path.relative_to(brain / "projects").parts
        if any(part in NEVER for part in parts[:-1]) or path.is_symlink():
            continue
        found.append(path)
    return found


def plan(brain: Path, labels: bool = True) -> list[Change]:
    kit = (brain.parent / "kit/brain").resolve()
    changes: dict[Path, Change] = {}

    def change_of(path: Path) -> Change:
        if path not in changes:
            text = path.read_bytes().decode("utf-8")
            changes[path] = Change(path, text, text)
        return changes[path]

    def apply(path: Path, convert, *extra) -> None:
        change = change_of(path)
        before = change.old
        change.old = change.new
        convert(change, *extra)
        change.old = before

    for path in project_files(brain):
        if path.parent.name == "state" and (path.name == "actions.md" or re.fullmatch(r"actions-archive-\d{4}\.md", path.name)):
            apply(path, convert_actions)
        elif path.parent.name == "state" and path.name == "decisions.md":
            apply(path, convert_decisions)
        elif path.stem == path.parent.name:
            apply(path, convert_page)
    for path in sorted((brain / "people").rglob("*.md")) if (brain / "people").is_dir() else []:
        if path.name != "README.md" and not path.name.startswith("_") and not path.is_symlink():
            apply(path, convert_person)
    if (brain / "tasks.md").is_file():
        apply(brain / "tasks.md", convert_tasks, labels)
    for path in [brain / "README.md", brain / "AGENTS.md", brain / "inbox" / "README.md", *sorted((brain / "docs").glob("*.md")),
                 *project_files(brain)]:
        if path.is_file():
            apply(path, convert_anchors, path, brain, kit)
    for name, kind in (("transcripts.json", "transcripts"), ("messages-state.json", "messages"), ("brain.json", "brain")):
        path = brain / ".data" / name
        if path.is_file():
            apply(path, convert_json, kind)
    return [change for change in changes.values() if change.new != change.old or change.left]


def dirty(brain: Path, paths: list[Path]) -> tuple[set[Path], str]:
    """Files that must not be written, and why: uncommitted changes, or all of them outside a Git repository."""
    result = subprocess.run(["git", "-C", str(brain), "status", "--porcelain", "-z", "--", *map(str, paths)],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        return {path.resolve() for path in paths}, "not a Git repository, use --allow-dirty"
    return {(brain / entry[3:]).resolve() for entry in filter(None, result.stdout.split("\0"))}, "uncommitted changes"


def write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.migrate-{os.getpid()}")
    try:
        temporary.write_bytes(text.encode("utf-8"))
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a brain's French format labels to English (dry run by default).")
    parser.add_argument("--brain", type=Path, metavar="PATH", help="brain to convert (default: Work/brain or BRAIN_DIR)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="apply the changes")
    mode.add_argument("--check", action="store_true", help="exit 1 when something is left to convert")
    parser.add_argument("--diff", action="store_true", help="print the unified diff of each file")
    parser.add_argument("--allow-dirty", action="store_true", help="also write files with uncommitted changes")
    parser.add_argument("--no-tasks-labels", action="store_true", help="keep the French titles and help of tasks.md")
    args = parser.parse_args()
    brain = (args.brain or BRAIN).expanduser().resolve()
    if not (brain / "projects").is_dir():
        print(f"error: no projects/ under {brain}", file=sys.stderr)
        return 2
    try:
        changes = plan(brain, labels=not args.no_tasks_labels)
    except (ValueError, OSError, UnicodeDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    pending = [change for change in changes if change.new != change.old]
    blocked, why = dirty(brain, [change.path for change in pending]) if args.write and not args.allow_dirty else (set(), "")
    total = 0
    for change in changes:
        name = change.path.relative_to(brain).as_posix()
        n = sum(change.counts.values())
        total += n
        if n:
            detail = ", ".join(f"{rule} {k}" for rule, k in sorted(change.counts.items()))
            state = f"refused ({why})" if change.path.resolve() in blocked else ("written" if args.write else "to convert")
            print(f"{name}: {n} change(s), {state} — {detail}")
        for left in change.left:
            print(f"{name}: left as is — {left}")
        if args.diff and change.new != change.old:
            sys.stdout.writelines(difflib.unified_diff(change.old.splitlines(keepends=True), change.new.splitlines(keepends=True),
                                                       f"a/{name}", f"b/{name}"))
    if args.write:
        for change in pending:
            if change.path.resolve() not in blocked:
                write(change.path, change.new)
    verb = "written" if args.write else "to convert"
    print(f"Total: {total} change(s) {verb} in {len(pending) - len(blocked)} file(s)"
          + (f"; {len(blocked)} file(s) refused, commit or set them aside first" if blocked else ""))
    if blocked:
        return 1
    return 1 if args.check and pending else 0


if __name__ == "__main__":
    sys.exit(main())
