#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""commit-msg check: Conventional Commits subject, no AI attribution (rules of kit/brain/docs/GIT.md).

Usage: check-commit-msg.py <message-file>. Merge, revert and fixup/squash commits are not checked.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = "feat|fix|docs|refactor|chore|test|perf|build|ci|style|revert"
SUBJECT = re.compile(rf"^({TYPES})(\([a-z0-9][a-z0-9._/-]*\))?!?: \S.*$")
AI_MARKS = re.compile(r"(?i)(co-authored-by:.*(claude|anthropic|openai|chatgpt|gpt|copilot|gemini|codex|cursor|bot))|generated (with|by) |🤖|noreply@anthropic\.com")
MAX_SUBJECT = 100


def main() -> int:
    lines = [line for line in Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").splitlines() if not line.startswith("#")]
    subject = next((line for line in lines if line.strip()), "")
    if re.match(r"^(Merge |Revert \"|fixup! |squash! )", subject):
        return 0
    errors = []
    if not SUBJECT.match(subject):
        errors.append(f"sujet non conforme (attendu `type(scope): sujet`, types : {TYPES.replace('|', ', ')}) : « {subject} »")
    elif subject.endswith("."):
        errors.append("le sujet ne se termine pas par un point")
    elif len(subject) > MAX_SUBJECT:
        errors.append(f"sujet trop long ({len(subject)} caractères, environ 72 attendus, {MAX_SUBJECT} au plus)")
    elif SUBJECT.match(subject) and re.match(r"^[^:]+: [A-Z]", subject):
        errors.append("le sujet commence par une minuscule")
    if any(AI_MARKS.search(line) for line in lines):
        errors.append("mention d'IA interdite dans le message (pas de Co-Authored-By d'IA ni de « Generated with »)")
    if errors:
        print("Commit refusé :", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    if len(subject) > 72:
        print(f"Avertissement : sujet de {len(subject)} caractères (environ 72 attendus).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
