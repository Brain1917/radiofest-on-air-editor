# Паспорт мастер-версии

```yaml
version_id: "YYYYMMDD-HHMM-v1"
updated_at: "YYYY-MM-DD HH:MM TZ"
status: "требуется проверка | готово к допуску | допущено человеком"
result_type: "эфирный лист | разговорная карточка | рекламное чтение"
source_set: []
approver: "ответственный не назначен"
approval_confirmed_by: null
approval_confirmed_version: null
approval_confirmed_at: null
duration_seconds: null
presenter_wpm: null
applicable_reviews: []
chain_state:
  M1: complete
  M2: complete
  M3: complete
  M4: complete
  M5: complete
  M6A: complete
  M6B: complete
  M6C: not_applicable
  M7: not_applicable
  M8A: complete
  M8B: not_applicable
  M9: complete
  M10: complete
  M11: complete
earliest_blocker: null
mandatory_wording: []
permitted_cut_points: []
blockers: []
```

Правила:

- Новый факт, источник, обязательное условие или редакционное решение создаёт новую версию.
- Допуск относится только к указанному `version_id`.
- Instruction-only скилл оставляет локальный статус `требуется проверка`.
- `готово к допуску` и `допущено человеком` - host-only статусы. Их может установить только доверенная система после привязки ответственного и, для финального допуска, проверки личности и конкретного `version_id`.
- Для допуска `approval_confirmed_by` совпадает с `approver`, `approval_confirmed_version` совпадает с `version_id`, а `approval_confirmed_at` содержит время ISO 8601 с часовым поясом.
- `готово к допуску` и `допущено человеком` требуют `earliest_blocker: null` и завершённой обязательной цепочки.
- Короткая версия получает собственный идентификатор или явно связанную ревизию.
