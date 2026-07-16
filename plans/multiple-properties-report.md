# Отчёт о реализации поддержки `is_multiple` для свойств объектов

## 1. Описание задачи

Добавить возможность выбора нескольких значений для свойства объекта (флаг `is_multiple` в таблице `object_property`). Если флаг `true` — в модалке редактирования свойств объекта отображается chip-UI (аналогично подтипам), позволяющий выбрать несколько значений из справочника. Если `false` — обычный select/input.

---

## 2. Изменённые файлы

### 2.1. Модель: [`AdminPanel/models/eco_assistant_models.py`](AdminPanel/models/eco_assistant_models.py:487)

Добавлено поле `is_multiple` в класс `ObjectProperty`:

```python
is_multiple = Column(Boolean, default=False, server_default='false', nullable=False,
                     doc='Флаг: можно ли выбрать несколько значений для этого свойства')
```

Импорт `Boolean` добавлен в начало файла.

---

### 2.2. Бэкенд: [`AdminPanel/main.py`](AdminPanel/main.py)

#### 2.2.1. Добавление `is_multiple` в словарь `available_properties`

Во всех трёх роутах (biological, geographical, service) в словарь свойства добавлено поле `is_multiple`:

```python
available_properties = [
    {
        "name": p.name,
        "json_key": p.json_key,
        "values": p.values,
        "is_multiple": p.is_multiple,  # <-- добавлено
    }
    for p in props
    if p.object_type_id == object_type_id
]
```

Строки:
- [`biological_edit`](AdminPanel/main.py:883)
- [`geographical_edit`](AdminPanel/main.py:1974)
- [`service_edit`](AdminPanel/main.py:2736)

#### 2.2.2. Эндпоинт редактирования свойства в каталоге

[`/properties/{prop_id}/edit`](AdminPanel/main.py:3666) — добавлен приём и сохранение `is_multiple`:

```python
@app.post("/properties/{prop_id}/edit")
async def properties_edit(
    request: Request,
    prop_id: int,
    property_values: str = Form(""),
    is_multiple: str = Form("false"),  # <-- добавлено
    db: AsyncSession = Depends(get_db),
):
    ...
    prop.is_multiple = (is_multiple == "true")  # <-- добавлено
```

#### 2.2.3. Эндпоинты `set_property` (все три)

Очистка свойства теперь работает корректно — пустая строка и пустой массив передаются на бэкенд и обрабатываются:

- [`biological_set_property`](AdminPanel/main.py:3792)
- [`geographical_set_property`](AdminPanel/main.py:3817)
- [`service_set_property`](AdminPanel/main.py:3842)

---

### 2.3. Шаблоны

#### 2.3.1. Модалка редактирования свойств (`editPropertiesModal`)

Во всех трёх шаблонах добавлен блок для multiple-свойств с chip-UI:

```jinja
{% elif prop['values'] | length > 0 and prop.get('is_multiple') %}
{% set prop_slug = prop.name | replace(' ', '_') %}
<div id="prop_{{ prop_slug }}_chips" class="d-flex flex-wrap gap-1 mb-2">
    {% set cur_val = (entity.object_properties or {}).get(prop.json_key, []) %}
    {% if cur_val is string %}{% set cur_val = [cur_val] %}{% endif %}
    {% for v in cur_val %}
    <span class="badge bg-light text-dark border d-flex align-items-center gap-1" style="font-size:0.85rem;">
        {{ v }}
        <button type="button" class="btn-close" style="font-size:0.6rem;" onclick="removeMultipleChip(this, '{{ prop_slug }}')"></button>
    </span>
    {% endfor %}
</div>
<datalist id="prop_{{ prop_slug }}_datalist">
    {% for v in prop['values'] %}
    <option value="{{ v }}">
    {% endfor %}
</datalist>
<div class="input-group">
    <input type="text" class="form-control" id="prop_{{ prop_slug }}_input"
           list="prop_{{ prop_slug }}_datalist" placeholder="Введите значение...">
    <button class="btn btn-outline-secondary" type="button" onclick="addMultipleChip('{{ prop_slug }}')">Добавить</button>
</div>
```

Файлы:
- [`biological_edit.html`](AdminPanel/templates/biological_edit.html)
- [`geographical_edit.html`](AdminPanel/templates/geographical_edit.html)
- [`service_edit.html`](AdminPanel/templates/service_edit.html)

#### 2.3.2. JS-функция `saveProperties`

Добавлена ветка для multiple-свойств:

```javascript
{% elif prop.get('is_multiple') %}
{
    {% set prop_slug = prop.name | replace(' ', '_') %}
    const chips = document.querySelectorAll('#prop_{{ prop_slug }}_chips .badge');
    const valList = Array.from(chips).map(c => c.childNodes[0].textContent.trim()).filter(Boolean);
    props['{{ prop.json_key }}'] = valList;
}
```

Также исправлена очистка значений — теперь всегда передаётся значение (пустая строка или пустой массив):

```javascript
{% else %}
{
    const el = document.getElementById('prop_{{ prop.name }}');
    if (el) props['{{ prop.json_key }}'] = el.value || '';
}
```

#### 2.3.3. Универсальные JS-функции для chip-UI

Добавлены во все три шаблона:

```javascript
function addMultipleChip(slug) {
    const input = document.getElementById('prop_' + slug + '_input');
    const val = input.value.trim(); if (!val) return;
    const datalist = document.getElementById('prop_' + slug + '_datalist');
    const allowed = datalist ? Array.from(datalist.options).map(o => o.value) : [];
    if (!allowed.includes(val)) { alert('Такого значения нет в справочнике — выберите из списка подсказок'); return; }
    const container = document.getElementById('prop_' + slug + '_chips');
    const existing = Array.from(container.querySelectorAll('.badge')).map(c => c.childNodes[0].textContent.trim());
    if (existing.includes(val)) { input.value = ''; return; }
    const span = document.createElement('span');
    span.className = 'badge bg-light text-dark border d-flex align-items-center gap-1';
    span.style.fontSize = '0.85rem';
    span.innerHTML = val + ' <button type="button" class="btn-close" style="font-size:0.6rem;" onclick="removeMultipleChip(this, \'' + slug + '\')"></button>';
    container.appendChild(span);
    input.value = '';
}

function removeMultipleChip(btn, slug) {
    btn.parentElement.remove();
}

function onMultipleInput(el, slug) {
    // обработка Enter и выбор из datalist
}
```

#### 2.3.4. Карточка объекта (левая колонка)

Добавлено отображение multiple-свойств в виде списка badge-элементов:

```jinja
{% if prop.get('is_multiple') and val is not string %}
    {% for v in val %}
    <span class="badge bg-light text-dark border me-1 mb-1">{{ v }}</span>
    {% endfor %}
{% else %}
    {{ val if val is string else (val | join(', ')) }}
{% endif %}
```

**Дополнительно**: добавлен фильтр `{% if prop.name != 'подтип объекта' %}`, чтобы исключить дублирование подтипа (он уже отображается отдельно через `entity.subtypes`).

Файлы:
- [`biological_edit.html`](AdminPanel/templates/biological_edit.html:117)
- [`geographical_edit.html`](AdminPanel/templates/geographical_edit.html:103)
- [`service_edit.html`](AdminPanel/templates/service_edit.html:100)

---

### 2.4. Каталог свойств: [`AdminPanel/templates/properties_list.html`](AdminPanel/templates/properties_list.html)

В модалку редактирования свойства (`editPropertyModal`) добавлен чекбокс `is_multiple`:

```html
<div class="form-check mb-3">
    <input class="form-check-input" type="checkbox" id="editIsMultiple">
    <label class="form-check-label" for="editIsMultiple">
        Разрешить несколько значений
    </label>
</div>
```

В JS-функцию `openEditProperty` добавлена передача `isMultiple`:

```javascript
function openEditProperty(id, name, jsonKey, values, isMultiple) {
    ...
    document.getElementById('editIsMultiple').checked = isMultiple;
    ...
}
```

---

## 3. Настройка в БД

Для свойства «Географическая зона» установлен `is_multiple = true` для обоих типов объектов (id=20 и id=491).

---

## 4. Проблемы, возникшие в процессе

| Проблема | Причина | Решение |
|----------|---------|---------|
| 502 Bad Gateway | Не импортирован `Boolean` в модели | Добавлен импорт |
| Колонка называлась `is_muliple` | Опечатка в имени колонки | Переименована в `is_multiple` |
| Docker не подхватывал изменения | `COPY . .` — требуется пересборка | `docker compose build admin` |
| Нельзя было очистить select/input | Условие `if (el.value)` не передавало пустую строку | Убрана проверка, всегда передаётся значение |
| Нельзя было очистить multiple/подтипы | Условие `if (valList.length > 0)` не передавало пустой массив | Убрана проверка, всегда передаётся массив |
| Подтип дублировался на карточке | Цикл выводил все свойства включая «подтип объекта» | Добавлен `{% if prop.name != 'подтип объекта' %}` |

---

## 5. Итог

Реализована полная поддержка флага `is_multiple` для свойств объектов:

- **Модель**: новое поле `is_multiple` (Boolean)
- **Бэкенд**: флаг передаётся в `available_properties`, сохраняется через `properties_edit`
- **Модалка**: chip-UI для multiple-свойств, select/input для обычных
- **JS**: универсальные функции `addMultipleChip`, `removeMultipleChip`, `onMultipleInput`
- **Сохранение**: корректная очистка значений (пустая строка / пустой массив)
- **Карточка**: отображение multiple-значений списком badge, подтип не дублируется
- **Каталог свойств**: чекбокс `is_multiple` в модалке редактирования