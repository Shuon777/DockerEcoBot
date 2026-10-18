# Промпт для Claude Code: аннотатор в ветку version2 + локальная проверка

Запусти Claude Code в папке проекта (`annote` на рабочем столе) и вставь всё, что ниже линии.
Файл `annotator-version2.patch` положи в эту же папку `annote`, рядом с `.git`
(или поправь путь в первой строке).

---

Патч: `annotator-version2.patch` в корне репозитория (если его нет — спроси у меня путь).

Это проект ЭкоБайкал / Экоассистент (https://github.com/Shuon777/DockerEcoBot), уже склонированный
в текущую папку (`annote` на рабочем столе). Компьютер — Windows, оболочка PowerShell.

## Задача

1. От ветки `version2` создать ветку `feature/annotator` и внести в неё изменения из патча.
2. Запустить админку и аннотатор локально — **без Docker, WSL и виртуальных машин** — чтобы я
   проверил в браузере.
3. **Остановиться и ждать.** Ничего не мержить и не пушить, пока я не напишу «мержим».
4. После моего «мержим» — влить `feature/annotator` в `version2` и запушить.

## Что в патче (кратко)

- Новый сервис `annotator/` (FastAPI): фото + список признаков → ответ каждой модели
  (CLIP, Grounding DINO, OWLv2, PhenoVision, опционально GigaChat) и итог взвешенным голосованием.
  Асинхронно: `POST /annotate` → `task_id` → `GET /tasks/{id}` → `GET /tasks/{id}/result`.
- Админка: кнопка «Аннотировать» на карточке фото, модалка, прокси-эндпоинты `/annotator/*`.
- Исправления: `pg_trgm`, колонки `priority`/`is_multiple`, регистр ключей признаков,
  синонимы не падают на дублях.

## Этап 1. Ветка и патч

```powershell
git status                      # если есть незакоммиченные изменения — остановись и спроси меня
git config core.autocrlf false
git fetch origin
git checkout version2
git pull origin version2
git log --oneline -3
git checkout -b feature/annotator
git am --keep-cr annotator-version2.patch
git show --stat HEAD
```
- `--keep-cr` обязателен: `AdminPanel/main.py` в этой ветке хранится с переводами строк Windows,
  без флага патч не применится.
- Ожидаемо: `version2` заканчивается на `59bbb7d geo+browser audio`, а по `AdminPanel/main.py`
  в коммите около +96 строк, а не тысячи.
- Если `git am` выдал конфликт или version2 ушла вперёд — `git am --abort` и **остановись,
  покажи мне**. Сам конфликты не решай.
- Сам файл патча в репозиторий не добавляй.

## Этап 2. Окружение — переиспользуем готовое из D:\EcoBot

Раньше проект уже запускался у меня в `D:\EcoBot`. Ничего не переустанавливай, используй:
- `D:\EcoBot\venvs\admin` — Python-окружение админки;
- `D:\EcoBot\venvs\ann` — окружение аннотатора (PyTorch с CUDA уже стоит);
- `D:\EcoBot\DockerEcoBot\annotator\models` — веса моделей (~4 ГБ), не копировать — указать путём;
- база `eco` в локальном PostgreSQL (пароль спроси у меня) — уже заполнена, **не импортировать
  заново** (импорт с `--full` стирает всё);
- Redis — служба Windows на порту 6379;
- nginx в `C:\nginx\nginx-1.26.3`, уже настроен: порт 8080, `/admin/` → 127.0.0.1:8000,
  `/images/` → `D:/EcoBot/images/`.

Проверь, что всё это на месте, и покажи мне результат. Если чего-то нет — скажи, сам не ставь.

Доустанови в окружение аннотатора только то, чего могло не быть (scipy нужна OWLv2):
```powershell
$env:PYTHONUTF8 = "1"
D:\EcoBot\venvs\ann\Scripts\python.exe -m pip install --timeout 120 --retries 10 -r annotator\requirements.txt
```
PyTorch при этом не переустанавливается — уже стоит подходящий.

Важно для Windows: перед любым запуском Python ставь `$env:PYTHONUTF8 = "1"`
(иначе ошибки чтения файлов с кириллицей) и вызывай python.exe полным путём из venv.

## Этап 3. Скрипты запуска

Создай в `D:\EcoBot` два файла (не в репозитории). `<РЕПО>` — полный путь к текущей папке проекта.

`1_annotator_v2.bat`
```bat
@echo off
cd /d <РЕПО>\annotator
set PYTHONUTF8=1
set MODELS_DIR=D:\EcoBot\DockerEcoBot\annotator\models
set IMAGE_TIMEOUT_SEC=120
set ANNOTATOR_EXECUTORS=clip,grounding_dino,owlv2,phenovision
D:\EcoBot\venvs\ann\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
pause
```
`2_admin_v2.bat`
```bat
@echo off
cd /d <РЕПО>\AdminPanel
set PYTHONUTF8=1
set DB_HOST=localhost
set DB_USER=postgres
set DB_PASSWORD=<пароль>
set DB_NAME=eco
set REDIS_HOST=localhost
set ADMIN_DB_URL=sqlite:///D:/EcoBot/admin_panel.db
set SESSION_SECRET_KEY=local-demo
set ANNOTATOR_URL=http://127.0.0.1:8010
D:\EcoBot\venvs\admin\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
pause
```
nginx запускается старым `D:\EcoBot\3_nginx.bat`.
GigaChat не включай — ключ я добавлю сам, если понадобится.

## Этап 4. Запуск и самопроверка

1. Проверь, не заняты ли порты 8000 и 8010 (`Get-NetTCPConnection -LocalPort 8000,8010`).
   Если заняты — это, скорее всего, старая версия из `D:\EcoBot`. **Скажи мне**, процессы сам не завершай.
2. Запусти `1_annotator_v2.bat`, дождись `Application startup complete`, в логе не должно быть `ERROR`.
3. Запусти `2_admin_v2.bat`, затем `3_nginx.bat` (если nginx ещё не запущен).
4. Проверь:
   - `http://127.0.0.1:8010/health` → в `executors` четыре модели, `"failed":{}`;
   - `http://localhost:8080/admin/` → страница входа (admin / admin).

## Этап 5. СТОП — жду проверки

Напиши мне коротко: что запущено, адрес админки, что не получилось.
Дальше **ничего не делай**: я проверю в браузере (Флора → вид → «Изображения» → «Аннотировать»).
Если найду ошибки — пришлю, исправляем в `feature/annotator` новыми коммитами.

## Этап 6. Мерж и пуш — только после моего «мержим»

```powershell
git status          # не должно быть .env, resources_local.json, annotator/models, *.bat, патча
git checkout version2
git pull origin version2
git merge --no-ff feature/annotator -m "Merge feature/annotator: сервис-аннотатор изображений"
git log --oneline -5
git push origin version2
```
- Если `git pull` принёс новые коммиты и `merge` даёт конфликт — `git merge --abort`
  и покажи мне конфликт.
- `--force` не использовать. В `master` ничего не пушить.
- Отдельно ветку `feature/annotator` в GitHub не пушить, если я не попрошу.

## Правила
- Работаем только с `feature/annotator` и `version2`.
- Без Docker, WSL, виртуальных машин и подключения к серверу.
- Системные программы (PostgreSQL, Redis, nginx, Python) не устанавливать.
- Не трогать базу `eco`, папку `D:\EcoBot` (кроме создания двух .bat) и чужие процессы без моего «да».
- Не коммитить секреты, пароли, `.env`, веса моделей.
