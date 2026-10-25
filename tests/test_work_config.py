"""Tests for the layered Work configuration (example, brains, local) and its generated files."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "tools/machine/work_config.py"


def entry(name: str, digest: str = "abc") -> dict[str, str]:
    return {"source": f"example/{name}", "sourceType": "github", "skillPath": f"{name}/SKILL.md", "computedHash": digest}


def config(third_party: dict | None = None, disabled: list | None = None) -> dict:
    return {"version": 1, "skills": {"thirdParty": third_party or {}, "disabled": disabled or []}}


class WorkConfigTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.env = {**os.environ, "WORK_DIR": str(self.root)}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_json(self, name: str, value: object) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def read_json(self, name: str) -> object:
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def make_brain(self, name: str, own: tuple[str, ...] = (), copies: tuple[str, ...] = (), conf: dict | None = None) -> None:
        brain = self.root / name
        (brain / ".data").mkdir(parents=True, exist_ok=True)
        (brain / "AGENTS.md").write_text("# brain\n", encoding="utf-8")
        for skill in (*own, *copies):
            (brain / "skills" / skill).mkdir(parents=True, exist_ok=True)
            (brain / "skills" / skill / "SKILL.md").write_text(f"# {skill}\n", encoding="utf-8")
        for skill in copies:
            (brain / "skills" / skill / ".install-as-copy").write_text("", encoding="utf-8")
        if conf is not None:
            self.write_json(f"{name}/.data/work-config.json", conf)

    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(TOOL), *args], env=self.env, capture_output=True, text=True)

    def ok(self, *args: str) -> str:
        result = self.run_tool(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def fails(self, *args: str) -> str:
        result = self.run_tool(*args)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        return result.stderr


class LayersTest(WorkConfigTestCase):
    def test_empty_workspace_is_valid(self) -> None:
        self.assertIn("Work configuration OK", self.ok("check"))
        self.assertEqual(self.ok("list-own"), "")
        self.assertEqual(self.ok("list-third-party"), "")
        self.assertEqual(self.ok("list-catalog"), "")

    def test_brain_discovery_follows_the_brain_state_rule(self) -> None:
        self.make_brain("brain-perso")
        self.make_brain("brain")
        self.make_brain("brain-acme-x")
        self.make_brain("brainstorm")  # not brain or brain-*
        (self.root / "brain-nodata").mkdir()
        (self.root / "brain-nodata/AGENTS.md").write_text("x", encoding="utf-8")  # no .data/
        self.assertEqual(self.ok("list-brains").split(), ["brain", "brain-acme-x", "brain-perso"])

    def test_layers_merge_and_disabled_names_are_a_union(self) -> None:
        self.write_json("work-config.example.json", config({"from-example": entry("from-example")}))
        self.make_brain("brain", conf=config({"from-brain": entry("from-brain")}, ["from-example"]))
        self.make_brain("brain-perso", conf=config({"from-perso": entry("from-perso")}))
        self.write_json("work-config.local.json", config({"from-local": entry("from-local")}, ["from-perso"]))
        self.assertEqual(
            self.ok("list-catalog").split(), ["from-brain", "from-example", "from-local", "from-perso"]
        )
        self.assertEqual(self.ok("list-third-party").split(), ["from-brain", "from-local"])

    def test_same_third_party_entry_in_two_layers_is_accepted(self) -> None:
        self.write_json("work-config.example.json", config({"shared": entry("shared")}))
        self.make_brain("brain", conf=config({"shared": entry("shared")}))
        self.make_brain("brain-perso", conf=config({"shared": entry("shared")}))
        self.assertEqual(self.ok("list-third-party").split(), ["shared"])

    def test_different_third_party_entries_in_two_layers_are_refused(self) -> None:
        self.make_brain("brain", conf=config({"shared": entry("shared", "one")}))
        self.make_brain("brain-perso", conf=config({"shared": entry("shared", "two")}))
        error = self.fails("check")
        self.assertIn("shared", error)
        self.assertIn("brain/.data/work-config.json", error)
        self.assertIn("brain-perso/.data/work-config.json", error)

    def test_local_layer_may_override_a_third_party_entry(self) -> None:
        self.make_brain("brain", conf=config({"shared": entry("shared", "one")}))
        self.write_json("work-config.local.json", config({"shared": entry("shared", "local")}))
        self.ok("lock")
        self.assertEqual(self.read_json("skills-lock.json")["skills"]["shared"]["computedHash"], "local")

    def test_own_skills_report_brain_and_mode_and_honor_disabled(self) -> None:
        self.make_brain("brain", own=("alpha", "zeta"))
        self.make_brain("brain-perso", copies=("beta",))
        self.write_json("work-config.local.json", config(disabled=["zeta"]))
        self.assertEqual(self.ok("list-own").splitlines(), ["alpha\tbrain\tlink", "beta\tbrain-perso\tcopy"])

    def test_skill_folder_without_skill_md_is_not_a_skill(self) -> None:
        self.make_brain("brain", own=("alpha",))
        (self.root / "brain/skills/notes").mkdir()
        self.assertEqual(self.ok("list-own").splitlines(), ["alpha\tbrain\tlink"])

    def test_same_own_skill_in_two_brains_names_both_paths(self) -> None:
        self.make_brain("brain", own=("alpha",))
        self.make_brain("brain-perso", own=("alpha",))
        error = self.fails("check")
        self.assertIn("brain/skills/alpha", error)
        self.assertIn("brain-perso/skills/alpha", error)

    def test_own_and_third_party_name_clash_is_refused(self) -> None:
        self.make_brain("brain", own=("alpha",), conf=config({"alpha": entry("alpha")}))
        self.assertIn("both own and third-party: alpha", self.fails("check"))


class DefaultBrainTest(WorkConfigTestCase):
    """`default_brain(root)`: the setting, then `brain/`, then the only brain, else none."""

    def default_brain(self) -> subprocess.CompletedProcess[str]:
        return self.run_tool("default-brain")

    def test_setting_in_the_local_layer_wins_over_brain(self) -> None:
        self.make_brain("brain")
        self.make_brain("brain-initech")
        self.write_json("work-config.local.json", {"version": 1, "defaultBrain": "brain-initech"})
        self.assertEqual(self.ok("default-brain"), "brain-initech\n")
        self.assertIn("Work configuration OK", self.ok("check"))

    def test_brain_is_the_default_when_there_is_no_setting(self) -> None:
        self.make_brain("brain-perso")
        self.make_brain("brain")
        self.make_brain("brain-acme-x")
        self.assertEqual(self.ok("default-brain"), "brain\n")

    def test_the_only_brain_is_the_default(self) -> None:
        self.make_brain("brain-initech")
        (self.root / "brain-nodata").mkdir()  # not a brain: no AGENTS.md and no .data/
        self.assertEqual(self.ok("default-brain"), "brain-initech\n")

    def test_no_default_brain_prints_nothing_and_exits_with_1(self) -> None:
        result = self.default_brain()  # no brain at all
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, "", ""))
        self.make_brain("brain-perso")
        self.make_brain("brain-initech")  # several brains, no `brain/`, no setting
        result = self.default_brain()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, "", ""))
        self.assertEqual(self.ok("list-brains").split(), ["brain-initech", "brain-perso"])

    def test_list_brains_puts_the_default_brain_first_then_the_others_by_name(self) -> None:
        for name in ("brain", "brain-acme", "brain-perso", "brain-zed"):
            self.make_brain(name)
        self.assertEqual(self.ok("list-brains").split(), ["brain", "brain-acme", "brain-perso", "brain-zed"])
        self.write_json("work-config.local.json", {"version": 1, "defaultBrain": "brain-perso"})
        self.assertEqual(self.ok("list-brains").split(), ["brain-perso", "brain", "brain-acme", "brain-zed"])

    def test_invalid_or_absent_setting_is_an_error_naming_the_file(self) -> None:
        self.make_brain("brain")
        self.make_brain("brain-perso", own=("alpha",))
        (self.root / "brain-vide").mkdir()  # a folder, but not a brain
        cases = [
            ("brain-nope", "is not a brain at the Work root"),
            ("brain-vide", "is not a brain at the Work root"),
            ("Brain-Perso", "invalid brain name"),
            ("perso", "invalid brain name"),
            ("../brain", "invalid brain name"),
            ("", "invalid brain name"),
            (None, "invalid brain name"),
            (3, "invalid brain name"),
        ]
        for value, message in cases:
            self.write_json("work-config.local.json", {"version": 1, "defaultBrain": value})
            for command in ("default-brain", "check", "list-brains", "list-own"):
                with self.subTest(value=value, command=command):
                    error = self.fails(command)
                    self.assertIn("work-config.local.json: defaultBrain", error)
                    self.assertIn(message, error)

    def test_setting_is_only_accepted_in_the_local_layer(self) -> None:
        self.write_json("work-config.example.json", {"version": 1, "defaultBrain": "brain", "skills": {}})
        self.make_brain("brain")
        error = self.fails("check")
        self.assertIn("work-config.example.json: defaultBrain is only accepted in work-config.local.json", error)
        (self.root / "work-config.example.json").unlink()
        self.make_brain("brain-perso", conf={"version": 1, "defaultBrain": "brain-perso"})
        error = self.fails("check")
        self.assertIn("brain-perso/.data/work-config.json: defaultBrain is only accepted in work-config.local.json", error)
        # The same key is fine in the local layer, next to the other settings of that layer.
        self.make_brain("brain-perso", conf=config())
        self.write_json("work-config.local.json", {"version": 1, "defaultBrain": "brain-perso", "skills": {"disabled": ["x"]}})
        self.assertIn("Work configuration OK", self.ok("check"))

    def test_adopt_goes_to_the_default_brain_unless_a_brain_is_named(self) -> None:
        self.make_brain("brain")
        self.make_brain("brain-initech")
        self.write_json("work-config.local.json", {"version": 1, "defaultBrain": "brain-initech"})
        self.write_json("skills-lock.json", {"version": 1, "skills": {"added": entry("added")}})
        self.assertIn("Adopted added into brain-initech/.data/work-config.json", self.ok("adopt"))
        self.assertFalse((self.root / "brain/.data/work-config.json").exists())
        self.write_json("skills-lock.json", {"version": 1, "skills": {"added": entry("added"), "more": entry("more")}})
        self.assertIn("Adopted more into brain/.data/work-config.json", self.ok("adopt", "--brain", "brain"))

    def test_adopt_without_a_default_brain_asks_for_one(self) -> None:
        self.make_brain("brain-perso")
        self.make_brain("brain-initech")
        self.write_json("skills-lock.json", {"version": 1, "skills": {"added": entry("added")}})
        error = self.fails("adopt")
        self.assertIn("no default brain", error)
        self.assertIn("--brain", error)
        self.assertIn("defaultBrain", error)
        self.assertFalse((self.root / "brain-initech/.data/work-config.json").exists())

    def test_functions_take_the_root_explicitly(self) -> None:
        spec = importlib.util.spec_from_file_location("work_config_under_test", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # importing has no side effect: nothing is read or written
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertIsNone(module.default_brain(self.root))
        self.make_brain("brain-initech")
        self.assertEqual(module.default_brain(self.root), self.root / "brain-initech")
        self.make_brain("brain")
        self.make_brain("brain-perso")
        self.assertEqual([path.name for path in module.discover_brains(self.root)], ["brain", "brain-initech", "brain-perso"])
        self.write_json("work-config.local.json", {"version": 1, "defaultBrain": "brain-perso"})
        self.assertEqual([path.name for path in module.discover_brains(self.root)], ["brain-perso", "brain", "brain-initech"])
        other = self.root / "other"
        other.mkdir()
        self.assertIsNone(module.default_brain(other))  # another root, not the module's ROOT nor the setting of this one
        (other / "work-config.local.json").write_text(json.dumps({"version": 1, "defaultBrain": "brain-x"}), encoding="utf-8")
        with self.assertRaises(module.ConfigError) as caught:
            module.default_brain(other)
        self.assertIn("brain-x", str(caught.exception))


class ValidationTest(WorkConfigTestCase):
    def assert_rejected(self, value: object, message: str) -> None:
        self.write_json("work-config.local.json", value)
        error = self.fails("check")
        self.assertIn("work-config.local.json", error)
        self.assertIn(message, error)

    def test_invalid_layers_are_rejected_with_a_clear_message(self) -> None:
        cases = [
            ({"version": 2}, "version 1"),
            ({"version": 1, "obsidian": {}}, "unknown key(s): obsidian"),
            ({"version": 1, "skills": {"house": []}}, "unknown key(s) in skills: house"),
            ({"version": 1, "skills": []}, "skills must be an object"),
            ({"version": 1, "skills": {"thirdParty": ["x"]}}, "thirdParty must be an object"),
            ({"version": 1, "skills": {"thirdParty": {"Bad Name": entry("x")}}}, "invalid skill name"),
            ({"version": 1, "skills": {"thirdParty": {"../x": entry("x")}}}, "invalid skill name"),
            ({"version": 1, "skills": {"thirdParty": {"x": {"source": "a"}}}}, "needs a non-empty string sourceType"),
            ({"version": 1, "skills": {"thirdParty": {"x": "a/b"}}}, "must be an object"),
            ({"version": 1, "skills": {"disabled": "x"}}, "disabled must be a list"),
            ({"version": 1, "skills": {"disabled": ["a", "a"]}}, "contains duplicates"),
            ({"version": 1, "skills": {"disabled": [1]}}, "invalid skill name"),
            ([], "version 1"),
        ]
        for value, message in cases:
            with self.subTest(message=message, value=value):
                self.assert_rejected(value, message)

    def test_invalid_json_names_the_file(self) -> None:
        (self.root / "work-config.local.json").write_text("{", encoding="utf-8")
        error = self.fails("check")
        self.assertIn("invalid JSON in work-config.local.json", error)

    def test_invalid_brain_layer_names_the_brain_file(self) -> None:
        self.make_brain("brain-perso", conf={"version": 1, "skills": {"disabled": "x"}})
        self.assertIn("brain-perso/.data/work-config.json", self.fails("check"))

    def test_invalid_own_skill_folder_name_is_rejected(self) -> None:
        self.make_brain("brain", own=("Bad Name",))
        self.assertIn("invalid skill name", self.fails("check"))


class LockAndAdoptTest(WorkConfigTestCase):
    def test_lock_contains_enabled_third_party_skills_in_deterministic_json(self) -> None:
        self.make_brain("brain", conf=config({"b-skill": entry("b-skill"), "a-skill": entry("a-skill")}, ["b-skill"]))
        self.ok("lock")
        first = (self.root / "skills-lock.json").read_bytes()
        expected = {"version": 1, "skills": {"a-skill": entry("a-skill")}}
        self.assertEqual(first.decode(), json.dumps(expected, indent=2, sort_keys=True) + "\n")
        self.ok("lock")
        self.assertEqual((self.root / "skills-lock.json").read_bytes(), first)

    def test_lock_accepts_an_existing_lock_that_only_lists_known_skills(self) -> None:
        self.make_brain("brain", conf=config({"a-skill": entry("a-skill"), "off": entry("off")}, ["off"]))
        self.write_json("skills-lock.json", {"version": 1, "skills": {"a-skill": entry("a-skill"), "off": entry("off")}})
        self.ok("lock")
        self.assertEqual(list(self.read_json("skills-lock.json")["skills"]), ["a-skill"])

    def test_lock_refuses_skills_unknown_to_every_layer(self) -> None:
        self.make_brain("brain", conf=config({"a-skill": entry("a-skill")}))
        self.write_json("skills-lock.json", {"version": 1, "skills": {"a-skill": entry("a-skill"), "added": entry("added")}})
        before = (self.root / "skills-lock.json").read_text(encoding="utf-8")
        error = self.fails("lock")
        self.assertIn("added", error)
        self.assertIn("adopt", error)
        self.assertEqual((self.root / "skills-lock.json").read_text(encoding="utf-8"), before)

    def test_adopt_copies_unknown_entries_to_the_default_brain(self) -> None:
        self.make_brain("brain", conf=config({"a-skill": entry("a-skill")}))
        self.write_json("skills-lock.json", {"version": 1, "skills": {"a-skill": entry("a-skill"), "added": entry("added")}})
        self.assertIn("Adopted added into brain/.data/work-config.json", self.ok("adopt"))
        conf = self.read_json("brain/.data/work-config.json")
        self.assertEqual(sorted(conf["skills"]["thirdParty"]), ["a-skill", "added"])
        self.ok("lock")
        self.assertEqual(sorted(self.read_json("skills-lock.json")["skills"]), ["a-skill", "added"])
        self.assertIn("Nothing to adopt", self.ok("adopt"))

    def test_adopt_creates_the_config_of_the_chosen_brain(self) -> None:
        self.make_brain("brain")
        self.make_brain("brain-perso")
        self.write_json("skills-lock.json", {"version": 1, "skills": {"added": entry("added")}})
        self.ok("adopt", "--brain", "brain-perso")
        self.assertEqual(
            self.read_json("brain-perso/.data/work-config.json"),
            {"version": 1, "skills": {"thirdParty": {"added": entry("added")}, "disabled": []}},
        )
        self.assertFalse((self.root / "brain/.data/work-config.json").exists())

    def test_adopt_keeps_the_disabled_names_of_an_existing_config(self) -> None:
        self.make_brain("brain", conf=config({}, ["old"]))
        self.write_json("skills-lock.json", {"version": 1, "skills": {"added": entry("added")}})
        self.ok("adopt")
        self.assertEqual(self.read_json("brain/.data/work-config.json")["skills"]["disabled"], ["old"])

    def test_adopt_rejects_an_unknown_brain_and_invalid_lock_entries(self) -> None:
        self.make_brain("brain")
        self.write_json("skills-lock.json", {"version": 1, "skills": {"added": entry("added")}})
        self.assertIn("no brain named brain-nope", self.fails("adopt", "--brain", "brain-nope"))
        self.write_json("skills-lock.json", {"version": 1, "skills": {"added": {"source": "x"}}})
        self.assertIn("needs a non-empty string", self.fails("adopt"))
        self.assertFalse((self.root / "brain/.data/work-config.json").exists())


class StampTest(WorkConfigTestCase):
    def test_status_needs_a_stamp_then_follows_the_configuration(self) -> None:
        self.make_brain("brain", own=("alpha",))
        self.assertIn("No valid .work-state.json", self.run_tool("status").stdout)
        self.fails_status()
        self.ok("stamp")
        self.assertIn("unchanged", self.ok("status"))

        self.write_json("work-config.local.json", config(disabled=["alpha"]))
        self.fails_status()
        self.ok("stamp")
        self.ok("status")

        self.make_brain("brain", own=("beta",))  # a new own skill changes the resolved configuration
        self.fails_status()

    def fails_status(self) -> None:
        result = self.run_tool("status")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_stamp_is_deterministic_json_and_ignores_unrelated_changes(self) -> None:
        self.make_brain("brain", own=("alpha",))
        self.ok("stamp")
        first = (self.root / ".work-state.json").read_text(encoding="utf-8")
        data = json.loads(first)
        self.assertEqual(list(data), ["configHash"])
        self.assertEqual(len(data["configHash"]), 64)
        self.assertEqual(first, json.dumps(data, indent=2, sort_keys=True) + "\n")
        (self.root / "brain/skills/alpha/SKILL.md").write_text("# edited\n", encoding="utf-8")
        self.ok("status")

    def test_corrupt_stamp_counts_as_missing(self) -> None:
        (self.root / ".work-state.json").write_text("[", encoding="utf-8")
        self.assertEqual(self.run_tool("status").returncode, 1)

    def test_invalid_configuration_fails_every_command_but_list_brains(self) -> None:
        self.write_json("work-config.local.json", {"version": 1, "nope": 1})
        for command in ("check", "list-own", "list-third-party", "list-catalog", "lock", "stamp", "status"):
            with self.subTest(command=command):
                self.assertIn("unknown key(s): nope", self.fails(command))
        self.assertEqual(self.run_tool("list-brains").returncode, 0)


if __name__ == "__main__":
    unittest.main()
