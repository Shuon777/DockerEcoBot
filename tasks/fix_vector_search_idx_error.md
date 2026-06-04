# Fix: vector search idx referenced before assignment

## Описание

Исправлена ошибка `UnboundLocalError: local variable 'idx' referenced before assignment`
в fallback-логике векторного поиска.

## Изменения

- `salut_bot/search_api/use_cases/search_use_case.py` — исправлен отступ блока
  `vector_resources.append(...)`: перемещён внутрь цикла `for idx, doc in enumerate(vector_docs)`.

## Проблемы

1. При пустом `vector_docs` цикл не выполнялся, `idx` оставалась неопределённой,
   после цикла обращение к ней вызывало краш.
2. При непустом `vector_docs` в список добавлялся только последний элемент вместо всех,
   что нарушало логику накопления результатов.

## Решения

Оба дефекта — следствие одного неправильного отступа. Блок `append` перенесён
внутрь тела цикла (добавлен один уровень отступа — 4 пробела).
