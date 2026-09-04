from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = PLUGIN_ROOT / "skills" / "on-air-text-editor" / "scripts"


def run_script(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_ROOT / script), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def load_script(script: str) -> ModuleType:
    path = SCRIPT_ROOT / script
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось загрузить {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def chain_yaml(
    blocked: bool = False,
    *,
    m6c: str = "not_applicable",
    m8b: str = "not_applicable",
) -> str:
    states = {
        "M1": "complete",
        "M2": "complete",
        "M3": "complete",
        "M4": "complete",
        "M5": "complete",
        "M6A": "complete",
        "M6B": "blocked" if blocked else "complete",
        "M6C": m6c,
        "M7": "not_applicable",
        "M8A": "complete",
        "M8B": m8b,
        "M9": "complete",
        "M10": "complete",
        "M11": "blocked" if blocked else "complete",
    }
    return "\n".join(f"  {key}: {value}" for key, value in states.items())


def result_text(
    *,
    status: str,
    approver: str,
    editor_blockers: str,
    passport_blockers: list[str],
    blocked_chain: bool,
    confirmed_by: str | None = None,
    confirmed_version: str | None = None,
    confirmed_at: str | None = None,
    version_id: str = "test-v1",
    presenter: str = "Текст для чтения.",
    result_type: str = "эфирный лист",
    applicable_reviews: list[str] | None = None,
    earliest_override: str | None = None,
    m6c: str = "not_applicable",
    m8b: str = "not_applicable",
) -> str:
    def yaml_scalar(value: str | None) -> str:
        return "null" if value is None else f'"{value}"'

    blockers_yaml = (
        "[]"
        if not passport_blockers
        else "\n" + "\n".join(f'  - "{value}"' for value in passport_blockers)
    )
    reviews = applicable_reviews or []
    reviews_yaml = "[]" if not reviews else "[" + ", ".join(f'"{item}"' for item in reviews) + "]"
    earliest = (
        yaml_scalar(earliest_override)
        if earliest_override is not None
        else ('"M6B: подтвердить произношение"' if blocked_chain else "null")
    )
    return f"""## Эфирный лист
{presenter}

## Редакторская карточка
### Источники
S1.
### Рисковые сущности
Нет.
### Блокеры
{editor_blockers}

## Паспорт мастер-версии
version_id: "{version_id}"
updated_at: "2026-08-30 12:00 UTC"
status: "{status}"
result_type: "{result_type}"
approver: "{approver}"
approval_confirmed_by: {yaml_scalar(confirmed_by)}
approval_confirmed_version: {yaml_scalar(confirmed_version)}
approval_confirmed_at: {yaml_scalar(confirmed_at)}
applicable_reviews: {reviews_yaml}
chain_state:
{chain_yaml(blocked_chain, m6c=m6c, m8b=m8b)}
earliest_blocker: {earliest}
permitted_cut_points: []
blockers:{blockers_yaml}
"""


class DurationEstimatorTest(unittest.TestCase):
    def test_estimates_duration_and_limit(self) -> None:
        result = run_script(
            "estimate_duration.py",
            "--text",
            "Раз два три четыре пять",
            "--wpm",
            "120",
            "--limit-seconds",
            "2",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["word_count"], 5)
        self.assertEqual(payload["estimated_seconds"], 3)
        self.assertFalse(payload["fits_limit"])
        self.assertEqual(payload["over_limit_seconds"], 1)

    def test_rejects_non_positive_tempo(self) -> None:
        result = run_script("estimate_duration.py", "--text", "Текст", "--wpm", "0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Темп должен быть больше нуля", result.stdout)


class OutputValidatorTest(unittest.TestCase):
    def validate_text(self, content: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.md"
            path.write_text(content, encoding="utf-8")
            return run_script("validate_output.py", str(path))

    def test_rejects_ready_with_role_approver(self) -> None:
        content = result_text(
            status="готово к допуску",
            approver="выпускающий продюсер",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_ready_with_placeholder_name(self) -> None:
        content = result_text(
            status="готово к допуску",
            approver="Имя Фамилия",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_local_ready_status_as_host_only(self) -> None:
        content = result_text(
            status="готово к допуску",
            approver="Мария Петрова",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)
        self.assertIn("host-система", result.stdout)

    def test_accepts_required_review_with_structured_blocker(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="- Подтвердить произношение.",
            passport_blockers=["Подтвердить произношение."],
            blocked_chain=True,
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_rejects_ready_status_with_arbitrary_blocker(self) -> None:
        content = result_text(
            status="готово к допуску",
            approver="Мария Петрова",
            editor_blockers="- Дата события не подтверждена.",
            passport_blockers=["Дата события не подтверждена."],
            blocked_chain=True,
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["valid"])

    def test_rejects_human_approval_without_named_approver(self) -> None:
        content = result_text(
            status="допущено человеком",
            approver="ответственный не назначен",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
            confirmed_by="Мария Петрова",
            confirmed_version="test-v1",
            confirmed_at="2026-08-30T12:05:00+03:00",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_human_approval_with_role_instead_of_name(self) -> None:
        content = result_text(
            status="допущено человеком",
            approver="дежурный редактор",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
            confirmed_by="дежурный редактор",
            confirmed_version="test-v1",
            confirmed_at="2026-08-30T12:05:00+03:00",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_human_approval_by_another_person(self) -> None:
        content = result_text(
            status="допущено человеком",
            approver="Мария Петрова",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
            confirmed_by="Пётр Сидоров",
            confirmed_version="test-v1",
            confirmed_at="2026-08-30T12:05:00+03:00",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_human_approval_without_version_confirmation(self) -> None:
        content = result_text(
            status="допущено человеком",
            approver="Мария Петрова",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
            confirmed_by="Мария Петрова",
            confirmed_version="other-v1",
            confirmed_at="2026-08-30T12:05:00+03:00",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_human_approval_without_timestamp(self) -> None:
        content = result_text(
            status="допущено человеком",
            approver="Мария Петрова",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
            confirmed_by="Мария Петрова",
            confirmed_version="test-v1",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_human_approval_with_impossible_timestamp(self) -> None:
        content = result_text(
            status="допущено человеком",
            approver="Мария Петрова",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
            confirmed_by="Мария Петрова",
            confirmed_version="test-v1",
            confirmed_at="2026-99-99T99:99:99+99:99",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_local_human_approval_even_with_complete_fields(self) -> None:
        content = result_text(
            status="допущено человеком",
            approver="Мария Петрова",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
            confirmed_by="Мария Петрова",
            confirmed_version="test-v1",
            confirmed_at="2026-08-30T12:05:00+03:00",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)
        self.assertIn("host-система", result.stdout)

    def test_rejects_unknown_status(self) -> None:
        content = result_text(
            status="готово",
            approver="Мария Петрова",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_wrong_earliest_blocker(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="- Подтвердить произношение.",
            passport_blockers=["Подтвердить произношение."],
            blocked_chain=True,
            earliest_override="M11: назначить ответственного",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_advertising_without_conditional_review(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="- Назначить ответственного.",
            passport_blockers=["Назначить ответственного."],
            blocked_chain=True,
            result_type="рекламное чтение",
            applicable_reviews=[],
            m6c="not_applicable",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_accepts_advertising_with_conditional_review(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="- Назначить ответственного.",
            passport_blockers=["Назначить ответственного."],
            blocked_chain=True,
            result_type="рекламное чтение",
            applicable_reviews=["advertising"],
            m6c="complete",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_accepts_blocked_conditional_review(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="- Проверить приватность.",
            passport_blockers=["Проверить приватность."],
            blocked_chain=True,
            applicable_reviews=["privacy"],
            m6c="blocked",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_rejects_blocked_m6c_without_applicable_review(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="- Проверить приватность.",
            passport_blockers=["Проверить приватность."],
            blocked_chain=True,
            applicable_reviews=[],
            m6c="blocked",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_non_string_block_applicable_review(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="- Проверить приватность.",
            passport_blockers=["Проверить приватность."],
            blocked_chain=True,
            applicable_reviews=["privacy"],
            m6c="blocked",
        ).replace('applicable_reviews: ["privacy"]', "applicable_reviews:\n  - null")
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_null_applicable_reviews(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="- Назначить ответственного.",
            passport_blockers=["Назначить ответственного."],
            blocked_chain=True,
        ).replace("applicable_reviews: []", "applicable_reviews: null")
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_bare_applicable_reviews(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="- Назначить ответственного.",
            passport_blockers=["Назначить ответственного."],
            blocked_chain=True,
        ).replace("applicable_reviews: []", "applicable_reviews:")
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_scalar_applicable_reviews(self) -> None:
        content = result_text(
            status="готово к допуску",
            approver="Мария Петрова",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
        ).replace("applicable_reviews: []", "applicable_reviews: privacy")
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_missing_applicable_reviews_field(self) -> None:
        content = result_text(
            status="готово к допуску",
            approver="Мария Петрова",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
        ).replace("applicable_reviews: []\n", "")
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_both_m8_branches_complete(self) -> None:
        content = result_text(
            status="готово к допуску",
            approver="Мария Петрова",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=False,
            m8b="complete",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_accepts_required_review_with_inline_blocker(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=True,
        ).replace("blockers:[]", 'blockers: ["Дата не подтверждена"]')
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_rejects_non_string_block_list_blocker(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="- Подтвердить дату.",
            passport_blockers=["Подтвердить дату."],
            blocked_chain=True,
        ).replace('  - "Подтвердить дату."', "  - null")
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_unclosed_inline_blocker(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="- Подтвердить дату.",
            passport_blockers=[],
            blocked_chain=True,
        ).replace("blockers:[]", "blockers: [")
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_malformed_inline_blocker(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=True,
        ).replace("blockers:[]", "blockers: [not valid]")
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_required_review_without_listed_blocker(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="Нет.",
            passport_blockers=[],
            blocked_chain=True,
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)

    def test_rejects_service_marker_in_presenter_block(self) -> None:
        content = result_text(
            status="требуется проверка",
            approver="ответственный не назначен",
            editor_blockers="- Подтвердить дату.",
            passport_blockers=["Подтвердить дату."],
            blocked_chain=True,
            presenter="НЕ ЧИТАТЬ ДО ПРОВЕРКИ [двенадцатого / тринадцатого] сентября.",
        )
        result = self.validate_text(content)
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertGreaterEqual(len(payload["errors"]), 2)


class PackageValidatorTest(unittest.TestCase):
    def test_public_package_is_valid(self) -> None:
        result = run_script("validate_package.py", str(PLUGIN_ROOT))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(json.loads(result.stdout)["valid"])

        marketplace_path = PLUGIN_ROOT / ".agents" / "plugins" / "marketplace.json"
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        plugin = next(
            entry for entry in marketplace["plugins"] if entry["name"] == "radiofest-on-air-editor"
        )
        self.assertEqual(plugin["source"]["path"], "./")
        self.assertEqual(plugin["policy"]["installation"], "INSTALLED_BY_DEFAULT")
        self.assertEqual(plugin["policy"]["authentication"], "ON_INSTALL")

        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(
            manifest["repository"],
            "https://github.com/Brain1917/radiofest-on-air-editor",
        )

    def test_ignores_git_repository_metadata(self) -> None:
        validator = load_script("validate_package.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / ".git" / "index"
            metadata.parent.mkdir(parents=True)
            metadata.write_bytes(bytes([255, 254, 0]))
            findings = validator.scan_private_material(root, ())
        self.assertEqual(findings, [])

    def test_detects_generated_bytecode(self) -> None:
        validator = load_script("validate_package.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "tests" / "__pycache__" / "leak.pyc"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"compiled")
            findings = validator.scan_private_material(root, ())
        self.assertTrue(any("generated Python bytecode" in item for item in findings))

    def test_detects_private_text_and_caller_term(self) -> None:
        validator = load_script("validate_package.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.txt"
            absolute_path = "/" + "Users" + "/private/work/file.txt"
            source.write_text(absolute_path + " private-client-code", encoding="utf-8")
            findings = validator.scan_private_material(root, ("private-client-code",))
        self.assertGreaterEqual(len(findings), 2)

    def test_detects_sensitivity_marker(self) -> None:
        validator = load_script("validate_package.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = "INTERNAL" + "_ONLY"
            (root / "sample.txt").write_text(marker, encoding="utf-8")
            findings = validator.scan_private_material(root, ())
        self.assertEqual(len(findings), 1)

    def test_detects_common_secret(self) -> None:
        validator = load_script("validate_package.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = "sk" + "-proj-" + "A1b2C3d4E5f6G7h8I9j0"
            (root / "secret.txt").write_text(token, encoding="utf-8")
            findings = validator.scan_private_material(root, ())
        self.assertEqual(len(findings), 1)

    def test_rejects_binary_content_with_text_extension(self) -> None:
        validator = load_script("validate_package.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload.txt").write_bytes(bytes([255, 254, 0]))
            findings = validator.scan_private_material(root, ())
        self.assertEqual(len(findings), 1)
        self.assertIn("invalid UTF-8", findings[0])

    def test_rejects_unknown_binary_file(self) -> None:
        validator = load_script("validate_package.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload.bin").write_bytes(b"opaque")
            findings = validator.scan_private_material(root, ())
        self.assertEqual(len(findings), 1)
        self.assertIn("unexpected non-text file", findings[0])


if __name__ == "__main__":
    unittest.main()
