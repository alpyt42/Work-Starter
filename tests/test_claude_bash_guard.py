"""Regression checks for the Claude Code Bash guard hook: direct Python, artifacts/ protection, Git hook bypass."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "tools/machine/hooks/claude-bash-guard.py"

PYTHON_MESSAGE = "Direct Python is not allowed"
ARTIFACTS_MESSAGE = "artifacts/ is protected"
HOOKS_MESSAGE = "Git hooks are the workspace guardrails"

PYTHON_BLOCKED = [
    "python x.py",
    "python3 x.py",
    "python3.12 x.py",
    "python2.7 x.py",
    "/usr/bin/python3 x.py",
    ".venv/bin/python x.py",
    "./venv/bin/python3.11 -m pytest",
    "~/tools/python3 x.py",
    "cd repos/demo && python3 x.py",
    "echo hi; python3 x.py",
    "echo hi || python3 x.py",
    "echo hi | python3 -c 'print(1)'",
    "(python3 x.py)",
    "echo $(python3 -c 'print(1)')",
    "echo `python3 x.py`",
    'echo "$(python3 x.py)"',
    "echo hi\npython3 x.py",
    "if true; then python3 x.py; fi",
    "for f in a b; do python3 $f; done",
    "if false; then echo a; else python3 x.py; fi",
    "while python3 x.py; do echo again; done",
    "{ python3 x.py; }",
    "! python3 x.py",
    "FOO=1 python3 x.py",
    "FOO=1 BAR='a b' python3 x.py",
    "env python3 x.py",
    "env -i FOO=1 python3 x.py",
    "env FOO=1 -- python3 x.py",
    "exec python3 x.py",
    "time python3 x.py",
    "nohup python3 x.py > out.log 2>&1 &",
    "ls *.txt | xargs -n1 python3",
    "xargs -I{} python3 {}",
    "sudo -u nobody python3 x.py",
    "sudo env FOO=1 python3 x.py",
    "command python3 x.py",
    "timeout 5 python3 x.py",
    "bash -c 'python3 x.py'",
    'sh -c "cd repos && python3 y.py"',
    'zsh -c "python3 x.py"',
    "bash -lc 'python3 x.py'",
    "eval 'python3 x.py'",
    "find . -name '*.py' -exec python3 {} \\;",
    "cat <<EOF | python3 -\nprint(1)\nEOF",
    "python3 <<EOF\nprint(1)\nEOF",
    "\\python3 x.py",
    '"python3" x.py',
    "$VENV/bin/python3 x.py",
    "function run { python3 x.py; }",
    "case $x in a) python3 x.py;; esac",
]

PYTHON_ALLOWED = [
    "uv run x.py",
    "uv run python x.py",
    "uv run python3 -c 'print(1)'",
    "uv run -m unittest",
    "uv run --with markdown-it-py==3.0.0 -m unittest discover -s tests",
    "FOO=1 uv run x.py",
    "time uv run x.py",
    "command -v python3",
    "command -v python3 || echo missing",
    "command -V python3",
    "which python3",
    "type python3",
    "grep python3 notes.txt",
    "grep -rn 'python3' tools",
    'echo "python3"',
    "echo python3 x.py",
    "echo 'a; python3 x.py'",
    'git commit -m "run python3 through uv"',
    'git commit -m "fix: x\n\npython3 leftovers"',
    "git commit -m \"$(cat <<'EOF'\nfeat: x\n\npython3 y.py\nEOF\n)\"",
    "echo hi # python3 x.py",
    "cat <<EOF > run.sh\npython3 x.py\nEOF",
    "cat > a.py <<'EOF'\n#!/usr/bin/env python3\nimport os\nEOF\nuv run a.py",
    "cat <<-EOF\n\tpython3 x.py\n\tEOF",
    "ls /usr/bin/python3",
    "ls python3 python/",
    "cd python3 && ls",
    "chmod +x python3",
    "man python3",
    "bash x.sh",
    "bash -c 'uv run x.py'",
    "uv run bash -c 'echo hi'",
    "xargs echo python3",
    "env | grep PYTHON",
    "PYTHON=python3 uv run x.py",
    "python3-config --help",
    "pythonista x",
    "for f in python3 python; do echo $f; done",
]

HOOKS_BLOCKED = [
    "git commit --no-verify -m x",
    "git commit -m x --no-verify",
    "git commit -n -m x",
    "git commit -m x -n",
    "git commit -nm x",
    "git commit -anm x",
    "git commit -a -n",
    "git commit --amend --no-edit -n",
    "git commit --no-verif -m x",
    "git push --no-verify",
    "git push origin main --no-verify",
    "git merge --no-verify topic",
    "git -c core.hooksPath=/dev/null commit -m x",
    "git -c core.hooksPath=/dev/null push",
    "git -c core.hookspath=/dev/null commit -m x",
    "git -c user.name=x -c core.hooksPath=/dev/null commit -m x",
    "git -C repos/demo commit --no-verify",
    "git --no-pager commit -n",
    "cd repos/demo && git commit -n -m x",
    "/usr/bin/git commit -n",
    "sudo git push --no-verify",
    'bash -c "git commit -n -m x"',
    "git commit -m \"$(cat <<'EOF'\nfeat: x\nEOF\n)\" --no-verify",
]

HOOKS_ALLOWED = [
    "git commit -m x",
    "git commit -am msg",
    "git commit --amend --no-edit",
    "git commit -F msg.txt",
    'git commit -m "fix -n handling"',
    'git commit -m "--no-verify"',
    "git commit -mn",
    "git commit -m -n",
    "git commit -- file -n",
    "git push",
    "git push -n",
    "git push --dry-run",
    "git push origin main",
    "git log -n 5",
    "git diff -n",
    "git status",
    "git -c user.name=x commit -m x",
    "git config user.name x",
    'echo "git commit -n"',
    "echo git push --no-verify",
    "grep -n no-verify README.md",
    "git commit -m x # --no-verify",
    "cat <<EOF\ngit commit --no-verify\nEOF",
]

# Commands run with cwd = the fictitious Work root and HOME = its parent.
ARTIFACTS_BLOCKED = [
    "rm artifacts/acme-report/deck.pptx",
    "rm -rf artifacts",
    "rm -rf artifacts/",
    "rm -rf ./artifacts/acme-report",
    "rm -rf -- artifacts/acme-report",
    "rm -rf artifacts/*",
    "rm -rf artifacts/acme-*",
    "rm -rf artifacts/{acme-report,notes}",
    "rm -rf {repos,artifacts}/x",
    "rm -rf Artifacts",
    "rm -rf artifacts/$NAME",
    "rm -rf *",
    "rm -rf ./*",
    "rm -rf .",
    "rm -rf ~/Work",
    "rm -rf ~/Work/",
    "rm -rf ~",
    "rm -rf ~/Work/*",
    "rm -rf ~/Work/art*",
    "rm -rf ~/Work/artifacts/acme-report",
    'rm -rf "$HOME/Work/artifacts"',
    "rm -rf ${HOME}/Work",
    "rm -rf @WORK@/artifacts/acme-report",
    "rm -rf /",
    "rm -rf repos/../artifacts/acme-report",
    "rm -rf agents/../artifacts",
    "/bin/rm -rf artifacts",
    "\\rm -rf artifacts",
    "command rm artifacts/x",
    "sudo rm -rf artifacts",
    "xargs rm -f artifacts/x",
    "bash -c 'rm -rf artifacts'",
    "echo a; rm -rf artifacts",
    "echo a && rm -rf artifacts",
    "cd artifacts && rm -rf acme-report",
    "cd artifacts; rm deck.pptx",
    "cd ~/Work/artifacts && rm x",
    "cd artifacts/acme-report && rm *",
    "cd artifacts && rm -rf .",
    "cd repos/demo && rm -rf ../../artifacts",
    "cd repos/demo && rm -rf ../..",
    "(cd artifacts && rm x)",
    "cd \"$(git rev-parse --show-toplevel)\" && rm -rf artifacts/x",
    "rmdir artifacts/acme-report",
    "unlink artifacts/acme-report/deck.pptx",
    "trash artifacts/acme-report",
    "shred -u artifacts/acme-report/deck.pptx",
    "git rm -r artifacts/acme-report",
    "git clean -fdx",
    "git clean -fd artifacts",
    "git -C artifacts clean -fd",
    "cd artifacts && git clean -fdx",
    "find artifacts -name '*.tmp' -delete",
    "find artifacts -type f -exec rm {} \\;",
    "find artifacts -type f -exec rm -f {} +",
    "find artifacts -name '*.tmp' -exec mv {} /tmp/ \\;",
    "find . -name '*.pyc' -delete",
    "find ~/Work -delete",
    "find -L artifacts -delete",
    "rsync -a --delete src/ artifacts/acme-report/",
    "rsync -a --delete-after src/ ~/Work/artifacts/",
    "rsync -a --remove-source-files artifacts/acme-report/ /tmp/out/",
    "mv artifacts/acme-report ~/Desktop/",
    "mv artifacts/acme-report /tmp/y",
    "mv artifacts/* repos/",
    "mv artifacts/acme-report artifacts/renamed",
    "mv artifacts/acme-report artifacts/",
    "mv -t repos artifacts/acme-report",
    "mv --target-directory=repos artifacts/acme-report",
    "mv artifacts/archive/old /tmp/",
    "mv ~/Work ~/Work-old",
    "mv artifacts/acme-report \"$DEST\"",
    "mv artifacts ~/Work/artifacts-old",
]

ARTIFACTS_ALLOWED = [
    "rm -rf agents/scratch",
    "rm repos/demo/x.txt",
    "rm -rf /tmp/foo",
    'rm "$f"',
    'rm -rf "$DIR"/x',
    "rm -rf $(ls)",
    "rm *.pyc",
    "rm -rf repos/*/node_modules",
    "rm -rf agents/artifacts",
    "rm -rf artifacts-old",
    "rm -rf ~/Downloads/x",
    "rm -rf ~/Work/agents/x",
    "rm -rf ~/Work/repos/demo",
    "rm -rf ./artifacts/../repos/demo/build",
    "rmdir agents/empty",
    "trash agents/scratch",
    "unlink repos/demo/link",
    "git rm repos/demo/x.txt",
    "git rm --cached notes.md",
    "git clean -n",
    "git clean -nfd",
    "git clean -fd repos/demo",
    "git -C repos/demo clean -fdx",
    "cd repos/demo && git clean -fdx",
    "cd repos/demo && rm -rf build",
    "cd agents && rm -rf scratch",
    "cd repos/demo && rm -rf ../../agents/x",
    "(cd artifacts && ls); rm agents/x",
    "echo $(cd artifacts && ls); rm agents/x",
    "ls artifacts",
    "cat artifacts/acme-report/deck.pptx",
    "cp -r artifacts/acme-report /tmp/copy",
    "echo \"rm -rf artifacts\"",
    "grep rm artifacts/notes.md",
    "cat <<EOF\nrm -rf artifacts\nEOF",
    "find repos -name '*.pyc' -delete",
    "find artifacts -name '*.pdf' -print",
    "find artifacts -type f -exec ls {} \\;",
    "find agents -exec rm {} \\;",
    "rsync -a src/ artifacts/acme-report/",
    "rsync -a --delete src/ repos/demo/",
    "rsync -a --delete src/ host:artifacts/",
    "mv agents/a agents/b",
    "mv repos/a repos/b",
    "mv ~/Downloads/report.pdf artifacts/",
    "mv x.pdf artifacts/acme-report/",
    "mv artifacts/acme-report artifacts/archive/",
    "mv artifacts/acme-report artifacts/archive/2026/acme-report",
    "mv artifacts/acme-report ~/Work/artifacts/archive/old/",
    "mv -t artifacts/archive artifacts/acme-report",
    "mv artifacts/archive/old artifacts/archive/older",
    "cd artifacts && mv acme-report archive/",
    "mv artifacts/* artifacts/archive/",
]

ARTIFACTS_OUTSIDE_WORK = [
    "rm -rf artifacts",
    "rm -rf artifacts/x",
    "mv artifacts/x /tmp/y",
    "find artifacts -delete",
]


class GuardTestCase(unittest.TestCase):
    """A fictitious Work root under a temporary HOME, and a runner for the hook."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls._tmp.name).resolve()
        cls.work = cls.home / "Work"
        (cls.work / "tools/machine").mkdir(parents=True)
        (cls.work / "tools/machine/work_config.py").write_text("# fictitious work root\n", encoding="utf-8")
        for folder in ("artifacts/acme-report", "artifacts/archive", "repos/demo", "agents", "brain"):
            (cls.work / folder).mkdir(parents=True)
        (cls.home / "elsewhere").mkdir()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def run_hook(self, command: object, cwd: Path | str | None = None, project_dir: Path | str | None = None, raw: str | None = None, tool: str | None = "Bash") -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        env["HOME"] = str(self.home)
        if project_dir is not None:
            env["CLAUDE_PROJECT_DIR"] = str(project_dir)
        if raw is None:
            payload: dict = {"tool_input": {"command": command}, "cwd": str(cwd or self.work)}
            if tool is not None:
                payload["tool_name"] = tool
            raw = json.dumps(payload)
        return subprocess.run([sys.executable, str(HOOK)], input=raw, env=env, capture_output=True, text=True)

    def assert_blocked(self, command: str, message: str, **kwargs: object) -> subprocess.CompletedProcess:
        result = self.run_hook(command, **kwargs)
        self.assertEqual(result.returncode, 2, f"not blocked: {command!r}\n{result.stderr}")
        self.assertIn(message, result.stderr, command)
        self.assertEqual(result.stdout, "")
        return result

    def assert_allowed(self, command: str, **kwargs: object) -> None:
        result = self.run_hook(command, **kwargs)
        self.assertEqual(result.returncode, 0, f"blocked: {command!r}\n{result.stderr}")
        self.assertEqual(result.stderr, "", command)
        self.assertEqual(result.stdout, "")

    def fill(self, command: str) -> str:
        return command.replace("@WORK@", str(self.work))


class NoDirectPythonTest(GuardTestCase):
    def test_python_in_command_position_is_blocked(self) -> None:
        for command in PYTHON_BLOCKED:
            with self.subTest(command=command):
                result = self.assert_blocked(command, PYTHON_MESSAGE)
                self.assertNotIn(ARTIFACTS_MESSAGE, result.stderr)
                self.assertNotIn(HOOKS_MESSAGE, result.stderr)

    def test_other_commands_and_mentions_are_allowed(self) -> None:
        for command in PYTHON_ALLOWED:
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_the_reason_names_the_uv_alternatives(self) -> None:
        result = self.assert_blocked("python3 x.py", "`uv run <script>`")
        self.assertIn("uv run python", result.stderr)
        self.assertIn("uv run -m", result.stderr)
        self.assertIn("AGENTS.md", result.stderr)


class ArtifactsProtectionTest(GuardTestCase):
    def test_deleting_or_moving_out_of_artifacts_is_blocked(self) -> None:
        for command in ARTIFACTS_BLOCKED:
            with self.subTest(command=command):
                result = self.assert_blocked(self.fill(command), ARTIFACTS_MESSAGE)
                self.assertNotIn(PYTHON_MESSAGE, result.stderr)
                self.assertNotIn(HOOKS_MESSAGE, result.stderr)

    def test_everything_else_is_allowed(self) -> None:
        for command in ARTIFACTS_ALLOWED:
            with self.subTest(command=command):
                self.assert_allowed(self.fill(command))

    def test_the_reason_points_to_archive_and_the_owner(self) -> None:
        result = self.assert_blocked("rm -rf artifacts", "artifacts/archive/")
        self.assertIn("never deletes or moves anything out of artifacts/", result.stderr)
        self.assertIn("ask the owner", result.stderr)

    def test_work_root_found_from_a_parent_of_cwd(self) -> None:
        cwd = self.work / "repos/demo"
        self.assert_blocked("rm -rf ../../artifacts/acme-report", ARTIFACTS_MESSAGE, cwd=cwd)
        self.assert_blocked("rm -rf ../..", ARTIFACTS_MESSAGE, cwd=cwd)
        self.assert_blocked("mv ../../artifacts/acme-report /tmp/y", ARTIFACTS_MESSAGE, cwd=cwd)
        self.assert_allowed("rm -rf build", cwd=cwd)
        self.assert_allowed("mv ../../artifacts/acme-report ../../artifacts/archive/", cwd=cwd)

    def test_cwd_inside_artifacts_protects_relative_paths(self) -> None:
        cwd = self.work / "artifacts/acme-report"
        self.assert_blocked("rm deck.pptx", ARTIFACTS_MESSAGE, cwd=cwd)
        self.assert_blocked("rm -rf *", ARTIFACTS_MESSAGE, cwd=cwd)
        self.assert_blocked("rm -rf ..", ARTIFACTS_MESSAGE, cwd=cwd)
        self.assert_blocked("mv deck.pptx /tmp/", ARTIFACTS_MESSAGE, cwd=cwd)
        self.assert_allowed("mv deck.pptx ../archive/", cwd=cwd)
        self.assert_allowed("ls", cwd=cwd)

    def test_claude_project_dir_defines_the_work_root(self) -> None:
        elsewhere = self.home / "elsewhere"
        absolute = f"rm -rf {self.work}/artifacts/acme-report"
        self.assert_blocked(absolute, ARTIFACTS_MESSAGE, cwd=elsewhere, project_dir=self.work)
        self.assert_blocked(f"cd {self.work} && rm -rf artifacts", ARTIFACTS_MESSAGE, cwd=elsewhere, project_dir=self.work)
        self.assert_blocked("rm -rf $CLAUDE_PROJECT_DIR/artifacts/x", ARTIFACTS_MESSAGE, cwd=elsewhere, project_dir=self.work)
        # Relative to a cwd that is not the Work root, `artifacts` is another folder.
        self.assert_allowed("rm -rf artifacts/x", cwd=elsewhere, project_dir=self.work)
        # Without the variable and outside any Work root, nothing is protected.
        self.assert_allowed(absolute, cwd=elsewhere)

    def test_claude_project_dir_wins_over_the_parent_search(self) -> None:
        other = self.home / "other-work"
        (other / "artifacts").mkdir(parents=True)
        self.assert_allowed(f"rm -rf {other}/artifacts", cwd=self.work / "repos/demo", project_dir=self.work)
        self.assert_blocked(f"rm -rf {other}/artifacts", ARTIFACTS_MESSAGE, cwd=self.work / "repos/demo", project_dir=other)

    def test_outside_any_work_root_nothing_is_protected(self) -> None:
        for command in ARTIFACTS_OUTSIDE_WORK:
            with self.subTest(command=command):
                self.assert_allowed(command, cwd=self.home / "elsewhere")

    def test_symlinked_artifacts_is_still_protected(self) -> None:
        work = self.home / "linked-work"
        (work / "tools/machine").mkdir(parents=True)
        (work / "tools/machine/work_config.py").write_text("# fictitious\n", encoding="utf-8")
        (self.home / "synced-artifacts").mkdir()
        (work / "artifacts").symlink_to(self.home / "synced-artifacts")
        self.assert_blocked("rm -rf artifacts/x", ARTIFACTS_MESSAGE, cwd=work)
        self.assert_blocked(f"rm -rf {self.home}/synced-artifacts/x", ARTIFACTS_MESSAGE, cwd=work)
        self.assert_blocked("rm -rf ~/linked-work", ARTIFACTS_MESSAGE, cwd=work)
        self.assert_allowed("rm -rf repos/x", cwd=work)


class NoHookBypassTest(GuardTestCase):
    def test_bypassing_the_git_hooks_is_blocked(self) -> None:
        for command in HOOKS_BLOCKED:
            with self.subTest(command=command):
                result = self.assert_blocked(command, HOOKS_MESSAGE)
                self.assertNotIn(PYTHON_MESSAGE, result.stderr)
                self.assertNotIn(ARTIFACTS_MESSAGE, result.stderr)

    def test_ordinary_git_commands_are_allowed(self) -> None:
        for command in HOOKS_ALLOWED:
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_the_reason_asks_to_fix_what_the_hooks_report(self) -> None:
        result = self.assert_blocked("git commit -n -m x", "fix what they report instead")
        self.assertIn("guardrails", result.stderr)


class SeveralRulesTest(GuardTestCase):
    def test_all_reasons_are_reported_in_one_paragraph(self) -> None:
        result = self.assert_blocked("python3 x.py; rm -rf artifacts; git commit -n -m x", PYTHON_MESSAGE)
        for message in (PYTHON_MESSAGE, ARTIFACTS_MESSAGE, HOOKS_MESSAGE):
            self.assertEqual(result.stderr.count(message), 1)
        self.assertEqual(result.stderr.count("\n"), 1)  # one paragraph, one trailing newline

    def test_two_rules_in_one_command(self) -> None:
        result = self.assert_blocked("git push --no-verify && python3 x.py", HOOKS_MESSAGE)
        self.assertIn("Direct Python is not allowed", result.stderr)
        self.assertNotIn(ARTIFACTS_MESSAGE, result.stderr)

    def test_a_blocked_command_after_an_allowed_one_is_still_blocked(self) -> None:
        self.assert_blocked("uv run a.py && echo ok\nrm -rf artifacts", ARTIFACTS_MESSAGE)


class RobustnessTest(GuardTestCase):
    def test_unreadable_input_exits_zero(self) -> None:
        for raw in ("", "not json", "{", "[]", "null", "42", '"python3 x"', "{}", '{"tool_name":"Bash"}', '{"tool_name":"Bash","tool_input":null}', '{"tool_name":"Bash","tool_input":{"command":123}}', '{"tool_name":"Bash","tool_input":{"command":""}}', '{"tool_name":"Bash","tool_input":{"command":"   "}}'):
            with self.subTest(raw=raw):
                result = self.run_hook(None, raw=raw)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertLess(len(result.stderr), 200)

    def test_missing_cwd_does_not_break_the_hook(self) -> None:
        raw = json.dumps({"tool_name": "Bash", "tool_input": {"command": "python3 x.py"}})
        result = self.run_hook(None, raw=raw)
        self.assertEqual(result.returncode, 2)
        raw = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": 12})
        self.assertEqual(self.run_hook(None, raw=raw).returncode, 0)

    def test_other_tools_are_ignored(self) -> None:
        for tool in ("Write", "Read", "Edit", "mcp__server__run", "bash"):
            with self.subTest(tool=tool):
                self.assert_allowed("python3 x.py; rm -rf artifacts; git commit -n", tool=tool)

    def test_a_payload_without_tool_name_is_still_checked(self) -> None:
        self.assert_blocked("python3 x.py", PYTHON_MESSAGE, tool=None)

    def test_malformed_shell_never_crashes(self) -> None:
        for command in ('echo "abc', "echo 'abc", "echo $(", "echo `abc", "echo ${abc", "echo $((1+", "cat <<EOF\nabc", "cat <<", "echo > ", "echo )", "(((", "\\", "$", "$'abc", "echo a\\", "\0\0", "rm", "mv", "mv a", "find", "git", "git -c", "git -C", "git commit -", "rsync", "cd", "bash -c", "eval", "env", "sudo", "timeout"):
            with self.subTest(command=command):
                result = self.run_hook(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")

    def test_deeply_nested_input_is_survived(self) -> None:
        for command in ("$(" * 400 + ")" * 400, "bash -c '" + "bash -c " * 50 + "x'", "echo " + "{a,b}" * 40 + " x"):
            with self.subTest(command=command[:30]):
                result = self.run_hook(command)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_hit_survives_a_nested_command_with_no_effect(self) -> None:
        self.assert_blocked("echo $(echo $(echo `python3 x.py`))", PYTHON_MESSAGE)

    def test_hook_is_fast(self) -> None:
        command = "cd repos/demo && git status && uv run x.py | grep -n foo; rm -rf agents/scratch"
        self.run_hook(command)  # warm the file cache
        start = time.perf_counter()
        for _ in range(100):
            self.assertEqual(self.run_hook(command).returncode, 0)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed / 100, 0.1, f"{elapsed / 100 * 1000:.0f} ms per run")


if __name__ == "__main__":
    unittest.main()
