#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Refuse a commit that stages a credential file or adds a line that looks like a secret.

Run from inside a Git repository (pre-commit hook). Only the staged additions are read; a line
that carries `secret-scan: ignore` is skipped. Matches are reported by file and line, never with
the value. Exit 1 when something is found.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import PurePosixPath

FORBIDDEN_NAMES = re.compile(r"(^|/)(\.env(\.[^/]*)?|id_(rsa|dsa|ecdsa|ed25519)[^/]*|[^/]*\.(pem|key|p12|pfx|kdbx|ovpn)|\.netrc|\.npmrc|\.pypirc)$")
ALLOWED_NAMES = re.compile(r"(^|/)\.env\.(example|sample|template)$|\.pub$")
PATTERNS = [
    ("clé privée", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("clé AWS", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("token GitHub", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b")),
    ("token GitLab", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("token Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("clé API (sk-)", re.compile(r"\bsk-[A-Za-z0-9_-]{24,}")),
    ("jeton Bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{30,}")),
    ("URL avec mot de passe", re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s:@]{4,}@[^/\s]+")),
    ("secret affecté", re.compile(r"""(?i)\b(api[_-]?key|secret|token|passw(or)?d|client[_-]?secret)\b["']?\s*[:=]\s*["']?(?!(?:example|your|xxx|changeme|<|\$|\{|None\b|null\b|true\b|false\b))[A-Za-z0-9/+_=.-]{20,}["']?\s*$""")),
]
IGNORE_MARK = "secret-scan: ignore"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, errors="replace").stdout


def main() -> int:
    names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0")
    findings: list[str] = []
    for name in filter(None, names):
        posix = PurePosixPath(name).as_posix()
        if FORBIDDEN_NAMES.search(posix) and not ALLOWED_NAMES.search(posix):
            findings.append(f"{name} : fichier d'identifiants (nom interdit)")
    diff = git("diff", "--cached", "-U0", "--no-color", "--diff-filter=ACMR")
    current, line_no = "", 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            line_no = int(match.group(1)) - 1 if match else 0
        elif line.startswith("+") and not line.startswith("+++"):
            line_no += 1
            text = line[1:]
            if IGNORE_MARK in text or len(text) > 2000:
                continue
            for label, pattern in PATTERNS:
                if pattern.search(text):
                    findings.append(f"{current}:{line_no} : {label}")
                    break
    if findings:
        print("Secrets possibles dans l'index (valeurs non affichées) :", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print("Retirer la valeur (ou ajouter `secret-scan: ignore` sur la ligne si c'est un faux positif).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
