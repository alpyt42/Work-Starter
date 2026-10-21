#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Propose, read and settle the decisions of a brain's registers (`projects/**/state/decisions.md`).

The register sits next to the project's `actions.md` and has three sections: `## Proposées`,
`## Validées` and `## Refusées / remplacées`. Each decision is a block:

    ### Titre (2026-10-13, statut : proposée)
    - **Contexte :** …
    - **Décision :** …
    - **Conséquences :** …
    - **Source :** [CR du 13/10](../sources/2026-10/2026-10-13-cr-daily-migration.md)
    - **Validation :** Propriétaire, 2026-10-14.

Existing blocks vary (status missing from the title, `active`, `remplacée`, optional `Suite`,
`Remplacée par`, `Source et validation`): the parser tolerates all of it and a write only touches
the block it moves or completes. Validated and refused decisions are newest first.

Commands (from the Work root, `uv run tools/brain/decision.py <command> --help` for details):

    list      [--project P] [--status proposee|validee|refusee|all] [--table]
    show      REF --project P
    propose   --project P --title T --decision D --source S [--context C] [--consequences C] [--date D]
    validate  REF --project P [--on D] [--by NOM] [--note TEXTE]
    refuse    REF --project P [--on D] [--by NOM] [--reason TEXTE]
    replace   OLD --by NEW --project P [--on D]

REF is the number given by `list` for that project (rank in the register, 1..n) or a unique
substring of the title (case-insensitive). Numbers change when a decision moves: list again.
Every write accepts `--dry-run`. Output is JSON on stdout. Exit codes: 0 done, 2 invalid request,
3 not found, 4 conflict or ambiguous reference. `--brain PATH` or BRAIN_DIR selects another brain;
ACTION_NOW (`AAAA-MM-JJ HH:MM`) fixes the clock for tests.
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

SECTION_TITLES = {"proposee": "Proposées", "validee": "Validées", "refusee": "Refusées / remplacées"}
STATUS_LABELS = {"proposee": "proposée", "validee": "validée", "refusee": "refusée"}
HEADER_RE = re.compile(r"^### (.+) \((\d{4}-\d{2}-\d{2})(?:, statut : ([^()]*))?\)\s*$")
FIELD_RE = re.compile(r"^- \*\*([^*]+?)\s*:\*\*\s*(.*)$")
QUOTE = "> Garder la source et le statut de chaque décision ; une décision validée ne se réécrit pas : une nouvelle la remplace."


# --- Reading -------------------------------------------------------------------------------------


@dataclass
class Decision:
    start: int
    end: int  # exclusive, trailing blank lines excluded
    title: str
    date: str
    status: str  # as written in the title ("" when absent)
    section: str  # heading text
    state: str  # proposee | validee | refusee | "" (unknown section)
    number: int


def section_state(heading: str) -> str:
    key = heading.strip().lower()
    if key.startswith("propos"):
        return "proposee"
    if key.startswith("valid"):
        return "validee"
    if key.startswith("refus"):
        return "refusee"
    return ""


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
        raise ActionError("bad_request", "decisions.md est un lien symbolique.")
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
        raise ActionError("bad_request", "Référence de décision invalide.")
    if ref.isdigit():
        for decision in found:
            if decision.number == int(ref):
                return decision
        raise ActionError("not_found", f"Aucune décision n° {ref}.")
    wanted = ref.casefold()
    exact = [d for d in found if d.title.casefold() == wanted]
    matches = exact or [d for d in found if wanted in d.title.casefold()]
    if not matches:
        raise ActionError("not_found", f"Aucune décision ne contient « {ref} ».")
    if len(matches) > 1:
        names = " ; ".join(f"n° {d.number} {d.title}" for d in matches[:5])
        raise ActionError("conflict", f"Référence ambiguë « {ref} » ({len(matches)} décisions) : {names}. Utiliser le numéro.")
    return matches[0]


def locate(brain: Path, project: str, ref: str) -> tuple[Path, str, list[str], list[Decision], Decision]:
    path = decisions_path(brain, project)
    if not path.is_file():
        raise ActionError("not_found", "Ce projet n'a pas de registre de décisions.")
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
        raise ActionError("conflict", "Le registre de décisions a changé. Actualise avant de réessayer.")
    if not dry_run:
        action.atomic_write(path, text.encode("utf-8"))
    return text


def header(title: str, date: str, status: str) -> str:
    return f"### {title} ({date}, statut : {status})" if date else f"### {title} (statut : {status})"


def with_status(line: str, status: str) -> str:
    match = HEADER_RE.match(line)
    if match:
        return header(match.group(1).strip(), match.group(2), status)
    return f"{line.rstrip()} (statut : {status})"


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
        lines.extend(["", f"## {SECTION_TITLES[state]}"])
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
    title = action.clean_text(title, "Titre", 300)
    decision = action.clean_text(decision, "Décision", 1500)
    source = action.clean_note(source)
    context = action.clean_text(context, "Contexte", 1500) if context else ""
    consequences = action.clean_text(consequences, "Conséquences", 1500) if consequences else ""
    day = action.parse_date(date, "Date") if date else action.today()
    block = [header(title, day, STATUS_LABELS["proposee"])]
    if context:
        block.append(f"- **Contexte :** {context}")
    block.append(f"- **Décision :** {decision}")
    if consequences:
        block.append(f"- **Conséquences :** {consequences}")
    block.append(f"- **Source :** {source}")
    if path.exists():
        existing, lines = read(path)
        if any(d.title.casefold() == title.casefold() for d in parse(lines)):
            raise ActionError("conflict", "Une décision porte déjà ce titre dans ce registre.")
    else:
        existing = None
        name = action.project_name(register.read_text(encoding="utf-8").splitlines(), register)
        lines = [f"# Décisions — {name}", "", QUOTE, ""]
        for title_ in SECTION_TITLES.values():
            lines += [f"## {title_}", ""]
        lines.pop()
    append_last(lines, "proposee", block)
    number = next(d.number for d in parse(lines) if d.title == title and d.state == "proposee")
    commit(path, existing, lines, dry_run)
    return {"register": path.relative_to(brain).as_posix(), "number": number, "title": title, "date": day,
            "label": f"proposition de « {title} »", "block": block, "created_file": existing is None, "dry_run": dry_run}


def settle(brain: Path, project: str, ref: str, target: str, closing: list[str], *, allowed: set[str], status: str,
           verb: str, dry_run: bool) -> dict:
    path, existing, lines, _, decision = locate(brain, project, ref)
    if decision.state not in allowed:
        raise ActionError("bad_request", f"« {decision.title} » est déjà dans « {decision.section or 'aucune section'} » : {verb} impossible.")
    block = lines[decision.start:decision.end]
    block[0] = with_status(block[0], status)
    block += closing
    remove(lines, decision.start, decision.end)
    insert_top(lines, target, block)
    commit(path, existing, lines, dry_run)
    return {"register": path.relative_to(brain).as_posix(), "title": decision.title, "from": decision.section,
            "to": SECTION_TITLES[target], "label": f"{verb} de « {decision.title} »", "block": block, "dry_run": dry_run}


def decision_owner(brain: Path, by: str = "") -> str:
    if by.strip():
        return action.clean_text(by, "Nom", 120)
    try:
        return action.clean_text(action.board_owner(brain), "Nom", 120)
    except (OSError, json.JSONDecodeError, SystemExit):
        raise ActionError(
            "bad_request",
            "Propriétaire inconnu : utiliser --by, BRAIN_OWNER ou « owner » dans brain/.data/doctor.json.",
        ) from None


def validate(brain: Path, project: str, ref: str, on: str = "", by: str = "", note: str = "", dry_run: bool = False) -> dict:
    day = action.parse_date(on, "Date") if on else action.today()
    who = decision_owner(brain, by)
    extra = action.clean_note(note) if note else ""
    line = f"- **Validation :** {sentence(f'{who}, {day}', extra)}"
    return settle(brain, project, ref, "validee", [line], allowed={"proposee"}, status="validée", verb="validation", dry_run=dry_run)


def refuse(brain: Path, project: str, ref: str, on: str = "", by: str = "", reason: str = "", dry_run: bool = False) -> dict:
    day = action.parse_date(on, "Date") if on else action.today()
    who = decision_owner(brain, by)
    extra = action.clean_note(reason) if reason else ""
    line = f"- **Refus :** {sentence(f'{who}, {day}', extra)}"
    return settle(brain, project, ref, "refusee", [line], allowed={"proposee"}, status="refusée", verb="refus", dry_run=dry_run)


def replace(brain: Path, project: str, old: str, new: str, on: str = "", dry_run: bool = False) -> dict:
    day = action.parse_date(on, "Date") if on else action.today()
    path, existing, lines, found, target = locate(brain, project, new)
    previous = pick(found, old)
    if previous.number == target.number:
        raise ActionError("bad_request", "Une décision ne se remplace pas elle-même.")
    if target.state == "refusee":
        raise ActionError("bad_request", f"« {target.title} » est refusée ou remplacée : elle ne peut pas remplacer une autre décision.")
    if previous.state not in {"proposee", "validee"}:
        raise ActionError("bad_request", f"« {previous.title} » est déjà dans « {previous.section or 'aucune section'} » : remplacement impossible.")
    block = lines[previous.start:previous.end]
    block[0] = with_status(block[0], "remplacée")
    block.append(f"- **Remplacée par :** « {target.title} » ({day}).")
    remove(lines, previous.start, previous.end)
    insert_top(lines, "refusee", block)
    commit(path, existing, lines, dry_run)
    return {"register": path.relative_to(brain).as_posix(), "title": previous.title, "replaced_by": target.title,
            "from": previous.section, "to": SECTION_TITLES["refusee"], "label": f"remplacement de « {previous.title} »",
            "block": block, "dry_run": dry_run}


# --- Command line --------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Propose, lit et tranche les décisions des registres du brain (sortie JSON).")
    parser.add_argument("--brain", action="append", type=Path, metavar="CHEMIN", help="brain à traiter (défaut : Work/brain ou BRAIN_DIR)")
    sub = parser.add_subparsers(dest="command", required=True)
    project_help = "registre, dossier du projet, client/mission ou libellé"

    def writable(p: argparse.ArgumentParser) -> None:
        p.add_argument("--dry-run", action="store_true", help="affiche le résultat sans écrire")

    p = sub.add_parser("list", help="liste les décisions")
    p.add_argument("--project", help=project_help)
    p.add_argument("--status", choices=("proposee", "validee", "refusee", "all"), default="all")
    p.add_argument("--table", action="store_true", help="une ligne par décision au lieu du JSON")

    p = sub.add_parser("show", help="affiche une décision")
    p.add_argument("ref", help="numéro du list ou sous-chaîne unique du titre")
    p.add_argument("--project", required=True, help=project_help)

    p = sub.add_parser("propose", help="ajoute une décision à la fin de « Proposées »")
    p.add_argument("--project", required=True, help=project_help)
    p.add_argument("--title", required=True)
    p.add_argument("--decision", required=True)
    p.add_argument("--source", required=True, help="texte de la ligne Source (lien Markdown relatif au registre)")
    p.add_argument("--context", default="")
    p.add_argument("--consequences", default="")
    p.add_argument("--date", default="", help="date de la décision AAAA-MM-JJ (défaut : aujourd'hui)")
    writable(p)

    p = sub.add_parser("validate", help="déplace une décision proposée en haut de « Validées »")
    p.add_argument("ref")
    p.add_argument("--project", required=True, help=project_help)
    p.add_argument("--on", default="", help="date de la validation AAAA-MM-JJ (défaut : aujourd'hui)")
    p.add_argument("--by", default="", help="personne qui valide (défaut : propriétaire du brain)")
    p.add_argument("--note", default="")
    writable(p)

    p = sub.add_parser("refuse", help="déplace une décision proposée en haut de « Refusées / remplacées »")
    p.add_argument("ref")
    p.add_argument("--project", required=True, help=project_help)
    p.add_argument("--on", default="")
    p.add_argument("--by", default="", help="personne qui refuse (défaut : propriétaire du brain)")
    p.add_argument("--reason", default="")
    writable(p)

    p = sub.add_parser("replace", help="marque une décision comme remplacée par une autre")
    p.add_argument("old")
    p.add_argument("--by", required=True, dest="new", help="décision qui remplace (numéro ou titre)")
    p.add_argument("--project", required=True, help=project_help)
    p.add_argument("--on", default="")
    writable(p)
    return parser


def run(args: argparse.Namespace) -> object:
    brain = (args.brain[0] if args.brain else action.BRAIN).expanduser().resolve()
    if not (brain / "projects").is_dir():
        raise ActionError("not_found", f"Registres introuvables sous {brain / 'projects'}")
    if args.command == "list":
        return listing(brain, args.project, args.status)
    if args.command == "show":
        return show(brain, args.project, args.ref)
    if args.command == "propose":
        return propose(brain, args.project, args.title, args.decision, args.source, args.context, args.consequences,
                       args.date, args.dry_run)
    if args.command == "validate":
        return validate(brain, args.project, args.ref, args.on, args.by, args.note, args.dry_run)
    if args.command == "refuse":
        return refuse(brain, args.project, args.ref, args.on, args.by, args.reason, args.dry_run)
    return replace(brain, args.project, args.old, args.new, args.on, args.dry_run)


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
            status = item["status"] or STATUS_LABELS.get(item["state"], "?")
            print(f"{item['number']:>3}. [{status}] {item['date'] or '----------'} — {item['title']}  ({item['project']})")
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
