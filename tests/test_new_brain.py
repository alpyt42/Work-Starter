"""Regression checks for the blank-brain generator (no network, no real brain)."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools/brain/new-brain.py"
CHECK_LINKS = REPO / "tools/brain/check-links.py"
SEED = REPO / "kit/brain/seed"
EMPTY_BOUNDARY = {"version": 1, "scope": "", "description": "", "remote": "", "email": "", "allow": []}


class NewBrainTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name).resolve() / "Work"
        self.work.mkdir()
        # A brain reads the shared conventions and tools from its Work root.
        (self.work / "kit").symlink_to(REPO / "kit")
        (self.work / "tools").symlink_to(REPO / "tools")
        self.env = {**os.environ, "WORK_DIR": str(self.work)}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TOOL), *args], env=self.env, capture_output=True, text=True)

    def test_creates_brain_with_only_private_files(self) -> None:
        result = self.run_tool("brain")
        self.assertEqual(result.returncode, 0, result.stderr)
        brain = self.work / "brain"
        for path in ("AGENTS.md", "CLAUDE.md", "tasks.md", "inbox/inbox.md", "me/about-me.md",
                     ".data/doctor.json", "docs/LOCAL-WORKFLOWS.md", "projects/internal/setup/state/actions.md"):
            self.assertTrue((brain / path).is_file(), path)
        # Conventions and templates are read from kit/brain/, never copied.
        self.assertEqual(sorted(p.name for p in (brain / "docs").iterdir()), ["LOCAL-WORKFLOWS.md"])
        self.assertFalse((brain / "templates").exists())

    def test_scopes_placeholders_to_the_brain_name(self) -> None:
        self.assertEqual(self.run_tool("brain-perso").returncode, 0)
        brain = self.work / "brain-perso"
        leftovers = [str(p.relative_to(brain)) for p in brain.rglob("*")
                     if p.is_file() and ".git" not in p.parts and "{{BRAIN}}" in p.read_text(encoding="utf-8")]
        self.assertEqual(leftovers, [])
        tasks = (brain / "tasks.md").read_text(encoding="utf-8")
        self.assertIn(r"^brain-perso\/projects\/", tasks)
        self.assertNotIn(r"^brain\/projects\/", tasks)

    def test_initialises_git_without_commit_or_remote(self) -> None:
        self.assertEqual(self.run_tool("brain").returncode, 0)
        brain = self.work / "brain"
        self.assertTrue((brain / ".git").is_dir())
        self.assertNotEqual(subprocess.run(["git", "rev-parse", "HEAD"], cwd=brain, capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run(["git", "remote"], cwd=brain, capture_output=True, text=True).stdout, "")

    def test_no_git_option(self) -> None:
        self.assertEqual(self.run_tool("brain", "--no-git").returncode, 0)
        self.assertFalse((self.work / "brain/.git").exists())

    def test_refuses_existing_folder_and_bad_name(self) -> None:
        (self.work / "brain").mkdir()
        (self.work / "brain/keep.md").write_text("x", encoding="utf-8")
        result = self.run_tool("brain")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([p.name for p in (self.work / "brain").iterdir()], ["keep.md"])
        self.assertNotEqual(self.run_tool("notes").returncode, 0)
        self.assertFalse((self.work / "notes").exists())

    def test_links_of_a_new_brain_resolve(self) -> None:
        self.assertEqual(self.run_tool("brain").returncode, 0)
        env = {**os.environ, "BRAIN_DIR": str(self.work / "brain")}
        result = subprocess.run([sys.executable, str(CHECK_LINKS)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_seed_declares_boundary_skills_and_work_config(self) -> None:
        self.assertEqual(self.run_tool("brain-perso").returncode, 0)
        brain = self.work / "brain-perso"
        self.assertEqual(json.loads((brain / ".data/brain.json").read_text(encoding="utf-8")), EMPTY_BOUNDARY)
        self.assertEqual(
            json.loads((brain / ".data/work-config.json").read_text(encoding="utf-8")),
            {"version": 1, "skills": {"thirdParty": {}, "disabled": []}},
        )
        readme = (brain / "skills/README.md").read_text(encoding="utf-8")
        for expected in ("SKILL.md", "scripts/", "references/", "assets/", ".install-as-copy",
                         ".data/work-config.json", "tools/machine/update.sh",
                         "uv run tools/machine/work_config.py adopt --brain <brain>"):
            self.assertIn(expected, readme)
        data_readme = (brain / ".data/README.md").read_text(encoding="utf-8")
        for expected in ("brain.json", "work-config.json"):
            self.assertIn(f"| `{expected}` |", data_readme)

    def test_seed_skills_readme_gives_a_way_to_find_the_work_root_that_survives_moves_and_links(self) -> None:
        readme = (SEED / "skills/README.md").read_text(encoding="utf-8")
        self.assertIn("tools/machine/work_config.py", readme)
        self.assertIn("WORK_DIR", readme)
        snippet = re.search(r"```python\n(.*?)```", readme, re.S).group(1)
        self.assertLessEqual(len([line for line in snippet.splitlines() if line.strip()]), 8)  # stays a short snippet
        self.assertNotIn("parents[", snippet)  # never a fixed depth

        self.assertEqual(self.run_tool("brain-perso").returncode, 0)
        script = self.work / "brain-perso/skills/demo/scripts/probe.py"
        script.parent.mkdir(parents=True)
        script.write_text(snippet + "print(work, brain, tools, sep='\\n')\n", encoding="utf-8")
        (self.work / "brain-perso/skills/demo/SKILL.md").write_text("# demo\n", encoding="utf-8")
        (self.work / ".claude/skills").mkdir(parents=True)
        (self.work / ".claude/skills/demo").symlink_to("../../brain-perso/skills/demo")

        def probe(path: Path, **extra: str) -> list[str]:
            env = {key: value for key, value in os.environ.items() if key not in ("WORK_DIR", "BRAIN_DIR")}
            result = subprocess.run([sys.executable, str(path)], env={**env, **extra}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.splitlines()

        expected = [str(self.work), str(self.work / "brain-perso"), str(self.work / "tools")]
        self.assertEqual(probe(script), expected)  # from the brain that holds the script
        self.assertEqual(probe(self.work / ".claude/skills/demo/scripts/probe.py"), expected)  # through the agent link
        elsewhere = self.work.parent / "Elsewhere"
        self.assertEqual(probe(script, WORK_DIR=str(elsewhere))[0], str(elsewhere))
        self.assertEqual(probe(script, BRAIN_DIR=str(self.work / "brain-initech"))[1], str(self.work / "brain-initech"))
        copy = self.work / ".claude/skills/copied/scripts/probe.py"  # a skill installed as a copy, outside its brain
        copy.parent.mkdir(parents=True)
        copy.write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
        self.assertEqual(probe(copy)[1], str(self.work / "brain"))
        # Outside a Work and without WORK_DIR: a clear message, not a traceback.
        stray = self.work.parent / "stray/probe.py"
        stray.parent.mkdir()
        stray.write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
        env = {key: value for key, value in os.environ.items() if key not in ("WORK_DIR", "BRAIN_DIR")}
        result = subprocess.run([sys.executable, str(stray)], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WORK_DIR", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_seed_ships_no_employer_tooling(self) -> None:
        self.assertEqual(self.run_tool("brain").returncode, 0)
        brain = self.work / "brain"
        for leftover in (".data/boond-mapping.json", ".data/toggl-projects-plan.json", ".data/brands"):
            self.assertFalse((brain / leftover).exists(), leftover)
        pattern = re.compile(r"boond|toggl|brand", re.IGNORECASE)
        hits = [str(p.relative_to(SEED)) for p in SEED.rglob("*")
                if p.is_file() and (pattern.search(p.read_text(encoding="utf-8")) or pattern.search(str(p.relative_to(SEED))))]
        self.assertEqual(hits, [])

    def test_seed_gitignore_keeps_local_caches_out_of_the_brain(self) -> None:
        self.assertEqual(self.run_tool("brain").returncode, 0)
        brain = self.work / "brain"

        def ignored(relative: str) -> bool:
            (brain / relative).parent.mkdir(parents=True, exist_ok=True)
            (brain / relative).write_text("x\n", encoding="utf-8")
            env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}  # no personal excludes
            return subprocess.run(["git", "check-ignore", "-q", relative], cwd=brain, env=env).returncode == 0

        for cache in (".cache/state.json", ".data/projects.cache.json", ".data/.projects-cache.json", ".data/sub/x.cache.json"):
            self.assertTrue(ignored(cache), cache)
        for versioned in (".data/doctor.json", ".data/work-config.json", ".data/transcripts.json", "skills/README.md"):
            self.assertFalse(ignored(versioned), versioned)

    def test_boundary_options_fill_brain_json(self) -> None:
        result = self.run_tool("brain-asso", "--scope", "asso", "--description", "Association data; never any client.",
                               "--remote", "git@github.com:asso/*", "--email", "*@asso.org")
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = (self.work / "brain-asso/.data/brain.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(raw), {
            "version": 1, "scope": "asso", "description": "Association data; never any client.",
            "remote": "git@github.com:asso/*", "email": "*@asso.org", "allow": [],
        })
        self.assertEqual(raw, json.dumps(json.loads(raw), indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        self.assertEqual(list(json.loads(raw)), sorted(json.loads(raw)))

    def test_partial_boundary_options_keep_the_other_fields_empty(self) -> None:
        self.assertEqual(self.run_tool("brain-perso", "--scope", "personal").returncode, 0)
        declared = json.loads((self.work / "brain-perso/.data/brain.json").read_text(encoding="utf-8"))
        self.assertEqual(declared, {**EMPTY_BOUNDARY, "scope": "personal"})

    def test_no_boundary_option_keeps_the_seed_file(self) -> None:
        self.assertEqual(self.run_tool("brain").returncode, 0)
        self.assertEqual((self.work / "brain/.data/brain.json").read_bytes(), (SEED / ".data/brain.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
