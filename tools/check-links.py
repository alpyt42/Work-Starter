#!/usr/bin/env python3
"""Vérifie que tous les liens markdown de la mémoire pointent vers un fichier qui existe.

  - liens markdown `[x](y.md)` — résolus par chemin relatif (la forme normale)
  - wikilinks `[[cible]]`     — tolérés, résolus par nom de fichier (au cas où)

Code retour non nul s'il reste des liens morts. C'est ce qui remplace
« faire attention pendant un moment » par quelque chose de vérifiable.

Usage : `uv run tools/check-links.py` depuis Work/ (ou n'importe où :
le script repère brain/ à côté de tools/ ; variable BRAIN_DIR pour forcer,
comme les autres outils ; BRAIN reste accepté). Échoue si la mémoire est
introuvable, pour ne jamais annoncer « 0 lien mort » sur un dossier vide.
`--allow-missing-local` signale séparément les liens manquants vers les
artifacts et repos locaux, absents d'un nouveau checkout.
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
    or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "brain")
)

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
        local_root = os.path.join(work_root, folder)
        if os.path.commonpath((local_root, target)) == local_root:
            return True
    return False


def mask_code(text: str) -> str:
    text = FENCE.sub(lambda m: " " * len(m.group(0)), text)
    return CODESPAN.sub(lambda m: " " * len(m.group(0)), text)


def list_md_files() -> list[str]:
    """Fichiers suivis par git si on est dans un repo, sinon tous les .md du dossier."""
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
                             cwd=BRAIN, capture_output=True, text=True, check=True).stdout.split()
        # un fichier déplacé / supprimé mais pas encore commité reste dans l'index : on l'ignore
        out = [f for f in out if os.path.exists(os.path.join(BRAIN, f))]
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
    return sorted(files)


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

    dead_wiki, dead_md, placeholders = [], [], 0
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
            if target.startswith(("http", "#", "mailto:")):
                continue
            target = target.split("#")[0]
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
    if args.allow_missing_local:
        print(f"liens locaux non vérifiés: {len(unverified_local)}")

    groups = [
        ("⛔", "LIEN MD MORT", dead_md, "({})", ""),
        ("⛔", "WIKILINK MORT", dead_wiki, "[[{}]]", ""),
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

    return 1 if (dead_wiki or dead_md) else 0


if __name__ == "__main__":
    sys.exit(main())
