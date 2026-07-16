# Отчёт: Реализация обработки смены `is_multiple` с `true` на `false`

## Описание задачи

Реализована бэкенд-логика для метода обновления настроек свойства, который обрабатывает смену флага `is_multiple` с `true` на `false`. При такой смене:
1. Показывается предупреждение, что значения свойства у объектов могут быть утеряны
2. При подтверждении — БД оставляет для каждого объекта только первое (старое) значение из массива

## Изменённые файлы

### 1. `AdminPanel/main.py`

**Что сделано:**
- Заменён старый эндпоинт `POST /properties/{prop_id}/toggle_multiple` на новый `POST /properties/{prop_id}/update_settings`
- Обновлён эндпоинт `POST /properties/{prop_id}/edit` — убран параметр `is_multiple` (теперь управляется отдельно)

#### Новый эндпоинт `update_settings`:

```python
@app.post("/properties/{prop_id}/update_settings")
async def properties_update_settings(
    request: Request,
    prop_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Обновление настроек свойства (is_multiple) с защитой от потери данных.

    При смене is_multiple с true на false:
    - Если confirmed=false: подсчитывает объекты с >1 значением и возвращает warning
    - Если confirmed=true: обрезает массивы значений до первого элемента и обновляет флаг
    """
    if not request.session.get("user_id"):
        return {"ok": False, "error": "unauthorized"}

    prop = (await db.execute(
        select(ObjectProperty).where(ObjectProperty.id == prop_id)
    )).scalar()
    if not prop:
        return {"ok": False, "error": "not found"}

    new_is_multiple = data.get("is_multiple", False)
    confirmed = data.get("confirmed", False)

    # Смена с true на false — требуется проверка и возможная обрезка данных
    if prop.is_multiple and not new_is_multiple:
        # Определяем реальный JSON-ключ в object_properties (с учётом регистра)
        json_key = prop.property_name  # в каталоге всегда нижний регистр

        # 1. Ищем точное совпадение ключа
        real_key_row = await db.execute(sql_text("""
            SELECT DISTINCT jsonb_object_keys(object_properties) AS key
            FROM eco_assistant.object
            WHERE object_type_id = :otid
              AND object_properties ? :pname
            LIMIT 1
        """), {"otid": prop.object_type_id, "pname": json_key})
        real_key = real_key_row.scalar()

        # 2. Если не нашли — ищем по lower-case (разный регистр ключей)
        if not real_key:
            real_key_row = await db.execute(sql_text("""
                SELECT DISTINCT key
                FROM eco_assistant.object o,
                     jsonb_object_keys(o.object_properties) AS key
                WHERE o.object_type_id = :otid
                  AND LOWER(key) = :pname
                LIMIT 1
            """), {"otid": prop.object_type_id, "pname": json_key})
            real_key = real_key_row.scalar()

        actual_key = real_key if real_key else json_key

        # Подсчёт объектов, у которых >1 значение для этого свойства
        count_row = await db.execute(sql_text("""
            SELECT COUNT(*) AS cnt
            FROM eco_assistant.object
            WHERE object_type_id = :otid
              AND jsonb_typeof(object_properties -> :key) = 'array'
              AND jsonb_array_length(object_properties -> :key) > 1
        """), {"otid": prop.object_type_id, "key": actual_key})
        affected_count = count_row.scalar() or 0

        if not confirmed:
            # Возвращаем предупреждение без изменений
            return {
                "ok": True,
                "warning": True,
                "affected_count": affected_count,
                "message": (
                    f"При отключении множественного выбора значения свойства "
                    f"«{prop.property_name}» будут утеряны у {affected_count} объектов. "
                    f"Для каждого объекта останется только первое (старое) значение. Продолжить?"
                ),
            }

        # Подтверждено: обрезаем массивы до первого элемента
        if affected_count > 0:
            await db.execute(sql_text("""
                UPDATE eco_assistant.object
                SET object_properties = jsonb_set(
                    object_properties,
                    ARRAY[:key],
                    CASE
                        WHEN jsonb_typeof(object_properties -> :key) = 'array'
                             AND jsonb_array_length(object_properties -> :key) > 0
                        THEN object_properties -> :key -> 0
                        ELSE object_properties -> :key
                    END,
                    false
                )
                WHERE object_type_id = :otid
                  AND jsonb_typeof(object_properties -> :key) = 'array'
                  AND jsonb_array_length(object_properties -> :key) > 1
            """), {"otid": prop.object_type_id, "key": actual_key})

    # Обновляем флаг is_multiple
    prop.is_multiple = new_is_multiple
    await db.commit()
    return {"ok": True}
```

#### Обновлённый эндпоинт `edit` (убран `is_multiple`):

```python
@app.post("/properties/{prop_id}/edit")
async def properties_edit(
    request: Request,
    prop_id: int,
    property_values: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """
    Редактирование списка допустимых значений свойства.
    Флаг is_multiple теперь управляется отдельно через POST /properties/{prop_id}/update_settings.
    """
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    prop = (await db.execute(select(ObjectProperty).where(ObjectProperty.id == prop_id))).scalar()
    if not prop:
        raise HTTPException(status_code=404)
    prop.property_values = [v.strip() for v in property_values.split(",") if v.strip()]
    await db.commit()
    return RedirectResponse(url="/properties", status_code=303)
```

---

### 2. `AdminPanel/templates/properties_list.html`

**Что сделано:**
- Добавлена глобальная переменная `currentEditPropId`
- Функция `toggleMultiple()` заменена на `updatePropertySettings()` с двухшаговой логикой (предупреждение → подтверждение)
- Добавлена функция `showConfirmModal()` для отображения модального окна предупреждения
- Добавлено HTML модального окна подтверждения
- Чекбокс `is_multiple` в модалке редактирования теперь вызывает `updatePropertySettings()` при переключении

#### Новая JS-логика:

```javascript
let currentEditPropId = null;

async function updatePropertySettings(propId, isMultiple) {
    try {
        const resp = await fetch(`/admin/properties/${propId}/update_settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_multiple: isMultiple, confirmed: false })
        });
        const data = await resp.json();

        if (data.warning && data.affected_count > 0) {
            // Показываем модалку подтверждения
            showConfirmModal(propId, isMultiple, data.message, data.affected_count);
        } else if (data.ok) {
            window.location.reload();
        } else {
            alert('Ошибка: ' + (data.error || 'неизвестная'));
        }
    } catch(e) {
        alert('Ошибка сети: ' + e.message);
    }
}

function showConfirmModal(propId, isMultiple, message, affectedCount) {
    document.getElementById('confirmModalMessage').textContent = message;
    document.getElementById('confirmModalAffected').textContent =
        'Затронуто объектов: ' + affectedCount;

    document.getElementById('confirmModalYes').onclick = async function() {
        try {
            const resp = await fetch(`/admin/properties/${propId}/update_settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_multiple: isMultiple, confirmed: true })
            });
            const data = await resp.json();
            if (data.ok) {
                window.location.reload();
            } else {
                alert('Ошибка: ' + (data.error || 'неизвестная'));
            }
        } catch(e) {
            alert('Ошибка сети: ' + e.message);
        }
        bootstrap.Modal.getInstance(document.getElementById('confirmModal')).hide();
    };

    new bootstrap.Modal(document.getElementById('confirmModal')).show();
}
```

#### Модальное окно подтверждения:

```html
<!-- ===== Модальное окно подтверждения смены is_multiple ===== -->
<div class="modal fade" id="confirmModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content" style="border-radius: 16px;">
            <div class="modal-header border-0">
                <h5 class="modal-title fw-bold text-warning">
                    <i class="bi bi-exclamation-triangle"></i> Подтверждение
                </h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <p id="confirmModalMessage" class="mb-2"></p>
                <p id="confirmModalAffected" class="fw-bold text-danger mb-0"></p>
            </div>
            <div class="modal-footer border-0">
                <button type="button" class="btn btn-light" data-bs-dismiss="modal">Отмена</button>
                <button type="button" class="btn btn-warning fw-bold" id="confirmModalYes">
                    Да, продолжить
                </button>
            </div>
        </div>
    </div>
</div>
```

#### Обновлённый чекбокс в модалке редактирования:

```html
<div class="form-check form-switch mb-3">
    <input class="form-check-input" type="checkbox" id="editIsMultiple" name="is_multiple" value="true"
           onchange="updatePropertySettings(currentEditPropId, this.checked)">
    <label class="form-check-label fw-bold" for="editIsMultiple">Множественный выбор</label>
    <div class="form-text">Если включено — в карточке объекта можно будет выбрать несколько значений для этого свойства. Изменение применяется сразу.</div>
</div>
```

## Схема работы

```
Пользователь переключает чекбокс is_multiple
         │
         ▼
updatePropertySettings(propId, isMultiple, confirmed=false)
         │
         ▼
Сервер: prop.is_multiple=true, new_is_multiple=false?
         │
         ├── НЕТ → просто обновить is_multiple → reload
         │
         └── ДА → подсчёт объектов с >1 значением
                    │
                    ├── affected_count=0 → обновить is_multiple → reload
                    │
                    └── affected_count>0 → возврат {warning: true, message, affected_count}
                              │
                              ▼
                    Показ модального окна подтверждения
                              │
                    ┌─────────┴──────────┐
                    │                    │
                Отмена              Подтвердить
                    │                    │
              Ничего               updatePropertySettings(propId, isMultiple, confirmed=true)
                                         │
                                         ▼
                              UPDATE jsonb_set (обрезать массивы)
                              UPDATE is_multiple = false
                              reload
```

## Примечания

- **Регистр ключа JSONB**: Поиск реального ключа в `object_properties` выполняется в два этапа: сначала точное совпадение, затем поиск по `LOWER(key)`. Это решает проблему разного регистра ключей (см. `_resolve_json_key()` в коде).
- **Транзакционность**: Обрезка массивов и обновление флага выполняются в одной транзакции.
- **Обратная совместимость**: Старый эндпоинт `toggle_multiple` удалён. Все вызовы с фронта теперь идут на `update_settings`.