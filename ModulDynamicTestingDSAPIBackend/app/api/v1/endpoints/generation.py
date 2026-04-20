from fastapi import APIRouter
from app.models.generation import GenerationParams, GeneratedQuestionsResponse
from app.services.generation.rule_based import RuleBasedGenerator
from app.services.llm_evaluator.evaluator import LLMService

router = APIRouter()
rule_gen = RuleBasedGenerator()
llm_service = LLMService()


@router.post("/generate-questions", response_model=GeneratedQuestionsResponse)
async def generate_questions(params: GenerationParams, use_llm: bool = False):
    """
    Генерация тестовых вопросов.
    Если use_llm=True, используется Qwen, иначе — алгоритмический метод.
    """
    if use_llm:
        questions = await llm_service.generate_questions_llm(params.template_question, params.count)
        method = "llm-based"
    else:
        questions = rule_gen.generate_variants(
            params.template_question,
            params.count,
            params.add_typos,
            params.change_cases
        )
        method = "rule-based"

    return {
        "source_template": params.template_question,
        "generated_questions": questions,
        "method": method
    }