#!/usr/bin/env python3
"""Gate de zone client — hook PreToolUse (matcher: Bash) de Claude Code.

Périmètre : UNIQUEMENT les commandes qui opèrent dans GATE_PATH (les clones de repos
client). Tout le reste sort en silence, aucun avis, aucune friction.

Doctrine : lecture libre · toute écriture qui laisse une trace chez le client = `ask`
(GO de la personne par action) · les gestes qui neutralisent les gates eux-mêmes = `deny`.
"""
import json
import re
import sys

# Chemin de la zone gatée, RELATIF à la racine de l'espace de travail. À adapter.
GATE_PATH = "repos/CLIENT/clones"

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)  # input illisible : ne pas bloquer le reste du monde

cmd = (data.get("tool_input") or {}).get("command") or ""
cwd = data.get("cwd") or ""

# Le chemin gaté ne compte que s'il est OPÉRÉ, pas cité : un message de commit qui
# mentionne la zone ne doit pas déclencher le gate. Donc les chaînes entre guillemets
# sont ignorées, SAUF quand elles suivent un cd / -C / --git-dir.
cmd_unquoted = re.sub(r"'[^']*'|\"[^\"]*\"", " ", cmd)
in_scope = (
    GATE_PATH in cwd
    or GATE_PATH in cmd_unquoted
    or re.search(r"(?:\bcd\s+|-C\s*|--git-dir[=\s]+)['\"][^'\"]*" + re.escape(GATE_PATH), cmd)
)
if not in_scope:
    sys.exit(0)


def decide(decision: str, reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


# ── DENY : les gestes qui neutralisent les gates eux-mêmes ──────────────────
if re.search(r"--no-verify\b", cmd):
    decide("deny", "Gate zone client : --no-verify court-circuite les hooks git — geste réservé à la personne, à la main.")

if re.search(r"\bgit\b[^\n]*\bconfig\b[^\n]*(hooksPath|user\.(email|name))", cmd) \
        or re.search(r"-c\s*core\.hooksPath", cmd):
    decide("deny", "Gate zone client : reconfigurer les hooks ou l'identité d'un clone client est réservé à la personne.")

# ── ASK : toute écriture qui laisse une trace chez le client — GO par action ─
ASK_PATTERNS = [
    (r"\bgit\b[^\n]*\bpush\b", "git push vers un remote client"),
    (r"\bgit\b[^\n]*\bcommit\b", "git commit dans un clone client"),
    (r"\bgit\b[^\n]*\brebase\b", "réécriture d'historique (rebase) dans un clone client"),
    (r"\bgit\b[^\n]*\bremote\b[^\n]*\b(add|set-url|remove|rm)\b", "modification des remotes d'un clone client"),
    (r"(^|[\s;&|(])(gh|glab)\s", "commande gh/glab — écriture potentielle chez le client (PR, issue, commentaire)"),
]
for pattern, label in ASK_PATTERNS:
    if re.search(pattern, cmd):
        decide("ask", f"Gate zone client — GO par action requis : {label}. Un GO précédent ne couvre pas celui-ci.")

# Lecture / edits / git local (status, diff, log, branch…) : libre
sys.exit(0)
