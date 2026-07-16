
class TestingAnswerBot:
    def __init__(self, GetApiModel:GetAPI, GigaChatModel: GigaChatModelLoader,
                 PreparationImageModel:PreparationImage, CheckTestValidModel:CheckTestValid,
                 TestText: InterfaceTestText, TestImage: InterfaceTestImage,
                 TestMap: InterfaceTestMap, TestMapWithGeoObject: InterfaceTestMapWithGeoObject):
        self.api_model = GetApiModel
        self.LLM = GigaChatModel
        self.image_model = PreparationImageModel
        self.check_test_valid = CheckTestValidModel
        self._testing_text = TestText
        self._testing_image = TestImage
        self._testing_map = TestMap
        self._testing_map_with_geo_object = TestMapWithGeoObject
        self.dict_results_testing_as_answer_bot = {}
        self.dict_results_testing_map = {
            "rasa":[],
            "gigachat":[]
        }
        self.dict_results_testing_picture = {
            "rasa":[],
            "gigachat":[]
        }
        self.dict_results_testing_text = {
            "rasa":[],
            "gigachat":[]
        }
        self.dict_results_testing_maps_with_geo = {
            "rasa":[],
            "gigachat":[]
        }


    def check_answer_from_bot_question_number_1_location(self, object_flora_fauna, question, question_var_split_type, mode, promt):
        results = self._testing_map.get_testing_map(
            self.api_model.post_test_query,
            self.LLM.process_LLM,
            object_flora_fauna,
            question, question_var_split_type,
            mode, GPROMT,
            promt)
        self.dict_results_testing_map[mode].append(results)

    def check_answer_from_bot_question_number_2_picture(self, object_flora_fauna, question,question_var_split_type, mode, promt):
        results = self._testing_image.get_testing_image(
            self.api_model.post_test_query,
            self.LLM.process_LLM,
            self.image_model.extract_image_links,
            object_flora_fauna,
            question, question_var_split_type,
            mode, GPROMT,
            promt)
        self.dict_results_testing_picture[mode].append(results)

    def check_answer_from_bot_question_number_3_description(self, object_flora_fauna, question, question_var_split_type, mode, promt):
        results = self._testing_text.get_testing_text(
            self.api_model.post_test_query,
            self.LLM.process_LLM,
            object_flora_fauna,
            question, question_var_split_type,
            mode, GPROMT,
            promt)
        self.dict_results_testing_text[mode].append(results)

    def check_answer_from_bot_question_number_4_location_as_feature(self, object_flora_fauna, question, question_var_split_type, geo_object, mode, promt):
        results = self._testing_map_with_geo_object.get_testing_map_with_geo_object(
            post_test_query=self.api_model.post_test_query,
            process_LLM=self.LLM.process_LLM,
            object_flora_fauna=object_flora_fauna,
            question=question, question_var_split_type=question_var_split_type,
            geo_object = geo_object,
            mode=mode, GPROMT=GPROMT,
            promt=promt)
        self.dict_results_testing_maps_with_geo[mode].append(results)


    def run_testing_text(self, gen_variation_q: GenerationQuestion.gen_variation_q,
                    split_trailing_parenthetical: GenerationQuestion.split_trailing_parenthetical,
                    check_answer: (),
                    df_template_sen, df_promts_asnwer_bot,
                    naimenovanie_off: str, id_template: int, id_promts: int,
                    activation_dict: Dict = {"rasa":False, "gigachat":True}
                    ):
        list_tepmplates_question = df_template_sen.loc[df_template_sen["id"] == 3, "Шаблон"].to_list()[:1]
        for question in list_tepmplates_question:
            list_question = [question.replace('<ОФФ>', naimenovanie_off)]
            # list_question = self.generation_question.gen_variation_q(
            #     question.replace('<ОФФ>', naimenovanie_off)).get(
            #     "ListQuestionVar", "None")
            if isinstance(list_question, list):
                for question_var in list_question:
                    question_var_split_main, question_var_split_type = split_trailing_parenthetical(
                        question_var)
                    for key_mode, act in activation_dict.items():
                        if act:
                            check_answer(
                                object_flora_fauna=naimenovanie_off,
                                question=question_var_split_main,
                                question_var_split_type=question_var_split_type,
                                mode=key_mode,
                                promt=df_promts_asnwer_bot.loc[
                                    df_promts_asnwer_bot[
                                        "id"] == id_promts, "promts"])

    def run_testing_picture(self, gen_variation_q: GenerationQuestion.gen_variation_q,
                    split_trailing_parenthetical: GenerationQuestion.split_trailing_parenthetical,
                    check_answer: (),
                    df_template_sen, df_promts_asnwer_bot,
                    naimenovanie_off: str, id_template: int, id_promts: int,
                    activation_dict: Dict = {"rasa":False, "gigachat":True}
                    ):
        for question in list(df_template_sen.loc[df_template_sen["id"] == id_template, "Шаблон"]):
            list_question = [question.replace('<ОФФ>', naimenovanie_off)]
            # list_question = gen_variation_q(question.replace('<ОФФ>', naimenovanie_off)).get(
            #     "ListQuestionVar", "None")
            if isinstance(list_question, list):
                for question_var in list_question:
                    question_var_split_main, question_var_split_type = split_trailing_parenthetical(
                        question_var)
                    for key_mode, act in activation_dict.items():
                        if act:
                            check_answer(
                                object_flora_fauna=naimenovanie_off,
                                question=question_var_split_main,
                                question_var_split_type=question_var_split_type,
                                mode=key_mode,
                                promt=df_promts_asnwer_bot.loc[
                                    df_promts_asnwer_bot[
                                        "id"] == id_promts, "promts"])
            break
    def run_testing_map(self, gen_variation_q: GenerationQuestion.gen_variation_q,
                    split_trailing_parenthetical: GenerationQuestion.split_trailing_parenthetical,
                    check_answer: (),
                    df_template_sen, df_promts_asnwer_bot,
                    naimenovanie_off: str, id_template: int, id_promts: int,
                    activation_dict: Dict = {"rasa":False, "gigachat":True}
                    ):
        for question in list(df_template_sen.loc[df_template_sen["id"] == id_template, "Шаблон"]):
            list_question = [question.replace('<ОФФ>', naimenovanie_off)]
            # list_question = gen_variation_q(question.replace('<ОФФ>', naimenovanie_off)).get(
            #     "ListQuestionVar", "None")
            if isinstance(list_question, list):
                for question_var in list_question:
                    question_var_split_main, question_var_split_type = split_trailing_parenthetical(
                        question_var)
                    for key_mode, act in activation_dict.items():
                        if act:
                            check_answer(
                                object_flora_fauna=naimenovanie_off,
                                question=question_var_split_main,
                                question_var_split_type=question_var_split_type,
                                mode=key_mode,
                                promt=df_promts_asnwer_bot.loc[
                                    df_promts_asnwer_bot[
                                        "id"] == id_promts, "promts"])

    def run_testing_map_with_geo_obj(self, gen_variation_q: GenerationQuestion.gen_variation_q,
                    split_trailing_parenthetical: GenerationQuestion.split_trailing_parenthetical,
                    check_answer: (),
                    df_template_sen, df_promts_asnwer_bot, df_name_location,
                    naimenovanie_off: str, id_template: int, id_promts: int,
                    activation_dict: Dict = {"rasa":False, "gigachat":True}
                    ):
        for question in list(df_template_sen.loc[df_template_sen["id"] == id_template, "Шаблон"]):
            list_question = [question.replace('<ОФФ>', naimenovanie_off)]
            # list_question = gen_variation_q(question.replace('<ОФФ>', naimenovanie_off)).get(
            #     "ListQuestionVar", "None")
            if isinstance(list_question, list):
                for question_var in list_question:
                    question_var_split_main, question_var_split_type = split_trailing_parenthetical(
                        question_var)
                    for name_location in df_name_location["name_location"]:
                        for key_mode, act in activation_dict.items():
                            if act:
                                check_answer(
                                    object_flora_fauna=naimenovanie_off,
                                    question=question_var_split_main,
                                    question_var_split_type=question_var_split_type,
                                    geo_object = name_location,
                                    mode=key_mode,
                                    promt=df_promts_asnwer_bot.loc[
                                        df_promts_asnwer_bot[
                                            "id"] == id_promts, "promts"])
