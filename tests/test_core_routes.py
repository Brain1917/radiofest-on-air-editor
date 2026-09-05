"""Static route/link contracts over the existing corpus, not model behavior."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1] / "skills/on-air-text-editor"


class CoreRouteContractTest(unittest.TestCase):
    def test_route_declarations_match_corpus_and_actual_reference_availability(self) -> None:
        cases = json.loads((SKILL_ROOT / "evals/v2-contracts.json").read_text())["cases"]
        expected = {case["eval_id"] for case in cases if case["kind"] == "positive"}
        text = (SKILL_ROOT / "SKILL.md").read_text()
        rows = []
        for line in text.splitlines():
            if not line.startswith("| `"):
                continue
            fields = [field.strip() for field in line.strip("|").split("|")]
            rows.append(fields)
        self.assertEqual(len(rows), len(expected), "One declaration per positive corpus route")
        self.assertEqual({row[0].strip("`") for row in rows}, expected)
        for route, result, resources, availability in rows:
            with self.subTest(route=route):
                self.assertTrue(result)
                references = re.findall(r"`(references/[^`]+\.md)`", resources)
                self.assertTrue(references, "A route must name its instruction documents")
                existing = []
                for reference in references:
                    path = (SKILL_ROOT / reference).resolve()
                    self.assertTrue(path.is_relative_to(SKILL_ROOT.resolve()))
                    existing.append(path.is_file() and bool(path.read_text().strip()))
                self.assertEqual(availability, "доступен" if all(existing) else "недоступен")

    def test_implemented_nonair_routes_from_corpus_have_ready_instructions(self) -> None:
        """Tasks 7-9 availability only; V2-01 to V2-08 need real model runs."""
        cases = json.loads((SKILL_ROOT / "evals/v2-contracts.json").read_text())["cases"]
        routes = {case["eval_id"] for case in cases if case["scenario_id"] in range(1, 9)}
        self.assertEqual(
            routes,
            {
                "editing",
                "social",
                "site",
                "internet_article",
                "factual_brief",
                "statistics",
                "archive",
                "table_row",
            },
        )
        declarations = {
            fields[0].strip("`"): fields
            for line in (SKILL_ROOT / "SKILL.md").read_text().splitlines()
            if line.startswith("| `")
            for fields in [[field.strip() for field in line.strip("|").split("|")]]
        }
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(declarations[route][3], "доступен")
                references = re.findall(r"`(references/[^`]+\.md)`", declarations[route][2])
                self.assertTrue(references)
                for reference in references:
                    path = SKILL_ROOT / reference
                    self.assertTrue(path.is_file(), reference)
                    self.assertTrue(path.read_text().strip(), reference)

    def test_common_document_links_resolve_inside_the_public_skill(self) -> None:
        documents = ["SKILL.md"] + [
            f"references/{name}.md"
            for name in (
                "workflow",
                "risk-rules",
                "governance",
                "editorial-principles",
                "editing",
                "channels",
                "research",
                "archive-and-tables",
            )
        ]
        for document in documents:
            path = SKILL_ROOT / document
            links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text())
            for link in links:
                if link.startswith(("https://", "http://", "#")):
                    continue
                with self.subTest(document=document, link=link):
                    target = (path.parent / link.split("#", 1)[0]).resolve()
                    self.assertTrue(target.is_relative_to(SKILL_ROOT.resolve()))
                    self.assertTrue(target.is_file(), "Do not link missing staged instructions")


if __name__ == "__main__":
    unittest.main()
