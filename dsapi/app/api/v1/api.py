from fastapi import APIRouter
from app.api.v1.endpoints import text_tests, generation, neural_tests
from app.api.v1.endpoints import map_tests
from app.api.v1.endpoints import pipeline_api

api_router = APIRouter()

api_router.include_router(text_tests.router, prefix="/text", tags=["Text Validation"])

api_router.include_router(generation.router, prefix="/generate", tags=["Generation"])

api_router.include_router(neural_tests.router, prefix="/neural", tags=["Neural & Linguistic Validation"])

api_router.include_router(map_tests.router, prefix="/maps", tags=["Map Testing"])

api_router.include_router(pipeline_api.router, prefix="/pipeline_testing", tags=["Pipeline Testing"])