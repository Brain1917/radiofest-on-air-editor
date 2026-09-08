"""Portable corpus checks; artifact checks do not evaluate model behavior.

Run CorpusContractTest for fixture integrity. Run V2ArtifactContractTest separately
for the intentionally red, pre-implementation reference-file contract.
RADIOFEST_ARTIFACT_ROOT selects an exported package without requiring Git or MB.
"""

from __future__ import annotations

import csv
import json
import os
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PLUGIN_ROOT / "skills/on-air-text-editor"
EVAL_ROOT = SKILL_ROOT / "evals"
SCENARIOS = [
    ("REQ-056__editing", "editing", [56, 57, 58, 59, 66, 67, 68, 92, 94, 95, 96, 97, 99]),
    ("REQ-057__social", "social", [57, 61, 69, 70, 72]),
    ("REQ-057__site", "site", [57, 71, 72, 91, 97]),
    ("REQ-057__internet_article", "internet_article", [57, 64, 65, 73, 74, 75, 93]),
    ("REQ-057__factual_brief", "factual_brief", [57, 64, 65, 78, 92, 93]),
    ("REQ-057__statistics", "statistics", [57, 79, 80, 81]),
    ("REQ-057__archive", "archive", [57, 82, 83]),
    ("REQ-057__table_row", "table_row", [57, 85, 86, 87, 91]),
    ("REQ-057__onair_news", "news", [57, 89, 90, 100]),
    ("REQ-057__interview", "interview", [57, 89, 90, 100]),
    ("REQ-057__advertising", "advertising", [57, 89, 90, 98, 100, 101]),
    ("REQ-060__conflicting_sources", "conflicting_sources", [60, 64, 65, 76, 79, 80, 81]),
    ("REQ-062__no_web", "no_web", [62, 73, 77, 93, 101]),
    ("REQ-060__unavailable_archive", "unavailable_archive", [60, 62, 82, 84]),
    ("REQ-060__unknown_table_schema", "unknown_table_schema", [60, 85, 86, 87, 88]),
    ("REQ-062__untrusted_instructions", "prompt-injection", [62, 63, 65, 90, 91, 95]),
]


class CorpusContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contracts = json.loads((EVAL_ROOT / "v2-contracts.json").read_text())
        self.cases = self.contracts["cases"]
        self.evals = json.loads((EVAL_ROOT / "evals.json").read_text())["evals"]

    def assert_case_contract(self, number: int) -> None:
        test_id, eval_id, req_numbers = SCENARIOS[number - 1]
        case = next(item for item in self.cases if item["scenario_id"] == number)
        self.assertEqual(case["test_id"], test_id)
        self.assertEqual(case["eval_id"], eval_id)
        self.assertEqual(case["case_id"], f"V2-{number:02}")
        self.assertEqual(case["kind"], "positive" if number <= 11 else "negative")
        evaluation = next(item for item in self.evals if item["id"] == eval_id)
        self.assertTrue(evaluation["prompt"].strip())
        self.assertTrue(evaluation["expected_output"].strip())
        self.assertTrue(evaluation["assertions"])
        for filename in evaluation["files"]:
            self.assert_source_ref(filename)
        self.assertTrue(case["input_refs"] or case["environment"]["attachments"] == "none")
        for reference in case["input_refs"]:
            self.assert_source_ref(reference)
        if "source_record_ref" in case:
            self.assert_source_ref(case["source_record_ref"])
        variants = case.get("variants", [])
        self.assertEqual(len({item["id"] for item in variants}), len(variants))
        for variant in variants:
            self.assertTrue(variant["prompt"].strip())
            self.assertTrue(variant["expected"].strip())
            for reference in variant["input_refs"]:
                self.assert_source_ref(reference)
        assertions = case["assertions"]
        self.assertTrue(assertions)
        self.assertEqual(len({item["id"] for item in assertions}), len(assertions))
        covered = set()
        for assertion in assertions:
            with self.subTest(assertion=assertion["id"]):
                self.assertTrue(assertion["req_ids"])
                covered.update(assertion["req_ids"])
                self.assertIn(
                    assertion["method"], {"static", "document", "behavior", "target-host"}
                )
                self.assertEqual(assertion["expected_status"], "pass")
                self.assertTrue(assertion["expected"].strip())
                self.assertNotIn("observed_status", assertion)
        self.assertEqual(covered, {f"REQ-{number:03}" for number in req_numbers})
        self.assertEqual(set(case["environment"]), {"web", "attachments", "archive"})

    def assert_source_ref(self, reference: str) -> None:
        filename, separator, section = reference.partition("#")
        path = (SKILL_ROOT / filename).resolve()
        self.assertTrue(path.is_relative_to(SKILL_ROOT.resolve()), reference)
        self.assertTrue(path.is_file(), reference)
        if separator:
            self.assertIn(f"## {section}\n", path.read_text(), reference)

    def test_req_056__editing(self) -> None:
        """REQ-056__editing: validate expectations, not an LLM response."""
        self.assert_case_contract(1)

    def test_req_057__social(self) -> None:
        self.assert_case_contract(2)

    def test_req_057__site(self) -> None:
        self.assert_case_contract(3)

    def test_req_057__internet_article(self) -> None:
        self.assert_case_contract(4)

    def test_req_057__factual_brief(self) -> None:
        self.assert_case_contract(5)

    def test_req_057__statistics(self) -> None:
        self.assert_case_contract(6)
        oracle = self.cases[5]["oracle"]
        self.assertEqual(oracle["inputs"], [100, 120])
        self.assertEqual(oracle["difference"], 120 - 100)
        self.assertEqual(oracle["percent"], (120 - 100) / 100 * 100)

    def test_req_057__archive(self) -> None:
        self.assert_case_contract(7)
        bundle = (EVAL_ROOT / "files/editorial-v2-cases.md").read_text()
        body = bundle.split("## meeting.md\n", 1)[1].split("```text\n", 1)[1].split("```", 1)[0]
        self.assertEqual(body.splitlines()[6], "Встреча назначена на 15:00 4 сентября 2026 года.")

    def test_req_057__table_row(self) -> None:
        self.assert_case_contract(8)
        self.assertEqual(list(csv.reader([self.cases[7]["oracle"]["csv"]])), [["Тихий город", ""]])

    def test_req_057__onair_news(self) -> None:
        self.assert_case_contract(9)

    def test_req_057__interview(self) -> None:
        self.assert_case_contract(10)

    def test_req_057__advertising(self) -> None:
        self.assert_case_contract(11)

    def test_req_060__conflicting_sources(self) -> None:
        self.assert_case_contract(12)
        self.assertIn("zero_base", {item["id"] for item in self.cases[11]["variants"]})

    def test_req_062__no_web(self) -> None:
        self.assert_case_contract(13)
        self.assertEqual(self.cases[12]["environment"]["web"], "unavailable")

    def test_req_060__unavailable_archive(self) -> None:
        self.assert_case_contract(14)
        self.assertEqual(self.cases[13]["environment"]["archive"], "unavailable")

    def test_req_060__unknown_table_schema(self) -> None:
        self.assert_case_contract(15)
        self.assertTrue(self.cases[14]["follow_up"]["prompt"])

    def test_req_062__untrusted_instructions(self) -> None:
        self.assert_case_contract(16)

    def test_corpus_has_exactly_sixteen_cases_and_all_requirements(self) -> None:
        self.assertEqual(len(self.cases), 16)
        self.assertEqual(len(self.evals), 16)
        self.assertEqual({case["scenario_id"] for case in self.cases}, set(range(1, 17)))
        self.assertEqual(len({case["id"] for case in self.evals}), 16)
        self.assertEqual(len({case["case_id"] for case in self.cases}), 16)
        assertions = [assertion for case in self.cases for assertion in case["assertions"]]
        self.assertEqual(len({item["id"] for item in assertions}), len(assertions))
        self.assertEqual(
            {req for item in assertions for req in item["req_ids"]},
            {f"REQ-{number:03}" for number in range(56, 102)},
        )

    def test_trigger_pairs_cover_each_positive_case_in_fresh_contexts(self) -> None:
        triggers = json.loads((EVAL_ROOT / "trigger-queries.json").read_text())
        queries = triggers["queries"]
        self.assertEqual(len({query["id"] for query in queries}), len(queries))
        pairs = [query for query in queries if query.get("suite") == "v2"]
        self.assertEqual(len(pairs), 22)
        for case in self.cases[:11]:
            pair = [query for query in pairs if query["case_id"] == case["case_id"]]
            self.assertEqual(len(pair), 2)
            self.assertEqual({query["should_trigger"] for query in pair}, {True, False})
            self.assertTrue(all(query["fresh_context"] for query in pair))
        retired = {query["id"] for query in queries if query.get("superseded_in_v2")}
        self.assertEqual(retired, {"N06", "N07"})


class V2ArtifactContractTest(unittest.TestCase):
    def test_v2_route_references_exist_as_nonempty_package_documents(self) -> None:
        """REQ-057/099: observable design paths, never a model-behavior test."""
        package = Path(os.environ.get("RADIOFEST_ARTIFACT_ROOT", PLUGIN_ROOT))
        root = package / "skills/on-air-text-editor/references"
        for filename in ("editing.md", "channels.md", "research.md", "archive-and-tables.md"):
            with self.subTest(document=filename):
                path = root / filename
                self.assertTrue(path.is_file(), f"Missing v2 route document: {filename}")
                self.assertTrue(path.read_text().strip(), f"Empty v2 route document: {filename}")

    def test_release_metadata_preserves_identity_version_and_license(self) -> None:
        """REQ-056/097: release identity is consistent across install surfaces."""
        manifest = json.loads((PLUGIN_ROOT / ".codex-plugin/plugin.json").read_text())
        marketplace = json.loads((PLUGIN_ROOT / ".agents/plugins/marketplace.json").read_text())
        skill = (SKILL_ROOT / "SKILL.md").read_text()
        self.assertEqual(manifest["name"], "radiofest-on-air-editor")
        self.assertEqual(marketplace["name"], manifest["name"])
        self.assertEqual(marketplace["plugins"][0]["name"], manifest["name"])
        self.assertEqual(marketplace["plugins"][0]["source"]["path"], "./")
        self.assertEqual(manifest["version"], "0.3.0")
        self.assertIn(f'  version: "{manifest["version"]}"', skill)
        self.assertEqual(manifest["license"], "MIT")
        self.assertIn("license: MIT\n", skill)
        self.assertEqual(
            (PLUGIN_ROOT / "LICENSE.txt").read_bytes(),
            (SKILL_ROOT / "LICENSE.txt").read_bytes(),
        )

    def test_release_display_name_matches_public_documents(self) -> None:
        """REQ-097: the broad display label does not rename the technical skill."""
        label = "Редакционный помощник радио"
        manifest = json.loads((PLUGIN_ROOT / ".codex-plugin/plugin.json").read_text())
        marketplace = json.loads((PLUGIN_ROOT / ".agents/plugins/marketplace.json").read_text())
        self.assertEqual(manifest.get("interface", {}).get("displayName"), label)
        self.assertEqual(marketplace["interface"]["displayName"], label)
        self.assertIn(f'display_name: "{label}"', (SKILL_ROOT / "agents/openai.yaml").read_text())
        for path in (
            SKILL_ROOT / "SKILL.md",
            PLUGIN_ROOT / "README.md",
            PLUGIN_ROOT / "docs/radiofest.md",
        ):
            with self.subTest(document=path.name):
                self.assertIn(label, path.read_text())

    def test_single_skill_has_stable_name_and_agent_metadata(self) -> None:
        """REQ-056/095: packaging only; metadata semantics need document review."""
        package = Path(os.environ.get("RADIOFEST_ARTIFACT_ROOT", PLUGIN_ROOT))
        skills = list((package / "skills").glob("*/SKILL.md"))
        self.assertEqual(len(skills), 1)
        self.assertTrue((skills[0].parent / "agents/openai.yaml").is_file())
        self.assertIn("name: on-air-text-editor", skills[0].read_text())


if __name__ == "__main__":
    unittest.main()
