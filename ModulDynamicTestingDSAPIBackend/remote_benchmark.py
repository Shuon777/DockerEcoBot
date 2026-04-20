import asyncio
import time
import json
import os
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

# --- НАСТРОЙКИ УДАЛЕННОГО ПОДКЛЮЧЕНИЯ ---
REMOTE_URL = os.environ.get("REMOTE_OLLAMA_URL", "http://109.194.19.82:11434")
REMOTE_MODEL = "qwen3-next:80b-a3b-instruct-q4_K_M"

# --- 1. Загрузка файлов ---
def load_prompt_part(file_path):
    try:
        with open(os.path.abspath(file_path), 'r', encoding='utf-8') as f:
            return f.read().strip()
    except: return ""

# --- 2. ЭТАЛОННЫЕ ДАННЫЕ (ТОЧНАЯ КОПИЯ из benchmark_full.py) ---
TEST_CASES = [
    {
        "query": "Где обитает эдельвейс около Култука?",
        "description": "Сложный поиск (Bio + Geo)",
        "expected": {
            "action": "find_nearby",
            "primary_entity": { 
                "name": "эдельвейс", 
                "type": "Biological", 
                "category": "Flora", 
                "subcategory": [] 
            },
            "secondary_entity": { 
                "name": "Култук", 
                "type": "GeoPlace", 
                "category": "", 
                "subcategory": [] 
            },
            "attributes": {}
        }
    },
    {
        "query": "Музеи в Листвянке",
        "description": "Инфраструктура + Список",
        "expected": {
            "action": "list_items",
            "primary_entity": { 
                "name": "музеи", 
                "type": "Infrastructure", 
                "category": "Достопримечательности", 
                "subcategory": ["Музеи"] 
            },
            "secondary_entity": { 
                "name": "Листвянка", 
                "type": "GeoPlace", 
                "category": "", 
                "subcategory": [] 
            },
            "attributes": {}
        }
    },
    {
        "query": "Покажи фото нерпы зимой",
        "description": "Картинка + Атрибут",
        "expected": {
            "action": "show_image",
            "primary_entity": { 
                "name": "нерпа", 
                "type": "Biological", 
                "category": "Fauna", 
                "subcategory": [] 
            },
            "secondary_entity": None,
            "attributes": { "season": "Зима" }
        }
    }
]

# --- 3. Строгая проверка (ТОЧНАЯ КОПИЯ из benchmark_full.py) ---
def strict_compare(actual, expected):
    """
    Сравнивает два JSON объекта по всем полям.
    """
    errors = []
    
    # 1. Action
    if actual.get("action") != expected.get("action"):
        errors.append(f"Action: ждали '{expected.get('action')}', получили '{actual.get('action')}'")

    # 2. Primary Entity
    exp_pe = expected.get("primary_entity")
    act_pe = actual.get("primary_entity")
    
    if exp_pe is None and act_pe is not None:
        errors.append(f"Primary Entity: ждали null, получили объект")
    elif exp_pe is not None:
        if act_pe is None:
            errors.append(f"Primary Entity: ждали объект, получили null")
        else:
            if act_pe.get("name", "").lower() != exp_pe.get("name", "").lower():
                errors.append(f"PE Name: '{act_pe.get('name')}' != '{exp_pe.get('name')}'")
            if act_pe.get("type") != exp_pe.get("type"):
                errors.append(f"PE Type: '{act_pe.get('type')}' != '{exp_pe.get('type')}'")
            if act_pe.get("category") != exp_pe.get("category"):
                errors.append(f"PE Category: '{act_pe.get('category')}' != '{exp_pe.get('category')}'")
            
            # Subcategory
            act_sub = act_pe.get("subcategory", [])
            exp_sub = exp_pe.get("subcategory", [])
            if sorted(act_sub) != sorted(exp_sub):
                errors.append(f"PE Subcategory: {act_sub} != {exp_sub}")

    # 3. Secondary Entity
    exp_se = expected.get("secondary_entity")
    act_se = actual.get("secondary_entity")
    
    if exp_se is None and act_se is not None:
         if act_se.get("name"): 
             errors.append(f"Secondary Entity: ждали null, получили {act_se}")
    elif exp_se is not None:
        if act_se is None:
            errors.append(f"Secondary Entity: ждали {exp_se['name']}, получили null")
        else:
            if act_se.get("name", "").lower() != exp_se.get("name", "").lower():
                errors.append(f"SE Name: '{act_se.get('name')}' != '{exp_se.get('name')}'")
            if act_se.get("type") != exp_se.get("type"):
                errors.append(f"SE Type: '{act_se.get('type')}' != '{exp_se.get('type')}'")

    # 4. Attributes
    exp_attr = expected.get("attributes", {})
    act_attr = actual.get("attributes", {})
    for k, v in exp_attr.items():
        if act_attr.get(k) != v:
             errors.append(f"Attribute '{k}': ждали '{v}', получили '{act_attr.get(k)}'")

    if not errors:
        return True, "ИДЕАЛЬНО"
    else:
        return False, "; ".join(errors)

async def run_remote_benchmark():
    print(f"🌍 ПОДКЛЮЧЕНИЕ К СЕРВЕРУ: {REMOTE_URL}")
    print(f"🤖 МОДЕЛЬ: {REMOTE_MODEL}")
    print("-" * 60)

    # Загрузка промптов
    prompts_data = {
        "actions": load_prompt_part('prompts_structure/classifications_actions_part_of_prompt.txt'),
        "types": load_prompt_part('prompts_structure/classifications_entities_part_of_prompt.txt'),
        "flora": load_prompt_part('prompts_structure/examples_entity.txt'),
        "examples": load_prompt_part('prompts_structure/examples_for_prompt.txt')
    }

    SYSTEM_TEMPLATE = """
    ## РОЛЬ
    Ты — NLU-аналитик.
    ## ИНСТРУКЦИЯ
    1. Reason about query.
    2. Create search_query.
    3. Fill JSON fields strictly.
    
    Actions: {actions}
    Types: {types}
    Flora: {flora}
    Examples: {examples}
    
    Output STRICT JSON.
    """
    prompt_template = ChatPromptTemplate.from_messages([("system", SYSTEM_TEMPLATE), ("human", "{query}")])

    try:
        llm = ChatOllama(
            model=REMOTE_MODEL,
            temperature=0,
            format="json",
            base_url=REMOTE_URL,
            num_ctx=10000, 
            num_predict=512,
        )
        chain = prompt_template | llm
        
        print("⏳ ПРОГРЕВ МОДЕЛИ 80B (Может занять минуту)...")
        start_warm = time.time()
        await chain.ainvoke({"query": "test", **prompts_data})
        print(f"🔥 Прогрев завершен за {time.time() - start_warm:.2f} сек.")
        
        score = 0
        total_time = 0
        
        print("\n🚀 ЗАПУСК СТРОГОГО ТЕСТА...")
        for case in TEST_CASES:
            q = case["query"]
            print(f"🔹 Запрос: '{q}' ({case['description']})")
            
            start = time.perf_counter()
            try:
                response = await chain.ainvoke({"query": q, **prompts_data})
                duration = time.perf_counter() - start
                total_time += duration
                
                actual_json = json.loads(response.content)
                is_valid, msg = strict_compare(actual_json, case["expected"])
                
                if is_valid:
                    print(f"   ✅ OK [{duration:.2f}s]")
                    score += 1
                else:
                    print(f"   ❌ FAIL [{duration:.2f}s]")
                    print(f"      Причина: {msg}")

            except Exception as e:
                print(f"   ❌ ОШИБКА: {e}")
            print("-" * 40)

        if len(TEST_CASES) > 0:
            avg_time = total_time / len(TEST_CASES)
            print(f"\n📊 ИТОГ REMOTE 80B:")
            print(f"   Точность: {score}/{len(TEST_CASES)}")
            print(f"   Среднее время: {avg_time:.2f} сек")
        
    except Exception as e:
        print(f"\n⛔ ОШИБКА ПОДКЛЮЧЕНИЯ: {e}")

if __name__ == "__main__":
    asyncio.run(run_remote_benchmark())