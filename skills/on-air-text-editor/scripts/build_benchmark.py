#!/usr/bin/env python3
"""Build a reproducible eval benchmark from result and grade artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

sys.dont_write_bytecode = True


def load_json(path: Path) -> dict[str, object]:
    """Load and validate a JSON object."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Ожидался JSON-объект: {path}")
    return data


def load_output_validator() -> ModuleType:
    """Load the sibling output validator without package dependencies."""
    path = Path(__file__).with_name("validate_output.py")
    spec = importlib.util.spec_from_file_location("on_air_validate_output", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось загрузить {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def file_digest(path: Path) -> str:
    """Return a SHA-256 digest for an artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def grade_status(grade: dict[str, object]) -> str:
    """Read the overall status used by independent grade files."""
    value = grade.get("overallStatus", grade.get("result"))
    return value if isinstance(value, str) else "UNKNOWN"


def assertion_statuses(grade: dict[str, object]) -> list[str]:
    """Return assertion statuses from a grade file."""
    assertions = grade.get("assertions")
    if not isinstance(assertions, list):
        return []
    statuses: list[str] = []
    for item in assertions:
        if isinstance(item, dict) and isinstance(item.get("status"), str):
            statuses.append(item["status"])
    return statuses


def resolve(project_root: Path, value: object) -> Path:
    """Resolve a manifest path relative to the project root."""
    if not isinstance(value, str) or not value:
        raise ValueError("Путь в run-manifest должен быть непустой строкой.")
    return project_root / value


def build(project_root: Path, manifest_path: Path) -> dict[str, object]:
    """Build benchmark data from current files instead of trusting a summary."""
    manifest = load_json(manifest_path)
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("В run-manifest нет cases.")
    validator = load_output_validator()
    case_results: dict[str, object] = {}
    passed = 0
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise ValueError("Каждый case должен содержать строковый id.")
        case_id = case["id"]
        result_path = resolve(project_root, case.get("result"))
        grade_path = resolve(project_root, case.get("grade"))
        input_path = resolve(project_root, case.get("input"))
        for path in (result_path, grade_path, input_path):
            if not path.is_file():
                raise ValueError(f"Не найден артефакт: {path}")
        output_errors, output_warnings = validator.validate(result_path.read_text(encoding="utf-8"))
        grade = load_json(grade_path)
        statuses = assertion_statuses(grade)
        assertions_pass = bool(statuses) and all(status == "PASS" for status in statuses)
        grade_pass = grade_status(grade) == "PASS"
        case_pass = not output_errors and grade_pass and assertions_pass
        if case_pass:
            passed += 1
        case_results[case_id] = {
            "passed": case_pass,
            "output_validator_errors": output_errors,
            "output_validator_warnings": output_warnings,
            "grade_status": grade_status(grade),
            "assertions_passed": sum(status == "PASS" for status in statuses),
            "assertions_total": len(statuses),
            "hashes": {
                "input_sha256": file_digest(input_path),
                "result_sha256": file_digest(result_path),
                "grade_sha256": file_digest(grade_path),
            },
        }
    skill_path = resolve(project_root, manifest.get("skill"))
    evals_path = resolve(project_root, manifest.get("evals"))
    return {
        "skill_version": manifest.get("skill_version"),
        "provider": manifest.get("provider"),
        "model": manifest.get("model"),
        "context_mode": manifest.get("context_mode"),
        "skill_sha256": file_digest(skill_path),
        "evals_sha256": file_digest(evals_path),
        "cases": case_results,
        "summary": {
            "passed": passed,
            "total": len(cases),
            "all_passed": passed == len(cases),
        },
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Build or verify the benchmark."""
    args = parse_args()
    try:
        project_root = args.project_root.resolve()
        benchmark = build(project_root, args.manifest.resolve())
        if args.check:
            if args.output is None or not args.output.is_file():
                raise ValueError("Для --check нужен существующий --output.")
            expected = load_json(args.output)
            if benchmark != expected:
                raise ValueError("Benchmark устарел: пересчитанный результат отличается.")
        elif args.output is not None:
            args.output.write_text(
                json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"valid": True, "summary": benchmark["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
