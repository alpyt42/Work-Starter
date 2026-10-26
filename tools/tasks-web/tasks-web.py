#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "markdown-it-py==3.0.0",
# ]
# ///
"""Serve a private, local action manager (Today, list and board views, notes, search, tools, Sync) backed by brain action registers.

Run from Work with: uv run tools/tasks-web/tasks-web.py
Only listens on 127.0.0.1. The Markdown registers remain the source of truth.

A Work can hold several brains (`brain`, `brain-<name>`): the page switches between them without a
restart, and every /api route takes an optional `brain=<name>` (a discovered name, never a path).
`--brain` only chooses the default brain (otherwise the default brain of Work, see tools/machine/work_config.py).
WORK_DIR points to another Work root.
"""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import importlib.util
import json
import os
import posixpath
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import unicodedata
from array import array
from bisect import bisect_left, bisect_right
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit
from zoneinfo import ZoneInfo

from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml

# The checkout that holds tools/ (the scripts run from here), and the Work root whose brains are served:
# WORK_DIR when set (like the other tools), else the same checkout.
TOOLS_ROOT = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get("WORK_DIR", TOOLS_ROOT)).resolve()
# Every write to an action register goes through tools/brain/action.py, run as a command (the same tool
# the agents use); reads import it, so the parsing is shared too.
ACTION_SCRIPT = TOOLS_ROOT / "tools/brain/action.py"
_spec = importlib.util.spec_from_file_location("brain_action", ACTION_SCRIPT)
assert _spec and _spec.loader
action_tool = importlib.util.module_from_spec(_spec)
sys.modules["brain_action"] = action_tool
_spec.loader.exec_module(action_tool)
# The rule of what a brain is and which one is the default lives in tools/machine/work_config.py.
_config_spec = importlib.util.spec_from_file_location("work_config", TOOLS_ROOT / "tools/machine/work_config.py")
assert _config_spec and _config_spec.loader
work_config = importlib.util.module_from_spec(_config_spec)
_config_spec.loader.exec_module(work_config)
# The push checks own the rule that hides the credentials of a remote URL: the Sync view shows URLs the same way.
_push_spec = importlib.util.spec_from_file_location("preflight_push", TOOLS_ROOT / "tools/machine/preflight-push.py")
assert _push_spec and _push_spec.loader
preflight_push = importlib.util.module_from_spec(_push_spec)
_push_spec.loader.exec_module(preflight_push)
# What the checks of the brain call a Markdown link, and how they resolve one, is shared with "delete a note" (the pages that link to it): so that a deletion
# never leaves the link the next save would be refused for. The module reads a brain when it loads; only its link rules are used here.
_links_spec = importlib.util.spec_from_file_location("check_links", TOOLS_ROOT / "tools/brain/check-links.py")
assert _links_spec and _links_spec.loader
check_links = importlib.util.module_from_spec(_links_spec)
_links_brain = os.environ.get("BRAIN_DIR")
os.environ["BRAIN_DIR"] = str(TOOLS_ROOT)
try:
    _links_spec.loader.exec_module(check_links)
finally:
    if _links_brain is None:
        del os.environ["BRAIN_DIR"]
    else:
        os.environ["BRAIN_DIR"] = _links_brain
ACTION_STATUS = {"bad_request": HTTPStatus.BAD_REQUEST, "not_found": HTTPStatus.NOT_FOUND, "conflict": HTTPStatus.CONFLICT}
ASSETS = Path(__file__).resolve().parent / "static"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DUE_NOTE_RE = re.compile(r"-\s*due\s*:\s*(.*)", re.IGNORECASE | re.DOTALL)
STATUS = {" ", "/", "w", "x", "-"}
PRIORITY = {"", "⏫", "🔼", "🔽"}
UNDO_LIMIT = 20
NOTE_TITLE_LIMIT = 150
NOTE_CONTENT_LIMIT = 100 * 1024
NOTE_REQUEST_LIMIT = 128 * 1024
NOTE_SUMMARY_READ = 16384
NOTE_EXCERPT_LIMIT = 160
NOTE_BACKLINK_LIMIT = 50  # pages listed when a note is still linked (the count is exact)
NOTE_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-|$)")
INBOX_DIR = "inbox"
INBOX_FILE = "inbox.md"  # the capture scratchpad of inbox/, triaged line by line: not a note
INBOX_LABEL = "Inbox"
INBOX_REGISTER = "inbox"  # wire value of `register` for a note left in the root inbox, to be sorted later
# What the interface writes into a brain file: the source of an action created from the interface and the
# header of a new note.
SOURCE_ENTERED = "entered in the local interface"
NOTE_HEADER = {"note": "Note from", "project": "project: ", "register": "register", "triage": "to triage"}
WRITE_LOCK = threading.Lock()
TOOL_LOCK = threading.Lock()
# In a tool's arguments: the folder name of the chosen brain, for a script that picks a brain by name rather than from BRAIN_DIR.
BRAIN_ARG = "<brain>"
TOOLS = {
    "links": ("Memory", "Check links", "Checks the Markdown links of the brain.", "brain/check-links.py", ()),
    "brains": ("Memory", "List brains", "Shows the memories present and the transcripts they track.", "brain/brain-state.py", ("brains",)),
    "map": ("Memory", "Brain map", "One line per project: page, register prefix, actions by state, overdue, proposed decisions, last timeline entry.", "brain/brain-state.py", ("map", "--brain", BRAIN_ARG)),
    "timeline-roll": ("Memory", "Timeline months to move", "Dry run: lists the timeline entries of past months that would move to journal/.", "brain/timeline.py", ("roll",)),
    "transcripts": ("Memory", "New transcripts", "Finds the transcripts that no brain tracks.", "brain/brain-state.py", ("transcripts", "--new")),
    "board": ("Actions", "Text view of actions", "Shows the registers by project in a terminal format.", "brain/action.py", ("board",)),
    "sweep_preview": ("Actions", "Actions to sort (preview)", "Lists the actions placed under a section that does not match their state (checked, cancelled or reopened), without changing anything.", "brain/action.py", ("sweep",)),
    "sweep_write": ("Actions", "Sort actions by status", "Moves each action into Open, Done or Cancelled according to its state (changes the registers; recoverable with Git, but outside the interface's undo stack).", "brain/action.py", ("sweep", "--write")),
    "archive_preview": ("Actions", "Actions to archive (preview)", "Lists the actions closed for more than 30 days that would move to state/actions-archive-YYYY.md, without changing anything.", "brain/action.py", ("archive",)),
    "archive_write": ("Actions", "Archive actions", "Moves the actions closed for more than 30 days to state/actions-archive-YYYY.md (changes the registers; recoverable with Git, but outside the interface's undo stack).", "brain/action.py", ("archive", "--write")),
    "repositories": ("Repositories", "Check repositories", "Compares the local clones with the private catalogue and checks their Git identity.", "repos/client-repos.py", ("check",)),
}


# Tools that write local brain files ask for a confirmation in the page before running.
TOOL_CONFIRM = {
    "sweep_write": "Sort the actions by status now? Run the preview first to see what will move.",
    "archive_write": "Archive the actions closed for more than 30 days now? Run the preview first to see what will move.",
}


def tool_catalog() -> list[dict]:
    return [
        {"id": tool_id, "group": group, "label": label, "description": description,
         "command": "uv run tools/" + " ".join((script, *args)), "confirm": TOOL_CONFIRM.get(tool_id)}
        for tool_id, (group, label, description, script, args) in TOOLS.items()
    ]


def run_tool(tool_id: str, brain: Path) -> dict:
    if tool_id not in TOOLS:
        raise TaskError(HTTPStatus.NOT_FOUND, "Unknown tool.")
    uv = shutil.which("uv") or next((str(path) for path in
        (Path("/opt/homebrew/bin/uv"), Path("/usr/local/bin/uv"), Path.home() / ".local/bin/uv")
        if path.is_file()), None)
    if uv is None:
        raise TaskError(HTTPStatus.SERVICE_UNAVAILABLE, "uv was not found on this machine.")
    script, args = TOOLS[tool_id][3:]
    environment = os.environ.copy()
    environment["BRAIN_DIR"] = str(brain)
    try:
        result = subprocess.run(
            [uv, "run", str(TOOLS_ROOT / "tools" / script), *(brain.name if arg == BRAIN_ARG else arg for arg in args)], cwd=WORK, env=environment,
            capture_output=True, text=True, errors="replace", timeout=90, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"id": tool_id, "ok": False, "output": "The 90-second limit was exceeded. Run the command again if needed.", "truncated": False}
    except OSError:
        raise TaskError(HTTPStatus.INTERNAL_SERVER_ERROR, "Could not start this tool.") from None
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if not output:
        output = "Command finished with no output."
    truncated = len(output) > 60000
    return {"id": tool_id, "ok": result.returncode == 0, "output": output[:60000], "truncated": truncated}


class TaskError(Exception):
    def __init__(self, status: HTTPStatus, message: str, **extra: object) -> None:
        self.status = status
        self.message = message
        self.extra = extra  # more fields for the answer of a write that was refused (the pages that link to a note)
        super().__init__(message)


def parse_date(value: object, field: str) -> str:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise TaskError(HTTPStatus.BAD_REQUEST, f"{field} must use the format YYYY-MM-DD.")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise TaskError(HTTPStatus.BAD_REQUEST, f"{field} is not a valid date.") from error
    return value


def optional_date(value: object, field: str) -> str:
    return "" if value == "" else parse_date(value, field)


def clean_text(value: object, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise TaskError(HTTPStatus.BAD_REQUEST, f"{field} is required.")
    value = value.strip()
    if not value or len(value) > limit or any(char in value for char in "\r\n\x00"):
        raise TaskError(HTTPStatus.BAD_REQUEST, f"{field} must be 1 to {limit} characters on one line.")
    if (field == "Owner" and " — " in value) or any(marker in value for marker in ("➕", "📅", "⏳", "⏫", "🔼", "🔽", "✅", "❌")):
        raise TaskError(HTTPStatus.BAD_REQUEST, f"{field} contains a separator reserved for registers.")
    return value


def clean_group(value: object) -> str:
    """A group slug (same rule as action.py), or '' for none."""
    slug = value.strip() if isinstance(value, str) else None
    if slug is None or (slug and not action_tool.valid_group(slug)):
        raise TaskError(HTTPStatus.BAD_REQUEST, f"Invalid group: lowercase letters, digits and hyphens, {action_tool.GROUP_LIMIT} characters at most.")
    return slug


def clean_note(value: object) -> str:
    if not isinstance(value, str):
        raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid note.")
    note = value.strip()
    if not note or len(note) > 1000 or note.splitlines() != [note] or "\x00" in note:
        raise TaskError(HTTPStatus.BAD_REQUEST, "The note must be 1 to 1000 characters on one line.")
    return note


def slugify(title: str) -> str:
    text = title.lower().replace("œ", "oe").replace("æ", "ae").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60].strip("-")
    return text or "note"


def clean_note_title(value: object) -> str:
    if not isinstance(value, str):
        raise TaskError(HTTPStatus.BAD_REQUEST, "Title required.")
    value = value.strip()
    if not value or len(value) > NOTE_TITLE_LIMIT or any(unicodedata.category(char) in {"Cc", "Cs"} for char in value):
        raise TaskError(HTTPStatus.BAD_REQUEST, f"The title must be 1 to {NOTE_TITLE_LIMIT} characters on one line.")
    return value


def clean_note_content(value: object, required: bool) -> str:
    """Normalize line endings and enforce size and character limits; the result ends with one newline (or is empty)."""
    if not isinstance(value, str):
        raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid content.")
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in text or any(unicodedata.category(char) == "Cs" for char in text):
        raise TaskError(HTTPStatus.BAD_REQUEST, "The content contains disallowed characters.")
    if required and not text.strip():
        raise TaskError(HTTPStatus.BAD_REQUEST, "The content cannot be empty.")
    text = text.rstrip() + "\n" if text.strip() else ""
    if len(text.encode("utf-8")) > NOTE_CONTENT_LIMIT:
        raise TaskError(HTTPStatus.BAD_REQUEST, f"The content exceeds {NOTE_CONTENT_LIMIT // 1024} KB.")
    return text


def note_label(title: str, verb: str) -> str:
    short = title if len(title) <= 40 else title[:40].rstrip() + "…"
    return f'note "{short}" {verb}'


def note_summary(text: str, fallback: str) -> tuple[str, str]:
    """Title (first ``# `` heading, else ``fallback``) and a one-line excerpt of the body that follows it."""
    lines = text.splitlines()
    title = fallback
    start = 0
    for index, line in enumerate(lines):
        if line.startswith("# ") and line[2:].strip():
            title, start = line[2:].strip(), index + 1
            break
    body = lines[start:]
    while body and (not body[0].strip() or body[0].lstrip().startswith(">")):
        body.pop(0)
    excerpt = " ".join(" ".join(body).split())
    if len(excerpt) > NOTE_EXCERPT_LIMIT:
        excerpt = excerpt[:NOTE_EXCERPT_LIMIT].rstrip() + "…"
    return title, excerpt


parse_action = action_tool.parse_action


def discover_brains(work: Path) -> list[Path]:
    """Brains at the Work root, the default brain first then by name.

    The rule is the one of tools/machine/work_config.py (a folder named `brain` or `brain-<name>` that holds an
    AGENTS.md and a .data/ folder, a test compares the tools). A `defaultBrain` setting that cannot be applied
    leaves them by name; tools/machine/doctor.py reports the setting.
    """
    try:
        try:
            return work_config.discover_brains(work)
        except work_config.ConfigError:
            return work_config.find_brains(work)
    except OSError:
        return []


def default_brain_dir() -> Path:
    """The default brain of Work (the `--brain` default); `Work/brain` when there is none. ConfigError if the setting is invalid."""
    try:
        return work_config.default_brain(WORK) or WORK / "brain"
    except OSError:
        return WORK / "brain"


def brain_label(name: str) -> str:
    """Short name shown in the page: `brain-initech` -> `Initech`, `brain-acme-corp` -> `Acme-corp`, `brain` -> `Brain`.

    The folder name stays the technical value (`brain=`, local storage, API); only the label is displayed.
    A name outside the `brain` / `brain-<name>` convention (a default brain given with --brain) just gets an initial capital.
    """
    short = name.removeprefix("brain-") or name
    return short[:1].upper() + short[1:]


def brain_boundary(brain: Path) -> dict[str, str]:
    """`scope` and `description` of <brain>/.data/brain.json; empty strings when the file is missing or unreadable."""
    values = {"scope": "", "description": ""}
    try:
        declared = json.loads((brain / ".data/brain.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return values
    if isinstance(declared, dict):
        for key in values:
            if isinstance(declared.get(key), str):
                values[key] = " ".join(declared[key].split())
    return values


# --- Git: save and send the changes of a brain -------------------------------------------------------------
# The Sync view works on the brains found in Work, never on Work itself and never on a path or a repository
# chosen by the page. Reading never touches the network. Saving is one confirmed `git add -A`, `git commit` and
# `git push` of one brain, with every Git hook running, no terminal to ask anything on and a time limit.

GIT_READ_TIMEOUT = 10
GIT_ADD_TIMEOUT = 60
GIT_COMMIT_TIMEOUT = 180
GIT_PUSH_TIMEOUT = 120
GIT_CHANGE_LIMIT = 200  # changed notes listed for one brain (the count stays exact)
GIT_COMPARE_LIMIT = 300_000  # bytes read on each side of a comparison
GIT_COMPARE_LINES = 3000  # lines shown by "See changes"
GIT_CONTEXT_LINES = 2
GIT_TITLE_READ = 16384
GIT_TITLE_DELETED_LIMIT = 50  # deleted notes whose committed title is read (one Git call each)
GIT_RENAME_SCAN_LIMIT = 300
GIT_DETAILS_LIMIT = 20_000
GIT_BODY_LIMIT = 50
GIT_TEXT_PEEK = 8192
GIT_SENSITIVE = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*", "*.kdbx", "credentials*", "*secret*", "*.token")
GIT_STRIPPED_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE")
# Variables that could make SSH or Git ask a question somewhere else than on a terminal (GIT_SSH_COMMAND and GIT_SSH are never set
# here, and never removed: the pre-push check refuses them).
GIT_NO_PROMPT_ENV = ("SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", "GIT_ASKPASS", "DISPLAY")
GIT_LOCK = threading.Lock()
GIT_VERSION_RE = re.compile(r"^[0-9a-f]{32}$")
GIT_REMOTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
GIT_BRANCH_REF_RE = re.compile(r"^refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]*$")
GIT_UNAVAILABLE = {
    "not_set_up": "Saving is unavailable here (this brain is not set up for saving): ask your agent to set it up.",
    "no_online_copy": "Saving is unavailable here (this brain has no online copy yet): ask your agent to connect it.",
    "detached": "Saving is unavailable here (this brain is not on its working branch): ask your agent to fix it.",
    "in_progress": "Saving is unavailable here (a merge or a rebase is in progress): ask your agent to finish it.",
    "unreadable": "Saving is unavailable here (Git could not read this brain): ask your agent to check it.",
}
GIT_MESSAGES = {
    "clean": "Everything is saved and sent.",
    "unsent": "Saved on this computer, not sent yet.",
    "behind": "This brain was changed on another computer. Ask your agent to bring those changes here before saving.",
}
GIT_CHANGED_NOTES = "{count} {notes} changed since the last save."
GIT_STALE = "These notes changed since you last looked. Check the list and try again."


def is_sensitive(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in GIT_SENSITIVE)


def git_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in GIT_STRIPPED_ENV}


def git_program() -> str:
    return shutil.which("git") or "/usr/bin/git"


def run_git(repo: Path, *args: str) -> bytes:
    """Read-only Git call: fixed argv, no shell, no network, no prompt, no optional lock."""
    environment = git_environment()
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C", "GIT_PAGER": "cat"})
    try:
        result = subprocess.run(
            [git_program(), "--no-pager", "-c", "core.quotepath=false", "-c", "color.ui=false", *args],
            cwd=repo, capture_output=True, timeout=GIT_READ_TIMEOUT, env=environment, check=False, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise TaskError(HTTPStatus.BAD_GATEWAY, "Git did not answer within 10 seconds.") from None
    except OSError:
        raise TaskError(HTTPStatus.BAD_GATEWAY, "Git was not found on this machine.") from None
    if result.returncode != 0:
        raise TaskError(HTTPStatus.BAD_GATEWAY, "Git returned an error for this repository.")
    return result.stdout


def run_git_write(repo: Path, args: list[str], timeout: int) -> tuple[int, str]:
    """A Git call that may change the brain or reach the online copy.

    stdin is closed, nothing can prompt (`GIT_TERMINAL_PROMPT=0`, no askpass) and the command runs in its own session,
    so it has no controlling terminal and SSH can never wait for a passphrase. The hooks run as they do from a terminal.
    Returns (exit status, output of both streams); 124 after the time limit (the whole process group is killed), 127
    when Git cannot start.
    """
    environment = git_environment()
    for name in GIT_NO_PROMPT_ENV:
        environment.pop(name, None)
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_EDITOR": "true", "GIT_PAGER": "cat",
                        "LC_MESSAGES": "C", "LANGUAGE": "C"})
    try:
        process = subprocess.Popen(
            [git_program(), "--no-pager", "-c", "core.quotepath=false", "-c", "color.ui=false", *args], cwd=repo,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment, start_new_session=True,
        )
    except OSError:
        return 127, ""
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            output = b""
        return 124, output.decode("utf-8", "replace")
    return process.returncode, (output or b"").decode("utf-8", "replace")


def change_word(item: dict) -> str:
    """The change in words: New, Edited, Deleted or Renamed."""
    if item["untracked"]:
        return "New"
    if item["index"] == "D" or item["worktree"] == "D":
        return "Deleted"
    if item["index"] == "R":
        return "Renamed"
    if item["index"] in ("A", "C"):
        return "New"
    return "Edited"


def parse_git_status(raw: bytes) -> tuple[dict, list[dict]]:
    tokens = raw.decode("utf-8", "replace").split("\0")
    head: dict[str, str] = {}
    files: list[dict] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        kind = token[0]
        orig = None
        blob = ""
        if token.startswith("# "):
            key, _, value = token[2:].partition(" ")
            head[key] = value
            continue
        if kind == "1" and len(token.split(" ", 8)) == 9:
            parts = token.split(" ", 8)
            code, path, blob = parts[1], parts[8], parts[6]
        elif kind == "2" and len(token.split(" ", 9)) == 10:
            parts = token.split(" ", 9)
            code, path, blob = parts[1], parts[9], parts[6]
            orig = tokens[index] if index < len(tokens) else None
            index += 1
        elif kind == "u" and len(token.split(" ", 10)) == 11:
            parts = token.split(" ", 10)
            code, path = "UU", parts[10]
        elif kind == "?":
            code, path = "?", token[2:]
        else:
            continue
        if code == "?":
            side_index, side_tree = ".", "?"
        elif code == "UU":
            side_index, side_tree = "U", "U"
        else:
            side_index = "M" if code[0] == "T" else code[0]
            side_tree = "." if code[1] == "." else "D" if code[1] == "D" else "M"
        item = {
            "path": path, "orig_path": orig, "index": side_index, "worktree": side_tree, "untracked": code == "?",
            "unmerged": code == "UU", "head_oid": blob, "sensitive": is_sensitive(path),
        }
        item["change"] = change_word(item)
        files.append(item)
    files.sort(key=lambda entry: entry["path"])
    return head, files


def read_worktree(brain: Path, relative: str, limit: int) -> bytes | None:
    """Up to limit + 1 bytes of a regular file of the brain (a symbolic link is never followed); None when it cannot be read."""
    full = brain / relative
    try:
        if full.is_symlink() or not full.is_file() or not full.resolve().is_relative_to(brain.resolve()):
            return None
        with full.open("rb") as handle:
            return handle.read(limit + 1)
    except OSError:
        return None


def git_blob(brain: Path, relative: str, limit: int) -> tuple[bytes | None, bool]:
    """(content of a file as last saved, whether it is larger than `limit`); content is None when it is missing or too large."""
    try:
        size = int(run_git(brain, "cat-file", "-s", f"HEAD:{relative}").strip())
        if size > limit:
            return None, True
        return run_git(brain, "cat-file", "blob", f"HEAD:{relative}"), False
    except (TaskError, ValueError):
        return None, False


def pair_renames(brain: Path, files: list[dict]) -> list[dict]:
    """A note moved without a change appears as a deletion and a new file: show it as one renamed note."""
    gone: dict[str, list[dict]] = {}
    for item in files:
        if item["worktree"] == "D" and item["index"] == "." and item["head_oid"]:
            gone.setdefault(item["head_oid"], []).append(item)
    fresh = [item for item in files if item["untracked"]]
    if not gone or not fresh:
        return files
    algorithm = "sha256" if len(next(iter(gone))) == 64 else "sha1"
    paired: set[int] = set()
    for item in fresh[:GIT_RENAME_SCAN_LIMIT]:
        data = read_worktree(brain, item["path"], GIT_COMPARE_LIMIT)
        if data is None or len(data) > GIT_COMPARE_LIMIT:
            continue
        candidates = gone.get(hashlib.new(algorithm, b"blob %d\0" % len(data) + data).hexdigest())
        if candidates:
            old = candidates.pop(0)
            item.update(orig_path=old["path"], untracked=False, change="Renamed", sensitive=item["sensitive"] or old["sensitive"])
            paired.add(id(old))
    return [item for item in files if id(item) not in paired]


def git_title(text: str, fallback: str) -> str:
    """First level-1 Markdown heading outside code, else `fallback`."""
    fenced = False
    for line in split_front_matter(text)[1].splitlines():
        if FENCE_RE.match(line):
            fenced = not fenced
            continue
        match = None if fenced else HEADING_RE.match(line)
        if match and len(match.group(1)) == 1 and match.group(2).strip():
            return " ".join(match.group(2).split())[:120]
    return fallback


def git_project(brain: Path, relative: str) -> str:
    """The project a changed file belongs to (the label of its register, `client / mission` or the project folder), else ''."""
    parts = relative.split("/")
    if parts[0] == INBOX_DIR and len(parts) > 1:
        return INBOX_LABEL
    if parts[0] != "projects":
        return ""
    for depth in range(len(parts) - 1, 1, -1):
        register = brain.joinpath(*parts[:depth], "state/actions.md")
        if register.is_file() and not register.is_symlink():
            return action_tool.project_label(register, brain)
    # No register (a client page, or a project deleted with its register): the same rule, read from the path.
    inner = parts[1:-1]
    if len(inner) >= 4 and inner[0] == "clients" and inner[2] == "missions":
        return f"{inner[1]} / {inner[3]}"
    return inner[1] if len(inner) >= 2 else ""


def describe_changes(brain: Path, files: list[dict]) -> list[dict]:
    """The changed notes in human terms: title, project and the change in a word (no hash, no line counts)."""
    items = []
    deleted_reads = 0
    for item in files[:GIT_CHANGE_LIMIT]:
        path = item["path"]
        base = posixpath.basename(path)
        title = posixpath.splitext(base)[0] or base
        if not item["sensitive"] and path.lower().endswith(".md"):
            data = None
            if item["change"] == "Deleted":
                if deleted_reads < GIT_TITLE_DELETED_LIMIT:
                    deleted_reads += 1
                    data = git_blob(brain, path, GIT_TITLE_READ * 4)[0]
            else:
                data = read_worktree(brain, path, GIT_TITLE_READ)
            if data:
                title = git_title(data[:GIT_TITLE_READ].decode("utf-8", "replace"), title)
        items.append({"path": path, "title": title, "project": git_project(brain, path), "change": item["change"],
                      "from": item["orig_path"] or "", "hidden": item["sensitive"]})
    return items


def git_directory(brain: Path) -> Path | None:
    try:
        return Path(run_git(brain, "rev-parse", "--absolute-git-dir").decode("utf-8", "replace").strip())
    except TaskError:
        return None


def git_operation_in_progress(brain: Path) -> bool:
    folder = git_directory(brain)
    return folder is not None and any((folder / name).exists() for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"))


def git_push_target(brain: Path, branch: str) -> tuple[str, str] | None:
    """(remote name, branch ref on the remote) the current branch is set up to push to, from its upstream configuration."""
    try:
        text = run_git(brain, "config", "--get-regexp", rf"^branch\.{re.escape(branch)}\.(remote|merge)$").decode("utf-8", "replace")
    except TaskError:
        return None
    values = {}
    for line in text.splitlines():
        key, _, value = line.partition(" ")
        values[key.rsplit(".", 1)[-1]] = value.strip()
    remote, ref = values.get("remote", ""), values.get("merge", "")
    return (remote, ref) if GIT_REMOTE_RE.fullmatch(remote) and GIT_BRANCH_REF_RE.fullmatch(ref) else None


def git_online_copy(brain: Path, remote: str | None) -> str:
    """The push URL of the remote the brain sends to (its upstream's, else `origin`), credentials hidden; '' when it has none.

    Only a local read of the configuration: no network. The URL is shown to the person, so it goes through the same rule as the
    push checks (HTTPS user-info becomes `https://***@host`; SSH user-info is removed).
    """
    try:
        text = run_git(brain, "remote", "get-url", "--push", remote or "origin").decode("utf-8", "replace")
    except TaskError:
        return ""
    url = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return "".join(char for char in preflight_push.redact(url) if char.isprintable())[:300]


WEB_URL_SCHEMES = ("http", "https", "ssh", "ssh+git", "git+ssh")
WEB_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$")  # a dotted name or an IPv4 address
# One path segment: plain URL characters or a %XX escape that is not a control character, a slash or a backslash.
WEB_SEGMENT_RE = re.compile(r"^(?:[A-Za-z0-9._~+-]|%(?!0[0-9a-fA-F]|1[0-9a-fA-F]|7[fF]|2[fF]|5[cC])[0-9a-fA-F]{2})+$")
WEB_AUTHORITY_URL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://([^/?#]*)(/[^?#]*)?$")
WEB_SCP_URL_RE = re.compile(r"^(?:[^@/:\s]+@)?([^/:\s@]+):([^/\s].*)$")


def git_web_url(url: str) -> str | None:
    """The web page of a repository, from its (already redacted) Git URL; None when there is no safe way to say it.

    `git@host:owner/repo.git`, `ssh://[user@]host[:port]/owner/repo.git` (user and port dropped, the port of SSH is not the one of the
    web) and `http(s)://[credentials@]host[:port]/owner/repo[.git]` give `https://host/owner/repo` (`http` stays `http`). Local paths, `file://`,
    `git://` and every other form give None. The result is built from checked parts only (a dotted host name, plain path segments),
    so it is always an `http(s)` address, never another scheme and never a query or a fragment.
    """
    text = url.strip() if isinstance(url, str) else ""
    if not text or len(text) > 300 or "\\" in text or any(ord(char) <= 32 or ord(char) == 127 for char in text):
        return None
    authority = WEB_AUTHORITY_URL_RE.match(text)
    if authority:
        scheme, location, path = authority.group(1).lower(), authority.group(2), authority.group(3) or ""
        if scheme not in WEB_URL_SCHEMES:
            return None
        host, _, port = location.rsplit("@", 1)[-1].partition(":")
        if port and (not port.isdigit() or not 0 < int(port) <= 65535):
            return None
        web_scheme = "http" if scheme == "http" else "https"
        web_port = port if scheme in ("http", "https") else ""
        path = path[1:]
    else:
        scp = WEB_SCP_URL_RE.match(text)
        if scp is None:
            return None
        (host, path), web_scheme, web_port = scp.groups(), "https", ""
    path = path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    segments = path.split("/")
    if not WEB_HOST_RE.fullmatch(host) or len(segments) < 2 or any(segment in ("", ".", "..") or not WEB_SEGMENT_RE.fullmatch(segment) for segment in segments):
        return None
    return f"{web_scheme}://{host.lower()}{':' + web_port if web_port else ''}/{'/'.join(segments)}"


def git_last_saved(brain: Path) -> str | None:
    try:
        stamp = run_git(brain, "log", "-1", "--format=%ct").decode().strip()
    except TaskError:
        return None
    return datetime.fromtimestamp(int(stamp), ZoneInfo("Europe/Paris")).isoformat(timespec="seconds") if stamp.isdigit() else None


def git_inspect(name: str, brain: Path) -> tuple[dict, tuple[str, str] | None, list[dict]]:
    """The card of a brain: where things stand in one sentence, the changed notes, and what the button does.

    Also returns the (remote, branch ref) a push goes to and the raw changed files; nothing here uses the network (the
    online copy is known as of the last fetch only).
    """
    card: dict = {"name": name, "label": brain_label(name), "state": "unavailable", "message": "", "pending": False, "action": None,
                  "count": 0, "unsent": 0, "changes": [], "more": 0, "last_saved": None, "version": "", "url": "", "web_url": None}

    def unavailable(reason: str) -> tuple[dict, None, list[dict]]:
        return {**card, "message": GIT_UNAVAILABLE[reason]}, None, []

    if not (brain / ".git").exists():
        return unavailable("not_set_up")
    try:
        raw = run_git(brain, "status", "--porcelain=v2", "-z", "--branch", "--untracked-files=all")
    except TaskError:
        return unavailable("unreadable")
    head, files = parse_git_status(raw)
    files = pair_renames(brain, files)
    changes = describe_changes(brain, files)
    digest = hashlib.sha256(raw)
    for item in files:
        try:
            info = (brain / item["path"]).lstat()
            digest.update(f"{item['path']}\0{info.st_size}\0{info.st_mtime_ns}\0".encode())
        except OSError:
            pass
    card.update(count=len(files), changes=changes, more=max(0, len(files) - len(changes)), last_saved=git_last_saved(brain), version=digest.hexdigest()[:32])
    branch = head.get("branch.head", "")
    target = git_push_target(brain, branch) if branch and branch != "(detached)" else None
    card["url"] = git_online_copy(brain, target[0] if target else None)
    card["web_url"] = git_web_url(card["url"])
    counts = re.fullmatch(r"\+(\d+) -(\d+)", head.get("branch.ab", ""))
    if any(item["unmerged"] for item in files) or git_operation_in_progress(brain):
        card["message"] = GIT_UNAVAILABLE["in_progress"]
        return card, None, files
    if branch == "(detached)" or not branch:
        card["message"] = GIT_UNAVAILABLE["detached"]
        return card, None, files
    if target is None or not head.get("branch.upstream") or counts is None:
        card["message"] = GIT_UNAVAILABLE["no_online_copy"]
        return card, None, files
    ahead, behind = int(counts.group(1)), int(counts.group(2))
    card["unsent"] = ahead
    if behind:
        card["state"] = "behind"
        card["message"] = GIT_MESSAGES["behind"]
    elif files:
        card.update(state="changes", action="save", message=GIT_CHANGED_NOTES.format(count=len(files), notes="note" if len(files) == 1 else "notes"))
    elif ahead:
        card.update(state="unsent", action="send", message=GIT_MESSAGES["unsent"])
    else:
        card.update(state="clean", message=GIT_MESSAGES["clean"])
    card["pending"] = card["state"] in ("changes", "unsent") or (card["state"] == "behind" and bool(files or ahead))
    return card, target, files


def git_card(name: str, brain: Path) -> dict:
    return git_inspect(name, brain)[0]


def git_overview(brains: dict[str, Path], current: str) -> dict:
    """One card per brain of the Work, the current brain first (never Work itself)."""
    names = [current, *(name for name in brains if name != current)]
    return {"brains": [git_card(name, brains[name].resolve()) for name in names if name in brains]}


def to_lines(data: bytes) -> list[str]:
    text = data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line[:2000] for line in lines]


def git_changes(name: str, brain: Path, relative: str) -> dict:
    """"See changes" for one changed note: what it was at the last save against what it is now, with the unchanged part collapsed."""
    _, _, files = git_inspect(name, brain)
    item = next((entry for entry in files if entry["path"] == relative), None)
    if item is None:
        raise TaskError(HTTPStatus.NOT_FOUND, "This note has no change to save.")
    described = describe_changes(brain, [item])[0]
    result = {"path": relative, "title": described["title"], "project": described["project"], "change": item["change"],
              "hidden": False, "binary": False, "too_large": False, "unchanged": False, "truncated": False, "blocks": []}
    if item["sensitive"]:
        return {**result, "hidden": True}
    old, new = b"", b""
    if item["change"] != "New":
        old, too_large = git_blob(brain, item["orig_path"] or relative, GIT_COMPARE_LIMIT)
        if too_large:
            return {**result, "too_large": True}
        old = old or b""
    if item["change"] != "Deleted":
        new = read_worktree(brain, relative, GIT_COMPARE_LIMIT)
        if new is None:
            raise TaskError(HTTPStatus.NOT_FOUND, "This note cannot be shown.")
        if len(new) > GIT_COMPARE_LIMIT:
            return {**result, "too_large": True}
    if b"\0" in old[:GIT_TEXT_PEEK] or b"\0" in new[:GIT_TEXT_PEEK]:
        return {**result, "binary": True}
    before, after = to_lines(old), to_lines(new)
    if len(before) > 5000 or len(after) > 5000:
        return {**result, "too_large": True}
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    blocks: list[list] = []
    covered = 0  # lines of `before` accounted for so far (an unchanged line counts the same on both sides)
    for group in matcher.get_grouped_opcodes(GIT_CONTEXT_LINES):
        if group[0][1] > covered:
            blocks.append(["gap", group[0][1] - covered])
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                blocks.extend(["ctx", line] for line in before[i1:i2])
            else:
                if tag in ("delete", "replace"):
                    blocks.extend(["del", line] for line in before[i1:i2])
                if tag in ("insert", "replace"):
                    blocks.extend(["add", line] for line in after[j1:j2])
        covered = group[-1][2]
    if blocks and covered < len(before):
        blocks.append(["gap", len(before) - covered])
    shown = 0
    for position, block in enumerate(blocks):
        if block[0] != "gap":
            shown += 1
            if shown > GIT_COMPARE_LINES:
                return {**result, "blocks": blocks[:position], "truncated": True}
    return {**result, "blocks": blocks, "unchanged": not blocks}


# What a refusal looks like in plain words. The first group reads the output of the brain's pre-commit hook (and of commit-msg),
# the second one the output of a push (Git itself and the pre-push identity checks).
GIT_NOISE = re.compile(r"^(hint:|Commit refused:?( fix the problems|$)|Push refused: fix the ERROR|Summary:|files +:|md links|wikilinks|dead \(|cross-brain|unverified|Action check:|Total (sweep|archive)|Known-name scan|Client-name scan|\(dry run)")


def git_note_name(path: str, titles: dict[str, str]) -> str:
    stem = posixpath.splitext(posixpath.basename(path))[0] or path
    return f"“{titles.get(path) or stem}”"


def git_first_line(output: str) -> str:
    lines = [line.strip() for line in output.replace("\r", "").splitlines()]
    lines = [line for line in lines if line and "--no-verify" not in line and not GIT_NOISE.match(line) and re.search(r"\w", line)]
    preferred = next((line for line in lines if re.match(r"(error:|fatal:|ERROR\b|⛔)", line)), lines[0] if lines else "")
    return re.sub(r"^(error:|fatal:|ERROR:?|⛔|-)\s*", "", preferred).strip().rstrip(".")[:200]


def git_commit_reason(output: str, code: int, titles: dict[str, str]) -> str:
    """Why the commit was refused, in a few plain words: the hooks of the brain, recognised one by one, else their first useful line."""
    text = output.replace("\r", "")
    if code == 124:
        return "the checks did not finish in time"
    if code == 127:
        return "Git could not be started"
    if "index.lock" in text:
        return "another program is using this brain right now: try again in a moment"
    secret = re.search(r"Possible secrets in the index.*?\n\s*- (.+?)(?::\d+)?: (.+)", text, re.DOTALL)
    if secret:
        label = secret.group(2).strip()
        if label.startswith("credentials file"):
            return f"{git_note_name(secret.group(1), titles)} looks like a file of credentials"
        return f"{git_note_name(secret.group(1), titles)} seems to contain a password, a key or a token"
    link = re.search(r"DEAD (?:MD LINK|WIKILINK) [(\[]+(.+?)[)\]]+ — \d+×\s*\n\s+(\S.*)", text)
    if link:
        return f"a link in {git_note_name(link.group(2).strip(), titles)} points to a note that does not exist ({link.group(1)})"
    cross = re.search(r"CROSS-BRAIN LINK [(\[]+(.+?)[)\]]+ — \d+×.*\n\s+(\S.*)", text)
    if cross:
        return f"a link in {git_note_name(cross.group(2).strip(), titles)} points into another brain"
    other = re.search(r"^Blocked .*? in (.+?): (.+)$", text, re.MULTILINE)
    if other:
        return f"{git_note_name(other.group(1), titles)} mentions a name that belongs to another brain ({other.group(2).strip()})"
    misfiled = re.search(r": sweep ([A-Z]{2,5}-\d{3}) .*? → (.+)$", text, re.MULTILINE)
    if misfiled:
        return f"action {misfiled.group(1)} is not under the section of its status ({misfiled.group(2).strip().capitalize()})"
    problem = re.search(r"^ERROR (.+?): (.+)$", text, re.MULTILINE)
    if problem:
        path = problem.group(1).split(":", 1)[0]
        detail = problem.group(2)
        if "malformed action line" in detail:
            return f"an action line in {git_note_name(path, titles)} is not written the way registers expect"
        if "already present" in detail:
            return f"an action number is used twice in {git_note_name(path, titles)}"
        return f"an action register has a problem ({problem.group(1)}: {detail})"
    if re.search(r"nothing (added )?to commit|no changes added", text):
        return "there was nothing new to save"
    return git_first_line(text) or "a check of the brain refused it"


def git_push_reason(output: str, code: int) -> str:
    """Why the push failed, in a few plain words."""
    text = output.replace("\r", "")
    if code == 124:
        return "the online copy did not answer in time"
    if code == 127:
        return "Git could not be started"
    if re.search(r"GIT_SSH(_COMMAND)? is set", text):
        return "this computer overrides the connection settings of Git (GIT_SSH_COMMAND): ask your agent to check it"
    if re.search(r"ERROR: user\.(email|name)|does not match the \"email\" pattern|no effective user\.email", text):
        return "the Git identity of this computer does not match this brain: ask your agent to check it"
    if re.search(r"does not match the \"remote\" pattern|no push URL to compare", text):
        return "the online copy is not the one this brain is declared to use: ask your agent to check it"
    ssh = re.search(r"SSH authentication to \S+ failed: (.+)", text)
    if ssh or re.search(r"Permission denied \(publickey", text):
        reason = ssh.group(1) if ssh else "permission denied"
        if "host key" in reason:
            return "the identity of the online copy could not be verified: ask your agent to check it"
        if "permission denied" in reason:
            return "the online copy refused the connection (the SSH key is locked or not accepted)"
        return "the online copy could not be reached (check the network)"
    if re.search(r"remote is ahead|history diverged|the remote moved|non-fast-forward|\[rejected\]|fetch first|remote tip is unknown", text):
        return "the online copy has newer changes: ask your agent to bring them here before sending"
    if re.search(r"Could not resolve host|Network is unreachable|Connection (timed out|refused|reset)|unable to access|Could not read from remote", text):
        return "the online copy could not be reached (check the network)"
    return git_first_line(text) or "the online copy did not accept the changes"


def git_index_file(brain: Path) -> Path | None:
    try:
        location = run_git(brain, "rev-parse", "--git-path", "index").decode("utf-8", "replace").strip()
    except TaskError:
        return None
    return brain / location if location else None


def git_clear_stale_lock(index: Path | None, since: float) -> None:
    """A Git command that was killed may leave its index.lock behind: remove the one made since `since` (never an older one)."""
    if index is None:
        return
    lock = index.with_name(index.name + ".lock")
    try:
        if lock.is_file() and lock.stat().st_mtime >= since - 1:
            lock.unlink()
    except OSError:
        pass


def git_restore_index(index: Path | None, backup: bytes | None) -> bool:
    """Put the index back as it was before `git add -A`, the way Git itself replaces it (through index.lock). False when it could not."""
    if index is None:
        return False
    lock = index.with_name(index.name + ".lock")
    try:
        handle = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except OSError:
        return False
    try:
        with os.fdopen(handle, "wb") as stream:
            if backup is not None:
                stream.write(backup)
                stream.flush()
                os.fsync(stream.fileno())
        if backup is None:
            lock.unlink()
            index.unlink(missing_ok=True)
        else:
            os.replace(lock, index)
        return True
    except OSError:
        lock.unlink(missing_ok=True)
        return False


def git_head(brain: Path) -> str:
    try:
        return run_git(brain, "rev-parse", "--verify", "-q", "HEAD").decode().strip()
    except TaskError:
        return ""


def git_commit_message(card: dict) -> tuple[str, str]:
    """Conventional Commits subject accepted by the commit-msg hook (no scope, no AI attribution) and a short body listing the files."""
    count = card["count"]
    subject = f"docs: save {count} {'note' if count == 1 else 'notes'} from tasks-web"
    lines = []
    for item in card["changes"][:GIT_BODY_LIMIT]:
        where = f"{item['from']} -> {item['path']}" if item["from"] else item["path"]
        lines.append(f"- {item['change'].lower()}: {where}")
    if count > len(lines):
        lines.append(f"- and {count - len(lines)} more")
    return subject, "\n".join(lines)


def git_outcome(ok: bool, stage: str, message: str, details: str, brain: dict, saved: bool = False) -> dict:
    return {"ok": ok, "stage": stage, "saved": saved, "message": message, "details": details.strip()[:GIT_DETAILS_LIMIT], "brain": brain}


def git_save_and_send(name: str, brain: Path, version: str, push_only: bool) -> dict:
    """Save (`git add -A`, `git commit`) and send (`git push`) one brain; or only send what is already saved.

    The brain's hooks all run. Refuses when the brain is not in a safe state, when the notes changed since the page
    listed them (`version`) or when there is nothing to do. A refused commit puts the index back as it was.
    """
    card, target, _ = git_inspect(name, brain)
    if card["state"] in ("unavailable", "behind") or target is None:
        raise TaskError(HTTPStatus.CONFLICT, card["message"])
    if card["version"] != version:
        raise TaskError(HTTPStatus.CONFLICT, GIT_STALE)
    if push_only and not card["unsent"]:
        raise TaskError(HTTPStatus.CONFLICT, "Nothing is waiting to be sent.")
    if not push_only and card["state"] == "clean":
        raise TaskError(HTTPStatus.CONFLICT, "Everything is already saved and sent.")
    details = ""
    saved = False
    if not push_only and card["count"]:
        head = git_head(brain)
        index = git_index_file(brain)
        backup = index.read_bytes() if index is not None and index.is_file() else None
        titles = {item["path"]: item["title"] for item in card["changes"]}
        started = datetime.now().timestamp()
        code, output = run_git_write(brain, ["add", "-A"], GIT_ADD_TIMEOUT)
        details = output
        if code == 0:
            subject, body = git_commit_message(card)
            code, output = run_git_write(brain, ["commit", "-m", subject, "-m", body], GIT_COMMIT_TIMEOUT)
            details = f"{details}\n{output}"
        saved = git_head(brain) not in ("", head)  # the commit exists when HEAD moved, whatever a hook said afterwards
        if code == 124:
            git_clear_stale_lock(index, started)
        if not saved:
            restored = git_restore_index(index, backup)
            reason = git_commit_reason(output, code, titles)
            ending = "Nothing was changed." if restored else "Nothing was lost: the notes are still waiting to be saved."
            return git_outcome(False, "commit", f"Not saved: {reason}. {ending}", details, git_card(name, brain))
    remote, ref = target
    code, output = run_git_write(brain, ["push", "--", remote, f"HEAD:{ref}"], GIT_PUSH_TIMEOUT)
    details = f"{details}\n{output}"
    if code != 0:
        return git_outcome(False, "send", f"Saved on this computer, but not sent: {git_push_reason(output, code)}.", details, git_card(name, brain), saved=True)
    return git_outcome(True, "done", "Saved and sent.", details, git_card(name, brain), saved=True)


# --- Documents: catalogue, search and rendering ------------------------------------------------------------

DOC_SIZE_LIMIT = 1_000_000
SEARCH_QUERY_LIMIT = 300
SEARCH_MAX_TERMS = 10
SEARCH_TERM_MAX = 60
SEARCH_RESULT_LIMIT = 50
SEARCH_SNIPPETS = 2
SEARCH_WINDOW = 160
SEARCH_LEAD = 40
SEARCH_BODY_CAP = 20
SEARCH_OCCURRENCE_CAP = 100
SEARCH_CANDIDATE_CAP = 300
HEADING_ID_PREFIX = "h-"
DOC_OFF_TITLE = "File not shown here"
WHITESPACE_RE = re.compile(r"\s+")
FENCE_RE = re.compile(r"^ {0,3}(?:`{3,}|~{3,})")
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
QUERY_TOKEN_RE = re.compile(r'"([^"]*)"|([^\s"]+)')
_FOLD_CACHE: dict[str, str] = {}


def _fold_char(char: str) -> str:
    folded = _FOLD_CACHE.get(char)
    if folded is None:
        plain = "".join(item for item in unicodedata.normalize("NFKD", char) if not unicodedata.combining(item))
        folded = "".join(item for item in plain.casefold() if not unicodedata.combining(item))
        if len(_FOLD_CACHE) < 50_000:
            _FOLD_CACHE[char] = folded
    return folded


def fold_mapped(text: str) -> tuple[str, array]:
    """Accent-, case- and whitespace-insensitive form of ``text`` plus, for each folded character, the index of its source character."""
    out: list[str] = []
    origin = array("I")
    spaced = False
    for index, char in enumerate(text):
        folded = _fold_char(char)
        if not folded:
            continue
        if folded.isspace():
            if not spaced:
                out.append(" ")
                origin.append(index)
            spaced = True
            continue
        spaced = False
        out.append(folded)
        origin.extend([index] * len(folded))
    return "".join(out), origin


def fold(text: str) -> str:
    if text.isascii():
        return WHITESPACE_RE.sub(" ", text.casefold())
    return fold_mapped(text)[0]


def parse_query(raw: str) -> list[str]:
    """Normalised search terms: whitespace-separated words or "quoted phrases", all required."""
    if len(raw) > SEARCH_QUERY_LIMIT:
        raise TaskError(HTTPStatus.BAD_REQUEST, f"The search exceeds {SEARCH_QUERY_LIMIT} characters.")
    found = [fold(quoted or bare).strip() for quoted, bare in QUERY_TOKEN_RE.findall(raw)]
    found = [term for term in found if term]
    if len(found) > SEARCH_MAX_TERMS:
        raise TaskError(HTTPStatus.BAD_REQUEST, f"The search accepts {SEARCH_MAX_TERMS} terms at most.")
    if any(len(term) > SEARCH_TERM_MAX for term in found):
        raise TaskError(HTTPStatus.BAD_REQUEST, f"A term exceeds {SEARCH_TERM_MAX} characters.")
    terms: list[str] = []
    for term in found:
        if len(term) >= 2 and term not in terms:
            terms.append(term)
    return terms


def heading_slug(text: str) -> str:
    slug = re.sub(r"[^\w]+", "-", fold(text)).strip("-_")[:80].strip("-_")
    return slug or "section"


class DocEntry:
    """One Markdown file of the brain with its pre-folded fields; ``origin`` (folded index -> source index) is built on demand."""
    __slots__ = ("id", "path", "key", "mtime", "text", "title", "norm_title", "norm_path", "norm_text", "norm_heads", "_origin")

    def __init__(self, doc_id: str, path: str, key: tuple[int, int], text: str) -> None:
        self.id = doc_id
        self.path = path
        self.key = key
        self.mtime = key[0] / 1e9
        self.text = text
        title = ""
        heads: list[str] = []
        fenced = False
        for line in text.splitlines():
            if FENCE_RE.match(line):
                fenced = not fenced
                continue
            match = None if fenced else HEADING_RE.match(line)
            if match and match.group(2):
                heads.append(match.group(2))
                if not title and len(match.group(1)) == 1:
                    title = match.group(2).strip()
        self.title = title or posixpath.splitext(posixpath.basename(doc_id))[0]
        self.norm_title = fold(self.title)
        self.norm_path = fold(doc_id)
        self.norm_text = fold(text)
        self.norm_heads = fold("\n".join(heads))
        self._origin: array | None = None

    @property
    def origin(self) -> array:
        if self._origin is None:
            self._origin = fold_mapped(self.text)[1]
        return self._origin


def _window_pick(starts: list[int], ends: list[int], owners: list[int], length: int, floor: int) -> tuple[int, int] | None:
    """Best ~SEARCH_WINDOW-wide window (folded coordinates) at or after ``floor``: most distinct terms, then most hits, then earliest."""
    best: tuple[tuple[int, int, int], tuple[int, int]] | None = None
    begin = bisect_left(starts, floor)
    for position in range(begin, min(len(starts), begin + SEARCH_CANDIDATE_CAP)):
        first = max(floor, starts[position] - SEARCH_LEAD)
        last = min(length, first + SEARCH_WINDOW)
        inside = [index for index in range(bisect_left(starts, first), bisect_right(starts, last)) if ends[index] <= last]
        key = (len({owners[index] for index in inside}), len(inside), -first)
        if best is None or key > best[0]:
            best = (key, (first, last))
    return best[1] if best else None


def doc_snippets(entry: DocEntry, terms: list[str]) -> list[dict]:
    """Up to two ~160-character excerpts around matches; ``ranges`` are code-point offsets into each snippet text."""
    norm = entry.norm_text
    hits: list[tuple[int, int, int]] = []
    for number, term in enumerate(terms):
        at, count = norm.find(term), 0
        while at != -1 and count < SEARCH_OCCURRENCE_CAP:
            hits.append((at, at + len(term), number))
            count += 1
            at = norm.find(term, at + len(term))
    if not hits:
        return []
    hits.sort()
    starts, ends, owners = [hit[0] for hit in hits], [hit[1] for hit in hits], [hit[2] for hit in hits]
    origin, text = entry.origin, entry.text
    snippets: list[dict] = []
    floor = 0
    while len(snippets) < SEARCH_SNIPPETS:
        window = _window_pick(starts, ends, owners, len(norm), floor)
        if window is None:
            break
        first, last = window
        inside = [index for index in range(bisect_left(starts, first), bisect_right(starts, last)) if ends[index] <= last]
        if not inside:
            break
        if first > 0 and norm[first - 1] != " ":
            cut = norm.find(" ", first, starts[inside[0]])
            first = cut + 1 if cut != -1 else first
        if last < len(norm) and norm[last] != " ":
            cut = norm.rfind(" ", ends[inside[-1]], last)
            last = cut if cut != -1 else last
        floor = last
        raw_first, raw_last = origin[first], origin[last - 1] + 1
        out: list[str] = []
        offsets: list[int] = []
        spaced = True
        for position in range(raw_first, raw_last):
            char = text[position]
            offsets.append(len(out))
            if char.isspace():
                if not spaced:
                    out.append(" ")
                spaced = True
            else:
                out.append(char)
                spaced = False
        offsets.append(len(out))
        if out and out[-1] == " ":
            out.pop()
        body = "".join(out)
        lead = "…" if raw_first > 0 and text[:raw_first].strip() else ""
        tail = "…" if raw_last < len(text) and text[raw_last:].strip() else ""
        ranges: list[list[int]] = []
        for index in inside:
            begin = min(offsets[origin[starts[index]] - raw_first], len(body))
            finish = min(offsets[origin[ends[index] - 1] + 1 - raw_first], len(body))
            if finish <= begin:
                continue
            if ranges and begin <= ranges[-1][1]:
                ranges[-1][1] = max(ranges[-1][1], finish)
            else:
                ranges.append([begin, finish])
        shift = len(lead)
        snippets.append({"text": lead + body + tail, "ranges": [[begin + shift, finish + shift] for begin, finish in ranges]})
        if floor >= len(norm):
            break
    return snippets


def _doc_link(href: str, env: dict) -> tuple[str, str, str]:
    """Classify a Markdown link: ("external"|"doc"|"off", target, anchor)."""
    try:
        parts = urlsplit(href)
    except ValueError:
        return "off", "", ""
    scheme = parts.scheme.lower()
    if scheme in {"http", "https", "mailto"}:
        return "external", href, ""
    if scheme or parts.netloc:
        return "off", "", ""
    path, fragment = unquote(parts.path), unquote(parts.fragment)
    anchor = HEADING_ID_PREFIX + heading_slug(fragment) if fragment else ""
    if not path:
        return ("doc", env["id"], anchor) if fragment else ("off", "", "")
    if path.startswith("/") or not path.lower().endswith(".md"):
        return "off", "", ""
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(env["id"]), path))
    if resolved in env["ids"]:
        return "doc", resolved, anchor
    return "off", "", ""


def _render_link_open(self, tokens, idx, options, env) -> str:
    token = tokens[idx]
    kind, target, anchor = _doc_link(token.attrGet("href") or "", env)
    env.setdefault("link_stack", []).append(kind != "off")
    if kind == "off":
        return f'<span class="doc-link-off" title="{DOC_OFF_TITLE}">'
    title = token.attrGet("title")
    extra = f' title="{escapeHtml(str(title))}"' if title and kind == "external" else ""
    if kind == "external":
        return f'<a href="{escapeHtml(target)}" target="_blank" rel="noopener noreferrer"{extra}>'
    data_anchor = f' data-anchor="{escapeHtml(anchor)}"' if anchor else ""
    return f'<a href="#doc" class="doc-link" data-doc="{escapeHtml(target)}"{data_anchor}>'


def _render_link_close(self, tokens, idx, options, env) -> str:
    stack = env.get("link_stack") or []
    return "</a>" if (stack.pop() if stack else True) else "</span>"


def _render_image(self, tokens, idx, options, env) -> str:
    token = tokens[idx]
    alt = self.renderInlineAsText(token.children, options, env) if token.children else ""
    return f'<span class="doc-image-off" title="Image not shown here">{escapeHtml(alt.strip() or "image")}</span>'


def _render_table_open(self, tokens, idx, options, env) -> str:
    return '<div class="table-wrap">' + self.renderToken(tokens, idx, options, env)


def _render_table_close(self, tokens, idx, options, env) -> str:
    return self.renderToken(tokens, idx, options, env) + "</div>\n"


UNDERLINE_CLOSE = re.compile(r"</u>", re.IGNORECASE)


def _underline(state, silent: bool) -> bool:
    """Inline rule for `<u>text</u>`, the underline Obsidian notes use and Markdown lacks. It matches the bare tags only: no
    attribute, no other tag. The tags are emitted by the parser and so always balanced; an opening tag with no closing one in the
    same block (and any stray closing tag) stays what raw HTML is everywhere else, escaped text."""
    if state.src[state.pos : state.pos + 3].lower() != "<u>":
        return False
    close = UNDERLINE_CLOSE.search(state.src, state.pos + 3, state.posMax)
    if not close:
        return False
    if not silent:
        state.push("underline_open", "u", 1).markup = "<u>"
        end = state.posMax
        state.pos += 3
        state.posMax = close.start()
        state.md.inline.tokenize(state)
        state.posMax = end
        state.push("underline_close", "u", -1).markup = "</u>"
    state.pos = close.end()
    return True


def _heading_ids(state) -> None:
    used: dict[str, int] = {}
    tokens = state.tokens
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and index + 1 < len(tokens) and tokens[index + 1].type == "inline":
            text = "".join(child.content for child in tokens[index + 1].children or [] if child.type in {"text", "code_inline"})
            slug = heading_slug(text)
            used[slug] = used.get(slug, 0) + 1
            token.attrSet("id", HEADING_ID_PREFIX + slug + ("" if used[slug] == 1 else f"-{used[slug]}"))


def build_markdown() -> MarkdownIt:
    """Raw HTML in documents is escaped (never rendered), but for a bare `<u>…</u>` (underline); links and images are rewritten by the rules above."""
    markdown = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False}).enable(["table", "strikethrough"])
    for name, rule in (("link_open", _render_link_open), ("link_close", _render_link_close), ("image", _render_image),
                       ("table_open", _render_table_open), ("table_close", _render_table_close)):
        markdown.add_render_rule(name, rule)
    markdown.inline.ruler.before("html_inline", "underline", _underline)
    markdown.core.ruler.push("heading_ids", _heading_ids)
    return markdown


MARKDOWN = build_markdown()


FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def split_front_matter(text: str) -> tuple[list[tuple[str, str]], str]:
    """Separate a leading YAML block (Obsidian properties) so it is not rendered as a setext heading."""
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return [], text
    properties: list[tuple[str, str]] = []
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and not line[:1].isspace() and not line.lstrip().startswith("-"):
            properties.append((key.strip(), value.strip()))
        elif line.strip() and properties:
            properties[-1] = (properties[-1][0], f"{properties[-1][1]} {line.strip()}".strip())
    return properties, text[match.end():]


def front_matter_html(properties: list[tuple[str, str]]) -> str:
    if not properties:
        return ""
    rows = "".join(f"<dt>{escapeHtml(key)}</dt><dd>{escapeHtml(value.strip(chr(34)).strip(chr(39)))}</dd>" for key, value in properties)
    return f'<dl class="doc-props">{rows}</dl>\n'


class Store:
    def __init__(self, brain: Path) -> None:
        self.brain = brain.resolve()
        self.projects = self.brain / "projects"
        if not self.projects.is_dir():
            raise ValueError(f"Registers not found under {self.projects}")
        self.undo_stack: list[dict] = []
        self._doc_cache: dict[str, DocEntry] = {}
        self._doc_lock = threading.Lock()

    def registers(self) -> list[Path]:
        root = self.projects.resolve()
        files = []
        for path in sorted(root.glob("**/state/actions.md")):
            if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
                continue
            files.append(path)
        return files

    def owner(self) -> str:
        config = self.brain / ".data/doctor.json"
        if config.is_file():
            try:
                return str(json.loads(config.read_text(encoding="utf-8")).get("owner", "")).strip()
            except (OSError, ValueError, TypeError):
                pass
        return os.environ.get("BRAIN_OWNER", "").strip()

    @staticmethod
    def _due_notes(path: Path, entries: list[dict]) -> None:
        """Give each action `due_note`: the wording of its `due:` sub-bullet when it has no 📅 date ("week of 05/10"), else "".
        The Timeline lists these as vague deadlines. A "—" (no deadline), or a register that changed meanwhile, gives an empty note."""
        for entry in entries:
            entry["due_note"] = ""
        pending = [entry for entry in entries if not entry["due"]]
        if not pending:
            return
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return
        for entry in pending:
            index = entry["line"] - 1
            if index >= len(lines) or f"**{entry['id']}**" not in lines[index]:
                continue
            for start, end in action_tool.items(lines, index, action_tool.last_detail(lines, index)):
                match = DUE_NOTE_RE.match(action_tool.item_text(lines, start, end))
                if match:
                    note = " ".join(match.group(1).split())
                    entry["due_note"] = "" if note in {"", "—", "–", "-"} else note[:200]
                    break

    def _scan_registers(self) -> list[dict]:
        infos = []
        for path in self.registers():
            entries = action_tool.load(path, self.brain)
            self._due_notes(path, entries)
            label = entries[0]["project"] if entries else action_tool.project_label(path, self.brain)
            prefixes = {entry["id"].split("-", 1)[0] for entry in entries}
            infos.append({"file": path, "path": path.relative_to(self.brain).as_posix(), "label": label,
                          "prefix": next(iter(prefixes)) if len(prefixes) == 1 else "", "entries": entries,
                          "groups": sorted({entry["group"] for entry in entries if entry["group"]})})
        return infos

    def snapshot(self) -> dict:
        infos = self._scan_registers()
        actions = [action for info in infos for action in info["entries"]]
        registers = [{key: info[key] for key in ("path", "label", "prefix", "groups")} for info in infos]
        return {"actions": actions, "registers": registers, "owner": self.owner(), "today": datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()}

    def _register(self, relative: object) -> Path:
        if not isinstance(relative, str):
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid project.")
        for path in self.registers():
            if path.relative_to(self.brain).as_posix() == relative:
                return path
        raise TaskError(HTTPStatus.BAD_REQUEST, "Unknown project.")

    def _find(self, action_id: str) -> tuple[Path, list[str], int, dict]:
        try:
            return action_tool.find(self.brain, action_id)
        except action_tool.ActionError as error:
            raise TaskError(ACTION_STATUS[error.kind], error.message) from None

    def details(self, action_id: str) -> dict:
        try:
            return action_tool.details(self.brain, action_id)
        except action_tool.ActionError as error:
            raise TaskError(ACTION_STATUS[error.kind], error.message) from None

    @staticmethod
    def _fields(data: dict) -> tuple[str, str, str, str, str, str, str | None]:
        # `group` is optional: absent means unchanged on update (a status change does not send it), none on create.
        if set(data) - {"group"} != {"title", "owner", "state", "priority", "due", "scheduled"}:
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid action fields.")
        title = clean_text(data["title"], "Title", 300)
        owner = clean_text(data["owner"], "Owner", 120)
        state = data["state"]
        priority = data["priority"]
        if not isinstance(state, str) or not isinstance(priority, str) or state not in STATUS or priority not in PRIORITY:
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid status or priority.")
        return (title, owner, state, priority, optional_date(data["due"], "Due date"), optional_date(data["scheduled"], "Scheduled date"),
                clean_group(data["group"]) if "group" in data else None)

    @staticmethod
    def _atomic(path: Path, data: bytes) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".actions-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o644)
            os.replace(temporary, path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def _run_action(self, path: Path, action_id: str | None, *argv: str) -> dict:
        """Run tools/brain/action.py and record the register's bytes before and after for one undo step."""
        before = path.read_bytes()
        try:
            result = subprocess.run([sys.executable, str(ACTION_SCRIPT), "--brain", str(self.brain), *argv],
                                    capture_output=True, text=True, timeout=30, check=False)
            payload = json.loads(result.stdout or "{}")
        except (OSError, subprocess.TimeoutExpired, ValueError):
            raise TaskError(HTTPStatus.INTERNAL_SERVER_ERROR, "Could not run the actions tool.") from None
        if result.returncode:
            raise TaskError(ACTION_STATUS.get(payload.get("kind"), HTTPStatus.INTERNAL_SERVER_ERROR), payload.get("error") or "The actions tool failed.")
        after = path.read_bytes()
        if after != before:
            self.undo_stack.append({"path": path, "before": before, "after": after, "label": payload["label"],
                                    "action_id": action_id or payload.get("id")})
            del self.undo_stack[:-UNDO_LIMIT]
        return payload

    def undo_state(self) -> dict:
        top = self.undo_stack[-1] if self.undo_stack else None
        return {"available": top is not None, "label": top["label"] if top else None, "depth": len(self.undo_stack)}

    def _restore_deleted_note(self, entry: dict) -> None:
        """Undo of a deletion: the bytes of the note come back at its path, with its mode, unless something is there now (then nothing is written)."""
        path = entry["path"]
        if path.exists() or path.is_symlink():
            self.undo_stack[:] = [item for item in self.undo_stack if item["path"] != path]
            raise TaskError(HTTPStatus.CONFLICT, "A file now exists where this note was: it cannot be restored.")
        created: list[Path] = []
        try:
            for directory in reversed([parent for parent in path.parents if not parent.exists() and parent.is_relative_to(self.brain)]):
                directory.mkdir()
                created.append(directory)
            if path.parent.is_symlink() or not path.parent.resolve().is_relative_to(self.brain):
                raise TaskError(HTTPStatus.CONFLICT, "The folder of this note can no longer be used: it cannot be restored.")
            self._atomic(path, entry["before"])
        except (OSError, TaskError):
            for directory in reversed(created):
                try:
                    directory.rmdir()
                except OSError:
                    break
            raise
        try:
            os.chmod(path, entry["mode"])
        except OSError:
            pass

    def undo(self, payload: dict) -> dict:
        if set(payload) != {"label"} or not isinstance(payload["label"], str):
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid undo data.")
        if not self.undo_stack:
            raise TaskError(HTTPStatus.CONFLICT, "Nothing to undo.")
        entry = self.undo_stack[-1]
        if payload["label"] != entry["label"]:
            raise TaskError(HTTPStatus.CONFLICT, "The last change is different. Refresh before undoing.")
        path = entry["path"]
        if entry.get("deleted"):
            self._restore_deleted_note(entry)
            self.undo_stack.pop()
            return {"undone": entry["label"], "action_id": entry["action_id"], "restored": True, "undo": self.undo_state()}
        try:
            current = path.read_bytes()
        except OSError:
            current = None
        if current != entry["after"]:
            self.undo_stack[:] = [item for item in self.undo_stack if item["path"] != path]
            raise TaskError(HTTPStatus.CONFLICT, f"The {'note' if entry.get('note') else 'register'} changed since this edit; it cannot be undone.")
        if entry["before"] is None:
            path.unlink()
            for directory in entry.get("created_dirs", []):
                try:
                    directory.rmdir()
                except OSError:
                    break
        else:
            self._atomic(path, entry["before"])
        self.undo_stack.pop()
        return {"undone": entry["label"], "action_id": entry["action_id"], "undo": self.undo_state()}

    @staticmethod
    def _field_args(fields: tuple[str, str, str, str, str, str, str | None]) -> list[str]:
        title, owner, state, priority, due, scheduled, group = fields
        return [f"--title={title}", f"--owner={owner}", f"--state={state}", f"--priority={priority}", f"--due={due}", f"--scheduled={scheduled}",
                *([] if group is None else [f"--group={group}"])]

    def create(self, payload: dict) -> dict:
        if set(payload) != {"register", "action"} or not isinstance(payload["action"], dict):
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid creation data.")
        path = self._register(payload["register"])
        fields = self._fields(payload["action"])
        if fields[2] not in {" ", "/", "w"}:
            raise TaskError(HTTPStatus.BAD_REQUEST, "A new action must be to do, in progress or waiting.")
        today = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
        result = self._run_action(path, None, "create", f"--project={payload['register']}", *self._field_args(fields),
                                  f"--source={SOURCE_ENTERED}, {today[8:10]}/{today[5:7]}")
        return {"id": result["id"]}

    def update(self, action_id: str, payload: dict) -> dict:
        if set(payload) != {"version", "action"} or not isinstance(payload["action"], dict):
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid update data.")
        fields = self._fields(payload["action"])
        if not isinstance(payload["version"], str):
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid update data.")
        path = self._find(action_id)[0]
        self._run_action(path, action_id, "update", action_id, *self._field_args(fields), f"--expect-version={payload['version']}")
        return {"id": action_id}

    def _locked(self, action_id: str, payload: dict, keys: set[str]) -> Path:
        if set(payload) != keys or not isinstance(payload["details_version"], str):
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid note data.")
        return self._find(action_id)[0]

    def add_note(self, action_id: str, payload: dict) -> dict:
        note = clean_note(payload.get("note"))
        path = self._locked(action_id, payload, {"details_version", "note"})
        self._run_action(path, action_id, "history", "add", action_id, f"--text={note}",
                         f"--expect-details-version={payload['details_version']}")
        return self.details(action_id)

    def delete_note(self, action_id: str, number: int, payload: dict) -> dict:
        if not isinstance(payload.get("text"), str):
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid note data.")
        path = self._locked(action_id, payload, {"details_version", "text"})
        self._run_action(path, action_id, "history", "remove", action_id, f"--index={number}", f"--expect-text={payload['text']}",
                         f"--expect-details-version={payload['details_version']}")
        return self.details(action_id)

    def delete_action(self, action_id: str, payload: dict) -> dict:
        if set(payload) != {"version", "details_version"} or not all(isinstance(payload[key], str) for key in payload):
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid deletion data.")
        path = self._find(action_id)[0]
        self._run_action(path, action_id, "delete", action_id, f"--expect-version={payload['version']}",
                         f"--expect-details-version={payload['details_version']}")
        return {"deleted": action_id}

    # --- Notes -------------------------------------------------------------------------------------------

    def _project_dirs(self) -> list[dict]:
        return [{"dir": info["file"].parent.parent, "register": info["path"], "label": info["label"]} for info in self._scan_registers()]

    def _note_safe(self, path: Path, *, directory: bool = False) -> bool:
        try:
            return not path.is_symlink() and (path.is_dir() if directory else path.is_file()) and path.resolve().is_relative_to(self.brain)
        except OSError:
            return False

    @staticmethod
    def _note_date(path: Path) -> str:
        match = NOTE_DATE_PREFIX_RE.match(path.name)
        if match:
            try:
                datetime.strptime(match.group(1), "%Y-%m-%d")
                return match.group(1)
            except ValueError:
                pass
        return datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo("Europe/Paris")).date().isoformat()

    def _note_files(self) -> list[tuple[Path, str, str]]:
        """Note files as (path, project label, register path); symlinks, archives, README files and the inbox scratchpad are skipped. Inbox notes use INBOX_REGISTER."""
        found = []
        folders = [(project["dir"] / "notes", project["label"], project["register"]) for project in self._project_dirs()]
        for folder, label, register in [*folders, (self.brain / INBOX_DIR, INBOX_LABEL, INBOX_REGISTER)]:
            if not self._note_safe(folder, directory=True):
                continue
            for path in sorted(folder.glob("*.md")):
                skipped = {"readme.md", INBOX_FILE} if register == INBOX_REGISTER else {"readme.md"}
                if path.name.lower() not in skipped and not path.name.startswith(".") and self._note_safe(path):
                    found.append((path, label, register))
        return found

    def notes(self) -> dict:
        items = []
        for path, label, register in self._note_files():
            try:
                with path.open("rb") as handle:
                    head = handle.read(NOTE_SUMMARY_READ).decode("utf-8", "replace")
                info = path.stat()
                title, excerpt = note_summary(head, path.stem)
                items.append({
                    "id": path.relative_to(self.brain).as_posix(), "title": title, "project": label, "register": register,
                    "date": self._note_date(path), "modified": datetime.fromtimestamp(info.st_mtime, ZoneInfo("Europe/Paris")).isoformat(timespec="seconds"),
                    "excerpt": excerpt, "size": info.st_size,
                })
            except OSError:
                continue
        items.sort(key=lambda item: item["title"].casefold())
        items.sort(key=lambda item: item["date"], reverse=True)
        return {"notes": items}

    def _note_entry(self, note_id: object) -> tuple[Path, str, str]:
        if isinstance(note_id, str):
            for path, label, register in self._note_files():
                if path.relative_to(self.brain).as_posix() == note_id:
                    return path, label, register
        raise TaskError(HTTPStatus.NOT_FOUND, "Note not found.")

    def _note_payload(self, path: Path, label: str, register: str, data: bytes) -> dict:
        text = data.decode("utf-8", "replace")
        return {"id": path.relative_to(self.brain).as_posix(), "title": note_summary(text, path.stem)[0], "project": label, "register": register,
                "content": text, "deletable": True, "version": hashlib.sha256(data).hexdigest()[:16]}

    def note_content(self, note_id: object) -> dict:
        path, label, register = self._note_entry(note_id)
        try:
            return self._note_payload(path, label, register, path.read_bytes())
        except OSError:
            raise TaskError(HTTPStatus.NOT_FOUND, "Note not found.") from None

    def _note_header(self, project_dir: Path | None, label: str, today: str) -> str:
        words = NOTE_HEADER
        date = f"{today[8:10]}/{today[5:7]}/{today[:4]}"
        if project_dir is None:
            return f"> {words['note']} {date} · {words['triage']}"
        name = project_dir.name
        page = project_dir / f"{name}.md"
        if self._note_safe(page):
            target, text = f"../{quote(name)}.md", label
        else:
            target, text = "../state/actions.md", f"{label} ({words['register']})"
        text = text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        return f"> {words['note']} {date} · {words['project']}[{text}]({target})"

    def _note_write(self, path: Path, before: bytes | None, after: bytes, label: str, created_dirs: list[Path] | None) -> None:
        self._atomic(path, after)
        self.undo_stack.append({"path": path, "before": before, "after": after, "label": label, "action_id": path.relative_to(self.brain).as_posix(),
                                "note": True, "created_dirs": created_dirs or []})
        del self.undo_stack[:-UNDO_LIMIT]

    def create_note(self, payload: dict) -> dict:
        if set(payload) != {"title", "register", "content"}:
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid note data.")
        title = clean_note_title(payload["title"])
        content = clean_note_content(payload["content"], required=False)
        if payload["register"] == INBOX_REGISTER:
            project_dir, label, register = None, INBOX_LABEL, INBOX_REGISTER
            folder = self.brain / INBOX_DIR
        else:
            known = {info["path"]: info for info in self._scan_registers()}
            info = known.get(payload["register"]) if isinstance(payload["register"], str) else None
            if info is None:
                raise TaskError(HTTPStatus.BAD_REQUEST, "Unknown project.")
            project_dir, label, register = info["file"].parent.parent, info["label"], info["path"]
            folder = project_dir / "notes"
        today = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
        slug = slugify(title)
        text = f"# {title}\n\n{self._note_header(project_dir, label, today)}\n" + (f"\n{content}" if content else "")
        data = text.encode("utf-8")
        if len(data) > NOTE_CONTENT_LIMIT + 4096:
            raise TaskError(HTTPStatus.BAD_REQUEST, f"The content exceeds {NOTE_CONTENT_LIMIT // 1024} KB.")
        if (folder.exists() or folder.is_symlink()) and not self._note_safe(folder, directory=True):
            raise TaskError(HTTPStatus.CONFLICT, "The notes folder cannot be used.")
        created: list[Path] = []
        number = 1
        while True:
            suffix = "" if number == 1 else f"-{number}"
            path = folder / f"{today}-{slug}{suffix}.md"
            if not (path.exists() or path.is_symlink()):
                break
            number += 1
        try:
            for directory in reversed([parent for parent in (path.parent, *path.parent.parents) if not parent.exists() and parent.is_relative_to(self.brain)]):
                directory.mkdir()
                created.append(directory)
            self._note_write(path, None, data, note_label(title, "created"), list(reversed(created)))
        except OSError:
            for directory in reversed(created):
                try:
                    directory.rmdir()
                except OSError:
                    break
            raise
        return {"id": path.relative_to(self.brain).as_posix(), "note": self._note_payload(path, label, register, data)}

    def update_note(self, payload: dict) -> dict:
        if set(payload) != {"id", "version", "content"} or not isinstance(payload["version"], str):
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid note data.")
        content = clean_note_content(payload["content"], required=True)
        path, _, _ = self._note_entry(payload["id"])
        try:
            before = path.read_bytes()
        except OSError:
            raise TaskError(HTTPStatus.NOT_FOUND, "Note not found.") from None
        if payload["version"] != hashlib.sha256(before).hexdigest()[:16]:
            raise TaskError(HTTPStatus.CONFLICT, "The note changed on disk. Reload it before retrying.")
        after = content.encode("utf-8")
        if after != before:
            self._note_write(path, before, after, note_label(note_summary(content, path.stem)[0], "edited"), None)
        return {"id": path.relative_to(self.brain).as_posix(), "version": hashlib.sha256(after).hexdigest()[:16]}


    # --- Deleting a note ---------------------------------------------------------------------------------

    def _deletable_note(self, note_id: object) -> Path:
        """The file of a working note (`<project>/notes/*.md` or an inbox note, as `_note_files` lists them), else a refusal.

        Nothing else is ever deletable here: not a source, a project page, a register, `docs/`, `me/`, `people/`, `tasks.md`, a file
        outside the brain, a symbolic link. The id is only compared with the notes found, never turned into a path.
        """
        try:
            return self._note_entry(note_id)[0]
        except TaskError:
            if isinstance(note_id, str) and any(entry.id == note_id for entry in self.docs()):
                raise TaskError(HTTPStatus.BAD_REQUEST, "Only a working note can be deleted from here.") from None
            raise

    def note_backlinks(self, note_id: str) -> list[dict]:
        """The pages of the brain that link to a note: what the next check of links would report as dead once it is gone.

        Uses the rules of tools/brain/check-links.py: Markdown links to a `.md` file, with or without an `#anchor`, resolved from the folder
        of the page, and `[[wikilinks]]` by file name when no other file has that name. Code is ignored, like there. The note itself is not a page
        that blocks its own deletion.
        """
        base = posixpath.basename(note_id)[:-3]
        entries = self.docs()
        wiki_breaks = not any(entry.id != note_id and posixpath.basename(entry.id)[:-3] == base for entry in entries)
        projects = self._doc_projects()
        pages = []
        for entry in entries:
            name = posixpath.basename(entry.id)
            if entry.id == note_id or check_links.is_skill_asset(entry.id) or (name.startswith("_") and "TEMPLATE" in entry.id):
                continue
            text = check_links.mask_code(entry.text)
            linked = False
            if wiki_breaks:
                for raw in check_links.WIKILINK.findall(text):
                    target = re.split(r"\\?\|", raw)[0].strip().rstrip("\\")
                    stem = posixpath.basename(target)
                    stem = stem[:-3] if stem.endswith(".md") else stem
                    if "<" not in target and stem == base:
                        linked = True
                        break
            if not linked:
                for target in check_links.MDLINK.findall(text):
                    if target.startswith(("http", "#", "mailto:")) or check_links.SCHEME.match(target):
                        continue
                    target = target.split("#")[0]
                    if not target.endswith(".md") or "<" in target or "YYYY" in target:
                        continue
                    folder = posixpath.dirname(entry.id)
                    if note_id in (posixpath.normpath(posixpath.join(folder, target)), posixpath.normpath(posixpath.join(folder, unquote(target)))):
                        linked = True
                        break
            if linked:
                owner = self._doc_project(entry.id, projects)
                pages.append({"id": entry.id, "title": entry.title, "project": owner[0] if owner else None})
        pages.sort(key=lambda page: page["id"])
        return pages

    def note_links(self, note_id: object) -> dict:
        """What the page needs to confirm a deletion: the note and the pages that still link to it."""
        path, label, register = self._note_entry(note_id)
        try:
            payload = self._note_payload(path, label, register, path.read_bytes())
        except OSError:
            raise TaskError(HTTPStatus.NOT_FOUND, "Note not found.") from None
        pages = self.note_backlinks(payload["id"])
        return {"id": payload["id"], "title": payload["title"], "version": payload["version"], "count": len(pages), "pages": pages[:NOTE_BACKLINK_LIMIT]}

    def delete_note_file(self, payload: dict) -> dict:
        """Delete a working note, if it is the version the person saw and no page links to it; one undo step brings its bytes back."""
        if set(payload) != {"id", "version"} or not isinstance(payload["id"], str) or not isinstance(payload["version"], str):
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid note data.")
        path = self._deletable_note(payload["id"])
        try:
            before = path.read_bytes()
            mode = path.stat().st_mode & 0o777
        except OSError:
            raise TaskError(HTTPStatus.NOT_FOUND, "Note not found.") from None
        if payload["version"] != hashlib.sha256(before).hexdigest()[:16]:
            raise TaskError(HTTPStatus.CONFLICT, "The note changed on disk. Reload it before deleting it.")
        note_id = path.relative_to(self.brain).as_posix()
        pages = self.note_backlinks(note_id)
        if pages:
            raise TaskError(HTTPStatus.CONFLICT, f"This note is linked from {len(pages)} {'page' if len(pages) == 1 else 'pages'}. Remove those links first, or ask your agent.",
                            backlinks=pages[:NOTE_BACKLINK_LIMIT], count=len(pages))
        title = note_summary(before.decode("utf-8", "replace"), path.stem)[0]
        path.unlink()
        self.undo_stack.append({"path": path, "before": before, "after": None, "label": note_label(title, "deleted"), "action_id": note_id,
                                "note": True, "deleted": True, "mode": mode})
        del self.undo_stack[:-UNDO_LIMIT]
        return {"deleted": note_id, "title": title}

    # --- Documents ---------------------------------------------------------------------------------------

    def _doc_files(self):
        """(absolute path, brain-relative id, stat) of every Markdown file: dot-entries, symlinks and oversized files are skipped."""
        stack = [str(self.brain)]
        prefix = len(str(self.brain)) + 1
        while stack:
            folder = stack.pop()
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for item in entries:
                if item.name.startswith("."):
                    continue
                try:
                    if item.is_symlink():
                        continue
                    if item.is_dir(follow_symlinks=False):
                        stack.append(item.path)
                    elif item.name.lower().endswith(".md") and item.is_file(follow_symlinks=False):
                        info = item.stat(follow_symlinks=False)
                        if info.st_size <= DOC_SIZE_LIMIT:
                            yield item.path, item.path[prefix:].replace(os.sep, "/"), info
                except OSError:
                    continue

    def docs(self) -> list[DocEntry]:
        """Parsed catalogue, cached per file by (path, mtime_ns, size); a changed file is re-read, a vanished one is forgotten."""
        with self._doc_lock:
            fresh: dict[str, DocEntry] = {}
            for path, doc_id, info in self._doc_files():
                key = (info.st_mtime_ns, info.st_size)
                entry = self._doc_cache.get(doc_id)
                if entry is None or entry.key != key or entry.path != path:
                    try:
                        if not os.path.realpath(path).startswith(str(self.brain) + os.sep):
                            continue
                        with open(path, "rb") as handle:
                            data = handle.read(DOC_SIZE_LIMIT + 1)
                    except OSError:
                        continue
                    if len(data) > DOC_SIZE_LIMIT:
                        continue
                    entry = DocEntry(doc_id, path, key, data.decode("utf-8", "replace").lstrip("﻿"))
                fresh[doc_id] = entry
            self._doc_cache = fresh
            return list(fresh.values())

    def _doc_projects(self) -> list[tuple[str, str, str]]:
        """(project dir relative to the brain, label, register path), longest directory first."""
        found = [(info["dir"].relative_to(self.brain).as_posix(), info["label"], info["register"]) for info in self._project_dirs()]
        found.append((INBOX_DIR, INBOX_LABEL, INBOX_REGISTER))
        return sorted(found, key=lambda item: -len(item[0]))

    @staticmethod
    def _doc_project(doc_id: str, projects: list[tuple[str, str, str]]) -> tuple[str, str] | None:
        for folder, label, register in projects:
            if doc_id.startswith(folder + "/"):
                return label, register
        return None

    def recent_docs(self, project: str, limit: int = 20) -> dict:
        """Most recently modified documents of the catalogue (all kinds), for the empty search view."""
        projects = self._doc_projects()
        docs = []
        for entry in sorted(self.docs(), key=lambda item: (-item.mtime, item.id)):
            owner = self._doc_project(entry.id, projects)
            if project == "none" and owner is not None:
                continue
            if project not in {"", "none"} and (owner is None or owner[1] != project):
                continue
            excerpt = note_summary(split_front_matter(entry.text)[1], entry.title)[1]
            docs.append({"id": entry.id, "title": entry.title, "project": owner[0] if owner else None, "register": owner[1] if owner else None,
                         "date": datetime.fromtimestamp(entry.mtime, ZoneInfo("Europe/Paris")).date().isoformat(), "excerpt": excerpt})
            if len(docs) >= limit:
                break
        return {"docs": docs}

    def search(self, query: str, project: str) -> dict:
        terms = parse_query(query)
        empty = {"query": query, "terms": terms, "results": [], "total": 0, "truncated": False}
        if not terms:
            return empty
        projects = self._doc_projects()
        now = datetime.now().timestamp()
        matches: list[tuple[float, str, DocEntry, tuple[str, str] | None]] = []
        for entry in self.docs():
            owner = self._doc_project(entry.id, projects)
            if project == "none" and owner is not None:
                continue
            if project not in {"", "none"} and (owner is None or owner[1] != project):
                continue
            score = 0.0
            for term in terms:
                in_title, in_path = term in entry.norm_title, term in entry.norm_path
                body = entry.norm_text.count(term)
                if not (in_title or in_path or body):
                    break
                score += (10 if in_title else 0) + (5 if in_path else 0)
                score += 3 * min(entry.norm_heads.count(term), 5) + min(body, SEARCH_BODY_CAP)
            else:
                age_days = max(0.0, (now - entry.mtime) / 86400)
                matches.append((round(score + 0.5 / (1 + age_days / 30), 2), entry.id, entry, owner))
        matches.sort(key=lambda item: (-item[0], item[1]))
        results = [{
            "id": entry.id, "title": entry.title, "project": owner[0] if owner else None, "register": owner[1] if owner else None,
            "snippets": doc_snippets(entry, terms), "score": score,
        } for score, _, entry, owner in matches[:SEARCH_RESULT_LIMIT]]
        return {**empty, "results": results, "total": len(matches), "truncated": len(matches) > SEARCH_RESULT_LIMIT}

    def render_doc(self, doc_id: object) -> dict:
        catalogue = {entry.id: entry for entry in self.docs()}
        entry = catalogue.get(doc_id) if isinstance(doc_id, str) else None
        if entry is None:
            raise TaskError(HTTPStatus.NOT_FOUND, "Document not found.")
        try:
            with open(entry.path, "rb") as handle:
                data = handle.read(DOC_SIZE_LIMIT + 1)
        except OSError:
            raise TaskError(HTTPStatus.NOT_FOUND, "Document not found.") from None
        if len(data) > DOC_SIZE_LIMIT:
            raise TaskError(HTTPStatus.NOT_FOUND, "Document not found.")
        text = data.decode("utf-8", "replace").lstrip("﻿")
        owner = self._doc_project(entry.id, self._doc_projects())
        try:
            self._note_entry(entry.id)
            is_note = True
        except TaskError:
            is_note = False
        properties, text = split_front_matter(text)
        html = front_matter_html(properties) + MARKDOWN.render(text, {"id": entry.id, "ids": set(catalogue)})
        return {"id": entry.id, "title": entry.title,
                "project": owner[0] if owner else None, "register": owner[1] if owner else None, "html": html,
                "note": is_note, "deletable": is_note, "version": hashlib.sha256(data).hexdigest()[:16] if is_note else None}


class Handler(BaseHTTPRequestHandler):
    server: TaskServer

    def log_message(self, format: str, *args: object) -> None:
        pass

    def _headers(self, status: HTTPStatus, mime: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()

    def _send(self, status: HTTPStatus, data: bytes, mime: str) -> None:
        self._headers(status, mime, len(data))
        self.wfile.write(data)

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _host_ok(self) -> bool:
        return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def _store(self) -> Store:
        """The brain selected by the optional `brain=<name>` query parameter (default brain when absent)."""
        values = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get("brain")
        if values is None:
            return self.server.store
        if len(values) != 1:
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid brain parameter.")
        return self.server.store_for(values[0])

    def do_GET(self) -> None:
        if not self._host_ok():
            self._json(HTTPStatus.FORBIDDEN, {"error": "Host refused."})
            return
        path = urlsplit(self.path).path
        if path == "/api/brains":
            self._json(HTTPStatus.OK, self.server.brain_list())
            return
        if path in {"/api/git", "/api/git/changes"}:
            self._git_request(path)
            return
        store = self.server.store
        if path.startswith("/api/"):
            try:
                store = self._store()
            except TaskError as error:
                self._json(error.status, {"error": error.message})
                return
        if path == "/api/actions":
            self._json(HTTPStatus.OK, store.snapshot())
            return
        match = re.fullmatch(r"/api/actions/([A-Z]{2,5}-\d{3})/details", path)
        if match:
            try:
                with WRITE_LOCK:
                    result = store.details(match.group(1))
                self._json(HTTPStatus.OK, result)
            except TaskError as error:
                self._json(error.status, {"error": error.message})
            return
        if path == "/api/tools":
            self._json(HTTPStatus.OK, {"tools": tool_catalog()})
            return
        if path in {"/api/notes", "/api/notes/content", "/api/notes/backlinks"}:
            self._notes_request(path, store)
            return
        if path in {"/api/search", "/api/docs/render", "/api/docs/recent"}:
            self._docs_request(path, store)
            return
        if path == "/api/undo":
            with WRITE_LOCK:
                self._json(HTTPStatus.OK, store.undo_state())
            return
        assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.css": ("app.css", "text/css; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/md-edit.js": ("md-edit.js", "text/javascript; charset=utf-8"), "/timeline-view.js": ("timeline-view.js", "text/javascript; charset=utf-8")}
        if path not in assets:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Page not found."})
            return
        filename, mime = assets[path]
        data = (ASSETS / filename).read_bytes()
        if path == "/":
            data = data.replace(b"__CSRF_TOKEN__", self.server.token.encode("ascii"))
        self._send(HTTPStatus.OK, data, mime)

    def _notes_request(self, path: str, store: Store) -> None:
        try:
            with WRITE_LOCK:
                if path == "/api/notes":
                    result = store.notes()
                else:
                    values = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get("id", [])
                    if len(values) != 1:
                        raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid id parameter.")
                    result = store.note_links(values[0]) if path == "/api/notes/backlinks" else store.note_content(values[0])
            self._json(HTTPStatus.OK, result)
        except TaskError as error:
            self._json(error.status, {"error": error.message})
        except OSError:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Could not read the notes."})

    def _docs_request(self, path: str, store: Store) -> None:
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)

        def one(name: str, default: str | None = None) -> str:
            values = query.get(name, [] if default is None else [default])
            if len(values) != 1:
                raise TaskError(HTTPStatus.BAD_REQUEST, f"Invalid {name} parameter.")
            return values[0]
        try:
            if path == "/api/search":
                result = store.search(one("q", ""), one("project", ""))
            elif path == "/api/docs/recent":
                result = store.recent_docs(one("project", ""))
            else:
                result = store.render_doc(one("id"))
            self._json(HTTPStatus.OK, result)
        except TaskError as error:
            self._json(error.status, {"error": error.message})
        except OSError:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Could not read the documents."})

    def _brain_name(self, required: bool = False) -> str | None:
        """The `brain=<name>` query parameter as written (None when absent, unless `required`)."""
        values = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get("brain")
        if values is None:
            if required:
                raise TaskError(HTTPStatus.BAD_REQUEST, "Unknown brain.")
            return None
        if len(values) != 1:
            raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid brain parameter.")
        return values[0]

    def _git_request(self, path: str) -> None:
        """`GET /api/git` (one card per brain, the chosen one first) and `GET /api/git/changes` (what changed in one note)."""
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        try:
            name, brain = self.server.git_brain(self._brain_name())
            if path == "/api/git":
                result = git_overview(self.server.git_brains(), name)
            else:
                values = query.get("path", [])
                if len(values) != 1:
                    raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid path parameter.")
                result = git_changes(name, brain, values[0])
            self._json(HTTPStatus.OK, result)
        except TaskError as error:
            self._json(error.status, {"error": error.message})
        except OSError:
            self._json(HTTPStatus.BAD_GATEWAY, {"error": "Could not read Git."})

    def _write_allowed(self) -> bool:
        """The rules of every write route: this host and origin, the page's token, a JSON body (a refusal is already answered)."""
        if not self._host_ok() or self.headers.get("Origin") not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}:
            self._json(HTTPStatus.FORBIDDEN, {"error": "Origin refused."})
        elif self.headers.get("X-Tasks-Token") != self.server.token:
            self._json(HTTPStatus.FORBIDDEN, {"error": "Invalid local token."})
        elif self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "JSON required."})
        else:
            return True
        return False

    def _git_write_request(self, path: str) -> None:
        """`POST /api/git/save` (save the notes of one brain and send them) and `POST /api/git/send` (send what is already saved).

        The brain is named in the address and required; the body carries the `version` of the card the person confirmed.
        """
        if not self._write_allowed():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 256:
                raise TaskError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request too large.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or set(payload) != {"version"} or not isinstance(payload["version"], str) or not GIT_VERSION_RE.fullmatch(payload["version"]):
                raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid request.")
            name, brain = self.server.git_brain(self._brain_name(required=True))
            if not GIT_LOCK.acquire(blocking=False):
                raise TaskError(HTTPStatus.CONFLICT, "Another save is already running.")
            try:
                result = git_save_and_send(name, brain, payload["version"], push_only=path == "/api/git/send")
            finally:
                GIT_LOCK.release()
            self._json(HTTPStatus.OK, result)
        except TaskError as error:
            self._json(error.status, {"error": error.message})
        except (ValueError, UnicodeDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON."})
        except OSError:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Could not run Git."})

    def _write_request(self, kind: str) -> None:
        if not self._host_ok() or self.headers.get("Origin") not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}:
            self._json(HTTPStatus.FORBIDDEN, {"error": "Origin refused."})
            return
        if self.headers.get("X-Tasks-Token") != self.server.token:
            self._json(HTTPStatus.FORBIDDEN, {"error": "Invalid local token."})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "JSON required."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= (NOTE_REQUEST_LIMIT if kind in {"note_create", "note_update"} else 8192):
                raise TaskError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request too large.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise TaskError(HTTPStatus.BAD_REQUEST, "JSON object required.")
            path = urlsplit(self.path).path
            status = HTTPStatus.OK
            store = self._store()
            with WRITE_LOCK:
                if kind == "create":
                    status, result = HTTPStatus.CREATED, store.create(payload)
                elif kind == "update":
                    match = re.fullmatch(r"/api/actions/([A-Z]{2,5}-\d{3})", path)
                    if not match:
                        raise TaskError(HTTPStatus.NOT_FOUND, "Action not found.")
                    result = store.update(match.group(1), payload)
                elif kind == "add_note":
                    match = re.fullmatch(r"/api/actions/([A-Z]{2,5}-\d{3})/notes", path)
                    if not match:
                        raise TaskError(HTTPStatus.NOT_FOUND, "Action not found.")
                    status, result = HTTPStatus.CREATED, store.add_note(match.group(1), payload)
                elif kind == "note_create":
                    status, result = HTTPStatus.CREATED, store.create_note(payload)
                elif kind == "note_update":
                    result = store.update_note(payload)
                elif kind == "note_delete":
                    result = store.delete_note_file(payload)
                elif kind == "undo":
                    result = store.undo(payload)
                elif kind == "delete_action":
                    result = store.delete_action(re.fullmatch(r"/api/actions/([A-Z]{2,5}-\d{3})", path).group(1), payload)
                else:
                    match = re.fullmatch(r"/api/actions/([A-Z]{2,5}-\d{3})/notes/(\d{1,4})", path)
                    if not match:
                        raise TaskError(HTTPStatus.NOT_FOUND, "Note not found.")
                    result = store.delete_note(match.group(1), int(match.group(2)), payload)
                if kind != "undo":
                    result = {**result, "undo": store.undo_state()}
            self._json(status, result)
        except TaskError as error:
            self._json(error.status, {"error": error.message, **error.extra})
        except (ValueError, UnicodeDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON."})
        except OSError:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The note could not be deleted." if kind == "note_delete" else "The file could not be saved." if kind in {"note_create", "note_update"} else "The register could not be saved."})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/shutdown":
            self._shutdown_request()
            return
        if path == "/api/tools/run":
            self._tool_request()
            return
        if path in {"/api/git/save", "/api/git/send"}:
            self._git_write_request(path)
            return
        if re.fullmatch(r"/api/actions/[A-Z]{2,5}-\d{3}/notes", path):
            self._write_request("add_note")
            return
        if path == "/api/undo":
            self._write_request("undo")
            return
        if path == "/api/notes":
            self._write_request("note_create")
            return
        if path != "/api/actions":
            self._json(HTTPStatus.NOT_FOUND, {"error": "Page not found."})
            return
        self._write_request("create")

    def _shutdown_request(self) -> None:
        if not self._host_ok() or self.headers.get("Origin") not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"} or self.headers.get("X-Tasks-Token") != self.server.token:
            self._json(HTTPStatus.FORBIDDEN, {"error": "Access refused."})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json" or self.headers.get("Content-Length") != "2" or self.rfile.read(2) != b"{}":
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Invalid shutdown request."})
            return
        self._json(HTTPStatus.OK, {"stopping": True})
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _tool_request(self) -> None:
        if not self._host_ok() or self.headers.get("Origin") not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}:
            self._json(HTTPStatus.FORBIDDEN, {"error": "Origin refused."})
            return
        if self.headers.get("X-Tasks-Token") != self.server.token:
            self._json(HTTPStatus.FORBIDDEN, {"error": "Invalid local token."})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "JSON required."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 256:
                raise TaskError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request too large.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or set(payload) != {"id"} or not isinstance(payload["id"], str):
                raise TaskError(HTTPStatus.BAD_REQUEST, "Invalid tool.")
            brain = self._store().brain
            if not TOOL_LOCK.acquire(blocking=False):
                raise TaskError(HTTPStatus.CONFLICT, "A tool is already running.")
            try:
                result = run_tool(payload["id"], brain)
            finally:
                TOOL_LOCK.release()
            self._json(HTTPStatus.OK, result)
        except TaskError as error:
            self._json(error.status, {"error": error.message})
        except (ValueError, UnicodeDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON."})

    def do_PATCH(self) -> None:
        self._write_request("note_update" if urlsplit(self.path).path == "/api/notes" else "update")

    def do_DELETE(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/notes":
            self._write_request("note_delete")
            return
        is_action = re.fullmatch(r"/api/actions/[A-Z]{2,5}-\d{3}", path)
        self._write_request("delete_action" if is_action else "delete_note")


class TaskServer(ThreadingHTTPServer):
    """One server, several brains: `store` is the default brain's Store, the others are built on first use.

    `work` is the Work root whose brains are offered (default: WORK).
    """

    def __init__(self, address: tuple[str, int], store: Store, work: Path | None = None) -> None:
        super().__init__(address, Handler)
        self.work = (work if work is not None else WORK).resolve()
        self.store = store
        self._stores: dict[str, Store] = {}
        self._stores_lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)

    def _catalog(self) -> tuple[dict[str, Path], str]:
        """(brain name -> folder, name of the default brain), rediscovered on every call.

        The default brain (`--brain`) is the discovered brain with the same folder; when it is none of them it
        is offered first, and it hides a discovered brain that has the same name.
        """
        found = {path.name: path for path in discover_brains(self.work)}
        default = self.store.brain
        for name, path in found.items():
            if path.resolve() == default:
                return found, name
        return {default.name: default, **{name: path for name, path in found.items() if name != default.name}}, default.name

    def brain_list(self) -> dict:
        brains, default = self._catalog()
        return {"brains": [{"name": name, "label": brain_label(name), **brain_boundary(path), "default": name == default}
                           for name, path in brains.items()],
                "default": default}

    def store_for(self, name: str | None) -> Store:
        """The Store of a discovered brain name; None is the default brain. Anything else (a path included) is refused."""
        if name is None:
            return self.store
        brains, default = self._catalog()
        if name == default:
            return self.store
        path = brains.get(name)
        if path is None:
            raise TaskError(HTTPStatus.BAD_REQUEST, "Unknown brain.")
        with self._stores_lock:
            store = self._stores.get(name)
            if store is None or store.brain != path.resolve():
                try:
                    store = self._stores[name] = Store(path)
                except ValueError:
                    raise TaskError(HTTPStatus.NOT_FOUND, "This brain has no projects folder.") from None
            return store

    def git_brains(self) -> dict[str, Path]:
        """The brains the Sync view lists: the discovered ones, the default brain first. Never Work itself."""
        return self._catalog()[0]

    def git_brain(self, name: str | None) -> tuple[str, Path]:
        """(name, folder) of a discovered brain; None is the default brain. Anything else (a path included) is refused."""
        brains, default = self._catalog()
        name = default if name is None else name
        path = brains.get(name)
        if path is None:
            raise TaskError(HTTPStatus.BAD_REQUEST, "Unknown brain.")
        return name, path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--brain", type=Path, default=None,
                        help="default brain (default: the default brain of Work); the other brains of Work are chosen in the page")
    parser.add_argument("--port", type=int, default=8765, help="local port (default: 8765)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("invalid port")
    try:
        brain = args.brain or default_brain_dir()
    except work_config.ConfigError as error:
        parser.error(f"work config error: {error}")
    try:
        store = Store(brain)
    except ValueError as error:
        parser.error(f"{error}" + ("" if args.brain else " (no default brain: set \"defaultBrain\" in work-config.local.json, or pass --brain)"))
    with TaskServer(("127.0.0.1", args.port), store) as server:
        print(f"Actions: http://127.0.0.1:{server.server_port}/ (Ctrl+C to stop)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
