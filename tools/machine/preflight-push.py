#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Identity and safety checks before a push: the automated form of tools/machine/GIT-IDENTITY.md.

Usage: preflight-push.py [--repo DIR] [REMOTE] [--no-ssh] [--no-fetch] [--hook]

Checks, each printed as an OK:, INFO:, WARN: or ERROR: line, then a summary (exit status 1 on any ERROR):

- GIT_SSH_COMMAND and GIT_SSH are not set in the environment (they silently override core.sshCommand);
- user.name, user.email and core.sshCommand are effective, shown with the file they come from: none may
  come from the repository's own config (local override) or from the plain global config (the identity
  comes from a ~/.gitconfig-<boundary> file); user.email must be set;
- in a brain (.data/brain.json at its root), the push URL matches the "remote" pattern and the effective
  user.email the "email" pattern (fnmatch globs, as in doctor.py);
- for an SSH remote (unless --no-ssh), the SSH login really authenticates and names its account (GitHub and
  GitLab banners), through the effective SSH command and with BatchMode, never weakening host-key checks;
- fast-forward: with --hook, the ref updates that Git writes on stdin (a remote ref deletion, a force push
  and a remote that moved are refused); by hand, the current branch against its remote branch after a
  fetch of REMOTE (skipped by --no-fetch, which compares with the last fetched state).

REMOTE is the remote name or URL; by default the upstream remote of the current branch, else origin, else
the only remote. --hook is for the pre-push hook (tools/machine/hooks/pre-push), which passes the remote
name Git gives it and forwards the ref lines on stdin. The script only reads, except the optional fetch.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

SSH_TIMEOUT = 20  # seconds for the SSH login test
FETCH_TIMEOUT = 60
GIT_TIMEOUT = 30
SSH_OVERRIDES = ("GIT_SSH_COMMAND", "GIT_SSH")
IDENTITY_KEYS = ("user.name", "user.email", "core.sshCommand")
# Variables a Git hook may set to point at its own repository: the checks name the repository themselves.
STALE_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_OBJECT_DIRECTORY",
             "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_QUARANTINE_PATH")
ENV = {**{k: v for k, v in os.environ.items() if k not in STALE_ENV}, "GIT_TERMINAL_PROMPT": "0"}
ZERO_SHA = re.compile(r"^0+$")
ACCOUNT_BANNERS = (  # the account an SSH login reports
    re.compile(r"Hi ([^\s!]+)! You've successfully authenticated"),  # GitHub
    re.compile(r"Welcome to GitLab, @([^\s!]+)!"),  # GitLab
)
SSH_FAILURES = (  # (pattern in the SSH output, short reason); nothing else of the output is printed
    (re.compile(r"REMOTE HOST IDENTIFICATION HAS CHANGED"), "the host key changed: verify it before anything else"),
    (re.compile(r"Host key verification failed"), "host key not verified"),
    (re.compile(r"Permission denied"), "permission denied: the key is not accepted"),
    (re.compile(r"Could not resolve hostname"), "host name not resolved"),
    (re.compile(r"Connection (timed out|refused|closed|reset)|timed out", re.I), "connection failed"),
)


class Report:
    """Prints each finding as it is made and counts the errors and warnings."""

    def __init__(self) -> None:
        self.errors = 0
        self.warnings = 0

    def emit(self, level: str, text: str) -> None:
        self.errors += level == "ERROR"
        self.warnings += level == "WARN"
        print(f"{level}: {text}", flush=True)


def git(repo: Path, *args: str, timeout: int = GIT_TIMEOUT) -> tuple[int, str]:
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout,
                                env=ENV, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""
    return result.returncode, result.stdout.strip()


def run_detached(argv: list[str], timeout: int) -> tuple[int, str]:
    """Run a command with no terminal (nothing can prompt) and kill its whole process group on timeout.

    Returns (exit status, stdout and stderr together); 124 on timeout, 127 when the command cannot start.
    """
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, env=ENV, start_new_session=True)
    except OSError:
        return 127, ""
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()
        process.communicate()
        return 124, ""
    return process.returncode, output or ""


def redact(url: str) -> str:
    """The URL without the credentials it may carry."""
    url = re.sub(r"^((?:https?|ftps?)://)[^/@]*@", r"\1***@", url)
    return re.sub(r"^((?:ssh|ssh\+git|git\+ssh)://[^/@:]+):[^/@]*@", r"\1@", url)


def ssh_target(url: str) -> tuple[str, str, str | None] | None:
    """(user, host, port) of an SSH remote URL (ssh://… or scp-like user@host:path); None for any other URL."""
    if "://" in url:
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            return None
        if parts.scheme not in ("ssh", "ssh+git", "git+ssh") or not parts.hostname:
            return None
        return parts.username or "git", parts.hostname, str(port) if port else None
    match = re.match(r"^(?:([^@/:\[]+)@)?(\[[0-9A-Fa-f:.]+\]|[^@/:\[]+):", url)
    if not match:
        return None
    return match.group(1) or "git", match.group(2).strip("[]"), None


def ssh_probe(command: str, user: str, host: str, port: str | None, timeout: int = SSH_TIMEOUT) -> tuple[str | None, str]:
    """Log in to the host as Git does and return (account, reason): the account named by the banner, else why not."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+|[0-9A-Fa-f:.]+", host) or host.startswith("-") or not re.fullmatch(r"[A-Za-z0-9._-]+", user):
        return None, "unsafe user or host name in the URL"
    args = ["-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", *(["-p", port] if port else []), f"{user}@{host}"]
    # Git runs the SSH command through the shell with the arguments appended: do the same.
    code, output = run_detached(["sh", "-c", f'{command} "$@"', "ssh", *args], timeout)
    if code == 124:
        return None, f"no answer within {timeout} seconds"
    if code == 127:
        return None, "the SSH command could not be run"
    for banner in ACCOUNT_BANNERS:
        match = banner.search(output)
        if match:
            return match.group(1), ""
    for pattern, reason in SSH_FAILURES:
        if pattern.search(output):
            return None, reason
    return None, "no GitHub or GitLab account banner in the answer"


def local_config_dirs(repo: Path) -> set[Path]:
    """The directories holding the repository's own config files (.git, and the common dir of a linked worktree)."""
    dirs: set[Path] = set()
    code, out = git(repo, "rev-parse", "--absolute-git-dir")
    if code == 0 and out:
        dirs.add(Path(out).resolve())
    code, out = git(repo, "rev-parse", "--git-common-dir")
    if code == 0 and out:
        dirs.add((repo / out).resolve())
    return dirs


def global_configs() -> set[Path]:
    """The plain global config files Git reads (home config and XDG config, or GIT_CONFIG_GLOBAL alone)."""
    if "GIT_CONFIG_GLOBAL" in os.environ:
        return {Path(os.environ["GIT_CONFIG_GLOBAL"]).resolve()} if os.environ["GIT_CONFIG_GLOBAL"] else set()
    xdg = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return {(Path.home() / ".gitconfig").resolve(), (xdg / "git/config").resolve()}


def classify_origin(repo: Path, origin: str, local_dirs: set[Path], global_files: set[Path]) -> tuple[str, str]:
    """(kind, display name) of a config origin: kind is command, local, global or file."""
    if not origin.startswith("file:"):
        return "command", "the command line or the GIT_CONFIG_* variables"
    path = Path(origin[len("file:"):].strip('"'))
    resolved = (path if path.is_absolute() else repo / path).resolve()
    if resolved.parent in local_dirs:
        return "local", f".git/{resolved.name}"
    kind = "global" if resolved in global_files else "file"
    home = Path.home().resolve()
    return kind, f"~/{resolved.name}" if resolved.parent == home else resolved.name


def config_value(repo: Path, key: str) -> tuple[str, str] | None:
    code, out = git(repo, "config", "--show-origin", "--get", key)
    if code != 0 or not out:
        return None
    origin, _, value = out.partition("\t")
    return (origin, value.strip()) if value.strip() else None


def check_environment(report: Report) -> None:
    for name in SSH_OVERRIDES:
        if name in os.environ:
            report.emit("ERROR", f"{name} is set in the environment: it overrides core.sshCommand and the home rules (unset it)")
    if not any(name in os.environ for name in SSH_OVERRIDES):
        report.emit("OK", "GIT_SSH_COMMAND and GIT_SSH are not set")


def check_identity(repo: Path, report: Report) -> str | None:
    """Show user.name, user.email and core.sshCommand with their origin; return the effective user.email."""
    local_dirs, global_files = local_config_dirs(repo), global_configs()
    email = None
    for key in IDENTITY_KEYS:
        found = config_value(repo, key)
        if found is None:
            if key == "user.email":
                report.emit("ERROR", "user.email is not set: no ~/.gitconfig-<boundary> rule applies to this clone (user.useConfigOnly)")
            elif key == "user.name":
                report.emit("WARN", "user.name is not set")
            else:
                report.emit("INFO", "core.sshCommand is not set: the SSH key comes from ~/.ssh/config")
            continue
        origin, value = found
        if key == "user.email":
            email = value
        kind, name = classify_origin(repo, origin, local_dirs, global_files)
        shown = f"{key} = {value} (from {name})"
        if kind == "local":
            report.emit("ERROR", f"{shown}: local override forbidden by GIT-IDENTITY.md; remove it with `git config --local --unset {key}`")
        elif kind == "global":
            report.emit("ERROR", f"{shown}: the identity must come from a ~/.gitconfig-<boundary> file selected by an includeIf rule, not from the plain global config")
        elif kind == "command":
            report.emit("ERROR", f"{shown}: the identity must come from a ~/.gitconfig-<boundary> file")
        elif not name.rsplit("/", 1)[-1].startswith(".gitconfig-"):
            report.emit("WARN", f"{shown}: not a ~/.gitconfig-<boundary> file")
        else:
            report.emit("OK", shown)
    return email


def default_remote(repo: Path) -> str | None:
    code, branch = git(repo, "symbolic-ref", "--short", "-q", "HEAD")
    if code == 0 and branch:
        code, upstream = git(repo, "config", "--get", f"branch.{branch}.remote")
        if code == 0 and upstream and upstream != ".":
            return upstream
    code, out = git(repo, "remote")
    remotes = out.split() if code == 0 else []
    if "origin" in remotes:
        return "origin"
    return remotes[0] if len(remotes) == 1 else None


def push_urls(repo: Path, remote: str) -> tuple[list[str], bool]:
    """(push URLs, whether REMOTE is a configured remote); a name that is no remote but looks like a URL is the URL."""
    code, out = git(repo, "remote", "get-url", "--push", "--all", remote)
    if code == 0 and out:
        return out.splitlines(), True
    if re.search(r"[/:@]", remote):
        code, out = git(repo, "ls-remote", "--get-url", remote)
        return [out if code == 0 and out else remote], False
    return [], False


def check_boundary(repo: Path, urls: list[str], email: str | None, report: Report) -> None:
    path = repo / ".data/brain.json"
    if not path.is_file():
        report.emit("INFO", "not a brain (no .data/brain.json): no trust-boundary declaration to compare")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
    except (OSError, ValueError):
        report.emit("ERROR", ".data/brain.json is unreadable: the trust boundary of this brain cannot be verified")
        return
    patterns = {field: data[field].strip() for field in ("remote", "email") if isinstance(data.get(field), str) and data[field].strip()}
    if "remote" not in patterns:
        report.emit("WARN", 'brain.json declares no "remote" pattern: the push URL is not compared')
    elif not urls:
        report.emit("ERROR", "no push URL to compare with the \"remote\" pattern of brain.json")
    else:
        for url in urls:
            if fnmatch.fnmatchcase(url, patterns["remote"]):
                report.emit("OK", f'push URL {redact(url)} matches the "remote" pattern of brain.json')
            else:
                report.emit("ERROR", f'push URL {redact(url)} does not match the "remote" pattern of brain.json (trust boundary)')
    if "email" not in patterns:
        report.emit("WARN", 'brain.json declares no "email" pattern: the effective user.email is not compared')
    elif not email:
        report.emit("ERROR", 'no effective user.email to compare with the "email" pattern of brain.json')
    elif fnmatch.fnmatchcase(email, patterns["email"]):
        report.emit("OK", 'effective user.email matches the "email" pattern of brain.json')
    else:
        report.emit("ERROR", f'effective user.email {email} does not match the "email" pattern of brain.json (trust boundary)')


def check_ssh(repo: Path, urls: list[str], report: Report) -> None:
    found = config_value(repo, "core.sshCommand")
    command = found[1] if found else "ssh"
    tested: set[tuple[str, str, str | None]] = set()
    for url in urls:
        target = ssh_target(url)
        if target is None:
            report.emit("INFO", f"{redact(url)} is not an SSH remote: no SSH test")
            continue
        if target in tested:
            continue
        tested.add(target)
        user, host, port = target
        account, reason = ssh_probe(command, user, host, port)
        if account is None:
            report.emit("ERROR", f"SSH authentication to {host} failed: {reason}")
        else:
            report.emit("OK", f"SSH authentication to {host} succeeded")
            report.emit("INFO", f"SSH account on {host}: {account}")


def count_commits(repo: Path, base: str, tip: str) -> int:
    code, out = git(repo, "rev-list", "--count", f"{base}^{{commit}}..{tip}^{{commit}}")
    return int(out) if code == 0 and out.isdigit() else 0


def compare(repo: Path, local: str, remote: str) -> tuple[bool, str]:
    """Whether updating a remote ref from `remote` to `local` is a fast-forward, with the reason."""
    if ZERO_SHA.match(remote):
        return True, "new on the remote"
    if git(repo, "cat-file", "-e", f"{remote}^{{commit}}")[0] != 0:
        return False, "the remote tip is unknown locally (the remote moved): fetch and integrate first"
    code, _ = git(repo, "merge-base", "--is-ancestor", f"{remote}^{{commit}}", f"{local}^{{commit}}")
    if code == 0:
        if remote == local:
            return True, "already up to date"
        return True, f"fast-forward ({count_commits(repo, remote, local)} commit(s))"
    if code == 1:
        if git(repo, "merge-base", "--is-ancestor", f"{local}^{{commit}}", f"{remote}^{{commit}}")[0] == 0:
            return False, f"the remote is ahead by {count_commits(repo, local, remote)} commit(s): fetch and integrate first"
        return False, "history diverged from the remote (force push or remote ahead): fetch and integrate first"
    return False, "cannot compare with the remote tip"


def check_hook_refs(repo: Path, lines: list[str], report: Report) -> None:
    """The ref updates Git writes to a pre-push hook: <local ref> <local sha> <remote ref> <remote sha>."""
    updates = 0
    for line in lines:
        parts = line.split()
        if len(parts) != 4:
            report.emit("WARN", "unexpected line from Git ignored")
            continue
        _, local_sha, remote_ref, remote_sha = parts
        updates += 1
        if ZERO_SHA.match(local_sha):
            report.emit("ERROR", f"{remote_ref}: remote branch deletion refused (delete it by hand, outside this check)")
            continue
        ok, message = compare(repo, local_sha, remote_sha)
        report.emit("OK" if ok else "ERROR", f"{remote_ref}: {message}")
    if not updates:
        report.emit("INFO", "no ref update to check")


def check_current_branch(repo: Path, remote: str, is_remote: bool, fetch: bool, report: Report) -> None:
    """By hand: the current branch against its branch on the remote, after a fetch unless disabled."""
    code, branch = git(repo, "symbolic-ref", "--short", "-q", "HEAD")
    if code != 0 or not branch:
        report.emit("WARN", "detached HEAD: fast-forward check skipped")
        return
    if not is_remote:
        report.emit("WARN", "the remote is a URL, not a configured remote: fast-forward check skipped")
        return
    if fetch:
        code, output = run_detached(["git", "-C", str(repo), "fetch", "--quiet", remote], FETCH_TIMEOUT)
        if code != 0:
            reason = next((line.strip()[:160] for line in reversed(output.splitlines()) if line.startswith(("fatal:", "error:"))), "")
            report.emit("ERROR", f"fetch of {remote} failed, remote state unknown{': ' + reason if reason else ''} (use --no-fetch to skip)")
            return
    else:
        report.emit("INFO", f"no fetch (--no-fetch): comparing with the last fetched state of {remote}")
    merge = git(repo, "config", "--get", f"branch.{branch}.merge")[1]
    tracked = git(repo, "config", "--get", f"branch.{branch}.remote")[1] == remote and merge.startswith("refs/heads/")
    name = merge[len("refs/heads/"):] if tracked else branch
    code, remote_sha = git(repo, "rev-parse", "--verify", "-q", f"refs/remotes/{remote}/{name}")
    local_sha = git(repo, "rev-parse", "--verify", "-q", "HEAD")[1]
    if code != 0 or not remote_sha:
        report.emit("INFO", f"{name} is not on {remote} yet (no remote-tracking branch): a push creates it")
        return
    ok, message = compare(repo, local_sha, remote_sha)
    report.emit("OK" if ok else "ERROR", f"{branch} against {remote}/{name}: {message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Identity and safety checks before a push (tools/machine/GIT-IDENTITY.md).")
    parser.add_argument("remote", nargs="?", help="remote name or URL (default: upstream remote of the current branch, else origin, else the only remote)")
    parser.add_argument("--repo", default=".", help="repository to check (default: current directory)")
    parser.add_argument("--no-ssh", action="store_true", help="skip the SSH login test")
    parser.add_argument("--no-fetch", action="store_true", help="by hand, compare with the last fetched state instead of fetching")
    parser.add_argument("--hook", action="store_true", help="pre-push hook mode: read the ref updates from stdin")
    args = parser.parse_args(argv)
    lines = [] if not args.hook or sys.stdin.isatty() else [line for line in sys.stdin.read().splitlines() if line.strip()]

    report = Report()
    code, top = git(Path(args.repo), "rev-parse", "--show-toplevel")
    if code != 0 or not top:
        report.emit("ERROR", "not a Git working tree")
        print(f"Summary: {report.errors} error(s), {report.warnings} warning(s).")
        return 1
    repo = Path(top)

    check_environment(report)
    email = check_identity(repo, report)

    remote = args.remote or default_remote(repo)
    urls: list[str] = []
    is_remote = False
    if remote is None:
        report.emit("ERROR", "no remote to push to: name one (REMOTE) or configure origin")
    else:
        urls, is_remote = push_urls(repo, remote)
        if not urls:
            report.emit("ERROR", f"remote {remote} not found")
        else:
            report.emit("INFO", f"remote {remote if is_remote else '(URL)'} pushes to {', '.join(redact(url) for url in urls)}")
    check_boundary(repo, urls, email, report)
    if not args.no_ssh and urls:
        check_ssh(repo, urls, report)
    if args.hook:
        check_hook_refs(repo, lines, report)
    elif remote is not None and urls:
        check_current_branch(repo, remote, is_remote, not args.no_fetch, report)

    print(f"Summary: {report.errors} error(s), {report.warnings} warning(s).")
    if report.errors:
        print("Push refused: fix the ERROR lines above; --no-verify is not a way around them." if args.hook
              else "Do not push before the ERROR lines above are fixed.")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
