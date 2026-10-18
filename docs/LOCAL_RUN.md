# Локальный запуск: админка + аннотатор изображений

Инструкция для Windows 10/11. Поднимается облегчённый набор сервисов, достаточный для показа
аннотатора: **БД, Redis, админка, аннотатор, nginx**. Бот, backend-поиск и LLM не запускаются —
для демо аннотатора они не нужны, а требуют ещё ~10 ГБ моделей и памяти.

Время: 1–2 часа, из них большая часть — скачивание (Docker-образы ~8 ГБ + веса моделей ~4 ГБ).

---

## 0. Что должно быть установлено

### 0.1. WSL2 и Ubuntu
Всё делаем внутри Linux-подсистемы Windows. Это важно: если держать проект на диске `D:\`,
PostgreSQL в Docker часто падает с ошибками прав на папку данных, а сборка идёт в разы медленнее.

PowerShell **от имени администратора**:
```powershell
wsl --install -d Ubuntu
```
Перезагрузить компьютер, открыть «Ubuntu» из меню Пуск, задать логин и пароль Linux.

Проверка (в PowerShell): `wsl -l -v` → у Ubuntu `VERSION 2`.

### 0.2. Docker Desktop
1. Скачать с docker.com, установить с галочкой **Use WSL 2 instead of Hyper-V**.
2. Docker Desktop → Settings → Resources → **WSL integration** → включить для Ubuntu → Apply.
3. Проверка в терминале Ubuntu:
   ```bash
   docker version
   docker compose version   # нужна v2.24 или новее
   ```

### 0.3. Память для WSL
По умолчанию WSL забирает половину RAM (8 ГБ из 16). Для модели на CPU этого впритык.
Создать файл `C:\Users\<ваше_имя>\.wslconfig`:
```ini
[wsl2]
memory=12GB
swap=8GB
```
Затем в PowerShell: `wsl --shutdown` и перезапустить Docker Desktop.

### 0.4. Видеокарта (необязательно, но ускоряет в 5–10 раз)
RTX 2060 Super подходит (8 ГБ видеопамяти, модели аннотатора занимают ~4 ГБ).
1. Обновить драйвер NVIDIA на Windows (обычный Game Ready/Studio). **В Ubuntu драйвер НЕ ставить.**
2. Проверка в Ubuntu:
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
   ```
   Должна появиться таблица с RTX 2060 SUPER. Если ошибка — работаем на CPU, всё тоже запустится.

### 0.5. Git
В Ubuntu уже есть. Один раз представиться (нужно для применения патча):
```bash
git config --global user.name "Oleg"
git config --global user.email "you@example.com"
```

---

## 1. Код проекта

В терминале **Ubuntu**:
```bash
cd ~
git clone https://github.com/Shuon777/DockerEcoBot.git
cd DockerEcoBot
```

Применить патч с аннотатором. Файл скачан в Windows, например в «Загрузки»:
```bash
cp /mnt/c/Users/<ваше_имя>/Downloads/annotator-full.patch .
git checkout -b feature/annotator
git am annotator-full.patch
git log --oneline -3      # должны появиться коммиты про аннотатор
```
> Если `git am` ругается на конфликт — значит, в репозитории что-то поменялось. Тогда `git am --abort`
> и `git apply --3way annotator-full.patch`, либо откатиться на коммит `7f02383`: `git checkout 7f02383 -b feature/annotator`.

Открыть проект в редакторе Windows: `explorer.exe .` (откроет папку) или `code .` (VS Code с расширением WSL).

---

## 2. Настройки (.env)

```bash
bash scripts/setup_local.sh
```
Скрипт создаёт все `.env` из шаблонов, генерирует пароль БД, ключ сессий админки и общий токен
админка ↔ аннотатор, создаёт папки. Существующие файлы не трогает. Логин в админку: **admin / admin**.

---

## 3. Веса моделей аннотатора (~4 ГБ)

Собрать образ аннотатора и скачать веса в `annotator/models`:
```bash
docker compose build annotator
docker compose run --rm --no-deps -e HF_HUB_OFFLINE=0 annotator python scripts/download_models.py
```
Сборка образа — 10–20 минут (PyTorch большой). Скачивание — зависит от интернета.

Проверка: `ls annotator/models` → папки `blip clip grounding_dino owlv2 phenovision`.

> Если скачивание обрывается — просто запустить команду ещё раз, докачает.
> Если Hugging Face не открывается без VPN — включить VPN в Windows, WSL пойдёт через него.

---

## 4. База данных

```bash
F="-f docker-compose.yml -f docker-compose.local.yml"

docker compose $F up -d db redis
docker compose $F ps            # db и redis должны быть healthy (подождать ~10 с)

docker compose $F run --rm db-init
```
Заполнение идёт ~2–3 минуты. В конце: `Resources import: success=10769 ... errors=0` и `=== БД заполнена ===`.

**Про фотографии.** В начальных данных у ~600 фото путь вида `/images/<имя>.jpg`, а самих файлов
в репозитории нет. Поэтому по умолчанию ссылки направляются на боевой сервер `https://testecobot.ru`.
Проверить заранее: открыть в браузере `https://testecobot.ru/images/Лиственница_сибирская.jpg`.
Если не открывается — либо скопировать папку `images` с сервера в `salut_bot/images` и перезаполнить БД так:
```bash
IMPORT_IMAGES_BASE_URL=http://localhost:8080 docker compose $F run --rm db-init
```
либо на демо использовать фото с внешними ссылками (см. шаг 6), они работают всегда.

---

## 5. Запуск админки и аннотатора

**С видеокартой:**
```bash
docker compose $F -f docker-compose.gpu.yml up -d --build --no-deps admin annotator nginx
```
**Без видеокарты:**
```bash
docker compose $F up -d --build --no-deps admin annotator nginx
```

Аннотатор загружает модели 1–3 минуты. Следить:
```bash
docker compose $F logs -f annotator
```
Ждать строк `phenovision загружен (cuda)` (или `(cpu)`) и `Application startup complete`. Выход — `Ctrl+C`.

Проверка аннотатора:
```bash
docker compose $F exec annotator python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8010/health').read().decode())"
```
Ожидаемо: `"executors":["clip","grounding_dino","owlv2","phenovision"],"failed":{}`.
Если модель есть в `failed` — там написана причина.

---

## 6. Демо

1. Браузер Windows: **http://localhost:8080/admin/** → admin / admin.
2. Слева **Флора** → найти «Лиственница сибирская» (или любое растение) → открыть карточку.
3. Вкладка **Изображения** → на фото кнопка **Аннотировать**.
4. Выбрать признаки (отмечены те, что есть в каталоге БД) и модели → **Запустить аннотацию**.
5. Прогресс-бар → таблица: итог, уверенность, согласие моделей, ответ каждой модели.
6. **Перенести в признаки** → откроется стандартная форма признаков, уже заполненная → **Сохранить**.

Для фауны — то же через **Фауна** (например, «Байкальская нерпа»): признаки цветения и плодов
там автоматически скрыты.

**Своё фото на демо:** на вкладке «Изображения» → «Прикрепить изображение» → вставить прямую
ссылку на картинку из интернета (заканчивается на `.jpg`/`.png`).

**Один момент с каталогом.** В БД у признака «наличие плодов» значения «Шишка / Нет», а PhenoVision
отвечает «Да / Нет» (она видит любые плоды, не только шишки). При переносе админка предупредит.
Чтобы переносилось: **Каталоги → Признаки ресурсов** → «наличие плодов» → добавить значение «Да».

---

## 7. Управление

```bash
F="-f docker-compose.yml -f docker-compose.local.yml"
docker compose $F ps                   # что запущено
docker compose $F logs -f admin        # логи админки
docker compose $F restart annotator    # перезапуск
docker compose $F stop                 # остановить всё (данные сохраняются)
docker compose $F up -d --no-deps db redis admin annotator nginx   # снова запустить
```
После перезагрузки Windows: запустить Docker Desktop, затем последнюю команду (для GPU добавить `-f docker-compose.gpu.yml`).

---

## 8. Если что-то не так

| Симптом | Причина и решение |
|---|---|
| `http://localhost:8080` не открывается | `docker compose $F ps` — nginx не запущен или порт 8080 занят. Поменять `8080:80` в `docker-compose.local.yml` |
| Модалка: «Сервис аннотации недоступен» | Аннотатор ещё грузит модели или упал: `docker compose $F logs annotator` |
| «неверный X-API-Token» | Токены разошлись: `ANNOTATOR_API_TOKEN` в `annotator/.env` ≠ `ANNOTATOR_TOKEN` в `AdminPanel/.env`. Выровнять → `docker compose $F up -d --no-deps admin annotator` |
| Задача `failed: не удалось скачать изображение: HTTP 404` | Файла фото нет по ссылке (см. шаг 4 «Про фотографии») |
| `failed` у модели в `/health`: нет файлов | Не докачались веса — повторить шаг 3 |
| `db-init`: `password authentication failed` | Пароли в `shared.env` и `db_custom/.env` разные, **или** БД уже создавалась раньше с другим паролем. Для чистого старта: `docker compose $F down`, `sudo rm -rf data/postgres_data`, повторить шаг 4 |
| Аннотатор убит (`exit 137`) | Не хватает памяти: увеличить `memory` в `.wslconfig` (шаг 0.3) или включить GPU |
| GPU-команда: `could not select device driver` | Docker не видит видеокарту: обновить драйвер NVIDIA и Docker Desktop, либо запускать без `docker-compose.gpu.yml` |
| Страница объекта — 500 Internal Server Error | `docker compose $F logs admin`. Если про `priority` или `is_multiple` — БД создана старой схемой, перезаполнить (шаг 4) |

---

## Что изменено в проекте для локального запуска

- `db_custom/init.sql` — добавлено расширение `pg_trgm`. Без него импорт на чистой БД падает на индексе синонимов.
- `schema.sql` импортёра — добавлены колонки `object_name_synonym_link.priority` и
  `object_property.is_multiple`, которые использует админка. Без них карточка объекта даёт ошибку 500
  на свежей установке. На сервере они, по всей видимости, были добавлены вручную.
- `docker-compose.local.yml`, `nginx/nginx.local.conf` — облегчённый режим без backend и бота.
- `docker-compose.gpu.yml` — видеокарта для аннотатора.
- `scripts/setup_local.sh` — подготовка `.env`.
- Форма «Признаки» в админке сохраняла ключи строчными («время года», как в каталоге), а поиск бота
  сравнивает ключи с учётом регистра («Время года»). Теперь сохраняется регистр, который уже есть
  у ресурса, иначе — с заглавной буквы.
- Аннотатор понимает тип объекта из БД в виде «Объект флоры» / «Объект фауны».

Проверено на настоящих PostgreSQL + PostGIS и админке: импорт (7864 объекта, 10769 ресурсов, 0 ошибок),
вход, карточка объекта, полный цикл аннотации с переносом в признаки. Реальные нейросети
в этой проверке заменялись заглушками — первый запуск с весами делается по шагам 3 и 5.
