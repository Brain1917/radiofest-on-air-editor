# Эфирный редактор

Один устанавливаемый Agent Skill для подготовки русского текста к прямому эфиру. Пользователь описывает задачу обычным языком и прикладывает текстовые материалы. Скилл сам выбирает эфирный лист, разговорную карточку или рекламную ветку.

## Результат

Скилл выдаёт:

1. Эфирный лист или разговорную карточку.
2. Редакторскую карточку с источниками и рисками.
3. Паспорт мастер-версии для человеческого допуска.

## Граница

Скилл работает с текстом, документами, таблицами, ссылками и готовыми расшифровками. Он не расшифровывает аудио, не создаёт голос, не монтирует, не публикует и не управляет эфирной системой.

## Структура

```text
radiofest-on-air-editor/
├── .agents/plugins/marketplace.json
├── .codex-plugin/plugin.json
├── skills/on-air-text-editor/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── references/
│   ├── assets/
│   ├── scripts/
│   └── evals/
└── README.md
```

## Проверка пакета

```bash
python3 skills/on-air-text-editor/scripts/validate_package.py .
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Проверка официальной библиотекой `skills-ref`:

```bash
uvx --from skills-ref agentskills validate skills/on-air-text-editor
```

## Установка из GitHub

Клонируйте репозиторий:

```bash
git clone https://github.com/Brain1917/radiofest-on-air-editor.git
```

В Codex подключите репозиторий как marketplace:

```bash
codex plugin marketplace add Brain1917/radiofest-on-air-editor
```

В ChatGPT Desktop добавьте GitHub-репозиторий как источник плагинов, перезапустите приложение и выберите каталог "Radiofest On-Air Editor" в Plugins Directory. Самодостаточная запись находится в `.agents/plugins/marketplace.json`; она объявляет плагин `radiofest-on-air-editor` с `source.path: "./"`.

Marketplace задаёт `policy.installation: "INSTALLED_BY_DEFAULT"`. Поддерживающий эту политику клиент устанавливает плагин при подключении marketplace. Поле `policy.authentication` имеет значение `ON_INSTALL`, но сам instruction-only плагин не подключается к внешнему сервису и не запрашивает его учётные данные.

Неявный запуск разрешён через `policy.allow_implicit_invocation: true`, но модель может не выбрать скилл для подходящего запроса. Проверяйте описание на целевой модели; `@` остаётся резервным способом.

Перед упаковкой удалите `__pycache__`, `*.pyc`, `.DS_Store` и кэши тестов. Локальный валидатор отклоняет такие файлы.

Сам пакет не отправляет данные внешнему сервису. Доступ к файлам, срок хранения, область памяти и удаление данных определяет среда ChatGPT. Скилл запрещает сохранять секреты, закрытые исходники и лишние персональные данные.

## Лицензия

Пакет распространяется по лицензии MIT. Полный текст находится в `LICENSE.txt` и `skills/on-air-text-editor/LICENSE.txt`.

## Готовность

Версия 0.1.0 является рабочим прототипом. Публичная готовность наступает только после сквозных тестов, независимого Review, Judge PASS и проверки установки на целевом аккаунте.
