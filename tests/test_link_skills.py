"""Tests for link-skills.sh and sync-house-skills.py on a temporary workspace with two brains.

link-skills.sh calls `uv run`, so these tests are skipped when uv is missing. No network, no npx.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
MACHINE = REPO / "tools/machine"
MARKER = ".generated-from-brain-skill"
LEGACY_MARKER = ".generated-from-skills-new-project"


def third_party_entry(name: str) -> dict[str, str]:
    return {"source": f"example/{name}", "sourceType": "github", "skillPath": f"{name}/SKILL.md", "computedHash": "abc"}


@unittest.skipUnless(shutil.which("uv") and shutil.which("bash"), "uv and bash are required")
class LinkSkillsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "tools/machine").mkdir(parents=True)
        for name in ("link-skills.sh", "work_config.py", "sync-house-skills.py"):
            shutil.copy(MACHINE / name, self.root / "tools/machine" / name)
        self.env = {**os.environ, "WORK_DIR": str(self.root)}
        self.make_skill("brain", "alpha")
        self.make_skill("brain-perso", "beta")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_skill(self, brain: str, name: str, copy: bool = False) -> Path:
        (self.root / brain / ".data").mkdir(parents=True, exist_ok=True)
        (self.root / brain / "AGENTS.md").write_text("# brain\n", encoding="utf-8")
        skill = self.root / brain / "skills" / name
        (skill / "scripts").mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        (skill / "scripts/run.sh").write_text("echo hi\n", encoding="utf-8")
        if copy:
            (skill / ".install-as-copy").write_text("", encoding="utf-8")
        return skill

    def write_local(self, disabled: list[str] = (), third_party: dict | None = None) -> None:
        config = {"version": 1, "skills": {"disabled": list(disabled), "thirdParty": third_party or {}}}
        (self.root / "work-config.local.json").write_text(json.dumps(config), encoding="utf-8")

    def link_skills(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.root / "tools/machine/link-skills.sh")], env=self.env, capture_output=True, text=True
        )

    def sync(self, *args: str) -> subprocess.CompletedProcess[str]:
        script = self.root / "tools/machine/sync-house-skills.py"
        return subprocess.run([sys.executable, str(script), *args], env=self.env, capture_output=True, text=True)

    def ok(self, result: subprocess.CompletedProcess[str]) -> subprocess.CompletedProcess[str]:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def fails(self, result: subprocess.CompletedProcess[str]) -> str:
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stderr

    def link(self, agent: str, name: str) -> Path:
        return self.root / agent / "skills" / name

    def names(self, agent: str) -> list[str]:
        folder = self.root / agent / "skills"
        return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []

    def test_own_skills_of_every_brain_are_linked_for_both_agents(self) -> None:
        self.ok(self.link_skills())
        for agent in (".agents", ".claude"):
            for brain, name in (("brain", "alpha"), ("brain-perso", "beta")):
                link = self.link(agent, name)
                self.assertTrue(link.is_symlink(), link)
                self.assertEqual(os.readlink(link), f"../../{brain}/skills/{name}")
                self.assertTrue((link / "SKILL.md").is_file())
        self.ok(self.link_skills())  # idempotent

    def test_name_collision_between_brains_stops_with_both_paths(self) -> None:
        self.make_skill("brain-perso", "alpha")
        error = self.fails(self.link_skills())
        self.assertIn("brain/skills/alpha", error)
        self.assertIn("brain-perso/skills/alpha", error)
        self.assertEqual(self.names(".claude"), [])

    def test_disabled_skill_is_not_exposed_and_its_managed_link_is_removed(self) -> None:
        self.ok(self.link_skills())
        self.write_local(disabled=["beta"])
        self.ok(self.link_skills())
        for agent in (".agents", ".claude"):
            self.assertEqual(self.names(agent), ["alpha"])
        self.write_local()
        self.ok(self.link_skills())
        self.assertEqual(self.names(".claude"), ["alpha", "beta"])

    def test_link_of_a_removed_skill_or_brain_is_cleaned_up(self) -> None:
        self.ok(self.link_skills())
        shutil.rmtree(self.root / "brain/skills/alpha")
        shutil.rmtree(self.root / "brain-perso")
        self.ok(self.link_skills())
        self.assertEqual(self.names(".agents"), [])
        self.assertEqual(self.names(".claude"), [])

    def test_link_into_a_renamed_brain_or_another_brain_is_replaced(self) -> None:
        self.ok(self.link_skills())
        (self.root / "brain").rename(self.root / "brain-initech")
        shutil.move(self.root / "brain-perso/skills/beta", self.root / "brain-initech/skills/beta")
        self.ok(self.link_skills())
        for agent in (".agents", ".claude"):
            for name in ("alpha", "beta"):
                self.assertEqual(os.readlink(self.link(agent, name)), f"../../brain-initech/skills/{name}")
                self.assertTrue((self.link(agent, name) / "SKILL.md").is_file())

    def test_unmanaged_paths_are_refused_or_left_alone(self) -> None:
        self.link(".claude", "alpha").mkdir(parents=True)
        self.assertIn("Conflicting skill path", self.fails(self.link_skills()))

        shutil.rmtree(self.link(".claude", "alpha"))
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (self.link(".claude", "mine")).symlink_to(elsewhere)
        self.ok(self.link_skills())
        self.assertTrue(self.link(".claude", "mine").is_symlink())

    def test_copy_skill_is_a_real_copy_made_by_sync_and_checked(self) -> None:
        source = self.make_skill("brain", "gamma", copy=True)
        self.ok(self.link_skills())
        self.assertEqual(self.names(".claude"), ["alpha", "beta"])  # no link for a copy skill

        self.ok(self.sync())
        for agent in (".agents", ".claude"):
            copy = self.link(agent, "gamma")
            self.assertTrue(copy.is_dir() and not copy.is_symlink())
            self.assertIn("brain/skills/gamma", (copy / MARKER).read_text(encoding="utf-8"))
            self.assertEqual((copy / "scripts/run.sh").read_text(encoding="utf-8"), "echo hi\n")
        self.ok(self.sync("--check"))
        self.ok(self.link_skills())  # leaves generated copies alone

        (source / "SKILL.md").write_text("# gamma, edited\n", encoding="utf-8")
        self.assertIn("missing or stale", self.fails(self.sync("--check")))
        self.ok(self.sync())
        self.ok(self.sync("--check"))
        self.assertEqual((self.link(".claude", "gamma") / "SKILL.md").read_text(encoding="utf-8"), "# gamma, edited\n")

    def test_stale_generated_copies_are_removed_but_foreign_directories_are_not(self) -> None:
        self.make_skill("brain", "gamma", copy=True)
        self.ok(self.sync())
        self.write_local(disabled=["gamma"])
        self.assertIn("Obsolete generated skill copy", self.fails(self.sync("--check")))
        self.ok(self.sync())
        self.assertEqual(self.names(".agents"), [])

        (self.link(".agents", "own-by-hand")).mkdir(parents=True)
        (self.link(".agents", "own-by-hand") / "SKILL.md").write_text("# mine\n", encoding="utf-8")
        self.ok(self.sync())
        self.assertTrue((self.link(".agents", "own-by-hand") / "SKILL.md").is_file())

    def test_copy_skill_never_replaces_a_non_generated_directory(self) -> None:
        self.make_skill("brain", "gamma", copy=True)
        self.link(".claude", "gamma").mkdir(parents=True)
        self.assertIn("non-generated", self.fails(self.sync()))

    def test_switching_between_link_and_copy_in_both_directions(self) -> None:
        marker = self.root / "brain/skills/alpha/.install-as-copy"
        self.ok(self.link_skills())
        self.assertTrue(self.link(".claude", "alpha").is_symlink())

        marker.write_text("", encoding="utf-8")  # link -> copy
        self.ok(self.sync())
        self.ok(self.link_skills())
        self.assertFalse(self.link(".claude", "alpha").is_symlink())
        self.assertTrue((self.link(".claude", "alpha") / MARKER).is_file())

        marker.unlink()  # copy -> link
        self.ok(self.sync())
        self.ok(self.link_skills())
        self.assertTrue(self.link(".claude", "alpha").is_symlink())

    def test_third_party_skills_are_linked_for_claude_and_disabled_ones_are_set_aside(self) -> None:
        self.write_local(third_party={"tp": third_party_entry("tp")})
        self.assertIn("Missing installed skill: tp", self.fails(self.link_skills()))

        installed = self.link(".agents", "tp")  # what `npx skills experimental_install` leaves
        installed.mkdir(parents=True)
        (installed / "SKILL.md").write_text("# tp\n", encoding="utf-8")
        self.ok(self.link_skills())
        self.assertEqual(os.readlink(self.link(".claude", "tp")), "../../.agents/skills/tp")

        self.write_local(disabled=["tp"], third_party={"tp": third_party_entry("tp")})
        self.ok(self.link_skills())
        self.assertFalse(self.link(".claude", "tp").exists() or self.link(".claude", "tp").is_symlink())
        self.assertTrue((self.root / ".agents/skills-disabled/tp/SKILL.md").is_file())

    def install_third_party(self, name: str, text: str) -> Path:
        installed = self.link(".agents", name)  # what `npx skills experimental_install` leaves
        installed.mkdir(parents=True, exist_ok=True)
        (installed / "SKILL.md").write_text(text, encoding="utf-8")
        return installed

    def test_third_party_skill_re_enabled_offline_comes_back_from_the_set_aside_copy(self) -> None:
        entry = {"tp": third_party_entry("tp")}
        installed = self.install_third_party("tp", "# tp\n")
        self.write_local(disabled=["tp"], third_party=entry)
        self.ok(self.link_skills())
        self.assertFalse(installed.exists())

        self.write_local(third_party=entry)  # re-enabled, no npx run in between
        self.ok(self.link_skills())
        self.assertEqual((installed / "SKILL.md").read_text(encoding="utf-8"), "# tp\n")
        self.assertFalse((self.root / ".agents/skills-disabled/tp").exists())
        self.assertEqual(os.readlink(self.link(".claude", "tp")), "../../.agents/skills/tp")

        self.write_local(third_party={"other": third_party_entry("other")})  # still missing when nothing is set aside
        self.assertIn("Missing installed skill: other", self.fails(self.link_skills()))

    def test_third_party_skill_disabled_a_second_time_replaces_the_old_set_aside_copy(self) -> None:
        entry = {"tp": third_party_entry("tp")}
        self.install_third_party("tp", "# tp, first\n")
        self.write_local(disabled=["tp"], third_party=entry)
        self.ok(self.link_skills())

        self.write_local(third_party=entry)  # re-enabled, then reinstalled by npx
        self.install_third_party("tp", "# tp, second\n")
        self.ok(self.link_skills())
        self.write_local(disabled=["tp"], third_party=entry)
        self.ok(self.link_skills())  # used to fail with "Disabled skill backup already exists"
        self.assertEqual((self.root / ".agents/skills-disabled/tp/SKILL.md").read_text(encoding="utf-8"), "# tp, second\n")
        self.assertFalse(self.link(".agents", "tp").exists())

    def test_links_of_the_previous_layout_are_replaced_or_removed(self) -> None:
        (self.root / "skills/alpha").mkdir(parents=True)  # the old target may still exist, or not
        (self.root / "skills/alpha/SKILL.md").write_text("# old alpha\n", encoding="utf-8")
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        for agent in (".agents", ".claude"):
            (self.root / agent / "skills").mkdir(parents=True)
            self.link(agent, "alpha").symlink_to("../../skills/alpha")  # enabled again: replaced
            self.link(agent, "beta").symlink_to("../../skills/beta")  # target gone: replaced
            self.link(agent, "gone").symlink_to("../../skills/gone")  # no longer enabled: removed
            self.link(agent, "mine").symlink_to("../../skills/other")  # not the pattern of a managed link
            self.link(agent, "theirs").symlink_to(elsewhere)
        self.ok(self.link_skills())
        for agent in (".agents", ".claude"):
            self.assertEqual(os.readlink(self.link(agent, "alpha")), "../../brain/skills/alpha")
            self.assertEqual(os.readlink(self.link(agent, "beta")), "../../brain-perso/skills/beta")
            self.assertTrue((self.link(agent, "beta") / "SKILL.md").is_file())
            self.assertFalse(self.link(agent, "gone").is_symlink())
            self.assertTrue(self.link(agent, "mine").is_symlink() and self.link(agent, "theirs").is_symlink())
        self.ok(self.link_skills())  # idempotent

    def write_legacy_copy(self, agent: str, name: str, marker: str = LEGACY_MARKER) -> Path:
        copy = self.link(agent, name)
        copy.mkdir(parents=True)
        (copy / "SKILL.md").write_text("# old copy\n", encoding="utf-8")
        if marker:
            (copy / marker).write_text("generated by the previous layout\n", encoding="utf-8")
        return copy

    def test_copy_made_by_the_previous_layout_is_replaced_by_the_current_copy(self) -> None:
        self.make_skill("brain", "new-project", copy=True)
        for agent in (".agents", ".claude"):
            self.write_legacy_copy(agent, "new-project")
        self.assertIn("missing or stale", self.fails(self.sync("--check")))
        self.ok(self.sync())
        for agent in (".agents", ".claude"):
            copy = self.link(agent, "new-project")
            self.assertTrue((copy / MARKER).is_file())
            self.assertFalse((copy / LEGACY_MARKER).exists())
            self.assertEqual((copy / "SKILL.md").read_text(encoding="utf-8"), "# new-project\n")
        self.ok(self.sync("--check"))

    def test_any_marker_of_the_previous_layout_counts_as_a_generated_copy(self) -> None:
        self.make_skill("brain", "other", copy=True)
        for agent in (".agents", ".claude"):
            self.write_legacy_copy(agent, "other", marker=".generated-from-skills-other")
        self.ok(self.sync())
        for agent in (".agents", ".claude"):
            copy = self.link(agent, "other")
            self.assertTrue((copy / MARKER).is_file())
            self.assertFalse((copy / ".generated-from-skills-other").exists())

    def test_link_of_the_previous_layout_is_replaced_by_the_current_copy(self) -> None:
        self.make_skill("brain", "new-project", copy=True)
        for agent in (".agents", ".claude"):
            (self.root / agent / "skills").mkdir(parents=True)
            self.link(agent, "new-project").symlink_to("../../skills/new-project")
        self.ok(self.sync())
        self.ok(self.link_skills())
        for agent in (".agents", ".claude"):
            copy = self.link(agent, "new-project")
            self.assertTrue(copy.is_dir() and not copy.is_symlink())
            self.assertTrue((copy / MARKER).is_file())

    def test_legacy_copy_of_a_skill_that_is_now_linked_or_gone_is_removed_not_refused(self) -> None:
        self.make_skill("brain", "new-project")  # linked now, no longer a copy
        for agent in (".agents", ".claude"):
            self.write_legacy_copy(agent, "new-project")
            self.write_legacy_copy(agent, "retired")
            self.write_legacy_copy(agent, "by-hand", marker="")  # no marker: never touched
        self.assertIn("Obsolete generated skill copy", self.fails(self.sync("--check")))
        self.ok(self.sync())
        self.ok(self.link_skills())
        for agent in (".agents", ".claude"):
            self.assertEqual(os.readlink(self.link(agent, "new-project")), "../../brain/skills/new-project")
            self.assertFalse(self.link(agent, "retired").exists())
            self.assertTrue((self.link(agent, "by-hand") / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
