# План: Обработка смены `is_multiple` с `true` на `false` для свойства объекта

## 1. Анализ текущего состояния

### Модель `ObjectProperty` (eco_assistant_models.py:469-491)
- Поле `is_multiple` (`Boolean`, default `false`) — флаг множественного выбора
- Поле `property_values` (`ARRAY(Text)`) — массив допустимых значений
- Поле `property_name` — имя свойства (ключ в `object.object_properties` JSONB)

### Текущий эндпоинт `POST /properties/{prop_id}/toggle_multiple` (main.py:3702-3716)
- Просто переключает `is_multiple` без какой-либо проверки
- Не обрабатывает случай, когда у объектов уже есть массивы значений

### Текущий эндпоинт `POST /properties/{prop_id}/edit` (main.py:3670-3686)
- Редактирует `property_values` и `is_multiple` через form-data
- Тоже без проверок на потерю данных

### Шаблон `properties_list.html`
- Чекбокс `is_multiple` в модалке редактирования
- Есть функция `toggleMultiple()` для AJAX-переключения

### Структура данных в `object.object_properties`
- Если `is_multiple = true`: значение свойства — массив `["значение1", "значение2"]`
- Если `is_multiple = false`: значение свойства — строка `"значение1"` (или массив из одного элемента, если раньше было multiple)

## 2. Требования

1. При смене `is_multiple` с `true` на `false`:
   - Показать предупреждение: "Свойства у объектов могут быть утеряны"
   - Подсчитать количество объектов, у которых >1 значения для этого свойства
   - При подтверждении: для каждого объекта оставить только **первое** (старое) значение из массива
   - Обновить `is_multiple` в БД

2. При смене `is_multiple` с `false` на `true`:
   - Никаких предупреждений, просто обновить флаг

## 3. Архитектура решения

### Новый эндпоинт: `POST /properties/{prop_id}/update_settings`

**Метод:** POST  
**URL:** `/admin/properties/{prop_id}/update_settings`  
**Body (JSON):**
```json
{
  "is_multiple": false,
  "confirmed": false
}
```

**Логика:**

```mermaid
flowchart TD
    A[Запрос POST /properties/{prop_id}/update_settings] --> B{is_multiple меняется<br>с true на false?}
    B -->|Нет| C[Просто обновить is_multiple]
    B -->|Да| D{confirmed == true?}
    D -->|Нет| E[Подсчитать объекты с >1 значением]
    E --> F[Вернуть warning + affected_count]
    D -->|Да| G[Обрезать массивы до 1-го элемента]
    G --> H[Обновить is_multiple = false]
    H --> I[Вернуть ok: true]
```

**SQL-логика обрезки массивов:**

Для каждого объекта, у которого `object_properties->property_json_key` является массивом с длиной > 1:
- Оставить только первый элемент массива
- Преобразовать в строку (одиночное значение)

**Пример:**
```sql
-- До: object_properties = '{"Подтип объекта": ["значение1", "значение2", "значение3"]}'
-- После: object_properties = '{"Подтип объекта": "значение1"}'
```

### Модификация шаблона `properties_list.html`

1. Заменить вызов `toggleMultiple()` на вызов нового эндпоинта
2. Добавить модальное окно подтверждения с информацией о количестве затронутых объектов
3. При получении `warning` от сервера — показывать модалку с кнопками "Отмена" / "Подтвердить"

## 4. Детальная реализация

### 4.1. Новый эндпоинт в `main.py`

```python
@app.post("/properties/{prop_id}/update_settings")
async def properties_update_settings(
    request: Request,
    prop_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Обновление настроек свойства (is_multiple).
    
    При смене is_multiple с true на false:
    - Если confirmed=false: возвращает warning с количеством затронутых объектов
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
    
    # Смена с true на false
    if prop.is_multiple and not new_is_multiple:
        # Определяем JSON-ключ в object_properties
        json_key = prop.property_name  # property_name уже в нижнем регистре
        
        # Ищем реальный ключ в существующих объектах (с учётом регистра)
        real_key_row = await db.execute(sql_text("""
            SELECT DISTINCT jsonb_object_keys(object_properties) AS key
            FROM eco_assistant.object
            WHERE object_type_id = :otid
              AND object_properties ? :pname
            LIMIT 1
        """), {"otid": prop.object_type_id, "pname": json_key})
        real_key_row = real_key_row.first()
        
        # Также проверим другие варианты регистра
        if not real_key_row:
            # Ищем по lower-case
            real_key_row = await db.execute(sql_text("""
                SELECT DISTINCT key
                FROM eco_assistant.object o,
                     jsonb_object_keys(o.object_properties) AS key
                WHERE o.object_type_id = :otid
                  AND LOWER(key) = :pname
                LIMIT 1
            """), {"otid": prop.object_type_id, "pname": json_key})
            real_key_row = real_key_row.first()
        
        actual_key = real_key_row[0] if real_key_row else json_key
        
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
            # Возвращаем предупреждение
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
    
    # Обновляем флаг
    prop.is_multiple = new_is_multiple
    await db.commit()
    return {"ok": True}
```

### 4.2. Модификация шаблона `properties_list.html`

**Изменения:**

1. **В модалке редактирования** — заменить стандартный submit на вызов `updatePropertySettings()` через JS
2. **Добавить модальное окно подтверждения** для случая с потерей данных
3. **Обновить JS-функции**

```javascript
// Новая функция вместо toggleMultiple
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

**HTML модального окна подтверждения:**
```html
<!-- Модальное окно подтверждения -->
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

## 5. Порядок реализации

1. **main.py**: Добавить новый эндпоинт `POST /properties/{prop_id}/update_settings`
2. **properties_list.html**: 
   - Добавить модальное окно подтверждения
   - Заменить вызов `toggleMultiple()` на `updatePropertySettings()`
   - Обновить обработку формы редактирования
3. **Создать md-отчёт** с блоками кода всех изменений

## 6. Риски и замечания

- **Регистр ключа JSONB**: В `object_properties` ключи могут быть в разном регистре (см. `_resolve_json_key()`). Нужно искать реальный ключ через `jsonb_object_keys()`.
- **Производительность**: UPDATE с `jsonb_set` для большого количества объектов может быть медленным. Для типовых объёмов (сотни-тысячи объектов) — приемлемо.
- **Транзакционность**: Вся операция обрезки + обновления флага выполняется в одной транзакции.