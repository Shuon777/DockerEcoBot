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
from app.services.validators.factory import ValidatorFactory
from app.services.clients.bot_client import IBotClient
from app.services.generation.strategies import IQuestionGenerator
from app.services.files_repositories.base import ITemplateRepository

# для работы Natasha и Pymorphy3 на Python 3.12
try:
    import pymorphy3
    sys.modules['pymorphy2'] = pymorphy3
except:
    pass


class IntegratedDynamicPipeline:
    def __init__(self, bot_client: IBotClient, generator: IQuestionGenerator, template_repo: ITemplateRepository):
        self.services = self._init_services()
        self.bot_client = bot_client
        self.generator = generator
        self.template_repo = template_repo
        self.llm = LLMService()
        self.factory = ValidatorFactory(self.services)
        self.id_to_sheet = {1: "Карты", 2: "Изображения", 3: "Текст"}

    def _init_services(self):
        """Инициализация сервисов"""
        return {
            'llm': LLMService(),
            'vlm': VisionLL_Service(),
            'text_checker': TextChecker(),
            'pii': TextCheckerPiiFIO(),
            'neural': NeuralValidator(),
            'speller': LocalSpellingChecker(),
            'img_checker': ImageChecker(),
            'nsfw': ImageSafetyValidator(),
            'map_classifier': MapClassifier(),
            'map_semantic': MapSemanticValidator()
        }

    async def process_dynamic_testing(self, session_id: str, mode: str, objs: list[str]):
        logger.info(f"[{session_id}] Старт фонового тестирования. Режим: {mode}")

        job = ACTIVE_JOBS[session_id]
        job.status = TaskStatus.RUNNING
        results_by_object = {}
        processed_count = 0

        try:

            templates = self.template_repo.get_all_templates()
            if not templates:
                raise Exception("Список шаблонов пуст. Проверьте источник данных.")
            total_tasks = len(objs) * len(templates)

            for obj_name in tqdm(objs, desc="Testing Objects"):
                logger.info(f"Тестирование {obj_name}")
                results_by_object[obj_name] = {"Текст": [], "Изображения": [], "Карты": []}

                #for _, t_row in df_templates.loc[df_templates["id"] != 4].iterrows():
                for t in templates:

                    validator = self.factory.get_validator(t.id)
                    sheet_name = self.id_to_sheet.get(t.id, "Текст")

                    query = t.text.replace('<ОФФ>', obj_name)
                    list_question = await self.generator.generate(query, 5)

                    # list_question = self.llm.generate_questions_llm(query, 5)
                    # list_question = await self.generator.generate(template, 5)
                    for question_var in list_question:
                        logger.debug(f"[{session_id}] Обработка строки {obj_name}: {question_var}")
                        bot_response_raw = await self.bot_client.send_query(question_var)
                        bot_res = self._parse_bot_response(bot_response_raw)

                        test_result = await validator.validate(
                            t.text, question_var, bot_res, mode
                        )

                        results_by_object[obj_name][sheet_name].append(test_result)
                    processed_count += 1

                    # Обновление прогресса
                    job.progress = int((processed_count / total_tasks) * 100)

            logger.info(f"[{session_id}] Тестирование успешно завершено. Файл создан.")

        except KeyboardInterrupt:
            msg = f"Тестирование прервано пользователем. Успели обработать: {processed_count}"
            print(f"\n⚠️ {msg}")
            logger.warning(f"[{session_id}] {msg}")
            job.error = "Прервано вручную (Ctrl+C)"
            logger.warning(f"[{session_id}] Бот вернул ошибку на запрос '{query}': {bot_res['error']}")
        except Exception as e:
            msg = f"Критический сбой пайплайна: {e}"
            print(f"\n❌ {msg}")
            logger.error(f"[{session_id}] {msg}", exc_info=True)
            job.error = str(e)
            logger.error(f"[{session_id}] КРИТИЧЕСКАЯ ОШИБКА ПАЙПЛАЙНА: {str(e)}", exc_info=True)

        finally:
            await self._save_results(
                session_id=session_id,
                mode=mode,
                results_by_object=results_by_object,
                processed_count=processed_count,
                total_rows=total_tasks
            )


    def _parse_bot_response(self, raw_data):
        """Логика выделения debug и content из ответа бота"""
        try:
            return raw_data[0] if raw_data[0]['type'] != "debug" else raw_data[1]
        except:
            return {"content": None}

    async def _save_results(self, session_id: str, mode: str, results_by_object: Dict, processed_count: int,
                            total_rows: int):
        """
        Итоговый расчет статистики и сохранение результатов в JSON
        """
        job = ACTIVE_JOBS.get(session_id)
        if not job:
            logger.error(f"Job {session_id} не найдено в ACTIVE_JOBS при сохранении")
            return

        if processed_count == 0:
            logger.warning(f"[{session_id}] Нет обработанных строк для сохранения")
            job.status = TaskStatus.FAILED
            job.error = "Тестирование было прервано до обработки первой строки"
            return

        try:
            # результаты для расчета статистики
            all_rows = []
            for obj_name, categories in results_by_object.items():
                for category_name, rows in categories.items():
                    all_rows.extend(rows)

            total = len(all_rows)
            passed = 0

            # количество пройденных тестов
            for row in all_rows:
                is_row_ok = True
                for val in row.values():
                    if val is not None and isinstance(val, str) and "❌" in val:
                        is_row_ok = False
                        break
                if is_row_ok:
                    passed += 1

            # статистики
            stats = TestStats(
                total_tests=total,
                passed=passed,
                failed=total - passed,
                success_rate=round((passed / total * 100), 2) if total > 0 else 0
            )

            # финальная модель
            final_report = FullTestResult(
                session_id=session_id,
                timestamp=datetime.now().isoformat(),
                mode=mode,
                stats=stats,
                results=results_by_object  # Ваша вложенная структура
            )

            # 5. Записываем в файл
            os.makedirs("results", exist_ok=True)
            result_path = f"results/result_{session_id}.json"

            with open(result_path, "w", encoding="utf-8") as f:
                f.write(final_report.model_dump_json(indent=2))

            # 6. Финальное обновление статуса задачи
            job.result_file = result_path
            job.progress = 100

            # Если обработали меньше, чем планировали - ставим статус PARTIAL (опционально)
            if processed_count < total_rows:
                job.status = TaskStatus.COMPLETED  # Или введите статус TaskStatus.PARTIAL
                logger.info(f"[{session_id}] Сохранение завершено (Частично: {processed_count}/{total_rows})")
            else:
                job.status = TaskStatus.COMPLETED
                logger.info(f"[{session_id}] Сохранение завершено успешно.")

        except Exception as e:
            logger.error(f"[{session_id}] Ошибка при формировании JSON отчета: {e}", exc_info=True)
            job.status = TaskStatus.FAILED
            job.error = f"Ошибка сохранения данных: {str(e)}"