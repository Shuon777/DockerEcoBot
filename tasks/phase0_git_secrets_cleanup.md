# Фаза 0 — Очистка секретов из git-истории

## Описание

Файл `shared.env` с реальными токенами (Telegram Bot Token, GigaChat credentials, DB password) был закоммичен в публичный репозиторий GitHub и отслеживался git. Задача — удалить его из всей истории.

## Изменения

- `shared.env` — удалён из всей git-истории с помощью `git filter-repo --path shared.env --invert-paths`
- `shared.env.example` — создан как шаблон с документированными переменными без реальных значений
- GitHub remote — обновлён через `git push --force`
- `.gitignore` — `shared.env` уже был в нём прописан, изменений не потребовалось

## Проблемы

- `git filter-repo` не был установлен — установлен через `pip install git-filter-repo`
- После `filter-repo` remote `origin` автоматически удаляется (защита утилиты) — восстановлен вручную
- Локальный `shared.env` исчез вместе с историей — нужно пересоздать вручную из `shared.env.example`

## Решения

- Использован `git filter-repo` (рекомендованная замена устаревшего `filter-branch`)
- Незакоммиченные изменения сохранены через `git stash` до перезаписи и восстановлены после

## Что осталось сделать (не входило в задачу)

- Ротировать скомпрометированные токены: `BOT_TOKEN`, `MAX_BOT_TOKEN`, `GIGACHAT_CREDENTIALS`, `DB_PASSWORD`
- Репозиторий был публичным во время коммита — секреты могли быть проиндексированы GitHub Secret Scanning
- Пересоздать `shared.env` с реальными значениями из `shared.env.example`
