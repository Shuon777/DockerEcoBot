# Отчёт: Архитектура toggle-полей в AdminPanel и добавление заглушки "Многоактовый диалог"

## 1. Общая архитектура toggle-полей в настройках

Система настроек AdminPanel построена на трёх уровнях:

### 1.1. Схема конфигурации — config_schema.json

Файл AdminPanel/config_schema.json определяет структуру вкладок и полей страницы /settings.

**Структура:**

```json
{
  "tabs": [
    {
      "id": "bot",
      "title": "Бот",
      "badge": "core-api · max",
      "restart_cmd": "docker compose restart core-api max",
      "fields": [
        {
          "key": "promo_enabled",
          "label": "Промо-реплики",
          "desc": "Добавлять рекламные вставки к ответам бота",
          "type": "toggle",
          "source": "redis",
          "redis_key": "settings:promo_enabled",
          "reload": "instant"
        }
      ]
    }
  ]
}
```

**Параметры поля типа toggle:**

| Поле | Описание | Обязательное |
|------|----------|-------------|
| key | Уникальный идентификатор поля (используется как id HTML-элемента) | Да |
| label | Отображаемое название в интерфейсе | Да |
| desc | Подсказка под переключателем | Нет |
| type | Должен быть "toggle" | Да |
| source | Откуда читается значение: "redis" или "env" | Да |
| redis_key | Ключ в Redis (если source: "redis") | Условно |
| reload | Тип применения: "instant" (мгновенно) или "restart" (требует перезапуска) | Да |

### 1.2. Шаблон — settings.html

Файл AdminPanel/templates/settings.html рендерит поля согласно схеме.

**Рендеринг toggle (строки 83-95):**

```html
{% if field.type == 'toggle' %}
<div class="d-flex align-items-center gap-3 py-2">
  <div class="form-check form-switch mb-0">
    <input class="form-check-input" type="checkbox" id="toggle-{{ field.key }}"
           style="width:2.5em; height:1.3em;"
           {% if field.key == 'promo_enabled' and promo_enabled %}checked{% endif %}>
    <label class="form-check-label fw-bold ms-1" for="toggle-{{ field.key }}">
      {{ field.label }}
    </label>
  </div>
  <span style="font-size:0.83rem; color:#475569;">{{ field.desc }}</span>
</div>
{% endif %}
```

**Важно:** На данный момент в шаблоне хардкод для поля promo_enabled — строка 89:

```
{% if field.key == 'promo_enabled' and promo_enabled %}checked{% endif %}
```

Это означает, что для нового toggle-поля multi_act_dialog потребуется либо:
- Добавить аналогичную проверку в шаблон (если значение хранится в Redis и передаётся отдельной переменной), либо
- Передавать значение через shared (из .env), и тогда оно будет подставляться автоматически через shared.get(field.key, ''), но для checkbox это не работает — checked не выставится.

### 1.3. Backend — main.py

Файл AdminPanel/main.py:

- **Загрузка схемы:** функция _load_config_schema() (строка 336) читает config_schema.json
- **Роут /settings** (строка 344): загружает shared из .env, promo_enabled из Redis, и передаёт всё в шаблон
- **Сохранение toggle:** для promo_enabled есть отдельный JS-обработчик (строки 194-209 в settings.html), который отправляет POST на /admin/chat/promo-setting

**Код загрузки схемы:**

```python
_CONFIG_SCHEMA_PATH = Path(__file__).parent / "config_schema.json"

def _load_config_schema() -> dict:
    try:
        return json.loads(_CONFIG_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[Settings] Ошибка загрузки схемы конфига: {e}")
        return {"tabs": []}
```

**Код роута /settings:**

```python
@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    bot_online = await is_bot_online_redis()
    prompts = {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            p_resp = await client.get(f"{CORE_API_BASE}/prompts")
            if p_resp.status_code == 200:
                prompts = p_resp.json()
        except Exception as e:
            print(f"Ошибка загрузки промптов: {e}")

    shared = dict(dotenv_values(SHARED_ENV_PATH)) if SHARED_ENV_PATH.exists() else {}
    promo_val = await settings_redis.get("settings:promo_enabled")
    promo_enabled = promo_val != "0"

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "active_page": "settings",
        "bot_online": bot_online,
        "prompts": prompts,
        "shared": shared,
        "promo_enabled": promo_enabled,
        "schema": _load_config_schema(),
    })
```

---

## 2. План добавления toggle-заглушки "Многоактовый диалог"

### 2.1. Что нужно сделать

Добавить toggle-поле-заглушку с id multi_act_dialog в раздел "Бот" на странице настроек.

### 2.2. Требования

| Параметр | Значение |
|----------|----------|
| key | multi_act_dialog |
| label | Многоактовый диалог |
| desc | Включить поддержку многоактовых диалогов (заглушка) |
| type | toggle |
| source | redis |
| redis_key | settings:multi_act_dialog |
| reload | instant |

### 2.3. Файлы для изменения

#### 2.3.1. AdminPanel/config_schema.json

Добавить новое поле в массив fields раздела "bot" (после promo_enabled):

```json
{
  "key": "multi_act_dialog",
  "label": "Многоактовый диалог",
  "desc": "Включить поддержку многоактовых диалогов (заглушка)",
  "type": "toggle",
  "source": "redis",
  "redis_key": "settings:multi_act_dialog",
  "reload": "instant"
}
```

**Результат после изменения (фрагмент config_schema.json, раздел bot):**

```json
{
  "id": "bot",
  "title": "Бот",
  "badge": "core-api · max",
  "restart_cmd": "docker compose restart core-api max",
  "fields": [
    {
      "key": "promo_enabled",
      "label": "Промо-реплики",
      "desc": "Добавлять рекламные вставки к ответам бота",
      "type": "toggle",
      "source": "redis",
      "redis_key": "settings:promo_enabled",
      "reload": "instant"
    },
    {
      "key": "multi_act_dialog",
      "label": "Многоактовый диалог",
      "desc": "Включить поддержку многоактовых диалогов (заглушка)",
      "type": "toggle",
      "source": "redis",
      "redis_key": "settings:multi_act_dialog",
      "reload": "instant"
    },
    {
      "key": "MAX_BOT_TOKEN",
      "label": "Токен MAX бота",
      "desc": "Токен бота платформы MAX — получается в личном кабинете MAX",
      "type": "password",
      "reload": "restart"
    },
    {
      "key": "STAND_ENDPOINT",
      "label": "STAND API Endpoint",
      "desc": "URL внешнего сервиса достопримечательностей",
      "type": "text",
      "reload": "restart"
    },
    {
      "key": "STAND_SECRET_KEY",
      "label": "STAND Secret Key",
      "desc": "Ключ аутентификации STAND API",
      "type": "password",
      "reload": "restart"
    }
  ]
}
```

#### 2.3.2. AdminPanel/main.py

Три изменения:

**a) Инициализация значения в Redis при старте (после строки 86):**

```python
@app.on_event("startup")
async def _init_redis_settings():
    await settings_redis.set("settings:promo_enabled", "1", nx=True)
    await settings_redis.set("settings:multi_act_dialog", "1", nx=True)
```

**b) Чтение значения в роуте /settings (после строки 363):**

```python
    promo_val = await settings_redis.get("settings:promo_enabled")
    promo_enabled = promo_val != "0"
    multi_act_val = await settings_redis.get("settings:multi_act_dialog")
    multi_act_enabled = multi_act_val != "0"
```

**c) Передача в шаблон (в словарь TemplateResponse):**

```python
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "active_page": "settings",
        "bot_online": bot_online,
        "prompts": prompts,
        "shared": shared,
        "promo_enabled": promo_enabled,
        "multi_act_enabled": multi_act_enabled,
        "schema": _load_config_schema(),
    })
```

#### 2.3.3. AdminPanel/templates/settings.html

Обновить условие checked в строке 89. Было:

```html
{% if field.key == 'promo_enabled' and promo_enabled %}checked{% endif %}
```

Стало:

```html
{% if (field.key == 'promo_enabled' and promo_enabled) or (field.key == 'multi_act_dialog' and multi_act_enabled) %}checked{% endif %}
```

### 2.4. Принцип работы (заглушка)

1. При первом запуске Redis инициализирует ключ settings:multi_act_dialog = 1 (включено)
2. На странице /settings отображается toggle-переключатель
3. Переключатель сохраняет значение через существующий механизм (JS → API)
4. На данный момент значение хранится в Redis, но не используется нигде в логике бота — это pure заглушка
5. В будущем, когда появится реальная реализация многоактовых диалогов, код будет читать settings:multi_act_dialog из Redis и включать/выключать функционал

---

## 3. Схема взаимодействия

```
┌──────────┐     ┌──────────────────┐     ┌───────────────────┐
│Пользователь│────>│ AdminPanel main.py│────>│ config_schema.json │
└──────────┘     └──────────────────┘     └───────────────────┘
                        │                           │
                        │                           │
                        v                           v
                 ┌──────────────┐          ┌──────────────────┐
                 │    Redis     │          │  settings.html   │
                 │──────────────│          │  (рендеринг)     │
                 │promo_enabled │          └──────────────────┘
                 │multi_act_dialog│                │
                 └──────────────┘                 │
                        ^                         │
                        │                         v
                 ┌──────────────┐          ┌──────────────────┐
                 │  JS fetch    │<──────────│  Toggle switch   │
                 │  POST save   │          │  (пользователь)  │
                 └──────────────┘          └──────────────────┘
```

---

## 4. Заключение

Добавление toggle-заглушки "Многоактовый диалог" — это минимальное изменение в 3-х файлах, которое добавляет переключатель в UI и инициализирует ключ в Redis. Сама заглушка не влияет на логику работы бота до тех пор, пока не будет реализован соответствующий функционал, который начнёт читать значение settings:multi_act_dialog из Redis.

### Список изменённых файлов:

1. AdminPanel/config_schema.json — добавлено поле multi_act_dialog в раздел bot
2. AdminPanel/main.py — инициализация Redis-ключа, чтение значения, передача в шаблон
3. AdminPanel/templates/settings.html — расширено условие checked для нового поля