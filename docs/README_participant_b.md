# Консультант МТС EnergyTool · участник Б

`consultation_agent/` содержит модели данных, чтение базы знаний, поиск, подготовку и проверку ответов и команду локального поиска. Публичные точки входа — `SearchIndex`, `parse_question` и `consult`. Тесты консультанта находятся в `tests/test_energytool_rag.py`.

Сборщик сабмита берёт корневой `energytool_rag.py`. Этот файл генерируется из пакета и работает после распаковки ZIP без каталогов исходного проекта. После правок пакета обновляйте корневой модуль.

```powershell
python scripts/export_consultation.py
python scripts/export_consultation.py --check
```

Локальная проверка на материалах организаторов.

```powershell
$env:ENERGYTOOL_QA_DATA = "$env:USERPROFILE/Downloads"
python -B -X utf8 -m unittest discover -s tests -p test_energytool_rag.py -v
python -B -X utf8 energytool_rag.py "$env:ENERGYTOOL_QA_DATA/knowledge-base.zip" --question "Что нужно для оценки проекта учёта?"
```

Отчёты по работе Б — [день 1](DAY1_B.md), [день 2](DAY2_B.md), [день 3](DAY3_B.md).
