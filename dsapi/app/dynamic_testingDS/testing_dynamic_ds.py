import pandas as pd
import time
import tqdm

class DynamicTestingDS:
    def __init__(self, testing_answer_bot_model:TestingAnswerBot, testing_unit_api_model: TestingUnitApiBot,
                check_test_valid_model:CheckTestValid,
                get_valid_results_testing_model:GetValidResultsTesting):
        self.testing_answer_bot = testing_answer_bot_model
        self.testing_unit_api_bot = testing_unit_api_model
        self.generation_question = generation_question_model
        self.check_test_valid = check_test_valid_model
        self.get_valid_results_testing = get_valid_results_testing_model

    def processTestingAnswerBot(self, naimenovanie_off_path:str, name_location_path:str,
                                template_sen_path:str,
                                promts_answers_bot:str,
                                activation_test: Dict = {"testing_map":False, "testing_picture":True,
                                                      "testing_text":False,  "testing_map_with_geo_obj":False}
                                ):

        df_naimenovanie_off = pd.read_excel("OFF_actual.xlsx")
        df_name_location = pd.read_excel("name_location.xlsx")
        df_template_sen = pd.read_excel("template_sen.xlsx")
        df_promts = pd.read_excel("promts_api.xlsx")
        df_promts_asnwer_bot = pd.read_excel("promts_answers_bot.xlsx")

        time_now = time.strftime("%m.%d.%Y %H-%M-%S", time.localtime())
        ids_template = set(df_template_sen["id"].to_list())


        # for id_template in ids_template:
        #     key_template_part=""
        #     for template in df_template_sen.loc[df_template_sen["id"]==id_template,"Шаблон"]:
        #         if '<Геообъект>' in template:
        #             for name_location in df_name_location["name_location"]:
        #                 template_after_replace = template.replace('<Геообъект>', name_location)
        #                 key_template_part = key_template_part + " / " + template_after_replace \
        #                     if len(key_template_part) else template_after_replace
        #             continue
        #         key_template_part = key_template_part + " / "+ template \
        #             if len(key_template_part) else template
        #     result_test_dict.update({id_template: [key_template_part]})
        try:
            #logging.info("Начало тестирования")

            for naimenovanie_off in tqdm(df_naimenovanie_off["Русское"][207:],
                                         desc="Тестирование по списку ОФФ"):
                #logging.info(f"Тестирование {naimenovanie_off}")

                for key_act, act in activation_test.items():
                    if key_act == "testing_map" and act:
                        #logging.info(f"Тестирование {naimenovanie_off} - шаблон 1")
                        pass
                    if key_act == "testing_picture" and act:
                        #logging.info(f"Тестирование {naimenovanie_off} - шаблон 2")
                        self.testing_answer_bot.run_testing_picture(
                            gen_variation_q=self.generation_question.gen_variation_q,
                            split_trailing_parenthetical=self.generation_question.split_trailing_parenthetical,
                            check_answer=self.testing_answer_bot.check_answer_from_bot_question_number_2_picture,
                            df_template_sen=df_template_sen,
                            df_promts_asnwer_bot=df_promts_asnwer_bot,
                            naimenovanie_off=naimenovanie_off,
                            id_template=2,
                            id_promts=2
                        )
                    if key_act == "testing_text" and act:
                        #logging.info(f"Тестирование {naimenovanie_off} - шаблон 3")
                        self.testing_answer_bot.run_testing_text(
                            gen_variation_q=self.generation_question.gen_variation_q,
                            split_trailing_parenthetical=self.generation_question.split_trailing_parenthetical,
                            check_answer=self.testing_answer_bot.check_answer_from_bot_question_number_3_description,
                            df_template_sen=df_template_sen,
                            df_promts_asnwer_bot=df_promts_asnwer_bot,
                            naimenovanie_off=naimenovanie_off,
                            id_template=3,
                            id_promts=3
                        )
                    if key_act == "testing_map_with_geo_obj" and act:
                        #logging.info(f"Тестирование {naimenovanie_off} - шаблон 4")
                        pass

            saved_paths = self.testing_answer_bot.save_by_source(
                out_dir="results",
                save_json=False,
                save_excel=True,
                timestamp_in_name=True,  # для примера - без метки
            )
            #     result_test_dict_rasa = self.get_valid_results_testing.get_balance_dict(result_test_dict_rasa)
            #     result_test_dict_gigachat = self.get_valid_results_testing.get_balance_dict(result_test_dict_gigachat)
            #     result_test_dict_rasa_errors = self.get_valid_results_testing.get_balance_dict(result_test_dict_rasa_errors)
            #     result_test_dict_gigachat_errors = self.get_valid_results_testing.get_balance_dict(result_test_dict_gigachat_errors)
            #
            # # Преобразуем словарь в DataFrame
            # df_result_test_dict_rasa = pd.DataFrame(result_test_dict_rasa)
            # df_result_test_dict_gigachat = pd.DataFrame(result_test_dict_gigachat)
            # df_result_test_dict_rasa_errors = pd.DataFrame(result_test_dict_rasa_errors)
            # df_result_test_dict_gigachat_errors = pd.DataFrame(result_test_dict_gigachat_errors)

            # logging.info(f"Сохранение результатов тестирования в файл \"Результаты тестирования Rasa (GigaChat).xlsx\"")
            #
            # # Сохраняем в Excel
            # df_result_test_dict_rasa.to_excel(
            #     f"results/Rasa/Successful/Результаты тестирования Rasa [{str(time_now)}].xlsx", index=False)
            # df_result_test_dict_gigachat.to_excel(
            #     f"results/GigaChat/Successful/Результаты тестирования GigaChat [{str(time_now)}].xlsx", index=False)
            # df_result_test_dict_rasa_errors.to_excel(
            #     f"results/Rasa/Successful/Результаты тестирования Rasa только с ошибками  [{str(time_now)}].xlsx",
            #     index=False)
            # df_result_test_dict_gigachat_errors.to_excel(
            #     f"results/GigaChat/Successful/Результаты тестирования GigaChat только с ошибками  [{str(time_now)}].xlsx",
            #     index=False)

            # print(f"Файл создан: \"Результаты тестирования Rasa [{str(time_now)}].xlsx\"")
            # print(f"Файл создан: \"Результаты тестирования GigaChat [{str(time_now)}].xlsx\"")

            # # Загружаем Excel для доработки
            # wb = load_workbook("Результаты тестирования.xlsx")
            # ws = wb.active
            #
            # # Вставляем пустую строку в самый верх
            # ws.insert_rows(2)
            # # Заполняем её значением
            # ws["B1"] = 1
            # # Если нужно объединить B1:D1
            # ws.merge_cells("B1:D1")
            # # Заполняем её значением
            # ws["E1"] = 2
            # ws.merge_cells("E1:J1")
            #
            # # Заполняем её значением
            # ws["K1"] = 3
            # ws.merge_cells("K1:M1")
            #
            # # Заполняем её значением
            # ws["N1"] = 4
            # ws.merge_cells("N1:P1")
            #
            # # Заполняем её значением
            # ws["B2"] = "\n".join(list(df_template_sen.loc[df_template_sen["id"]==1,"Шаблон"]))
            # # Если нужно объединить B2:D2
            # ws.merge_cells("B2:D2")
            #
            # # Заполняем её значением
            # ws["E2"] = "\n".join(list(df_template_sen.loc[df_template_sen["id"]==2,"Шаблон"]))
            # ws.merge_cells("E2:J2")
            #
            # # Заполняем её значением
            # ws["K2"] = "\n".join(list(df_template_sen.loc[df_template_sen["id"]==3,"Шаблон"]))
            # ws.merge_cells("K2:M2")
            #
            # # Заполняем её значением
            # ws["N2"] = "\n".join(list(df_template_sen.loc[df_template_sen["id"]==4,"Шаблон"]))
            # ws.merge_cells("N2:P2")
            #
            # wb.save("Результаты тестирования.xlsx")
        except KeyboardInterrupt:
            # print("Пользователь остановил процесс работы программы")
            #logging.info(f"Пользователь остановил процесс работы программы на \"{naimenovanie_off}\"")
            saved_paths = self.testing_answer_bot.save_by_source(
                out_dir="results",
                save_json=False,
                save_excel=True,
                timestamp_in_name=True,  # для примера - без метки
            )
        except Exception as e:
            #logging.error("Во время тестирования произошла ошибка!", exc_info=e)
            saved_paths = self.testing_answer_bot.save_by_source(
                out_dir="results",
                save_json=False,
                save_excel=True,
                timestamp_in_name=True,  # для примера - без метки
            )
            # if len(result_test_dict_rasa):
            #     # Преобразуем словарь в DataFrame
            #     df_result_test_dict = pd.DataFrame(result_test_dict_rasa)
            #     if len(result_test_dict_rasa_errors):
            #         df_result_test_dict_rasa_errors = pd.DataFrame(result_test_dict_rasa_errors)
            #         df_result_test_dict_rasa_errors.to_excel(
            #             f"results/Rasa/Unsuccessful/Результаты тестирования Rasa только с ошибками  [{str(time_now)}].xlsx",
            #             index=False)
            #     logging.info(
            #         f"Сохранение результатов тестирования в файл \"Результаты тестирования Rasa с ошибкой [{str(time_now)}].xlsx\"")
            #     # Сохраняем в Excel
            #     df_result_test_dict.to_excel(
            #         f"results/Rasa/Unsuccessful/Результаты тестирования Rasa с ошибкой {str(time_now)}.xlsx",
            #         index=False)
            #     print(f"Файл создан: \"Результаты тестирования Rasa с ошибкой [{str(time_now)}].xlsx\"")
            # if len(result_test_dict_gigachat):
            #     # Преобразуем словарь в DataFrame
            #     df_result_test_dict = pd.DataFrame(result_test_dict_gigachat)
            #     if len(result_test_dict_gigachat_errors):
            #         df_result_test_dict_gigachat_errors = pd.DataFrame(result_test_dict_gigachat_errors)
            #         df_result_test_dict_gigachat_errors.to_excel(
            #             f"results/GigaChat/Unsuccessful/Результаты тестирования GigaChat только с ошибками  [{str(time_now)}].xlsx",
            #             index=False)
            #     logging.info(
            #         f"Сохранение результатов тестирования в файл \"Результаты тестирования GigaChat с ошибкой [{str(time_now)}].xlsx\"")
            #     # Сохраняем в Excel
            #     df_result_test_dict.to_excel(
            #         f"results/GigaChat/Unsuccessful/Результаты тестирования GigaChat с ошибкой {str(time_now)}.xlsx",
            #         index=False)
            #     print(f"Файл создан: \"Результаты тестирования GigaChat с ошибкой [{str(time_now)}].xlsx\"")

