#!/usr/bin/env python3
"""Validate the three-part Markdown result of the on-air text skill."""

from __future__ import annotations

import argparse
import ast
import json
import re
from datetime import datetime
from pathlib import Path

ALLOWED_STATUSES = {
    "требуется проверка",
    "готово к допуску",
    "допущено человеком",
}
CHAIN_KEYS = (
    "M1",
    "M2",
    "M3",
    "M4",
    "M5",
    "M6A",
    "M6B",
    "M6C",
    "M7",
    "M8A",
    "M8B",
    "M9",
    "M10",
    "M11",
)
ALLOWED_CHAIN_STATES = {"complete", "blocked", "not_applicable"}
ALWAYS_REQUIRED_CHAIN_KEYS = {
    "M1",
    "M2",
    "M3",
    "M4",
    "M5",
    "M6A",
    "M6B",
    "M9",
    "M10",
    "M11",
}
EDITOR_SECTIONS = {
    "задача",
    "источники",
    "утверждения",
    "рисковые сущности",
    "преобразованные формы",
    "разбивка времени",
    "противоречия и неопределённость",
    "допущения",
    "блокеры",
    "изменения",
}
NULL_VALUES = {"", "null", "none", "[]", "нет", "-"}


def section(text: str, heading_pattern: str, next_heading: str) -> str:
    """Return text between two second-level Markdown headings."""
    match = re.search(
        rf"^## (?:{heading_pattern})\s*$([\s\S]*?)(?=^## (?:{next_heading})\s*$|\Z)",
        text,
        flags=re.MULTILINE,
    )
    return "" if match is None else match.group(1).strip()


def normalize_heading(line: str) -> str:
    """Normalize Markdown or plain editor-card section headings."""
    return line.lstrip("#").strip().rstrip(".:").casefold()


def editor_subsection(editor: str, name: str) -> str:
    """Extract a named editor-card subsection."""
    lines = editor.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        normalized = normalize_heading(line)
        if normalized == name.casefold():
            start = index + 1
            continue
        if start is not None and normalized in EDITOR_SECTIONS:
            return "\n".join(lines[start:index]).strip()
    return "" if start is None else "\n".join(lines[start:]).strip()


def scalar(passport: str, key: str) -> str | None:
    """Read a simple top-level YAML scalar from the passport block."""
    match = re.search(rf"^{re.escape(key)}:\s*(.*?)\s*$", passport, re.MULTILINE)
    if match is None:
        return None
    return match.group(1).strip().strip('"').strip("'")


def yaml_list(passport: str, key: str) -> list[str]:
    """Read a strict block or inline YAML-like string list."""
    key_match = re.search(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", passport, re.MULTILINE)
    if key_match is None:
        return []
    raw_value = key_match.group(1).strip()
    if raw_value:
        if not (raw_value.startswith("[") and raw_value.endswith("]")):
            return ["<invalid-inline-list>"]
        try:
            value = ast.literal_eval(raw_value)
        except (SyntaxError, ValueError):
            return ["<invalid-inline-list>"]
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        return ["<invalid-inline-list>"]

    lines = passport.splitlines()
    start = next(
        index + 1
        for index, line in enumerate(lines)
        if re.fullmatch(rf"{re.escape(key)}:\s*", line)
    )
    values: list[str] = []
    for line in lines[start:]:
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*:", line) or line.strip() == "```":
            break
        if not line.strip():
            continue
        item = re.fullmatch(r"\s*-\s+(.+)", line)
        if item is None:
            return ["<invalid-inline-list>"]
        try:
            parsed_item = ast.literal_eval(item.group(1).strip())
        except (SyntaxError, ValueError):
            return ["<invalid-inline-list>"]
        if not isinstance(parsed_item, str):
            return ["<invalid-inline-list>"]
        values.append(parsed_item)
    return values if values else ["<invalid-inline-list>"]


def has_top_level_key(passport: str, key: str) -> bool:
    """Return whether a top-level YAML key is present."""
    return re.search(rf"^{re.escape(key)}:", passport, re.MULTILINE) is not None


def is_valid_iso_datetime(value: str) -> bool:
    """Validate a real ISO 8601 timestamp with an explicit timezone."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def chain_state(passport: str) -> dict[str, str]:
    """Read M1-M11 state entries from the passport."""
    states: dict[str, str] = {}
    for key in CHAIN_KEYS:
        match = re.search(rf"^\s+{re.escape(key)}:\s*(\S+)\s*$", passport, re.MULTILINE)
        if match:
            states[key] = match.group(1).strip().strip('"').strip("'")
    return states


def has_blockers(editor: str, passport: str) -> bool:
    """Return whether either structured blocker list contains a real blocker."""
    editor_blockers = editor_subsection(editor, "Блокеры")
    editor_values = [
        line.lstrip("- ").strip().rstrip(".").casefold()
        for line in editor_blockers.splitlines()
        if line.strip()
    ]
    meaningful_editor = any(value not in NULL_VALUES for value in editor_values)
    passport_values = [value.rstrip(".").casefold() for value in yaml_list(passport, "blockers")]
    meaningful_passport = any(value not in NULL_VALUES for value in passport_values)
    return meaningful_editor or meaningful_passport


def validate_chain(
    states: dict[str, str],
    status: str,
    earliest_blocker: str | None,
    result_type: str,
    applicable_reviews: list[str],
) -> list[str]:
    """Validate chain completeness and OR/conditional semantics."""
    errors: list[str] = []
    missing = [key for key in CHAIN_KEYS if key not in states]
    if missing:
        errors.append("В chain_state нет звеньев: " + ", ".join(missing))
        return errors
    invalid = [
        f"{key}={value}" for key, value in states.items() if value not in ALLOWED_CHAIN_STATES
    ]
    if invalid:
        errors.append("Недопустимые состояния chain_state: " + ", ".join(invalid))

    for key in ALWAYS_REQUIRED_CHAIN_KEYS:
        if states.get(key) == "not_applicable":
            errors.append(f"Обязательное звено {key} не может быть not_applicable.")

    m8_values = (states.get("M8A"), states.get("M8B"))
    if m8_values.count("complete") != 1 or m8_values.count("not_applicable") != 1:
        errors.append("Ровно одна ветка M8A/M8B должна быть complete, другая not_applicable.")

    earliest_is_null = earliest_blocker is None or earliest_blocker.casefold() in NULL_VALUES
    blocked_keys = [key for key in CHAIN_KEYS if states.get(key) == "blocked"]
    if blocked_keys and not earliest_is_null:
        declared = earliest_blocker.split(":", 1)[0].strip() if earliest_blocker else ""
        if declared != blocked_keys[0]:
            errors.append(
                f"earliest_blocker должен начинаться с {blocked_keys[0]}, "
                f"получено {declared or '<empty>'}."
            )
    if result_type == "рекламное чтение" and "advertising" not in applicable_reviews:
        errors.append("Рекламное чтение требует applicable_reviews: advertising.")
    if applicable_reviews:
        if states.get("M6C") not in {"complete", "blocked"}:
            errors.append("Непустые applicable_reviews требуют M6C: complete или blocked.")
    elif states.get("M6C") != "not_applicable":
        errors.append("Пустые applicable_reviews требуют M6C: not_applicable.")
    if status in {"готово к допуску", "допущено человеком"}:
        if blocked_keys:
            errors.append("Статус готовности запрещён при blocked: " + ", ".join(blocked_keys))
        if not earliest_is_null:
            errors.append("Статус готовности требует earliest_blocker: null.")
        for key in ALWAYS_REQUIRED_CHAIN_KEYS:
            if states.get(key) != "complete":
                errors.append(f"Статус готовности требует {key}: complete.")
        if states.get("M6C") not in {"complete", "not_applicable"}:
            errors.append("M6C должен быть complete или not_applicable.")
        if states.get("M7") not in {"complete", "not_applicable"}:
            errors.append("M7 должен быть complete или not_applicable.")
    elif status == "требуется проверка":
        if not blocked_keys:
            errors.append("Статус 'требуется проверка' должен содержать blocked в chain_state.")
        if earliest_is_null:
            errors.append("Статус 'требуется проверка' должен указывать earliest_blocker.")
    return errors


def validate(text: str) -> tuple[list[str], list[str]]:
    """Return blocking errors and non-blocking warnings."""
    errors: list[str] = []
    warnings: list[str] = []
    presenter = section(text, "Эфирный лист|Разговорная карточка", "Редакторская карточка")
    editor = section(text, "Редакторская карточка", "Паспорт мастер-версии")
    passport = section(text, "Паспорт мастер-версии", r"(?!x)x")

    if not presenter:
        errors.append("Нет эфирного листа или разговорной карточки.")
    if not editor:
        errors.append("Нет редакторской карточки.")
    if not passport:
        errors.append("Нет паспорта мастер-версии.")
    if re.search(r"https?://|\]\(", presenter):
        errors.append("В блоке ведущего найдена ссылка или Markdown-ссылка.")
    if "НЕ ЧИТАТЬ ДО ПРОВЕРКИ" in presenter:
        errors.append("В блоке ведущего найден служебный маркер проверки.")
    if re.search(r"\[[^\]\n]+\s+/\s+[^\]\n]+\]", presenter):
        errors.append("В блоке ведущего найден незакрытый выбор вариантов.")

    for name in ("Источники", "Рисковые сущности", "Блокеры"):
        if editor and editor_subsection(editor, name) == "":
            errors.append(f"В редакторской карточке нет раздела: {name}.")

    values = {
        key: scalar(passport, key)
        for key in ("version_id", "updated_at", "status", "result_type", "approver")
    }
    for key in ("version_id", "updated_at", "status", "result_type", "approver"):
        value = values[key]
        if value is None or value.casefold() in NULL_VALUES:
            errors.append(f"В паспорте нет непустого поля: {key}.")

    status = values["status"] or ""
    if status not in ALLOWED_STATUSES:
        errors.append("Недопустимый status: " + (status or "<empty>"))
    approver_value = values["approver"] or ""
    approver = approver_value.casefold()
    blockers_present = has_blockers(editor, passport)
    earliest = scalar(passport, "earliest_blocker")
    applicable_reviews = yaml_list(passport, "applicable_reviews")
    if not has_top_level_key(passport, "applicable_reviews"):
        errors.append("В паспорте нет поля applicable_reviews.")
    if "<invalid-inline-list>" in applicable_reviews:
        errors.append("Поле applicable_reviews содержит невалидный inline-список.")
    passport_blockers = yaml_list(passport, "blockers")
    if "<invalid-inline-list>" in passport_blockers:
        errors.append("Поле blockers содержит невалидный inline-список.")
    errors.extend(
        validate_chain(
            chain_state(passport),
            status,
            earliest,
            values["result_type"] or "",
            applicable_reviews,
        )
    )

    if status in {"готово к допуску", "допущено человеком"}:
        errors.append(
            "Instruction-only пакет не может подтвердить статус готовности. "
            "Его устанавливает только доверенная host-система."
        )
        if blockers_present:
            errors.append("Статус готовности запрещён при непустом списке блокеров.")
    if status == "требуется проверка" and not blockers_present:
        errors.append("Статус 'требуется проверка' требует содержательного списка блокеров.")
    if status == "допущено человеком":
        confirmed_by = scalar(passport, "approval_confirmed_by") or ""
        confirmed_version = scalar(passport, "approval_confirmed_version") or ""
        confirmed_at = scalar(passport, "approval_confirmed_at") or ""
        version_id = values["version_id"] or ""
        if confirmed_by.casefold() != approver:
            errors.append("approval_confirmed_by должен совпадать с approver.")
        if confirmed_version != version_id:
            errors.append("approval_confirmed_version должен совпадать с version_id.")
        if not is_valid_iso_datetime(confirmed_at):
            errors.append(
                "approval_confirmed_at должен содержать действительное время ISO 8601 "
                "с часовым поясом."
            )

    if "permitted_cut_points" not in passport:
        warnings.append("Не указаны разрешённые точки сокращения.")
    return errors, warnings


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="Markdown-файл результата.")
    return parser.parse_args()


def main() -> int:
    """Run the output validator CLI."""
    args = parse_args()
    try:
        text = args.file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(json.dumps({"valid": False, "errors": [str(error)]}, ensure_ascii=False))
        return 1
    errors, warnings = validate(text)
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
