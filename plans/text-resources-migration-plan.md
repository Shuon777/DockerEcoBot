# План внедрения изменений текстовых ресурсов в AdminPanel/main.py

## Цель
Перенести из `AdminPaneledited/AdminPanel/main.py` в `AdminPanel/main.py` изменения, связанные с обработкой текстовых ресурсов, сохранив при этом уже существующие улучшения (приоритеты синонимов, нормализация, `_primary_synonym()`, блок управления синонимами).

## Изменения (в порядке внесения)

### 1. Добавить новые константы (после строки 64)
```python
PROP_BIO_TYPE = "Тип ОФФ"
CATALOG_BIO_TYPE = PROP_BIO_TYPE.lower()
```

### 2. Добавить функцию `_text_value_display()` (после `_create_resource_scaffold`, перед `_attach_text_to_object`)
Новая функция, которая классифицирует `TextValue.structured_data`:
- Если словарь ровно с одним ключом-строкой → "обычный текст" (возвращает `content`, `content_key`)
- Иначе → "структурированные данные" (возвращает `structured_data`)

### 3. Добавить функцию `_apply_text_value_edit()` (после `_text_value_display()`)
Применяет правки из формы редактирования:
- Если пришёл `structured_json` → парсит и сохраняет как есть
- Иначе → сохраняет обычный текст под исходным ключом (`content_key`)

### 4. Обновить `biological_edit()` (строки 777-909)
**Что меняется:**
- Обработка текстов: вместо `sd.get("description")` использовать `_text_value_display(sd)` и передавать в шаблон `content`, `content_key`, `structured_data`
- В `available_properties`: добавить специальный случай для `PROP_BIO_TYPE`

**Что НЕ меняется (сохраняется):**
- Сортировка синонимов по `priority` (строка 793)
- Вызов `_primary_synonym(list(synonyms), props)` с двумя аргументами

### 5. Обновить `edit_biological_text_resource()` (строки 1050-1071)
**Что меняется:**
- Параметр `content: str = Form(...)` → `content: str = Form(None)`
- Добавить `content_key: str = Form(None)` и `structured_json: str = Form(None)`
- Вместо `tv.structured_data = {"description": content}` → `_apply_text_value_edit(tv, content, content_key, structured_json)`

### 6. Обновить `geographical_edit()` (строки 1804-1958)
**Что меняется:**
- Обработка текстов: использовать `_text_value_display(sd)` вместо `sd.get("description")`

**Что НЕ меняется:**
- Сортировка синонимов по `priority` (строка 1822)
- Вызов `_primary_synonym(list(synonyms), obj.object_properties or {})` с двумя аргументами

### 7. Обновить `edit_geographical_text_resource()` (строки 2238-2260)
**Что меняется:**
- Параметр `content: str = Form(...)` → `content: str = Form(None)`
- Добавить `content_key`, `structured_json`
- Использовать `_apply_text_value_edit()`

### 8. Обновить `service_edit()` (строки 2597-2715)
**Что меняется:**
- Обработка текстов: использовать `_text_value_display(sd)` вместо `sd.get("description")`

**Что НЕ меняется:**
- Сортировка синонимов по `priority` (строка 2610)
- Вызов `_primary_synonym(list(synonyms), obj.object_properties or {})` с двумя аргументами

### 9. Обновить `edit_service_text_resource()` (строки 3045-3063)
**Что меняется:**
- Параметр `content: str = Form(...)` → `content: str = Form(None)`
- Добавить `content_key`, `structured_json`
- Использовать `_apply_text_value_edit()`

## Что НЕ нужно менять (уже есть в вашем коде и должно остаться)

| Функция/блок | Строки | Почему сохраняем |
|---|---|---|
| `biological_save()` | 728-774 | Уже есть `props["Вид (русское название)"]`, нормализация синонима, `priority=1` |
| `geographical_save()` | 1757-1801 | Уже есть нормализация синонима, `priority=1` |
| `service_save()` | 2557-2594 | Уже есть `props["Название услуги"]`, нормализация, `priority=1` |
| `_biological_list_impl()` primary_name_sq | 510-518 | Сортировка по `priority.asc()` |
| `geographical_list()` primary_name_sq | 1582-1590 | Сортировка по `priority.asc()` |
| `service_list()` primary_name_sq | 2398-2406 | Сортировка по `priority.asc()` |
| `_primary_synonym()` | 1449-1468 | Сложная логика с поиском по `object_properties` и кириллице |
| Блок управления синонимами | 3912-4077 | `_update_synonyms_impl()`, `_normalize_synonym()`, endpoints |
| Импорт `update` | 21 | Нужен для `_update_synonyms_impl()` |

## Проверка после внедрения

1. Файл должен импортироваться без ошибок (`python -c "import ast; ast.parse(open('AdminPanel/main.py').read())"`)
2. Все старые endpoints должны работать (проверить biological, geographical, service CRUD)
3. Редактирование текстовых ресурсов должно поддерживать как простой текст, так и структурированные данные
4. Синонимы должны сохранять приоритеты и нормализацию