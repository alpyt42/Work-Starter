"""Regression checks for the read-only machine doctor: workspace, skill configuration, brain boundaries (no network)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "tools/machine/doctor.py"
WORK_CONFIG = Path(__file__).resolve().parents[1] / "tools/machine/work_config.py"


def third_party_entry(name: str) -> dict:
    return {"source": f"example/{name}", "sourceType": "github", "skillPath": f"{name}/SKILL.md", "computedHash": "abc"}


class MachineDoctorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name).resolve()
        self.work = self.home / "Work"
        (self.home / "inbox/transcripts").mkdir(parents=True)
        for repo in (self.work, self.work / "brain"):
            repo.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (self.work / "brain/AGENTS.md").write_text("# test\n", encoding="utf-8")
        (self.work / "brain/.data").mkdir()
        (self.work / "artifacts").mkdir()
        self.write_config({"transcripts_dir": "inbox/transcripts", "recordings_dir": "inbox/missing", "brains": ["brain"]})
        self.env = {**os.environ, "WORK_DIR": str(self.work), "HOME": str(self.home)}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_config(self, config: dict) -> None:
        (self.work / "brain/.data/local-paths.json").write_text(json.dumps(config), encoding="utf-8")

    def run_doctor(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TOOL)], env=self.env, capture_output=True, text=True)

    def work_config(self, command: str) -> None:
        result = subprocess.run([sys.executable, str(WORK_CONFIG), command], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def write_local(self, value: object) -> None:
        (self.work / "work-config.local.json").write_text(json.dumps(value), encoding="utf-8")

    def write_brain_json(self, brain: str = "brain", **fields: str) -> None:
        data = {"version": 1, "scope": "s", "description": "d", "remote": "", "email": "", "allow": [], **fields}
        (self.work / brain / ".data/brain.json").write_text(json.dumps(data), encoding="utf-8")

    def test_input_folders_resolve_from_home_without_printing_paths(self) -> None:
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("« recordings_dir » introuvable", result.stdout)
        self.assertNotIn("« transcripts_dir » introuvable", result.stdout)
        self.assertNotIn("inbox/missing", result.stdout)

    def test_missing_expected_brain_is_an_error(self) -> None:
        self.write_config({"brains": ["brain", "brain-perso"]})
        result = self.run_doctor()
        self.assertEqual(result.returncode, 1)
        self.assertIn("brain attendu absent : brain-perso/", result.stdout)

    def test_invalid_state_json_is_an_error(self) -> None:
        (self.work / "brain/.data/transcripts.json").write_text("{", encoding="utf-8")
        result = self.run_doctor()
        self.assertEqual(result.returncode, 1)
        self.assertIn("transcripts.json : JSON illisible", result.stdout)

    def test_repository_without_upstream_is_a_warning(self) -> None:
        self.assertIn("brain : aucune branche distante suivie", self.run_doctor().stdout)

    def test_invalid_configuration_is_an_error(self) -> None:
        self.write_local({"version": 1, "obsidian": {}})
        result = self.run_doctor()
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: configuration des skills invalide", result.stdout)

    def test_changed_configuration_is_a_warning_after_a_stamp(self) -> None:
        self.assertIn("aucun .work-state.json", self.run_doctor().stdout)
        self.work_config("stamp")
        self.assertNotIn("config modifiée", self.run_doctor().stdout)
        self.write_local({"version": 1, "skills": {"disabled": ["anything"]}})
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("WARN: config modifiée depuis le dernier update.sh", result.stdout)

    def test_lock_entry_known_to_no_layer_is_a_warning(self) -> None:
        (self.work / "skills-lock.json").write_text(
            json.dumps({"version": 1, "skills": {"added": third_party_entry("added")}}), encoding="utf-8"
        )
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("WARN: skill installé mais non adopté : added", result.stdout)
        self.assertIn("work_config.py adopt", result.stdout)

    def test_enabled_third_party_skill_must_be_installed(self) -> None:
        self.write_local({"version": 1, "skills": {"thirdParty": {"tp": third_party_entry("tp")}}})
        self.assertIn("WARN: skill tiers activé mais non installé : tp", self.run_doctor().stdout)
        (self.work / ".agents/skills/tp").mkdir(parents=True)
        (self.work / ".agents/skills/tp/SKILL.md").write_text("# tp\n", encoding="utf-8")
        self.assertNotIn("non installé", self.run_doctor().stdout)

    def test_broken_and_orphan_links_are_warnings_but_foreign_links_are_ignored(self) -> None:
        skills = self.work / ".claude/skills"
        skills.mkdir(parents=True)
        (self.work / "brain/skills/live").mkdir(parents=True)
        (self.work / "brain/skills/live/SKILL.md").write_text("# live\n", encoding="utf-8")
        (self.work / "brain/skills/off").mkdir()
        (self.work / "brain/skills/off/SKILL.md").write_text("# off\n", encoding="utf-8")
        self.write_local({"version": 1, "skills": {"disabled": ["off"]}})
        (skills / "live").symlink_to("../../brain/skills/live")
        (skills / "off").symlink_to("../../brain/skills/off")  # exists but no longer enabled
        (skills / "gone").symlink_to("../../brain/skills/gone")  # target removed
        (skills / "foreign").symlink_to(self.home)  # not a managed link
        out = self.run_doctor().stdout
        self.assertIn("lien cassé : .claude/skills/gone", out)
        self.assertIn("lien orphelin : .claude/skills/off", out)
        self.assertNotIn("skills/live", out)
        self.assertNotIn("skills/foreign", out)

    def test_brain_json_missing_or_incomplete_is_a_warning(self) -> None:
        self.assertIn("brain/.data/brain.json absent", self.run_doctor().stdout)
        self.write_brain_json(scope="client", description="")
        out = self.run_doctor().stdout
        self.assertIn("brain/.data/brain.json : champ(s) non renseigné(s) : description, remote, email", out)
        self.assertNotIn("absent", out)

    def test_remote_and_email_must_match_the_declared_patterns(self) -> None:
        brain = self.work / "brain"
        subprocess.run(["git", "-C", str(brain), "remote", "add", "origin", "git@example.org:acme/brain.git"], check=True)
        subprocess.run(["git", "-C", str(brain), "config", "user.email", "me@acme.example"], check=True)

        self.write_brain_json(remote="git@example.org:acme/*", email="*@acme.example")
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("ne correspond pas", result.stdout)

        self.write_brain_json(remote="git@example.org:other/*", email="*@acme.example")
        result = self.run_doctor()
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: brain : remote origin ne correspond pas", result.stdout)
        self.assertNotIn("user.email effectif ne correspond pas", result.stdout)
        self.assertNotIn("git@example.org", result.stdout)

        self.write_brain_json(remote="git@example.org:acme/*", email="*@other.example")
        result = self.run_doctor()
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: brain : user.email effectif ne correspond pas", result.stdout)
        self.assertNotIn("me@acme.example", result.stdout)

    def test_declared_remote_without_origin_is_only_a_warning(self) -> None:
        self.write_brain_json(remote="git@example.org:acme/*")
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("WARN: brain : remote origin non défini", result.stdout)


if __name__ == "__main__":
    unittest.main()
