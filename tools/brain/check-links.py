#!/usr/bin/env python3
"""Vérifie que tous les liens markdown de la mémoire pointent vers un fichier qui existe.

  - liens markdown `[x](y.md)` — résolus par chemin relatif (la forme normale)
  - wikilinks `[[cible]]`     — tolérés, résolus par nom de fichier (au cas où)

Code retour non nul s'il reste des liens morts. C'est ce qui remplace
« faire attention pendant un moment » par quelque chose de vérifiable.

Usage : `uv run tools/brain/check-links.py` depuis Work/ (ou n'importe où :
le script repère brain/ à la racine de Work ; variable BRAIN_DIR pour forcer,
comme les autres outils ; BRAIN reste accepté). Échoue si la mémoire est
introuvable, pour ne jamais annoncer « 0 lien mort » sur un dossier vide.
`--allow-missing-local` signale séparément les liens manquants vers les
artifacts et repos locaux, absents d'un nouveau checkout. Les fichiers de
`skills/<nom>/assets/` sont ignorés : ce sont des modèles copiés ailleurs, leurs
liens sont des placeholders (comme les `_*-TEMPLATE.md`).

Chaque brain est une frontière de confiance : un lien dont la cible se trouve
dans un AUTRE brain de la même racine Work (un dossier frère nommé `brain` ou
`brain-*`) est signalé à part (« lien inter-brains ») et fait échouer le
contrôle, même si la cible existe.
"""
import argparse
import collections
import os
import re
import subprocess
import sys

BRAIN = (
    os.environ.get("BRAIN_DIR")
    or os.environ.get("BRAIN")
    or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "brain")
)

BRAIN_NAME = re.compile(r"^brain(-[a-z0-9][a-z0-9-]*)?$")
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)
WIKILINK = re.compile(r"\[\[([^\]]+?)\]\]")
MDLINK = re.compile(r"\[(?:[^\[\]]|\[\[[^\]]*\]\])*\]\(([^)\s]+)\)")
FENCE = re.compile(r"```.*?```", re.S)
CODESPAN = re.compile(r"`[^`\n]*`")

# Cibles hors mémoire, légitimement non résolvables (ex. fichiers de mémoire d'agent).
WHITELIST: set[str] = set()


def is_local_work_target(path: str) -> bool:
    """True for targets in the sibling artifacts/ or repos/ directories."""
    work_root = os.path.dirname(os.path.realpath(BRAIN))
    target = os.path.realpath(path)
    for folder in ("artifacts", "repos"):
        # realpath on both sides: the pre-commit snapshot links these folders to the real ones
        local_root = os.path.realpath(os.path.join(work_root, folder))
        if os.path.commonpath((local_root, target)) == local_root:
            return True
    return False


def other_brain(full_path: str) -> "str | None":
    """Name of the sibling brain that contains `full_path`, None when it is not in another brain."""
    work_root = os.path.dirname(os.path.abspath(BRAIN))
    own = os.path.basename(os.path.abspath(BRAIN))
    relative = os.path.relpath(os.path.normpath(full_path), work_root)
    first = relative.split(os.sep)[0]
    if first in ("", ".", "..") or first == own or not BRAIN_NAME.fullmatch(first):
        return None
    return first


def mask_code(text: str) -> str:
    text = FENCE.sub(lambda m: " " * len(m.group(0)), text)
    return CODESPAN.sub(lambda m: " " * len(m.group(0)), text)


def is_skill_asset(rel: str) -> bool:
    """True pour `skills/<nom>/assets/**` : des modèles copiés ailleurs, dont les liens sont des placeholders."""
    parts = rel.replace(os.sep, "/").split("/")
    return len(parts) > 3 and parts[0] == "skills" and parts[2] == "assets"


def list_md_files() -> list[str]:
    """Fichiers suivis par git si on est dans un repo, sinon tous les .md du dossier (hors modèles de skills)."""
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
                             cwd=BRAIN, capture_output=True, text=True, check=True).stdout.split()
        # un fichier déplacé / supprimé mais pas encore commité reste dans l'index : on l'ignore
        out = [f for f in out if os.path.exists(os.path.join(BRAIN, f)) and not is_skill_asset(f)]
        if out:
            return out
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    files = []
    for root, dirs, names in os.walk(BRAIN):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for n in names:
            if n.endswith(".md"):
                files.append(os.path.relpath(os.path.join(root, n), BRAIN))
    return sorted(f for f in files if not is_skill_asset(f))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-missing-local",
        action="store_true",
        help="report missing artifacts/ and repos/ targets without failing",
    )
    args = parser.parse_args()

    if not os.path.isdir(BRAIN):
        print(f"✗ mémoire introuvable : {BRAIN} (définir BRAIN_DIR)", file=sys.stderr)
        return 2
    files = list_md_files()
    if not files:
        print(f"✗ aucun fichier markdown dans {BRAIN}", file=sys.stderr)
        return 2
    by_basename = collections.defaultdict(list)
    for rel in files:
        by_basename[os.path.basename(rel)[:-3]].append(rel)

    dead_wiki, dead_md, cross_brain, placeholders = [], [], [], 0
    unverified_local = []
    n_wiki = n_md = 0

    for rel in files:
        if os.path.basename(rel).startswith("_") and "TEMPLATE" in rel:
            continue  # un template contient des placeholders par définition
        with open(os.path.join(BRAIN, rel), encoding="utf-8") as fh:
            text = mask_code(fh.read())

        for raw in WIKILINK.findall(text):
            target = re.split(r"\\?\|", raw)[0].strip().rstrip("\\")
            n_wiki += 1
            base = os.path.basename(target)
            if base.endswith(".md"):
                base = base[:-3]
            if "<" in target or base in WHITELIST:
                placeholders += 1
                continue
            if not by_basename.get(base):
                dead_wiki.append((rel, target))

        for target in MDLINK.findall(text):
            if target.startswith(("http", "#", "mailto:")) or SCHEME.match(target):
                continue
            target = target.split("#")[0]
            if not target:
                continue
            if "<" not in target and "YYYY" not in target:
                # A link into another brain is refused whatever it points at (file, folder, any extension).
                foreign = other_brain(os.path.join(BRAIN, os.path.dirname(rel), target))
                if foreign:
                    cross_brain.append((rel, target))
                    continue
            if not target.endswith(".md"):
                continue
            if "<" in target or "YYYY" in target:
                placeholders += 1
                continue
            n_md += 1
            resolved = os.path.normpath(os.path.join(os.path.dirname(rel), target))
            full_path = os.path.join(BRAIN, resolved)
            if not os.path.exists(full_path):
                if args.allow_missing_local and is_local_work_target(full_path):
                    unverified_local.append((rel, target))
                else:
                    dead_md.append((rel, target))

    print(f"fichiers      : {len(files)}")
    print(f"liens md      : {n_md}  (+ {placeholders} placeholders ignorés)")
    print(f"wikilinks     : {n_wiki}")
    print(f"morts (md)    : {len(dead_md)}")
    print(f"morts (wiki)  : {len(dead_wiki)}")
    print(f"inter-brains  : {len(cross_brain)}")
    if args.allow_missing_local:
        print(f"liens locaux non vérifiés: {len(unverified_local)}")

    groups = [
        ("⛔", "LIEN MD MORT", dead_md, "({})", ""),
        ("⛔", "WIKILINK MORT", dead_wiki, "[[{}]]", ""),
        ("⛔", "LIEN INTER-BRAINS", cross_brain, "({})", " (un brain ne renvoie jamais vers un autre brain)"),
    ]
    if args.allow_missing_local:
        groups.append(("⚠", "LIEN MD MORT", unverified_local, "({})", " (local, non bloquant)"))

    for icon, label, links, fmt, suffix in groups:
        if links:
            print()
            grouped = collections.defaultdict(list)
            for src, tgt in links:
                grouped[tgt].append(src)
            for tgt, srcs in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
                print(f"  {icon} {label} {fmt.format(tgt)} — {len(srcs)}×{suffix}")
                for s in sorted(set(srcs)):
                    print(f"       {s}")

    return 1 if (dead_wiki or dead_md or cross_brain) else 0


if __name__ == "__main__":
    sys.exit(main())
