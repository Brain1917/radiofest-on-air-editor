#!/usr/bin/env python3
"""Validate the public Radiofest plugin package and scan for private material."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PLUGIN_FIELDS = {"name", "version", "description", "skills"}
REQUIRED_SKILL_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/editorial-principles.md",
    "references/workflow.md",
    "references/governance.md",
    "references/risk-rules.md",
    "references/pronunciation.md",
    "references/advertising.md",
    "assets/on-air-script.md",
    "assets/conversation-card.md",
    "assets/editor-card.md",
    "assets/master-passport.md",
    "scripts/estimate_duration.py",
    "scripts/validate_output.py",
    "scripts/build_benchmark.py",
)
TEXT_SUFFIXES = {
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".py",
    ".toml",
    ".txt",
    ".tsv",
    ".svg",
}
ALLOWED_EXTENSIONLESS_FILES = {".gitignore"}
PRIVATE_PATTERNS = {
    "absolute macOS user path": re.compile(r"/Users/[^/\s]+/"),
    "Windows user path": re.compile(r"[A-Za-z]:\\Users\\"),
    "sha256-like digest": re.compile(r"\b[a-f0-9]{64}\b", re.IGNORECASE),
    "confidential marker": re.compile(
        r"CONFIDENTIAL[-_ ]MATERIAL|DO[-_ ]NOT[-_ ]DISTRIBUTE|INTERNAL[-_ ]ONLY",
        re.IGNORECASE,
    ),
    "OpenAI-like token": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub-like token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "Slack-like token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "assigned secret": re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*[\"']?[A-Za-z0-9_-]{12,}",
        re.IGNORECASE,
    ),
}


def load_json(path: Path) -> tuple[dict[str, object] | None, str | None]:
    """Load a JSON object and return an error message instead of raising."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return None, str(error)
    if not isinstance(data, dict):
        return None, "Корневое значение JSON должно быть объектом."
    return data, None


def frontmatter(skill_file: Path) -> tuple[dict[str, str], str | None]:
    """Parse simple scalar YAML frontmatter used by this skill."""
    try:
        text = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return {}, str(error)
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return {}, "SKILL.md не содержит корректные границы frontmatter."
    raw = text.split("\n---\n", 1)[0][4:]
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line[0].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values, None


def scan_private_material(
    plugin_root: Path,
    forbidden_terms: tuple[str, ...],
) -> list[str]:
    """Find generated files, private paths, identifiers, and forbidden terms."""
    findings: list[str] = []
    validator_path = Path(__file__).resolve()
    for path in sorted(plugin_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(plugin_root)
        if ".git" in relative.parts:
            continue
        if "__pycache__" in path.parts or path.suffix.lower() in {".pyc", ".pyo"}:
            findings.append(f"{relative}: generated Python bytecode")
            continue
        if path.name == ".DS_Store":
            findings.append(f"{relative}: generated macOS metadata")
            continue
        if path.resolve() == validator_path:
            continue
        if (
            path.suffix.lower() not in TEXT_SUFFIXES
            and path.name not in ALLOWED_EXTENSIONLESS_FILES
        ):
            findings.append(f"{relative}: unexpected non-text file")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            findings.append(f"{relative}: invalid UTF-8 in declared text file")
            continue
        for label, pattern in PRIVATE_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{relative}: {label}")
        folded = text.casefold()
        for term in forbidden_terms:
            pattern = re.compile(rf"(?<!\w){re.escape(term.casefold())}(?!\w)")
            if pattern.search(folded):
                findings.append(f"{relative}: forbidden term")
    return findings


def validate(
    plugin_root: Path,
    forbidden_terms: tuple[str, ...] = (),
) -> tuple[list[str], list[str]]:
    """Validate package structure, metadata, and privacy boundaries."""
    errors: list[str] = []
    warnings: list[str] = []
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    manifest, manifest_error = load_json(manifest_path)
    if manifest_error:
        errors.append(f"plugin.json: {manifest_error}")
        return errors, warnings
    assert manifest is not None

    missing_fields = sorted(PLUGIN_FIELDS - manifest.keys())
    if missing_fields:
        errors.append("plugin.json: нет полей " + ", ".join(missing_fields))
    if manifest.get("skills") != "./skills/":
        errors.append('plugin.json: skills должно быть "./skills/".')

    skills_dir = plugin_root / "skills"
    skill_dirs = (
        sorted(path for path in skills_dir.iterdir() if path.is_dir())
        if skills_dir.is_dir()
        else []
    )
    if len(skill_dirs) != 1:
        errors.append(f"Пакет должен содержать один скилл, найдено: {len(skill_dirs)}.")
        return errors, warnings

    skill_dir = skill_dirs[0]
    metadata, metadata_error = frontmatter(skill_dir / "SKILL.md")
    if metadata_error:
        errors.append(metadata_error)
    else:
        name = metadata.get("name", "")
        description = metadata.get("description", "")
        if name != skill_dir.name:
            errors.append("Имя скилла и название каталога не совпадают.")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            errors.append("Имя скилла нарушает формат kebab-case.")
        if not 1 <= len(description) <= 1024:
            errors.append("Description должен содержать от 1 до 1024 символов.")

    for relative in REQUIRED_SKILL_FILES:
        if not (skill_dir / relative).is_file():
            errors.append(f"Нет обязательного файла: {relative}")

    openai_file = skill_dir / "agents" / "openai.yaml"
    try:
        openai_text = openai_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        errors.append(f"openai.yaml: {error}")
    else:
        for token in (
            "interface:",
            "display_name:",
            "short_description:",
            "policy:",
            "allow_implicit_invocation: true",
        ):
            if token not in openai_text:
                errors.append(f"openai.yaml: нет {token}")

    private_findings = scan_private_material(plugin_root, forbidden_terms)
    errors.extend(f"Закрытый материал: {finding}" for finding in private_findings)

    if not (plugin_root / "README.md").is_file():
        warnings.append("Нет README.md.")
    return errors, warnings


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    default_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin_root", nargs="?", type=Path, default=default_root)
    parser.add_argument(
        "--forbidden-term",
        action="append",
        default=[],
        help="Дополнительный закрытый термин. Можно передать несколько раз.",
    )
    return parser.parse_args()


def main() -> int:
    """Run package validation and print JSON."""
    args = parse_args()
    errors, warnings = validate(
        args.plugin_root.resolve(),
        tuple(args.forbidden_term),
    )
    print(
        json.dumps(
            {"valid": not errors, "errors": errors, "warnings": warnings},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
