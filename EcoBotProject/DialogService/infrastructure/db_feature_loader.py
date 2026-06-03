import asyncpg
import os
import logging
from typing import Dict, Optional, Set

logger = logging.getLogger("FeatureLoader")


async def load_valid_features() -> Optional[Dict[str, Set[str]]]:
    """
    Загружает из resource_feature допустимые имена признаков по модальностям.
    Возвращает {modality_type: {feature_name_lowercase}} или None при недоступности БД.
    """
    host = os.getenv("DB_HOST", "db")
    port = int(os.getenv("DB_PORT", "5432"))
    db = os.getenv("DB_NAME", "eco")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")

    try:
        conn = await asyncpg.connect(
            host=host, port=port, database=db, user=user, password=password
        )
        try:
            rows = await conn.fetch("""
                SELECT m.modality_type, rf.feature_name
                FROM eco_assistant.resource_feature rf
                JOIN eco_assistant.modality m ON rf.modality_id = m.id
            """)
            result: Dict[str, Set[str]] = {}
            for row in rows:
                result.setdefault(row["modality_type"], set()).add(row["feature_name"].lower())
            logger.info(f"Valid features loaded: { {k: sorted(v) for k, v in result.items()} }")
            return result
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"Cannot load valid features from DB: {e}. Feature validation disabled.")
        return None
