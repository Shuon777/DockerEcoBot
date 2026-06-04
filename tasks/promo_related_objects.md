# Промо-функция: связанные услуги/экспозиции

## Описание

После ответа на вопрос пользователя о животном/растении дополнительно возвращается
список связанных услуг/экспозиций из таблицы `object_object_link`. Функция включается
через env-переменную `PROMO_ENABLED=true`.

## Изменения

- `salut_bot/search_api/adapters/sqlalchemy_repository.py` — добавлен метод
  `find_related_objects(object_ids, relation_type)`: SQL-запрос к `object_object_link`
  JOIN `object` → возвращает связанные объекты с именем и типом.

- `salut_bot/search_api/routes/related.py` — новый файл, Blueprint `related_bp`,
  роут `POST /objects/related` принимает `{object_ids, relation_type}`, возвращает
  `{related: [...]}`.

- `salut_bot/search_api/routes/__init__.py` — зарегистрирован `related_bp` в
  `all_blueprints`.

- `EcoBotProject/DialogService/application/search/slot_search_executor.py`:
  - `__init__`: добавлены `_promo_enabled` (из `PROMO_ENABLED`) и
    `_promo_relation_type` (из `PROMO_RELATION_TYPE`, дефолт `"promo"`).
  - `execute()`: после основного поиска вызывается `_fetch_promo()` при включённом флаге.
  - `_fetch_promo()`: новый метод, POST к `/objects/related` с id найденных объектов.
  - `_format_result()`: добавлен параметр `promo_objects`, заполняет `result["promo"]`.

## Проблемы

Существующий `/search` не читает `object_object_link`, поэтому потребовался новый
эндпоинт в salut_bot.

## Решения

Минимальные добавления без изменения существующей логики. Тип связи задаётся через
`PROMO_RELATION_TYPE` (дефолт `"promo"`), что позволяет переиспользовать эндпоинт
для других типов связей в будущем.

## Что нужно сделать после деплоя

1. В AdminPanel создать связь между объектом (напр. нерпа) и услугой (напр. экспозиция)
   с `relation_type = "promo"`.
2. Добавить в `.env` DialogService:
   ```
   PROMO_ENABLED=true
   PROMO_RELATION_TYPE=promo
   ```
3. Передеплоить `salut_bot` и `dialog_service`.
