# /// script
# requires-python = ">=3.11"
# ///
"""Read-only structural checks for the brain and its Work routing."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

WORK = Path(os.environ.get("WORK_DIR", Path(__file__).resolve().parents[3])).resolve()
BRAIN = Path(os.environ.get("BRAIN_DIR", WORK / "brain")).resolve()
ACTION = re.compile(r"^- \[([ xX])\] \*\*([A-Z]{2,5}-\d{3})\*\*")
KANBAN = re.compile(r"^- \[([ xX])\].*?\*\*([A-Z]{2,5}-\d{3})\b")
HUMAN_OUTPUTS = {".pptx", ".pdf", ".drawio", ".docx", ".xlsx"}


@dataclass(frozen=True)
class Finding:
    level: str
    path: Path
    detail: str

    def render(self) -> str:
        try:
            place = self.path.relative_to(WORK)
        except ValueError:
            place = self.path
        return f"{self.level}: {place}: {self.detail}"


def checked(value: str) -> bool:
    return value.lower() == "x"


def source_roots() -> list[tuple[Path, str, str | None]]:
    roots: list[tuple[Path, str, str | None]] = []
    for mission in sorted((BRAIN / "projects/clients").glob("*/missions/*")):
        if mission.is_dir():
            roots.append((mission, mission.name, mission.parent.parent.name))
    internal = BRAIN / "projects/internal/interne"
    if internal.is_dir():
        roots.append((internal, "interne", None))
    return roots


def action_checks(findings: list[Finding]) -> None:
    actions: dict[str, tuple[bool, Path, str]] = {}
    for root, _, _ in source_roots():
        register = root / "state/actions.md"
        if not register.is_file():
            findings.append(Finding("ERROR", register, "registre d'actions absent"))
            continue
        for line in register.read_text(encoding="utf-8").splitlines():
            match = ACTION.match(line)
            if not match:
                continue
            action_id = match.group(2)
            if action_id in actions:
                findings.append(Finding("ERROR", register, f"ID {action_id} déjà présent dans {actions[action_id][1].relative_to(WORK)}"))
            actions[action_id] = (checked(match.group(1)), register, line)

    kanban_file = BRAIN / "kanban.md"
    cards: dict[str, tuple[bool, str]] = {}
    for line in kanban_file.read_text(encoding="utf-8").splitlines():
        match = KANBAN.match(line)
        if not match:
            continue
        action_id = match.group(2)
        if action_id in cards:
            findings.append(Finding("ERROR", kanban_file, f"carte {action_id} présente plusieurs fois"))
        cards[action_id] = (checked(match.group(1)), line)
        if action_id not in actions:
            # Some personal projects still use the legacy in-file action list.
            if not action_id.startswith("PRS-"):
                findings.append(Finding("REVIEW", kanban_file, f"carte {action_id} sans registre structuré"))
        elif checked(match.group(1)) != actions[action_id][0]:
            findings.append(Finding("REVIEW", kanban_file, f"statut {action_id} différent de {actions[action_id][1].relative_to(WORK)}"))

    owner_file = BRAIN / ".data/doctor.json"
    owner_name = os.environ.get("BRAIN_OWNER", "").strip()
    if not owner_name and owner_file.is_file():
        owner_name = str(json.loads(owner_file.read_text(encoding="utf-8")).get("owner", "")).strip()
    if owner_name:
        for action_id, (_, register, line) in actions.items():
            owner = line.split(" — ", 2)[1] if " — " in line else ""
            if owner_name in owner and action_id not in cards:
                findings.append(Finding("REVIEW", register, f"action du propriétaire {action_id} absente du kanban"))

    print(f"Actions structurées : {len(actions)} ; cartes liées : {len(cards)}")


def frontmatter_field(content: str, name: str) -> str | None:
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---\n", 4)
    if end < 0:
        return None
    match = re.search(rf"^{re.escape(name)}:\s*(.*)$", content[4:end], re.M)
    return match.group(1).strip().strip('"\'') if match else None


def source_checks(findings: list[Finding]) -> None:
    count = 0
    for root, mission, client in source_roots():
        source_dir = root / "sources"
        if not source_dir.is_dir():
            continue
        for month in sorted(source_dir.iterdir()):
            if not month.is_dir():
                continue
            index = month / "index.md"
            if not index.is_file():
                findings.append(Finding("ERROR", index, "index mensuel absent"))
                continue
            index_text = index.read_text(encoding="utf-8")
            for item in sorted(month.iterdir()):
                if item == index:
                    continue
                target = item / "index.md" if item.is_dir() else item
                if not target.is_file():
                    findings.append(Finding("REVIEW", item, "entrée de source sans fichier Markdown d'index"))
                    continue
                count += 1
                relative = target.relative_to(month).as_posix()
                occurrences = index_text.count(f"]({relative})")
                if occurrences != 1:
                    findings.append(Finding("ERROR", index, f"source {relative} référencée {occurrences} fois"))
                if item.is_dir():
                    continue
                if item.suffix != ".md":
                    findings.append(Finding("REVIEW", item, "fichier non Markdown parmi les sources"))
                    continue
                content = item.read_text(encoding="utf-8")
                date = frontmatter_field(content, "date")
                if not date:
                    findings.append(Finding("REVIEW", item, "date de source absente"))
                elif not item.name.startswith(date) or not date.startswith(month.name):
                    findings.append(Finding("REVIEW", item, f"date {date}, nom et mois incohérents"))
                if frontmatter_field(content, "mission") != mission:
                    findings.append(Finding("REVIEW", item, f"mission attendue : {mission}"))
                if client and frontmatter_field(content, "client") != client:
                    findings.append(Finding("REVIEW", item, f"client attendu : {client}"))
    print(f"Sources indexées examinées : {count}")


def transcript_checks(findings: list[Finding]) -> None:
    state = BRAIN / ".data/transcripts.json"
    if not state.is_file():
        findings.append(Finding("REVIEW", state, "état des transcripts absent"))
        return
    data = json.loads(state.read_text(encoding="utf-8"))
    count = 0
    for name, record in data.items():
        for raw in record.get("destinations", []):
            count += 1
            destination = (BRAIN / raw).resolve()
            if not destination.is_relative_to(BRAIN.resolve()) or not destination.is_file():
                findings.append(Finding("ERROR", state, f"destination du transcript {name} absente ou hors brain : {raw}"))
    print(f"Destinations de transcripts examinées : {count}")


def routing_checks(findings: list[Finding]) -> None:
    for root, dirs, names in os.walk(BRAIN):
        dirs[:] = [d for d in dirs if d not in {".git", ".venv", ".uv-cache", "__pycache__"}]
        folder = Path(root)
        for name in names:
            path = folder / name
            if path.suffix.lower() in HUMAN_OUTPUTS:
                findings.append(Finding("REVIEW", path, "livrable humain dans brain ; vérifier son rangement dans artifacts/"))
        if folder.name == "build":
            findings.append(Finding("REVIEW", folder, "dossier build dans brain ; déterminer s'il est durable ou relève de agents/"))
    for surface in (WORK / ".agents/skills", WORK / ".claude/skills"):
        if not surface.is_dir():
            continue
        for path in surface.iterdir():
            if path.is_symlink() and not path.exists():
                findings.append(Finding("ERROR", path, "lien symbolique cassé"))

    artifacts = WORK / "artifacts"
    if artifacts.is_dir():
        for project in artifacts.iterdir():
            if not project.is_dir():
                continue
            roots = [project] if project.name != "internal" else [p for p in project.iterdir() if p.is_dir()]
            for root in roots:
                for bundle in root.iterdir():
                    if bundle.is_dir() and any(p.is_file() for p in bundle.rglob("*")) and not (bundle / "README.md").is_file():
                        findings.append(Finding("REVIEW", bundle, "artefact sans README.md de provenance"))


def git_hygiene_checks(findings: list[Finding]) -> None:
    result = subprocess.run(
        ["git", "-C", str(BRAIN), "ls-files", "-z"],
        capture_output=True,
        check=True,
    )
    tracked = [Path(os.fsdecode(raw)) for raw in result.stdout.split(b"\0") if raw]
    generated = {".DS_Store", "__pycache__", ".venv", ".uv-cache", "node_modules"}
    for relative in tracked:
        path = BRAIN / relative
        if path.name == ".env":
            findings.append(Finding("ERROR", path, ".env suivi par Git ; examiner les métadonnées sans lire son contenu"))
        elif any(part in generated for part in relative.parts) or path.suffix in {".pyc", ".log", ".tmp"}:
            findings.append(Finding("REVIEW", path, "fichier généré ou temporaire suivi par Git"))
    print(f"Fichiers suivis par Git examinés : {len(tracked)}")


def main() -> None:
    if not BRAIN.is_dir():
        raise SystemExit("brain/ absent : installer la mémoire avant le diagnostic")
    findings: list[Finding] = []
    action_checks(findings)
    source_checks(findings)
    transcript_checks(findings)
    routing_checks(findings)
    git_hygiene_checks(findings)
    for finding in sorted(findings, key=lambda item: (item.level != "ERROR", str(item.path), item.detail)):
        print(finding.render())
    errors = sum(f.level == "ERROR" for f in findings)
    reviews = sum(f.level == "REVIEW" for f in findings)
    print(f"Bilan : {errors} erreur(s), {reviews} point(s) à examiner")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
