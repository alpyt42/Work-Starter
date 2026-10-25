#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code PreToolUse hook for the Bash tool: refuse three kinds of command (see AGENTS.md).

Reads the hook JSON on stdin (`tool_name`, `tool_input.command`, `cwd`). A blocked command prints one
paragraph on stderr and exits 2; anything else exits 0 silently. Unreadable input or an internal error
also exits 0 (with a short note on stderr): the guard never breaks the session.

1. No direct Python: `python`, `python3`, `python3.N` in command position, also behind wrappers (`env`,
   `sudo`, `xargs`...), env assignments, shell keywords, substitutions and `bash -c` strings. `uv run ...`
   is allowed, and so is any mention that is not a command (arguments, quoted text, heredoc bodies).
2. Nothing deleted or moved out of `artifacts/` (`rm`, `rmdir`, `unlink`, `trash`, `shred`, `git rm`,
   `git clean`, `find -delete`, `rsync --delete`, `mv`): a target inside `artifacts/`, or a folder that
   contains it, is refused. `mv` into `artifacts/archive/` is allowed. The Work root is
   `$CLAUDE_PROJECT_DIR`, else the nearest parent of `cwd` holding `tools/machine/work_config.py`.
3. No Git hook bypass: `--no-verify`, `git commit -n`, `git -c core.hooksPath=...`.

The command is split by a small shell lexer (quotes, substitutions, heredocs, operators); nothing is
executed or expanded, except `~`, `$HOME` and `$CLAUDE_PROJECT_DIR`. A target that cannot be resolved
statically (`"$VAR"`, a command substitution in the first path component) is not blocked.
"""

from __future__ import annotations

import json
import os
import re
import sys
from fnmatch import fnmatchcase

MESSAGES = {
    "python": "Direct Python is not allowed in this workspace: run Python with `uv run <script>` (or `uv run python ...`, `uv run -m ...`), as AGENTS.md requires.",
    "artifacts": "artifacts/ is protected (AGENTS.md): an agent never deletes or moves anything out of artifacts/; moving into artifacts/archive/ is allowed; ask the owner for anything else.",
    "hooks": "The Git hooks are the workspace guardrails (AGENTS.md): do not bypass them with --no-verify, -n or core.hooksPath; fix what they report instead.",
}

OPEN, CLOSE = "(", ")"
GLOB_CHARS = "*?["
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
BRACED_NAME = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
PYTHON = re.compile(r"python[0-9]*(\.[0-9]+)*")
HOOKS_PATH = re.compile(r"(?i)core\.hookspath\b")
REMOTE = re.compile(r"[^/]*:")
KNOWN_VARS = ("HOME", "CLAUDE_PROJECT_DIR")
KEYWORDS = {"if", "then", "else", "elif", "while", "until", "do", "{", "}", "!", "coproc"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}
DELETERS = {"rm", "rmdir", "unlink", "trash", "trash-put", "gtrash", "shred", "srm"}
# Wrapper command -> options that take a separate value.
WRAPPERS = {
    "env": {"-u", "-C", "-S", "--unset", "--chdir", "--split-string"},
    "exec": {"-a"},
    "time": {"-f", "-o"},
    "nohup": set(),
    "command": set(),
    "builtin": set(),
    "xargs": {"-n", "-I", "-P", "-L", "-s", "-d", "-E", "-a", "-J", "--max-args", "--max-procs", "--delimiter", "--replace", "--max-lines", "--arg-file"},
    "sudo": {"-u", "-g", "-C", "-h", "-p", "-r", "-t", "-U", "-D", "-R", "-T", "--user", "--group"},
    "doas": {"-u", "-C"},
    "nice": {"-n", "--adjustment"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "setsid": set(),
    "stdbuf": {"-i", "-o", "-e"},
}
COMMIT_VALUE_LONG = {"--message", "--file", "--author", "--date", "--reuse-message", "--reedit-message", "--template", "--fixup", "--squash", "--cleanup", "--trailer", "--pathspec-from-file"}
RSYNC_VALUE_OPTS = {"-e", "-f", "-T", "--rsh", "--exclude", "--include", "--filter", "--exclude-from", "--include-from", "--files-from", "--rsync-path", "--port", "--log-file", "--backup-dir", "--temp-dir", "--compare-dest", "--copy-dest", "--link-dest", "--bwlimit", "--timeout", "--partial-dir", "--chmod", "--max-size", "--min-size"}


def home() -> str:
    return os.environ.get("HOME") or os.path.expanduser("~")


def basename(text: str) -> str:
    return text.rsplit("/", 1)[-1]


# --- Lexer -------------------------------------------------------------------------------------------


class Word:
    """A shell word with quotes removed; `\\0` stands for an expansion that is not known statically."""

    __slots__ = ("text", "glob")

    def __init__(self, text: str, glob: bool = False) -> None:
        self.text, self.glob = text, glob


class Buf:
    """The word being read."""

    __slots__ = ("parts", "have", "glob", "digits")

    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self.parts: list[str] = []
        self.have = False
        self.glob = False
        self.digits = True  # only unquoted digits so far: a file descriptor before a redirection

    def lit(self, text: str) -> None:
        self.parts.append(text)
        self.have, self.digits = True, False

    def plain(self, ch: str) -> None:
        self.parts.append(ch)
        self.have = True
        if not ch.isdigit():
            self.digits = False

    def star(self, ch: str) -> None:
        self.parts.append(ch)
        self.have, self.glob, self.digits = True, True, False

    def dyn(self) -> None:
        self.lit("\0")

    def take(self) -> Word:
        word = Word("".join(self.parts), self.glob)
        self.clear()
        return word


class Lexer:
    """Split a command line into simple commands (lists of Word) and OPEN/CLOSE scope markers.

    Substitutions (`$(...)`, backticks, `<(...)`) are scanned in place, scoped by OPEN/CLOSE. Heredoc bodies,
    comments and redirection targets are dropped.
    """

    def __init__(self, text: str, events: list) -> None:
        self.s, self.n, self.i, self.events = text, len(text), 0, events

    def sub(self) -> None:
        self.events.append(OPEN)
        self.scan(")")
        self.events.append(CLOSE)

    def scan(self, closer: str | None = None) -> None:
        s, n = self.s, self.n
        words: list[Word] = []
        buf = Buf()
        heredocs: list[tuple[str, bool]] = []
        redirect: str | None = None  # "skip" (drop the target), "heredoc" or "strip" (read the delimiter)
        depth = 0

        def end_word() -> None:
            nonlocal redirect
            if not buf.have:
                return
            word = buf.take()
            if redirect is None:
                words.append(word)
            else:
                if redirect != "skip":
                    heredocs.append((word.text, redirect == "strip"))
                redirect = None

        def end_cmd() -> None:
            nonlocal redirect
            end_word()
            redirect = None
            if words:
                self.events.append(words.copy())
                words.clear()

        while self.i < n:
            i = self.i
            c = s[i]
            if c in " \t":
                end_word()
                self.i += 1
            elif c == "\n":
                end_cmd()
                self.i += 1
                if heredocs:
                    self.skip_heredocs(heredocs)
            elif c == "\\":
                if i + 1 < n and s[i + 1] != "\n":
                    buf.lit(s[i + 1])
                self.i += 2
            elif c == "'":
                j = s.find("'", i + 1)
                j = n if j < 0 else j
                buf.lit(s[i + 1 : j])
                self.i = j + 1
            elif c == '"':
                self.dquote(buf)
            elif c == "`":
                self.backtick(buf)
            elif c == "$":
                self.dollar(buf, False)
            elif c == "#" and not buf.have:
                j = s.find("\n", i)
                self.i = n if j < 0 else j
            elif c in ";|" or (c == "&" and s[i + 1 : i + 2] != ">"):
                end_cmd()
                self.i += 1
            elif c == "(":
                end_cmd()
                self.events.append(OPEN)
                depth += 1
                self.i += 1
            elif c == ")":
                end_cmd()
                self.i += 1
                if depth:
                    depth -= 1
                    self.events.append(CLOSE)
                elif closer:
                    return
            elif c in "<>&":
                if c != "&" and s[i + 1 : i + 2] == "(":  # process substitution
                    self.i += 2
                    self.sub()
                    buf.dyn()
                    continue
                if buf.have and buf.digits:  # `2>file`: the digits are the descriptor
                    buf.clear()
                else:
                    end_word()
                j = i + 2 if c == "&" else i + 1
                if c == "<" and s[j : j + 1] == "<":
                    j += 1
                    if s[j : j + 1] == "<":  # here-string
                        j += 1
                        redirect = "skip"
                    elif s[j : j + 1] == "-":
                        j += 1
                        redirect = "strip"
                    else:
                        redirect = "heredoc"
                else:
                    if s[j - 1 : j] == ">" and s[j : j + 1] == ">":
                        j += 1
                    elif c == "<" and s[j : j + 1] == ">":
                        j += 1
                    if s[j : j + 1] in ("&", "|"):
                        j += 1
                    redirect = "skip"
                self.i = j
            elif c == "~" and not buf.have and (i + 1 >= n or s[i + 1] in "/ \t\n;|&)"):
                buf.lit(home())
                self.i += 1
            elif c in GLOB_CHARS:
                buf.star(c)
                self.i += 1
            else:
                buf.plain(c)
                self.i += 1
        end_cmd()

    def skip_heredocs(self, heredocs: list[tuple[str, bool]]) -> None:
        s, n = self.s, self.n
        for delimiter, strip in heredocs:
            while self.i < n:
                j = s.find("\n", self.i)
                line = s[self.i : n if j < 0 else j]
                self.i = n if j < 0 else j + 1
                if (line.lstrip("\t") if strip else line) == delimiter:
                    break
        heredocs.clear()

    def dquote(self, buf: Buf) -> None:
        s, n = self.s, self.n
        buf.lit("")
        self.i += 1
        while self.i < n:
            c = s[self.i]
            if c == '"':
                self.i += 1
                return
            if c == "\\":
                nxt = s[self.i + 1 : self.i + 2]
                if nxt in ('"', "\\", "$", "`"):
                    buf.lit(nxt)
                elif nxt != "\n":
                    buf.lit("\\" + nxt)
                self.i += 2
            elif c == "$":
                self.dollar(buf, True)
            elif c == "`":
                self.backtick(buf)
            else:
                j = self.i
                while j < n and s[j] not in '"\\$`':
                    j += 1
                buf.lit(s[self.i : j])
                self.i = j

    def backtick(self, buf: Buf) -> None:
        s, n = self.s, self.n
        i, out = self.i + 1, []
        while i < n and s[i] != "`":
            if s[i] == "\\" and s[i + 1 : i + 2] in ("`", "\\", "$"):
                i += 1
            out.append(s[i])
            i += 1
        self.i = i + 1
        self.events.append(OPEN)
        Lexer("".join(out), self.events).scan()
        self.events.append(CLOSE)
        buf.dyn()

    def dollar(self, buf: Buf, in_dquote: bool) -> None:
        s, n, i = self.s, self.n, self.i
        nxt = s[i + 1 : i + 2]
        if nxt == "(":
            if s[i + 2 : i + 3] == "(":  # arithmetic expansion
                depth, j = 0, i + 1
                while j < n:
                    if s[j] == "(":
                        depth += 1
                    elif s[j] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                self.i = j + 1
            else:
                self.i = i + 2
                self.sub()
            buf.dyn()
            return
        if nxt == "{":
            match = BRACED_NAME.match(s, i + 1)
            if match:
                self.var(buf, match.group(1))
                self.i = match.end()
                return
            depth, j = 1, i + 2
            while j < n and depth:
                ch = s[j]
                if ch == "\\":
                    j += 2
                    continue
                if ch == "$" and s[j + 1 : j + 2] == "(":
                    self.i = j + 2
                    self.sub()
                    j = self.i
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                j += 1
            self.i = j
            buf.dyn()
            return
        if not in_dquote and nxt == "'":  # $'...' (ANSI-C quoting)
            j = i + 2
            while j < n and s[j] != "'":
                j += 2 if s[j] == "\\" else 1
            buf.lit(s[i + 2 : j])
            self.i = j + 1
            return
        if not in_dquote and nxt == '"':
            self.i = i + 1
            self.dquote(buf)
            return
        match = NAME.match(s, i + 1)
        if match:
            self.var(buf, match.group())
            self.i = match.end()
            return
        if nxt and nxt in "#?$!@*-0123456789":
            buf.dyn()
            self.i = i + 2
            return
        buf.lit("$")
        self.i = i + 1

    @staticmethod
    def var(buf: Buf, name: str) -> None:
        value = os.environ.get(name) if name in KNOWN_VARS else None
        if value:
            buf.lit(value)
        else:
            buf.dyn()


# --- Paths -------------------------------------------------------------------------------------------


def expand_braces(text: str, budget: int = 64) -> list[str]:
    """Expand `{a,b}` lists (not ranges), at most `budget` results."""
    start = text.find("{")
    while start != -1:
        depth, commas, end = 0, [], -1
        for j in range(start, len(text)):
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
            elif ch == "," and depth == 1:
                commas.append(j)
        if end != -1 and commas:
            bounds = [start, *commas, end]
            head, tail = text[:start], text[end + 1 :]
            out: list[str] = []
            for a, b in zip(bounds, bounds[1:]):
                out.extend(expand_braces(head + text[a + 1 : b] + tail, budget))
                if len(out) >= budget:
                    break
            return out[:budget]
        start = text.find("{", start + 1)
    return [text]


def parts(path: str) -> list[str]:
    return [p.lower() for p in path.split("/") if p]


class Context:
    """What the rules share: the hits found so far, the working directory and the artifacts location."""

    def __init__(self, cwd: str | None) -> None:
        self.cwd = cwd
        self.hits: dict[str, str] = {}
        self.depth = 0
        self._work: str | None = None
        self._artifacts: tuple[list[list[str]], list[list[str]]] | None = None

    def hit(self, rule: str, detail: str) -> None:
        self.hits.setdefault(rule, " ".join(detail.split())[:80])

    def work(self) -> str | None:
        if self._work is None:
            found = ""
            env = os.environ.get("CLAUDE_PROJECT_DIR")
            if env and os.path.isabs(env):
                found = os.path.normpath(env)
            elif self.cwd:
                path = self.cwd
                while True:
                    if os.path.isfile(path + "/tools/machine/work_config.py"):
                        found = path
                        break
                    parent = os.path.dirname(path)
                    if parent == path:
                        break
                    path = parent
            self._work = found
        return self._work or None

    def artifacts(self) -> tuple[list[list[str]], list[list[str]]]:
        """Component lists of artifacts/ and of artifacts/archive/ (lexical and real path)."""
        if self._artifacts is None:
            work = self.work()
            lexical = os.path.normpath(work + "/artifacts") if work else None
            paths = list(dict.fromkeys((lexical, os.path.realpath(lexical)))) if lexical else []
            self._artifacts = ([parts(p) for p in paths], [parts(p) + ["archive"] for p in paths])
        return self._artifacts

    def analyze(self, text: str, cwd: str | None) -> None:
        if self.depth >= 6:
            return
        events: list = []
        Lexer(text, events).scan()
        self.depth += 1
        try:
            run(events, cwd, self)
        finally:
            self.depth -= 1


Resolved = list[list[tuple[list[str], int]]]


def resolve(word: Word, cwd: str | None, ctx: Context) -> Resolved:
    """Absolute path variants of a word, one list per brace expansion: (components, count of literal ones).

    Components after the first glob are patterns; the literal prefix is resolved (`..`, symlinks).
    Nothing is returned for a word that cannot be resolved statically.
    """
    out: Resolved = []
    for text in expand_braces(word.text):
        if "\0" in text.split("/", 1)[0]:
            continue
        glob = word.glob or "\0" in text
        text = text.replace("\0", "*")
        if not text.startswith("/"):
            if cwd is not None:
                text = cwd + "/" + text
            elif text.split("/", 1)[0].lower() == "artifacts" and ctx.work():  # after an unknown `cd`
                text = ctx.work() + "/" + text
            else:
                continue
        comps = [p for p in text.split("/") if p and p != "."]
        k = len(comps)
        if glob:
            k = next((j for j, p in enumerate(comps) if any(ch in p for ch in GLOB_CHARS)), k)
        prefix = "/" + "/".join(comps[:k])
        rest = [p.lower() for p in comps[k:]]
        variants = []
        for path in dict.fromkeys((os.path.normpath(prefix), os.path.realpath(prefix))):
            literal = parts(path)
            variants.append((literal + rest, len(literal)))
        out.append(variants)
    return out


def overlaps(resolved: Resolved, artifacts: list[list[str]]) -> bool:
    """True when a path is artifacts/, inside it, or a folder that contains it."""
    for variants in resolved:
        for comps, literal in variants:
            for art in artifacts:
                if all((comps[i] == art[i]) if i < literal else fnmatchcase(art[i], comps[i]) for i in range(min(len(comps), len(art)))):
                    return True
    return False


def touching(words: list[Word], cwd: str | None, ctx: Context) -> str | None:
    artifacts = ctx.artifacts()[0]
    if artifacts:
        for word in words:
            if overlaps(resolve(word, cwd, ctx), artifacts):
                return word.text
    return None


def in_archive(word: Word | None, cwd: str | None, ctx: Context) -> bool:
    """True when the path is artifacts/archive/ or inside it, for sure (no glob in the way)."""
    resolved = resolve(word, cwd, ctx) if word is not None else []
    archives = ctx.artifacts()[1]
    return bool(resolved) and all(any(literal >= len(arc) and comps[: len(arc)] == arc for comps, literal in variants for arc in archives) for variants in resolved)


def change_dir(args: list[Word], cwd: str | None) -> str | None:
    pos = [a for a in args if a.text == "-" or not a.text.startswith("-")]
    if not pos:
        return home()
    word = pos[0]
    if word.glob or "\0" in word.text or word.text == "-":
        return None
    path = word.text
    if not path.startswith("/"):
        if cwd is None:
            return None
        path = cwd + "/" + path
    return os.path.normpath(path)


# --- Rules -------------------------------------------------------------------------------------------


def positional(args: list[Word], value_opts: tuple[str, ...] = ()) -> list[Word]:
    out, done, i = [], False, 0
    while i < len(args):
        text = args[i].text
        if not done and text == "--":
            done = True
        elif not done and text in value_opts:
            i += 1
        elif done or text == "-" or not text.startswith("-"):
            out.append(args[i])
        i += 1
    return out


def has_flag(args: list[Word], letters: str, longs: tuple[str, ...], value_opts: tuple[str, ...] = ()) -> bool:
    i = 0
    while i < len(args):
        text = args[i].text
        if text == "--":
            return False
        if text in value_opts:
            i += 1
        elif text in longs:
            return True
        elif text.startswith("-") and not text.startswith("--") and any(ch in letters for ch in text[1:]):
            return True
        i += 1
    return False


def strip(words: list[Word]) -> list[Word]:
    """Drop what comes before the command itself: keywords, assignments and wrappers (`env`, `sudo`...)."""
    i, total = 0, len(words)
    while i < total:
        text = words[i].text
        if text in KEYWORDS or text == "--" or ASSIGN.match(text):
            i += 1
        elif text == "function":
            i += 2
        elif basename(text) in WRAPPERS:
            base = basename(text)
            value_opts = WRAPPERS[base]
            i += 1
            while i < total:
                option = words[i].text
                if option == "--":
                    i += 1
                    break
                if len(option) < 2 or option[0] != "-":
                    break
                if base == "command" and not option.startswith("--") and ("v" in option or "V" in option):
                    return []  # `command -v` only describes the command
                i += 2 if option in value_opts else 1
            if base == "timeout":
                i += 1  # the duration
        else:
            break
    return words[i:]


def shell_script(args: list[Word]) -> str | None:
    """The string given to `bash -c` and similar, if any."""
    seen_c, i = False, 0
    while i < len(args):
        text = args[i].text
        if text[:1] in ("-", "+") and text != "--":
            if text[0] == "-" and not text.startswith("--") and text[1:].isalpha() and "c" in text:
                seen_c = True
            elif text in ("-o", "+o", "-O", "+O"):
                i += 1
        elif text != "--":
            return text if seen_c else None
        i += 1
    return None


def handle(words: list[Word], cwd: str | None, ctx: Context) -> str | None:
    """Apply the rules to one simple command; return the working directory that follows it."""
    words = strip(words)
    if not words:
        return cwd
    name, args = basename(words[0].text), words[1:]
    if PYTHON.fullmatch(name):
        ctx.hit("python", name)
    elif name in SHELLS:
        script = shell_script(args)
        if script is not None:
            ctx.analyze(script, cwd)
    elif name == "eval":
        ctx.analyze(" ".join(w.text for w in args), cwd)
    elif name == "git":
        git(args, cwd, ctx)
    elif name in DELETERS:
        found = touching(positional(args), cwd, ctx)
        if found:
            ctx.hit("artifacts", f"{name} {found}")
    elif name == "mv":
        sources, dest = mv_split(args)
        found = touching(sources, cwd, ctx) if dest is not None else None
        if found and not in_archive(dest, cwd, ctx):
            ctx.hit("artifacts", f"mv {found}")
    elif name == "find":
        find(args, cwd, ctx)
    elif name == "rsync":
        rsync(args, cwd, ctx)
    elif name in ("cd", "pushd"):
        return change_dir(args, cwd)
    elif name == "popd":
        return None
    return cwd


def mv_split(args: list[Word]) -> tuple[list[Word], Word | None]:
    """Sources and destination of an `mv` command line."""
    pos: list[Word] = []
    dest: Word | None = None
    done, i = False, 0
    while i < len(args):
        text = args[i].text
        if done or text == "-" or not text.startswith("-"):
            pos.append(args[i])
        elif text == "--":
            done = True
        elif text.startswith("--"):
            if text == "--target-directory" and i + 1 < len(args):
                i += 1
                dest = args[i]
            elif text.startswith("--target-directory="):
                dest = Word(text.split("=", 1)[1], args[i].glob)
            elif text == "--suffix":
                i += 1
        else:
            for k, ch in enumerate(text[1:], 1):
                if ch in "tS":
                    value: Word | None = None
                    if text[k + 1 :]:
                        value = Word(text[k + 1 :], args[i].glob)
                    elif i + 1 < len(args):
                        i += 1
                        value = args[i]
                    if ch == "t":
                        dest = value
                    break
        i += 1
    if dest is None and pos:
        dest = pos.pop()
    return pos, dest


def find(args: list[Word], cwd: str | None, ctx: Context) -> None:
    i, paths = 0, []
    while i < len(args):
        text = args[i].text
        if text in ("-H", "-L", "-P", "-E", "-X", "-x", "-s", "-d") or text.startswith("-O"):
            i += 1
        elif text == "-f" and i + 1 < len(args):
            paths.append(args[i + 1])
            i += 2
        else:
            break
    while i < len(args) and args[i].text[:1] != "-" and args[i].text not in ("(", ")", "!", ","):
        paths.append(args[i])
        i += 1
    paths = paths or [Word(".")]
    destructive = False
    while i < len(args):
        text = args[i].text
        if text == "-delete":
            destructive = True
        elif text in ("-exec", "-execdir", "-ok", "-okdir"):
            j = i + 1
            while j < len(args) and args[j].text not in (";", "+"):
                j += 1
            command = strip(args[i + 1 : j])
            handle(command, cwd, ctx)
            if command:
                base = basename(command[0].text)
                if base in DELETERS:
                    destructive = True
                elif base == "mv":
                    destructive = destructive or not in_archive(mv_split(command[1:])[1], cwd, ctx)
            i = j
        i += 1
    if destructive:
        found = touching(paths, cwd, ctx)
        if found:
            ctx.hit("artifacts", f"find {found}")


def rsync(args: list[Word], cwd: str | None, ctx: Context) -> None:
    flags, pos, i = [], [], 0
    while i < len(args):
        text = args[i].text
        if text in RSYNC_VALUE_OPTS:
            i += 1
        elif text.startswith("-") and len(text) > 1:
            flags.append(text)
        else:
            pos.append(args[i])
        i += 1
    if len(pos) < 2:
        return
    dest, sources = pos[-1], [w for w in pos[:-1] if not REMOTE.match(w.text)]
    if any(f.startswith("--delete") or f == "--del" for f in flags) and not REMOTE.match(dest.text):
        found = touching([dest], cwd, ctx)
        if found:
            ctx.hit("artifacts", f"rsync --delete {found}")
    if any(f.startswith("--remove-source") for f in flags):
        found = touching(sources, cwd, ctx)
        if found and not in_archive(dest, cwd, ctx):
            ctx.hit("artifacts", f"rsync --remove-source-files {found}")


def commit_skips_hooks(args: list[Word]) -> bool:
    """`git commit` options after the subcommand: `--no-verify`, `-n`, `-nm`, but not the value of `-m`."""
    i = 0
    while i < len(args):
        text = args[i].text
        if text == "--":
            return False
        if text.startswith("--"):
            if len(text) >= 9 and "--no-verify".startswith(text):
                return True
            if text in COMMIT_VALUE_LONG:
                i += 1
        elif text.startswith("-") and len(text) > 1:
            for k, ch in enumerate(text[1:], 1):
                if ch == "n":
                    return True
                if ch in "mFCct":  # takes a value: the rest of the word, else the next word
                    if k == len(text) - 1:
                        i += 1
                    break
                if ch in "Su":  # optional attached value
                    break
        i += 1
    return False


def git(args: list[Word], cwd: str | None, ctx: Context) -> None:
    i = 0
    while i < len(args):
        text = args[i].text
        following = args[i + 1].text if i + 1 < len(args) else ""
        if text == "-C":
            cwd = change_dir([args[i + 1]], cwd) if i + 1 < len(args) else cwd
            i += 2
        elif text in ("-c", "--config-env"):
            if HOOKS_PATH.match(following):
                ctx.hit("hooks", "git -c core.hooksPath")
            i += 2
        elif text.startswith("--config-env="):
            if HOOKS_PATH.match(text.split("=", 1)[1]):
                ctx.hit("hooks", "git --config-env core.hooksPath")
            i += 1
        elif text.startswith("-c") and not text.startswith("--") and HOOKS_PATH.match(text[2:]):
            ctx.hit("hooks", "git -c core.hooksPath")
            i += 1
        elif text in ("--git-dir", "--work-tree", "--namespace", "--super-prefix", "--attr-source"):
            i += 2
        elif text.startswith("-"):
            i += 1
        else:
            break
    if i >= len(args):
        return
    sub, rest = args[i].text, args[i + 1 :]
    if sub == "commit" and commit_skips_hooks(rest):
        ctx.hit("hooks", "git commit --no-verify")
    elif sub in ("push", "merge", "rebase", "am") and commit_skips_hooks_long(rest):
        ctx.hit("hooks", f"git {sub} --no-verify")
    elif sub == "rm":
        if not has_flag(rest, "n", ("--cached", "--dry-run")):
            found = touching(positional(rest), cwd, ctx)
            if found:
                ctx.hit("artifacts", f"git rm {found}")
    elif sub == "clean":
        if not has_flag(rest, "n", ("--dry-run",), ("-e", "--exclude")):
            targets = positional(rest, ("-e", "--exclude")) or [Word(".")]
            found = touching(targets, cwd, ctx)
            if found:
                ctx.hit("artifacts", f"git clean {found}")


def commit_skips_hooks_long(args: list[Word]) -> bool:
    for word in args:
        if word.text == "--":
            return False
        if word.text.startswith("--") and len(word.text) >= 9 and "--no-verify".startswith(word.text):
            return True
    return False


def run(events: list, cwd: str | None, ctx: Context) -> None:
    """Walk the simple commands in order; `cd` is followed, and undone when a subshell or substitution ends."""
    stack = [cwd]
    for event in events:
        if isinstance(event, str):
            if event == OPEN:
                stack.append(stack[-1])
            elif len(stack) > 1:
                stack.pop()
        else:
            stack[-1] = handle(event, stack[-1], ctx)


# --- Entry point -------------------------------------------------------------------------------------


def main() -> int:
    try:
        data = json.loads(sys.stdin.read())
    except ValueError:
        sys.stderr.write("claude-bash-guard: unreadable input, command not checked\n")
        return 0
    if not isinstance(data, dict) or data.get("tool_name") not in (None, "Bash"):
        return 0
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command.strip():
        return 0
    cwd = data.get("cwd")
    cwd = os.path.normpath(cwd) if isinstance(cwd, str) and os.path.isabs(cwd) else os.getcwd()
    ctx = Context(cwd)
    try:
        ctx.analyze(command, cwd)
    except Exception as exc:  # a parsing slip must not hide a hit already found, nor break the session
        sys.stderr.write(f"claude-bash-guard: error while checking ({type(exc).__name__}: {exc})\n")
    if not ctx.hits:
        return 0
    reasons = " ".join(f"{MESSAGES[rule]} (matched: {ctx.hits[rule]})" for rule in MESSAGES if rule in ctx.hits)
    sys.stderr.write(f"claude-bash-guard blocked this command. {reasons}\n")
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        sys.stderr.write(f"claude-bash-guard: internal error ignored ({type(exc).__name__}: {exc})\n")
        code = 0
    sys.exit(code)
