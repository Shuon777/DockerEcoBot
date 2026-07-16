# -*- coding: utf-8 -*-
"""Тестовый скрипт для проверки FAISS поиска"""
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

from knowledge_base_scripts.Vector.faiss_adapter import TextResourceIndexer

def main():
    BASE_DIR = Path(__file__).parent
    INDEX_DIR = BASE_DIR / "knowledge_base_scripts" / "Vector" / "faiss_index"
    
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ FAISS ПОИСКА")
    print("=" * 60)
    
    # Создаем индексатор
    indexer = TextResourceIndexer(use_local_model=True)
    
    # Загружаем индекс
    vectorstore = indexer.load_faiss_index(str(INDEX_DIR))
    
    if not vectorstore:
        print("❌ Не удалось загрузить FAISS индекс")
        return
    
    print(f"\n✅ Индекс загружен: {vectorstore.index.ntotal} векторов")
    
    # Тестовые запросы
    test_queries = [
        "байкальская нерпа",
        "земляника лесная",
        "археологические находки",
        "растения Байкала",
        "животные озера Байкал",
        "вулкан",
        "пещера",
        "музей",
        "памятник",
        "озеро"
    ]
    
    print("\n" + "=" * 60)
    print("ТЕСТОВЫЙ ПОИСК")
    print("=" * 60)
    
    for query in test_queries:
        indexer.search_similar(vectorstore, query, k=3)
    
    print("\n" + "=" * 60)
    print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("=" * 60)

if __name__ == "__main__":
    main()