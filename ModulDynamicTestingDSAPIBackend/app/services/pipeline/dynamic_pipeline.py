import pandas as pd
import asyncio
import httpx
import sys
import json
import os

import logging
logger = logging.getLogger(__name__)

from datetime import datetime
from tqdm import tqdm
from typing import List, Dict, Any, Tuple
import json
from datetime import datetime
from app.models.pipeline_model import FullTestResult, TestStats
# Импорты ваших новых сервисов
from app.services.llm_evaluator.evaluator import LLMService
from app.services.llm_evaluator.vision_service import VisionLL_Service
from app.services.text_validation.checkers import TextChecker
from app.services.text_validation.checkers import TextCheckerPiiFIO
from app.services.text_validation.neural_checkers import NeuralValidator
from app.services.text_validation.spelling import LocalSpellingChecker
from app.services.image_validation.checkers import ImageChecker
from app.services.image_validation.nsfw_checker import ImageSafetyValidator
from app.services.image_validation.map_classifier import MapClassifier
from app.services.image_validation.map_semantic_validator import MapSemanticValidator
from app.models.testing_status import ACTIVE_JOBS, TaskStatus

# 1. Фикс для работы Natasha и Pymorphy3 на Python 3.12
try:
    import pymorphy3
    sys.modules['pymorphy2'] = pymorphy3
except:
    pass

class IntegratedDynamicPipeline:
    def __init__(self, domain: str = None):
        domain = domain or os.getenv("PUBLIC_BASE_URL", "https://testecobot.ru")
        self.domain = domain
        self.test_query_url = f"{domain}/test-api/test_query"

        self.llm = LLMService()
        self.vlm = VisionLL_Service()
        self.text_checker = TextChecker()
        self.text_checker_pii_fio = TextCheckerPiiFIO()
        self.neural = NeuralValidator()
        self.speller = LocalSpellingChecker()
        self.img_checker = ImageChecker()
        self.nsfw = ImageSafetyValidator()
        self.map_classifier = MapClassifier()
        self.map_semantic_validator = MapSemanticValidator()

    async def post_test_query(self, query: str, debug_mode: bool = True) -> Dict[str, Any]:
        payload = {
            "query": query,
            "user_id": "test_user",
            "settings": {"debug_mode": debug_mode},

        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(self.test_query_url, json=payload)
                if response.status_code == 200:
                    return response.json()
                return {"error": f"Status code {response.status_code}", "raw": response.text}
            except Exception as e:
                return {"error": str(e)}

    async def generate_q_variations(self, template: str, count: int = 5) -> List[str]:
        """Генерация вариаций"""
        prompt = (
            f"Дай {count} вариаций вопроса на русском языке. Меняй падежи, делай опечатки. "
            f"Верни строго JSON: {{\"variants\": [\"...\", \"...\"]}}. "
            f"Вопрос: {template}"
        )
        try:
            res = await self.llm.llm.ainvoke(prompt)
            data = json.loads(res.content)
            return data.get("variants", [template])
        except:
            return [template]

    async def run_full_suite(self, query: str, bot_response: Dict[str, Any]) -> Dict[str, Any]:
        """Комплексный запуск всех тестов проекта для одного ответа"""
        text = ""
        if isinstance(bot_response, list) and len(bot_response) > 0:
            text = bot_response[0].get("text", str(bot_response))
        elif isinstance(bot_response, dict):
            text = bot_response.get("text", str(bot_response))

        # Текстовые тесты (Лингвистика + PII)
        spell = await self.speller.check_spelling(text)
        pii = self.text_checker_pii_fio.check_pii_and_fio(text)

        # Нейронные тесты (Эмоции + Токсичность)
        tox = self.neural.analyze_detailed_toxicity(text)
        emo = self.neural.analyze_detailed_emotions(text)

        # Визуальные тесты (NSFW + VLM)
        img_urls = self.img_checker.extract_image_urls(bot_response)
        nsfw_status = "No Images"
        vlm_desc = "N/A"
        if img_urls:
            n_res = await self.nsfw.analyze_image_safety(img_urls[0])
            nsfw_status = "Safe" if n_res["is_safe"] else "NSFW DETECTED"
            vlm_res = await self.vlm.get_image_description(img_urls[0])
            vlm_desc = vlm_res.get("description", str(vlm_res))

        # Смысловой тест (LLM Relevance)
        rel = await self.llm.check_relevance(query, text)

        return {
            "query": query,
            "spelling_passed": spell["is_passed"],
            "pii_fio_passed": pii["is_passed"],
            "toxicity_passed": tox["is_passed"],
            "sentiment_label": emo["details"],
            "image_safety": nsfw_status,
            "vlm_image_description": vlm_desc,
            "llm_relevance_passed": rel["is_passed"],
            "llm_reasoning": rel.get("reasoning", ""),
            "bot_full_response": str(bot_response)[:500]
        }

    async def run_comprehensive_tests(self, t_id: int, template: str, query: str, bot_res: Dict[str, Any]) -> Dict[
        str, Any]:
        """
        Запуск тестов с оптимизацией: если ссылка на фото битая, нейросети не запускаются.
        """
        text = str(bot_res.get("text", bot_res))
        if isinstance(bot_res, list) and len(bot_res) > 0:
            text = bot_res[0].get("text", str(bot_res))

        # --- ОБЩИЕ ТЕСТЫ ДЛЯ ВСЕХ ЛИСТОВ ---
        empty_res = self.text_checker.check_not_empty(text)
        lang_res = self.text_checker.check_language(text, "ru")

        base_data = {
            "Шаблон": template,
            "Сгенерированный вопрос": query,
            "Ответ бота": text[:1000],
            "Ответ не пустой": "✅" if empty_res["is_passed"] else "❌ ПУСТО",
            "Соответствие языка (RU)": "✅" if lang_res["is_passed"] else f"❌ ({lang_res['data'].get('detected')})"
        }

        # --- СПЕЦИФИЧЕСКИЕ ТЕСТЫ ПО ID ---

        # ЛИСТ ТЕКСТ (ID 3)
        if t_id == 3:
            spell = self.speller.check_spelling(text)
            pii = self.text_checker_pii_fio.check_pii_and_fio(text)
            tox = self.neural.analyze_detailed_toxicity(text)
            emo = self.neural.analyze_detailed_emotions(text)
            res_encode = self.text_checker.check_encoding_and_markup(text)
            res_ethics_llm = await self.llm.check_sentiment_and_ethics(text)
            rel = await self.llm.check_relevance(query, text)
            safety_leakage = await self.llm.check_safety_leakage(query, text)


            base_data.update({
                "Проверка кодировки и разметки": '✅ Чисто' if res_encode['is_passed'] else '❌ ОШИБКА\n'+f"[Details]: {res_encode['details']}\n",
                "Орфография": "✅ Нет ошибок" if spell["is_passed"] else f"❌ ({len(spell['data']['errors'])} ош.)",
                "Конфиденциальность": "✅" if pii["is_passed"] else f"❌ Утечка - {pii.get('data')}",
                "Токсичность": "✅ Не токсично" if tox["is_passed"] else "❌ Токсично\n"+f"Детали: {tox['details']}\n",
                "Эмоция/Тон": emo["details"],
                "LLM Эмоция/Тон": res_ethics_llm.get('reasoning'),
                "Тест на утечку инструкций": "✅ Нет утечки" if safety_leakage["is_passed"] else f"❌ есть утечка - {safety_leakage['reasoning']}",
                "Релевантность (LLM)": "✅" if rel.get("is_passed") else "❌",
                "Анализ LLM": rel.get("reasoning", "")
            })

        # ЛИСТ ИЗОБРАЖЕНИЯ (ID 2)
        elif t_id == 2:
            img_urls = self.img_checker.extract_image_urls(bot_res)

            # Инициализация значений по умолчанию
            img_status = "Нет фото"
            img_size = "N/A"
            nsfw_status = "Пропуск (Нет фото)"
            vlm_desc = "Пропуск (Нет фото)"
            vlm_sync_res = "Пропуск (Нет фото)"

            if img_urls:
                url = img_urls[0]
                # 1. Сначала проверяем доступность ссылки (Технический чекер)
                size_res = await self.img_checker.validate_url_and_size(url)

                if size_res["is_valid"]:
                    # ССЫЛКА ВАЛИДНА - запускаем тяжелые нейросети
                    img_status = "✅ Доступна"
                    img_size = f"{size_res.get('width')}x{size_res.get('height')}"

                    # Нейросетевая проверка безопасности
                    n_res = await self.nsfw.analyze_image_safety(url)
                    nsfw_status = "✅ Безопасно" if n_res["is_safe"] else "❌ NSFW"

                    # Описание через Vision-модель (VLM)
                    v_res = await self.vlm.get_image_description(url)
                    vlm_desc = v_res.get("description", "Ошибка описания")

                    # Определение объекта через Vision-модель (VLM)
                    sync_res = await self.vlm.verify_object_in_image(url, text)
                    vlm_sync_res = '✅ ОБЪЕКТ ПОДТВЕРЖДЕН' if sync_res.get('found') else '❌ РАССИНХРОН\n'+f"Детали VLM: {sync_res.get('detected_what')}\n"
                else:
                    # ССЫЛКА БИТАЯ - пропускаем анализ нейросетями
                    img_status = f"❌ Ошибка URL ({size_res.get('error')})"
                    img_size = "N/A"
                    nsfw_status = "Пропуск (Ссылка битая)"
                    vlm_desc = "Пропуск (Ссылка битая)"
                    vlm_sync_res = "Пропуск (Ссылка битая)"

            base_data.update({
                "URL изображения": img_status,
                "Размер фото": img_size,
                "Безопасность (NSFW)": nsfw_status,
                "Что на фото (VLM)": vlm_desc,
                "Определение объекта (VLM)": vlm_sync_res
            })

        # ЛИСТ КАРТЫ (ID 1)
        elif t_id == 1:
            geo_links = await self.img_checker.check_geo_links(bot_res)
            geo_status = "✅ Ок" if geo_links and all(g["is_valid"] for g in geo_links) else "❌ Битая/Нет"

            img_urls = self.img_checker.extract_image_urls(bot_res)
            is_map_visual = "N/A"

            if img_urls:
                url = img_urls[0]
                # Также добавим проверку для CLIP (визуальный анализ карты)
                valid_res = await self.img_checker.validate_url_and_size(url)
                if valid_res["is_valid"]:
                    m_res = await self.map_classifier.is_it_a_map(url)
                    is_map_visual = "✅ Карта" if m_res["is_passed"] else f"❌ {m_res['top_prediction']}"
                else:
                    is_map_visual = "Пропуск (Ссылка битая)"

            base_data.update({
                "Валидность Гео-ссылок": geo_status,
                "Провайдер": geo_links[0]["provider"] if geo_links else "N/A",
                "Карта визуально": is_map_visual
            })

        return base_data

    async def run_tests(self, t_id: int, template: str, query: str, bot_res: Dict[str, Any], mode: str) -> Dict[
        str, Any]:
        """
        Запуск тестов с оптимизацией: если ссылка на фото битая, нейросети не запускаются.
        """
        text = str(bot_res.get("content", bot_res))
        #if isinstance(bot_res, list) and len(bot_res) > 0:
            #text = bot_res[0].get("content", str(bot_res))

        # --- ОБЩИЕ ТЕСТЫ ДЛЯ ВСЕХ ЛИСТОВ ---
        empty_res = self.text_checker.check_not_empty(text)
        lang_res = self.text_checker.check_language(text, "ru")

        base_data = {
            "Шаблон": template,
            "Сгенерированный вопрос": query,
            "Ответ бота": str(bot_res),
            "Наличие ответа": "✅" if empty_res["is_passed"] else "❌ ПУСТО",
            "Локализация контента (RU)": "✅" if lang_res["is_passed"] else f"❌ ({lang_res['data'].get('detected')})"
        }

        # --- СПЕЦИФИЧЕСКИЕ ТЕСТЫ ПО ID ---

        # ЛИСТ ТЕКСТ (ID 3)
        if t_id == 3:
            spell = self.speller.check_spelling(text)
            pii = self.text_checker_pii_fio.check_pii_and_fio(text)
            tox = self.neural.analyze_detailed_toxicity(text)
            emo = self.neural.analyze_detailed_emotions(text)

            rel = await self.llm.check_relevance(query, text) if mode != 'no llm' else {}
            safety_leakage = await self.llm.check_safety_leakage(query, text) if mode != 'no llm' else {}
            res_encode = self.text_checker.check_encoding_and_markup(text)
            res_ethics_llm = await self.llm.check_sentiment_and_ethics(text) if mode != 'no llm' else {}

            if mode != 'no llm':
                base_data.update({
                    "Техническая целостность текста": '✅ Чисто' if res_encode.get("is_passed") else '❌ ОШИБКА\n'+f"[Details]: {res_encode['details']}\n",
                    "Лингвистическая грамотность": "✅ Нет ошибок" if spell.get("is_passed") else f"❌ ({len(spell['data']['errors'])} ош.) Детали: {spell['data']['errors']}",
                    "Защита персональных данных (ПДн)": "✅" if pii["is_passed"] else f"❌ Утечка - {pii.get('data')}",
                    "Соблюдение этических норм": "✅ Не токсично" if tox.get("is_passed") else "❌ Токсично\n"+f"Детали: {tox['details']}\n",
                    "Эмоциональный профиль": emo["details"],
                    "Тональный аудит (LLM)": res_ethics_llm.get('reasoning'),
                    "Безопасность системных данных": "✅ Нет утечки" if safety_leakage.get("is_passed") else f"❌ есть утечка - {safety_leakage.get('reasoning')}",
                    "Смысловое соответствие запросу (LLM)": "✅" if rel.get("is_passed") else "❌",
                    "Заключение (LLM)": rel.get("reasoning", "")
                })
            else:
                base_data.update({
                    "Техническая целостность текста": '✅ Чисто' if res_encode.get("is_passed") else '❌ ОШИБКА\n'+f"[Details]: {res_encode['details']}\n",
                    "Лингвистическая грамотность": "✅ Нет ошибок" if spell.get("is_passed") else f"❌ ({len(spell['data']['errors'])} ош.) Детали: {spell['data']['errors']}",
                    "Защита персональных данных (ПДн)": "✅" if pii["is_passed"] else f"❌ Утечка - {pii.get('data')}",
                    "Соблюдение этических норм": "✅ Не токсично" if tox.get("is_passed") else "❌ Токсично\n"+f"Детали: {tox['details']}\n",
                    "Эмоциональный профиль": emo["details"],
                    "Тональный аудит (LLM)": "Выбран режим без LLM",
                    "Безопасность системных данных (LLM)": "Выбран режим без LLM",
                    "Смысловое соответствие запросу (LLM)": "Выбран режим без LLM",
                    "Заключение (LLM)": "Выбран режим без LLM"
                })

        # ЛИСТ ИЗОБРАЖЕНИЯ (ID 2)
        elif t_id == 2:
            img_urls = self.img_checker.extract_image_urls(str(bot_res.get("content", bot_res)))

            # Инициализация значений по умолчанию
            img_status = "Пропуск (Нет изображений)"
            img_size = "Пропуск (Нет изображений)"
            nsfw_status = "Пропуск (Нет изображений)"
            vlm_desc = "Пропуск (Нет изображений)"
            vlm_sync_res = "Пропуск (Нет изображений)"

            if img_urls:
                url = img_urls[0]
                # 1. Сначала проверяем доступность ссылки (Технический чекер)
                size_res = await self.img_checker.validate_url_and_size(url)

                if size_res["is_valid"]:
                    # ССЫЛКА ВАЛИДНА - запускаем тяжелые нейросети
                    img_status = "✅ Доступна"
                    img_size = f"{size_res.get('width')}x{size_res.get('height')}"

                    # Нейросетевая проверка безопасности
                    n_res = await self.nsfw.analyze_image_safety(url)
                    nsfw_status = "✅ Безопасно" if n_res["is_safe"] else "❌ NSFW"
                    # Определение объекта через Vision-модель (VLM)
                    if mode != 'no llm':
                        # Описание через Vision-модель (VLM)
                        v_res = await self.vlm.get_image_description(url) if mode != 'no llm' else {}
                        vlm_desc = v_res.get("description", "Нет описания")
                        sync_res = await self.vlm.verify_object_in_image(url, text) if mode != 'no llm' else {}
                        vlm_sync_res = '✅ ОБЪЕКТ ПОДТВЕРЖДЕН' if sync_res.get('found') else '❌ ОБЪЕКТ НЕ ПОДТВЕРЖДЕН\n'+f"Детали VLM: {sync_res.get('detected_what')}\n"
                    else:
                        vlm_desc = None
                        vlm_sync_res = None
                else:
                    # ССЫЛКА БИТАЯ - пропускаем анализ нейросетями
                    img_status = f"❌ Ошибка URL ({size_res.get('error')})"
                    img_size = "Не удалось протестировать"
                    nsfw_status = "Пропуск (Ссылка битая)"
                    vlm_desc = "Пропуск (Ссылка битая)"
                    vlm_sync_res = "Пропуск (Ссылка битая)"

            base_data.update({
                "Доступность медиа-ресурса": img_status,
                "Техническое качество (Разрешение)": img_size,
                "Визуальная цензура (NSFW)": nsfw_status,
                "Визуальный анализ содержимого (LLM)": vlm_desc,
                "Верификация объекта на фото (LLM)": vlm_sync_res
            })

        # ЛИСТ КАРТЫ (ID 1)
        elif t_id == 1:
            geo_links = await self.img_checker.check_geo_links(str(bot_res.get("static_map", bot_res)))
            geo_status = "✅ Ок" if geo_links and all(g["is_valid"] for g in geo_links) else "❌ Битая/Нет"

            img_urls = self.img_checker.extract_image_urls(bot_res)
            is_map_visual = "Нет карт для тестирования"
            is_map_valid = "Нет карт для тестирования"

            if img_urls:
                url = img_urls[0]
                # Также добавим проверку для CLIP (визуальный анализ карты)
                valid_res = await self.img_checker.validate_url_and_size(url)
                if valid_res["is_valid"]:
                    m_res = await self.map_classifier.is_it_a_map(url)
                    is_map_visual = "✅ Карта" if m_res.get("is_passed") else f"❌ {m_res.get('top_prediction')}"
                    if mode != 'no llm':
                        map_valid_res = await self.map_semantic_validator.validate_map_context(query,text, str(bot_res.get("static_map", bot_res))) if mode != 'no llm' else {}
                        is_map_valid = "✅ Карта соответствует запросу" if map_valid_res.get("is_passed") else f"❌ {map_valid_res.get('reasoning')}"
                    else:
                        is_map_valid = None
                else:
                    is_map_visual = "Пропуск (Ссылка битая)"
                    is_map_valid = "Пропуск (Ссылка битая)"

            base_data.update({
                "Работоспособность Гео-ссылок": geo_status,
                "Тип картографического сервиса": geo_links[0]["provider"] if geo_links else "Нет карт для тестирования",
                "Визуальная валидация карты": is_map_visual,
                "Гео-контекстное соответствие (LLM)": is_map_valid
            })

        return base_data


    async def process_from_file(self, file_path: str):
        """
        Чтение сценариев из файла с защитой от потери данных при сбоях или прерывании.
        """
        id_to_sheet = {
            1: "Карты",
            2: "Изображения",
            3: "Текст"
        }
        #file_path = 'doc/tests.xlsx'
        print(f"📂 Загрузка сценариев из {file_path}...")
        try:
            df_tests = pd.read_excel(file_path)
        except Exception as e:
            print(f"❌ Не удалось прочитать файл: {e}")
            return

        # Словарь для накопления результатов
        results_by_sheet = {"Текст": [], "Изображения": [], "Карты": []}

        # Переменная для отслеживания прогресса (сколько строк обработано)
        processed_count = 0
        total_rows = len(df_tests)

        print(f"🚀 Начинаю аудит ({total_rows} сценариев). Нажмите Ctrl+C для экстренного сохранения.")

        try:
            # Основной цикл тестирования
            for index, row in tqdm(df_tests.iterrows(), total=total_rows, desc="Аудит сценариев"):
                t_id = int(row['id_type'])
                template = row['template']
                query = row['generated_question']
                raw_answer = row['bot_answer_json']

                # Парсинг ответа
                try:
                    bot_res = json.loads(raw_answer) if isinstance(raw_answer, str) and raw_answer.strip().startswith(
                        '{') else {"text": raw_answer}
                except:
                    bot_res = {"text": str(raw_answer)}

                # ЗАПУСК ТЕСТОВ (с асинхронным ожиданием)
                test_results = await self.run_comprehensive_tests(t_id, template, query, bot_res)

                # Добавляем результат в соответствующий список
                sheet_name = id_to_sheet.get(t_id, "Текст")
                results_by_sheet[sheet_name].append(test_results)

                processed_count += 1

            print("\n✅ Тестирование завершено в штатном режиме.")

        except KeyboardInterrupt:
            print(f"\n⚠️ ТЕСТИРОВАНИЕ ПРЕРВАНО ПОЛЬЗОВАТЕЛЕМ (Ctrl+C).")
            print(f"💾 Сохраняю прогресс: обработано {processed_count} из {total_rows} строк...")

        except Exception as e:
            print(f"\n❌ ПРОИЗОШЛА КРИТИЧЕСКАЯ ОШИБКА: {e}")
            print(f"💾 Попытка спасения данных: обработано {processed_count} строк...")

        finally:
            # БЛОК СОХРАНЕНИЯ (Выполняется ВСЕГДА: и при успехе, и при ошибке)
            if processed_count > 0:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                # Если прервано — добавляем пометку PARTIAL в имя файла
                status_suffix = "FULL" if processed_count == total_rows else "PARTIAL"
                out_path = f"results/Audit_Report_{status_suffix}_{timestamp}.xlsx"

                os.makedirs("results", exist_ok=True)

                try:
                    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
                        for s_name, data in results_by_sheet.items():
                            if data:
                                df = pd.DataFrame(data)
                                df.to_excel(writer, sheet_name=s_name, index=False)
                    print(f"📊 Отчет сформирован и сохранен: {out_path}")
                except Exception as save_error:
                    print(f"❌ ОШИБКА ПРИ ЗАПИСИ EXCEL: {save_error}")
            else:
                print("ℹ️ Нет данных для сохранения (ни одна строка не была обработана).")

    async def process_dynamic_testing(self, session_id: str, mode: str, objs: list[str]):
        """
        Чтение сценариев из файла с защитой от потери данных при сбоях или прерывании.
        """
        logger.info(f"[{session_id}] Старт фонового тестирования. Режим: {mode}")
        id_to_sheet = {
            1: "Карты",
            2: "Изображения",
            3: "Текст"
        }
        job = ACTIVE_JOBS[session_id]
        job.status = TaskStatus.RUNNING
        #results_by_sheet = {"Текст": [], "Изображения": [], "Карты": []}
        #file_path = 'doc/tests.xlsx'
        print(f"📂 Загрузка сценариев")
        try:
            df_naimenovanie_off = pd.read_excel("doc/OFF_actual.xlsx")
            df_name_location = pd.read_excel("doc/name_location.xlsx")
            df_template_sen = pd.read_excel("doc/template_sen.xlsx")
            logger.info(f"[{session_id}] Загрузка данных из Excel завершена.")
        except Exception as e:
            print(f"❌ Не удалось прочитать файл: {e}")
            return

        # Словарь для накопления результатов
        results_by_sheet = {}

        # Переменная для отслеживания прогресса (сколько строк обработано)
        processed_count = 0
        total_rows = len(objs)

        print(f"🚀 Начинаю тестирование ({total_rows} сценариев). Нажмите Ctrl+C для экстренного сохранения.")

        try:
            for naimenovanie_off in tqdm(objs): #tqdm(df_naimenovanie_off["Русское"][:1], desc="Тестирование по списку ОФФ"):
                logger.info(f"Тестирование {naimenovanie_off}")
                # Инициализируем объект в итоговом словаре
                if naimenovanie_off not in results_by_sheet:
                    results_by_sheet[naimenovanie_off] = {"Текст": [], "Изображения": [], "Карты": []}
                for id_i in range(1,4):
                    """Тестирование карт"""
                    list_tepmplates_question = df_template_sen.loc[df_template_sen["id"] == id_i, "Шаблон"].to_list()

                    for question in list_tepmplates_question:
                        logger.debug(f"[{session_id}] Обработка строки {naimenovanie_off}: {question}")
                        list_question = [question.replace('<ОФФ>', naimenovanie_off)]
                        for question_var in list_question:
                            t_id = id_i
                            template = question
                            query = question_var
                            raw_answer = await self.post_test_query(query=query)
                            try:
                                # bot_res = json.loads(raw_answer) if isinstance(raw_answer, str) and raw_answer.strip().startswith(
                                #     '{') else {"content": raw_answer}
                                bot_res_debug = raw_answer[0] if raw_answer[0]['type'] == "debug" else raw_answer[1]
                                bot_res = raw_answer[0] if raw_answer[0]['type'] != "debug" else raw_answer[1]
                            except:
                                bot_res = {"content": None}

                            test_results = await self.run_tests(t_id, template, query, bot_res, mode)

                            sheet_name = id_to_sheet.get(t_id, "Текст")
                            results_by_sheet[naimenovanie_off][sheet_name].append(test_results)

                            processed_count += 1



            print("\n✅ Тестирование завершено в штатном режиме.")
            logger.info(f"[{session_id}] Тестирование успешно завершено. Файл создан.")

        except KeyboardInterrupt:
            print(f"\n⚠️ ТЕСТИРОВАНИЕ ПРЕРВАНО ПОЛЬЗОВАТЕЛЕМ (Ctrl+C).")
            print(f"💾 Сохраняю прогресс: обработано {processed_count} из {total_rows} строк...")
            logger.warning(f"[{session_id}] Бот вернул ошибку на запрос '{query}': {bot_res['error']}")

        except Exception as e:
            print(f"\n❌ ПРОИЗОШЛА КРИТИЧЕСКАЯ ОШИБКА: {e}")
            print(f"💾 Попытка спасения данных: обработано {processed_count} строк...")
            logger.error(f"[{session_id}] КРИТИЧЕСКАЯ ОШИБКА ПАЙПЛАЙНА: {str(e)}", exc_info=True)

        finally:
            if processed_count > 0:
                try:
                    # Считаем статистику
                    all_rows = []
                    for obj_name, categories in results_by_sheet.items():
                        for category_name, rows in categories.items():
                            all_rows.extend(rows)

                    total = len(all_rows)
                    passed = 0
                    for row in all_rows:
                        # Изначально считаем, что ряд прошел проверку
                        is_row_ok = True

                        for test_value in row.values():
                            # Если значение не None и в нем есть символ провала "❌"
                            if test_value is not None and isinstance(test_value, str) and "❌" in test_value:
                                is_row_ok = False
                                break  # Если хоть один тест в строке завален, вся строка считается проблемной

                        if is_row_ok:
                            passed += 1
                    #passed = sum(1 for r in all_rows for test_key, test in r.items() if test is not None and "❌" not in test)

                    stats = TestStats(
                        total_tests=total,
                        passed=passed,
                        failed=total - passed,
                        success_rate=round((passed / total * 100), 2) if total > 0 else 0
                    )

                    final_json_data = FullTestResult(
                        session_id=session_id,
                        timestamp=datetime.now().isoformat(),
                        mode=mode,
                        stats=stats,
                        results=results_by_sheet
                    )

                    # Сохраняем на диск как JSON
                    result_path = f"results/result_{session_id}.json"
                    with open(result_path, "w", encoding="utf-8") as f:
                        f.write(final_json_data.model_dump_json(indent=2))

                    # Обновляем статус задачи
                    job.status = TaskStatus.COMPLETED
                    job.result_file = result_path
                    job.progress = 100

                except Exception as e:
                    job.status = TaskStatus.FAILED
                    job.error = str(e)
            else:
                print("ℹ️ Нет данных для сохранения (ни одна строка не была обработана).")