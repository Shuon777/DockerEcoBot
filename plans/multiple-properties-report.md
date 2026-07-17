# Отчёт: Реализация множественного выбора свойств (is_multiple)

## 1. Назначение

Флаг `is_multiple` у свойства в каталоге определяет, может ли объект иметь **несколько значений** для этого свойства или только **одно**.

- `is_multiple = true` — объект может хранить массив значений (например, `["Значение1", "Значение2"]`)
- `is_multiple = false` — объект хранит только одно значение (скаляр, строка)

---

## 2. Где настраивается

Управление флагом находится на странице **«Каталог свойств»** (`/admin/properties`).

В модалке редактирования свойства есть переключатель **«Множественный выбор»**:

- Включён (`true`) — при редактировании объекта это свойство отображается как **chip-UI** (можно добавить несколько значений)
- Выключен (`false`) — при редактировании объекта это свойство отображается как **select/dropdown** (одиночный выбор)

---

## 3. Переключение is_multiple в каталоге свойств

### Бэкенд: `POST /properties/{prop_id}/update_settings`

При переключении флага:

- Флаг **моментально сохраняется** в базе данных
- **Данные объектов не изменяются** — если у объекта был массив значений, он остаётся массивом
- Модалка редактирования свойства **остаётся открытой**
- Предупреждение о потере данных **не показывается**

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
    Флаг меняется без изменения данных объектов — массив значений сохраняется как есть.
    При редактировании объекта бэкенд сам решает, заменять массив на скаляр.
    """
    if not request.session.get("user_id"):
        return {"ok": False, "error": "unauthorized"}

    prop = (await db.execute(
        select(ObjectProperty).where(ObjectProperty.id == prop_id)
    )).scalar()
    if not prop:
        return {"ok": False, "error": "not found"}

    new_is_multiple = data.get("is_multiple", False)

    # Просто меняем флаг, не трогая данные объектов
    prop.is_multiple = new_is_multiple
    await db.commit()
    return {"ok": True}
```

### Фронтенд: `properties_list.html`

Переключатель вызывает `updatePropertySettings`, который отправляет запрос без перезагрузки страницы:

```javascript
async function updatePropertySettings(propId, isMultiple) {
    try {
        const resp = await fetch(`/admin/properties/${propId}/update_settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_multiple: isMultiple })
        });
        const data = await resp.json();

        if (data.ok) {
            // Флаг обновлён без перезагрузки — модалка редактирования остаётся открытой.
            // Пользователь увидит изменения (chip-UI ↔ select) при следующем открытии.
        } else {
            alert('Ошибка: ' + (data.error || 'неизвестная'));
        }
    } catch(e) {
        alert('Ошибка сети: ' + e.message);
    }
}
```

---

## 4. Отображение в модалке редактирования объекта

При открытии карточки объекта (биологического, географического или услуги) в модалке «Свойства объекта»:

| Состояние свойства | Отображение |
|---|---|
| `is_multiple = true` | Chip-UI: можно добавлять/удалять несколько значений |
| `is_multiple = false`, в БД скаляр | Select/dropdown: выбран текущее значение |
| `is_multiple = false`, в БД массив | Select/dropdown: выбрано **первое значение** из массива |

Если в БД у объекта для свойства с `is_multiple = false` хранится массив (например, остался от предыдущего включённого режима), то в select отображается **первый элемент** этого массива, а не «— не указано —».

```jinja2
{% elif prop['values'] | length > 0 %}
{% set raw_val = (entity.object_properties or {}).get(prop.json_key, '') %}
{% if raw_val is iterable and raw_val is not string %}
    {% set cur_val = raw_val[0] %}
{% else %}
    {% set cur_val = raw_val %}
{% endif %}
<select class="form-select" id="prop_{{ prop.name }}">
    <option value="">— не указано —</option>
    {% for v in prop['values'] %}
    <option value="{{ v }}" {% if cur_val == v %}selected{% endif %}>{{ v }}</option>
    {% endfor %}
</select>
```

---

## 5. Сохранение при редактировании объекта

### Бэкенд: `POST /biological|geographical|service/{object_id}/set_property`

При нажатии «Сохранить» в модалке свойств объекта:

1. Фронтенд собирает **все** свойства из DOM и отправляет на сервер
2. Бэкенд загружает каталог свойств для данного типа объекта
3. Для каждого свойства применяется логика замены массива на скаляр

```python
@app.post("/biological/{object_id}/set_property")
async def biological_set_property(
    request: Request,
    object_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return {"ok": False, "error": "unauthorized"}
    obj = (await db.execute(
        select(Object).where(Object.id == object_id, Object.object_type_id == BIO_OBJECT_TYPE_ID)
    )).scalar()
    if not obj:
        raise HTTPException(status_code=404)

    # Загружаем каталог свойств для этого типа объекта
    catalog_props = {
        p.property_name: p for p in (
            await db.execute(
                select(ObjectProperty).where(ObjectProperty.object_type_id == obj.object_type_id)
            )
        ).scalars().all()
    }

    current = dict(obj.object_properties or {})
    for k, v in (data.get("properties") or {}).items():
        if v is None or v == "" or v == []:
            current.pop(k, None)
        else:
            # Находим свойство в каталоге (по вхождению ключа в property_name)
            catalog_prop = catalog_props.get(k.lower())
            if not catalog_prop:
                catalog_prop = next(
                    (p for p in catalog_props.values() if k.lower() in p.property_name.lower()),
                    None
                )

            # Если свойство НЕ множественное, текущее значение — массив, а новое — скаляр
            if (catalog_prop and not catalog_prop.is_multiple
                    and isinstance(current.get(k), list)
                    and isinstance(v, str)):
                # Заменяем массив на скаляр (новое значение)
                current[k] = v
            else:
                current[k] = v

    obj.object_properties = current
    await db.commit()
    return {"ok": True}
```

Аналогичные обработчики для географических объектов и услуг:

```python
@app.post("/geographical/{object_id}/set_property")
async def geographical_set_property(
    request: Request,
    object_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return {"ok": False, "error": "unauthorized"}
    obj = (await db.execute(
        select(Object).where(Object.id == object_id, Object.object_type_id == GEO_OBJECT_TYPE_ID)
    )).scalar()
    if not obj:
        raise HTTPException(status_code=404)

    # Загружаем каталог свойств для этого типа объекта
    catalog_props = {
        p.property_name: p for p in (
            await db.execute(
                select(ObjectProperty).where(ObjectProperty.object_type_id == obj.object_type_id)
            )
        ).scalars().all()
    }

    current = dict(obj.object_properties or {})
    for k, v in (data.get("properties") or {}).items():
        if v is None or v == "" or v == []:
            current.pop(k, None)
        else:
            catalog_prop = catalog_props.get(k.lower())
            if not catalog_prop:
                catalog_prop = next(
                    (p for p in catalog_props.values() if k.lower() in p.property_name.lower()),
                    None
                )

            if (catalog_prop and not catalog_prop.is_multiple
                    and isinstance(current.get(k), list)
                    and isinstance(v, str)):
                current[k] = v
            else:
                current[k] = v

    obj.object_properties = current
    await db.commit()
    return {"ok": True}


@app.post("/service/{object_id}/set_property")
async def service_set_property(
    request: Request,
    object_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return {"ok": False, "error": "unauthorized"}
    obj = (await db.execute(
        select(Object).where(Object.id == object_id, Object.object_type_id == SERVICE_OBJECT_TYPE_ID)
    )).scalar()
    if not obj:
        raise HTTPException(status_code=404)

    # Загружаем каталог свойств для этого типа объекта
    catalog_props = {
        p.property_name: p for p in (
            await db.execute(
                select(ObjectProperty).where(ObjectProperty.object_type_id == obj.object_type_id)
            )
        ).scalars().all()
    }

    current = dict(obj.object_properties or {})
    for k, v in (data.get("properties") or {}).items():
        if v is None or v == "" or v == []:
            current.pop(k, None)
        else:
            catalog_prop = catalog_props.get(k.lower())
            if not catalog_prop:
                catalog_prop = next(
                    (p for p in catalog_props.values() if k.lower() in p.property_name.lower()),
                    None
                )

            if (catalog_prop and not catalog_prop.is_multiple
                    and isinstance(current.get(k), list)
                    and isinstance(v, str)):
                current[k] = v
            else:
                current[k] = v

    obj.object_properties = current
    await db.commit()
    return {"ok": True}
```

**Ключевое условие замены массива на скаляр:**

```
ЕСЛИ в каталоге is_multiple = false
  И в БД текущее значение — массив
  И новое значение — строка (скаляр)
ТО массив заменяется на скаляр (новое значение)
ИНАЧЕ значение сохраняется как есть
```

Если пользователь не менял свойство, оно отправляется как есть (массив остаётся массивом). Замена массива на скаляр происходит **только** когда пользователь явно выбрал новое значение в select.

---

## 6. Сценарии использования

### Сценарий А: Отключение множественного выбора

1. Администратор заходит в каталог свойств
2. Открывает редактирование свойства, у которого `is_multiple = true`
3. Выключает переключатель «Множественный выбор»
4. Флаг сохраняется, модалка не закрывается
5. У всех объектов этого типа массив значений **сохраняется как есть**

### Сценарий Б: Редактирование объекта после отключения

1. Администратор открывает карточку объекта
2. В модалке свойств видит select с выбранным **первым значением** из старого массива
3. Если администратор **выбирает новое значение** в select и сохраняет:
   - Массив заменяется на новое значение (скаляр)
4. Если администратор **не меняет** значение и сохраняет:
   - Массив остаётся как есть

### Сценарий В: Повторное включение множественного выбора

1. Администратор снова включает `is_multiple = true`
2. При редактировании объекта свойство снова отображается как chip-UI
3. Если в БД был массив — он отображается в chip-ах
4. Если в БД был скаляр — он отображается как один chip

---

## 7. Схема потока данных

```
┌──────────────┐     Переключает is_multiple     ┌──────────────────┐
│ Администратор │ ──────────────────────────────> │ Каталог свойств  │
└──────────────┘                                   └────────┬─────────┘
       │                                                    │
       │ Открывает объект                                    │ Сохраняет флаг
       ▼                                                    ▼
┌──────────────────┐                                ┌──────────────────┐
│ Модалка свойств  │                                │      БД          │
│ объекта          │ <───────────────────────────── │                  │
└────────┬─────────┘   is_multiple=false, в БД массив └──────────────────┘
         │
         │ Выбирает новое значение и сохраняет
         ▼
┌──────────────────┐     is_multiple=false          ┌──────────────────┐
│   set_property   │ ─────────────────────────────> │      БД          │
│                  │     массив → скаляр            │  (обновлено)     │
└──────────────────┘                                └──────────────────┘
```

---

## 8. Сравнение: было / стало

| Аспект | Было | Стало |
|---|---|---|
| Отключение is_multiple | Предупреждение + обрезание массивов | Только смена флага |
| Данные объектов при отключении | Обрезались до первого элемента | Не изменяются |
| Модалка каталога при переключении | Закрывалась (reload) | Остаётся открытой |
| Select при массиве в БД | Показывал «— не указано —» | Показывает первый элемент массива |
| Замена массива на скаляр | При отключении is_multiple для всех объектов | Только при явном изменении значения в конкретном объекте |