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
        errors.append(f"subject does not follow the convention (expected `type(scope): subject`, types: {TYPES.replace('|', ', ')}): \"{subject}\"")
    elif subject.endswith("."):
        errors.append("the subject must not end with a period")
    elif len(subject) > MAX_SUBJECT:
        errors.append(f"subject too long ({len(subject)} characters, about 72 expected, {MAX_SUBJECT} at most)")
    elif SUBJECT.match(subject) and re.match(r"^[^:]+: [A-Z]", subject):
        errors.append("the subject must start with a lowercase letter after the colon")
    if any(AI_MARKS.search(line) for line in lines):
        errors.append("AI attribution is not allowed in the message (no AI Co-Authored-By, no \"Generated with\")")
    if errors:
        print("Commit refused:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    if len(subject) > 72:
        print(f"Warning: subject of {len(subject)} characters (about 72 expected).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
