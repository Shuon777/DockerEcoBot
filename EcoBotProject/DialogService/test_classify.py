"""
Интеграционный тест в режиме Classify Mode (аналог чекбокса 🔍 в /chat).
Запуск: docker exec dockerecobot-core-api-1 python test_classify.py

Каждый запрос → /search_pipeline (SlotClassifier + SlotSearchExecutor).
Консоль: читаемый Q&A с реальными результатами поиска.
Файл:    /app/qa_report_<timestamp>.json
"""
import asyncio
import aiohttp
import json
from datetime import datetime

BASE_URL = "http://localhost:5001/search_pipeline"
TEXT_PREVIEW = 180   # сколько символов текстового ответа показывать

# (запрос, ожидаемый шаблон)
TEST_CASES = [
    # ─── О1: ОФФ + синоним + Текст ───────────────────────────────────────────
    ("Расскажи о нерпе",                                    "О1"),
    ("Что такое омуль?",                                    "О1"),
    ("Кто такой байкальский осётр?",                       "О1"),
    ("Опиши сибирскую лиственницу",                        "О1"),
    ("Что за дерево кедр?",                                 "О1"),

    # ─── О2: ОФФ + синоним + Текст + доп. свойство ───────────────────────────
    ("Расскажи о краснокнижной нерпе",                     "О2"),
    ("Что известно об эндемичном омуле?",                  "О2"),

    # ─── О3: ОФФ + синоним + Изображение + image-features ────────────────────
    ("Покажи нерпу зимой",                                  "О3"),
    ("Фото омуля в реке",                                   "О3"),
    ("Как выглядит лиственница осенью?",                   "О3"),
    ("Покажи кедр в горах",                                 "О3"),

    # ─── О4: ОФФ + синоним + Изображение (без image-features) ────────────────
    ("Покажи нерпу",                                        "О4"),
    ("Фото омуля",                                          "О4"),
    ("Как выглядит байкальский осётр?",                    "О4"),

    # ─── О5: ОФФ + синоним + Геоданные + топоним ─────────────────────────────
    ("Где на Байкале живёт нерпа?",                        "О5"),
    ("Где в Иркутске растёт кедр?",                        "О5"),

    # ─── О6: ОФФ + синоним + Геоданные (без топонима) ───────────────────────
    ("Где обитает нерпа?",                                  "О6"),
    ("Где растёт сибирский кедр?",                         "О6"),
    ("Покажи на карте ареал омуля",                        "О6"),

    # ─── О7: ОФФ – синоним + свойства ────────────────────────────────────────
    ("Краснокнижные животные",                              "О7"),
    ("Эндемичные птицы",                                    "О7"),

    # ─── О8: ОФФ – синоним + доп. свойство + location ───────────────────────
    ("Краснокнижные растения на Ольхоне",                  "О8"),
    ("Редкие птицы в Иркутске",                            "О8"),
    ("Эндемичные рыбы около Байкала",                      "О8"),
    ("Редкие растения Байкала",                             "О8"),

    # ─── О9: ОФФ – синоним + image-features ──────────────────────────────────
    ("Покажи птиц в лесу",                                  "О9"),
    ("Фото цветущих растений на лугу",                     "О9"),
    ("Как выглядят рыбы в озере?",                         "О9"),

    # ─── О10: ОФФ – синоним + location ───────────────────────────────────────
    ("Флора и фауна острова Ольхон",                       "О10"),

    # ─── О11: ОФФ – синоним + location + Геоданные ───────────────────────────
    ("Покажи на карте растения Ольхона",                   "О11"),

    # ─── О12: ОФФ – синоним + тип офф + location ─────────────────────────────
    ("Какая флора есть на Байкале?",                       "О12"),
    ("Какие животные живут на Байкале?",                   "О12"),
    ("Какие рыбы водятся в Байкале?",                      "О12"),
    ("Животные Ольхона",                                    "О12"),
    ("Растения острова Ольхон",                            "О12"),

    # ─── Г1: Гео + синоним + Текст ───────────────────────────────────────────
    ("Расскажи о Байкальском музее СО РАН",                "Г1"),
    ("Что такое заповедник Баргузинский?",                 "Г1"),
    ("Расскажи об острове Ольхон",                         "Г2"),

    # ─── Г2: Гео + синоним + Текст + location ────────────────────────────────
    ("Байкальский музей в Листвянке — расскажи",           "Г2"),

    # ─── Г3: Гео + синоним + Геоданные ───────────────────────────────────────
    ("Где находится остров Ольхон?",                       "Г3"),
    ("Покажи на карте Баргузинский заповедник",            "Г3"),
    ("Где находится Байкальский музей СО РАН?",            "Г3"),

    # ─── Г4: Гео – синоним + subtypes + location ─────────────────────────────
    ("Музеи в Иркутске",                                    "Г4"),
    ("Заповедники рядом с Байкалом",                       "Г4"),
    ("Турбазы на острове Ольхон",                          "Г4"),
    ("Достопримечательности Байкала",                      "Г4"),

    # ─── Г5: Гео – синоним + subtypes + location + Геоданные ────────────────
    ("Покажи на карте музеи Иркутска",                     "Г5"),
    ("Где на карте заповедники около Байкала?",            "Г5"),

    # ─── Г6: Гео – синоним + subtypes (без location) ─────────────────────────
    ("Какие есть заповедники?",                            "Г6"),
    ("Список музеев",                                       "Г6"),
    ("Есть ли горнолыжные базы?",                          "Г6"),

    # ─── Г7: Гео – синоним + только location ─────────────────────────────────
    ("Что посмотреть в Иркутске?",                         "Г7"),

    # ─── У1/У3: Услуга ────────────────────────────────────────────────────────
    ("Как купить билет в Байкальский музей?",              "У1"),
    ("Режим работы Баргузинского заповедника",             "У1"),
    ("Как добраться до Байкальского музея из Иркутска?",   "У3"),
    ("Как добраться до Байкала?",                          "У3"),
    ("Правила посещения заповедников в Иркутске",          "У3"),
    ("Контакты Листвянки",                                  "У3"),
]


# ─────────────────────────── Форматирование ──────────────────────────────────

def _slots_line(slots: dict) -> str:
    """Одна строка: шаблон | тип | синоним | модальность | extras."""
    parts = [
        f"[{slots.get('template', '?')}]",
        slots.get("object_type", "—"),
    ]
    if slots.get("synonym"):
        parts.append(f"синоним: «{slots['synonym']}»")
    parts.append(slots.get("modality", "—"))

    extras = []
    for key in ("features", "properties", "extra"):
        d = slots.get(key) or {}
        for k, v in d.items():
            if v:
                extras.append(f"{k}={v}")
    if extras:
        parts.append("  " + "  ".join(extras))

    return "  |  ".join(parts)


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return content.get("text") or content.get("description") or ""
    return ""


def _resource_lines(resources: list, modality: str) -> list[str]:
    """Строки-ответы: текст / URL изображений / URL карт."""
    lines = []
    filtered = [r for r in resources if r.get("modality_type") == modality]
    if not filtered:
        # Покажем все ресурсы если фильтр ничего не дал
        filtered = resources

    for r in filtered:
        mtype = r.get("modality_type", "")
        content = r.get("content")

        if mtype == "Текст":
            text = _extract_text(content).strip()
            if text:
                preview = text[:TEXT_PREVIEW].replace("\n", " ")
                if len(text) > TEXT_PREVIEW:
                    preview += "…"
                lines.append(f"  💬  {preview}")

        elif mtype == "Изображение":
            url = content if isinstance(content, str) else (
                (content or {}).get("url") or (content or {}).get("file_path") or ""
            )
            if url:
                lines.append(f"  🖼   {url}")

        elif mtype == "Геоданные":
            static = (content or {}).get("map_links", {}).get("static") if isinstance(content, dict) else None
            inter  = (content or {}).get("map_links", {}).get("interactive") if isinstance(content, dict) else None
            if static:
                lines.append(f"  🗺   {static}")
            if inter:
                lines.append(f"  🔗  {inter}")

    return lines


async def call_pipeline(sem: asyncio.Semaphore,
                        client: aiohttp.ClientSession,
                        query: str):
    async with sem:
        try:
            async with client.post(BASE_URL, json={"query": query}) as resp:
                return await resp.json()
        except Exception as exc:
            return exc


# ─────────────────────────── Основной цикл ───────────────────────────────────

async def run_tests():
    started_at = datetime.now()
    timestamp  = started_at.strftime("%Y%m%d_%H%M%S")
    report_path = f"/app/qa_report_{timestamp}.json"

    W = 72  # ширина разделителей
    print(f"\n{'═'*W}")
    print(f"  Q&A ОТЧЁТ  (Classify Mode)  |  {started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  {len(TEST_CASES)} запросов  →  {BASE_URL}")
    print(f"{'═'*W}")

    sem = asyncio.Semaphore(6)
    connector = aiohttp.TCPConnector(limit=12)

    async with aiohttp.ClientSession(connector=connector) as client:
        tasks = [call_pipeline(sem, client, q) for q, _ in TEST_CASES]
        raw_results = await asyncio.gather(*tasks)

    # ── Вывод результатов ────────────────────────────────────────────────────
    report_entries = []
    current_template = None

    for (query, expected), result in zip(TEST_CASES, raw_results):

        # Разделитель при смене шаблона
        if expected != current_template:
            current_template = expected
            label = f"── {expected} "
            print(f"\n{label}{'─'*(W - len(label))}")

        # Разбираем ответ
        if isinstance(result, Exception):
            slots     = {}
            objects   = []
            resources = []
            error     = str(result)
        elif isinstance(result, dict) and "error" in result:
            slots     = {}
            objects   = []
            resources = []
            error     = result["error"]
        else:
            slots     = result.get("slots", {})
            search    = result.get("search", {}) or {}
            objects   = search.get("objects", []) or []
            resources = search.get("resources", []) or []
            error     = None

        # Отфильтруем ресурсы по модальности из слотов
        modality = slots.get("modality", "")
        res_matching = [r for r in resources if r.get("modality_type") == modality]
        res_count    = len(res_matching) if res_matching else len(resources)

        # ── Консольная запись ─────────────────────────────────────────────
        print(f"\n  ❓  {query}")

        if error:
            print(f"  ⛔  ОШИБКА: {error}")
        else:
            # Строка классификатора
            print(f"  🏷   {_slots_line(slots)}")

            # Статистика поиска
            obj_word = "объект" if len(objects) == 1 else (
                "объекта" if 2 <= len(objects) <= 4 else "объектов"
            )
            res_word = "ресурс" if res_count == 1 else (
                "ресурса" if 2 <= res_count <= 4 else "ресурсов"
            )
            obj_label  = f"{len(objects)} {obj_word}"
            res_label  = f"{res_count} {res_word} ({modality})" if modality else f"{res_count} {res_word}"
            total_note = f"  [{len(resources)} всего]" if modality and len(resources) != res_count else ""
            print(f"  📦  {obj_label}  ·  {res_label}{total_note}")

            if resources:
                for line in _resource_lines(resources, modality):
                    print(line)
            else:
                print("  —   нет ресурсов")

        # ── Запись для JSON ───────────────────────────────────────────────
        entry = {
            "expected_template": expected,
            "query":    query,
            "slots":    slots,
            "objects":  objects,
            "resources_count": {"total": len(resources), "modality_match": res_count},
            "error":    error,
            "raw":      result if not isinstance(result, Exception) else str(result),
        }
        report_entries.append(entry)

    # ── Итоговая таблица ─────────────────────────────────────────────────────
    elapsed = (datetime.now() - started_at).total_seconds()

    total   = len(report_entries)
    errors  = sum(1 for e in report_entries if e["error"])
    empty   = sum(1 for e in report_entries if not e["error"] and e["resources_count"]["total"] == 0)
    has_res = total - errors - empty

    print(f"\n{'═'*W}")
    print(f"  ИТОГО: {total} запросов  ·  {has_res} с результатами  ·  {empty} пустых  ·  {errors} ошибок")
    print(f"  Время: {elapsed:.1f}с\n")

    # По шаблонам
    by_tmpl: dict[str, list] = {}
    for e in report_entries:
        by_tmpl.setdefault(e["expected_template"], []).append(e)

    col = ("Шаблон", "Запросов", "С рез.", "Пустых", "Ошибок")
    print(f"  {col[0]:<8}  {col[1]:<10}  {col[2]:<7}  {col[3]:<7}  {col[4]}")
    print(f"  {'─'*44}")
    for tmpl, entries in sorted(by_tmpl.items()):
        errs  = sum(1 for x in entries if x["error"])
        empts = sum(1 for x in entries if not x["error"] and x["resources_count"]["total"] == 0)
        has   = len(entries) - errs - empts
        print(f"  {tmpl:<8}  {len(entries):<10}  {has:<7}  {empts:<7}  {errs}")

    print(f"{'═'*W}\n")

    # ── JSON-файл ─────────────────────────────────────────────────────────────
    report = {
        "mode":         "classify",
        "generated_at": started_at.isoformat(),
        "elapsed_sec":  round(elapsed, 2),
        "total":        total,
        "with_results": has_res,
        "empty":        empty,
        "errors":       errors,
        "entries":      report_entries,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"  Отчёт сохранён: {report_path}")
    print(f"  Скопировать:    docker cp dockerecobot-core-api-1:{report_path} ./qa_report_{timestamp}.json\n")


if __name__ == "__main__":
    asyncio.run(run_tests())
