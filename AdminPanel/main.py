import os
import httpx
import uvicorn
import requests
import folium
from shapely import wkb
import json

from fastapi import FastAPI, Request, Depends, Body, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, delete, or_, create_engine
from sqlalchemy.orm import sessionmaker
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone

from database import get_db
from models.models import ErrorLog, BiologicalEntity, TextContent, ImageContent, EntityRelation, EntityIdentifier, EntityIdentifierLink, GeographicalEntity, EntityGeo, MapContent
from models.admin_models import AdminBase, TestSession
from heartbeat import BotHeartbeat
from dotenv import load_dotenv

app = FastAPI()
load_dotenv()

app.mount("/admin/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
hb = BotHeartbeat(host=os.getenv('REDIS_HOST', 'redis'), port=int(os.getenv('REDIS_PORT', 6379)), db=2)
app.add_middleware(SessionMiddleware, secret_key=os.getenv('SESSION_SECRET_KEY', 'super-secret-key-for-admins'))
BOT_CORE_URL = os.getenv("BOT_CORE_URL")
parsed_url = urlparse(BOT_CORE_URL)
CORE_API_BASE = f"{parsed_url.scheme}://{parsed_url.netloc}" # Получится http://localhost:5001

ADMIN_DB_URL = os.getenv('ADMIN_DB_URL')
admin_engine = create_engine(ADMIN_DB_URL, connect_args={"check_same_thread": False})
AdminSessionLocal = sessionmaker(bind=admin_engine)
AdminBase.metadata.create_all(bind=admin_engine)

def get_admin_db():
    db = AdminSessionLocal()
    try:
        yield db
    finally:
        db.close()

TEST_API_BASE = os.getenv('TEST_API_BASE')
TEST_TOKEN = os.getenv('TEST_TOKEN')
TEST_HEADERS = {"Authorization": f"Bearer {TEST_TOKEN}", "Content-Type": "application/json"}

async def is_bot_online_redis():
    return await hb.is_alive()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    bot_online = await is_bot_online_redis()

    # --- Считаем ошибки за последние 24 часа ---
    time_24h_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    query = select(func.count(ErrorLog.id)).where(ErrorLog.created_at >= time_24h_ago)
    result = await db.execute(query)
    errors_24h = result.scalar() or 0  # Получаем число (или 0, если пусто)
    # -------------------------------------------
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "bot_online": bot_online,
        "errors_24h": errors_24h  # <--- Передаем число в шаблон
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...)):
    # Здесь можно добавить проверку пароля, но пока просто верим на слово
    request.session["user_id"] = f"admin_{username}"
    return RedirectResponse(url="/", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

@app.get("/logs", response_class=HTMLResponse)
async def view_logs(request: Request, db: AsyncSession = Depends(get_db)):
    bot_online = await is_bot_online_redis()
    # Берем последние 50 ошибок для полноты картины
    query = select(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(50)
    result = await db.execute(query)
    errors = result.scalars().all()
    
    return templates.TemplateResponse("logs.html", {
        "request": request, "errors": errors, "active_page": "logs", "bot_online": bot_online
    })

@app.get("/logs/stats", response_class=HTMLResponse)
async def view_stats(request: Request, db: AsyncSession = Depends(get_db)):
    bot_online = await is_bot_online_redis()
    return templates.TemplateResponse("stats.html", {
        "request": request, "active_page": "logs", "bot_online": bot_online
    })

@app.get("/bot-status")
async def get_bot_status_api():
    online = await hb.is_alive()
    return {"online": online}

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    # ПРОВЕРКА:
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    
    bot_online = await hb.is_alive()
    return templates.TemplateResponse("chat.html", {"request": request, "active_page": "chat", "bot_online": bot_online})

@app.post("/chat/ask")
async def proxy_to_core(request: Request, data: dict = Body(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return [{"type": "text", "content": "❌ Ошибка: вы не авторизованы"}]

    query = data.get("text")
    settings = data.get("settings", {}) # Принимаем настройки с фронта

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        try:
            response = await client.post(
                BOT_CORE_URL,
                json={
                    "query": query,
                    "user_id": user_id, # Теперь ID уникален для каждого админа
                    "settings": settings
                }
            )
            import json
            try:
                # Пытаемся вывести красиво отформатированный JSON
                raw_data = response.json()
                print("\n=== [CORE API RESPONSE START] ===")
                print(json.dumps(raw_data, indent=2, ensure_ascii=False))
                print("=== [CORE API RESPONSE END] ===\n")
            except Exception:
                # Если это не JSON, выводим просто текст
                print(f"\n!!! [RAW TEXT RESPONSE]: {response.text}\n")
            return response.json()
        except Exception as e:
            return [{"type": "text", "content": f"❌ Ошибка Core API: {str(e)}"}]


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    bot_online = await is_bot_online_redis()
    prompts = {}
    config = {}

    # Стучимся в Core API бота, чтобы забрать текущие промпты и конфиг
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            p_resp = await client.get(f"{CORE_API_BASE}/prompts")
            if p_resp.status_code == 200:
                prompts = p_resp.json()

            c_resp = await client.get(f"{CORE_API_BASE}/config")
            if c_resp.status_code == 200:
                config = c_resp.json()
        except Exception as e:
            print(f"Ошибка загрузки настроек из бота: {e}")

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "active_page": "settings",
        "bot_online": bot_online,
        "prompts": prompts,
        "config": config
    })


@app.post("/settings/prompts")
async def save_prompts(request: Request, data: dict = Body(...)):
    """Отправляем измененные промпты обратно в бота"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{CORE_API_BASE}/prompts", json=data)
        if resp.status_code == 200:
            return resp.json()
        raise HTTPException(status_code=500, detail="Ошибка сохранения промптов")


@app.post("/settings/config")
async def save_config(request: Request, data: dict = Body(...)):
    """Отправляем измененный конфиг (.env) обратно в бота"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{CORE_API_BASE}/config", json=data)
        if resp.status_code == 200:
            return resp.json()
        raise HTTPException(status_code=500, detail="Ошибка сохранения конфига")

# ==========================================
# CMS: ФЛОРА И ФАУНА (MVP)
# ==========================================

@app.get("/biological", response_class=HTMLResponse)
async def biological_list(
    request: Request, 
    search: str = None, 
    filter_type: str = None, 
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    
    bot_online = await is_bot_online_redis()
    
    # Базовый запрос
    query = select(BiologicalEntity)

    # 1. Применяем текстовый поиск (по русскому ИЛИ латинскому названию)
    if search:
        query = query.where(
            or_(
                BiologicalEntity.common_name_ru.ilike(f"%{search}%"),
                BiologicalEntity.scientific_name.ilike(f"%{search}%")
            )
        )

    # 2. Применяем фильтр по категории
    if filter_type and filter_type != "all":
        if filter_type == "flora":
            query = query.where(BiologicalEntity.type.ilike("%флор%"))
        elif filter_type == "fauna":
            query = query.where(BiologicalEntity.type.ilike("%фаун%"))

    # Сортировка от новых к старым
    query = query.order_by(BiologicalEntity.id.desc())
    
    result = await db.execute(query)
    entities = result.scalars().all()

    return templates.TemplateResponse("biological_list.html", {
        "request": request,
        "active_page": "biological",
        "bot_online": bot_online,
        "entities": entities,
        "search": search or "",
        "filter_type": filter_type or "all"
    })

@app.get("/biological/new", response_class=HTMLResponse)
async def biological_new(request: Request):
    """Страница с формой создания нового объекта"""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
        
    bot_online = await is_bot_online_redis()
    return templates.TemplateResponse("biological_form.html", {
        "request": request, 
        "active_page": "biological", 
        "bot_online": bot_online, 
        "entity": None # Передаем None, так как это создание, а не редактирование
    })

@app.post("/biological/save")
async def biological_save(
    request: Request, 
    common_name_ru: str = Form(...),
    scientific_name: str = Form(""),
    type: str = Form(...),
    status: str = Form(""),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db)
):
    """Сохранение базового <Описания объекта> в базу"""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
        
    # 1. Создаем сам объект (ОФФ)
    new_entity = BiologicalEntity(
        common_name_ru=common_name_ru,
        scientific_name=scientific_name,
        type=type,
        status=status,
        description=description,
        feature_data={} # Пустой JSONB, сюда потом лягут <Признаки ресурса>
    )
    db.add(new_entity)
    await db.commit()
    
    # После создания возвращаем пользователя к списку
    return RedirectResponse(url=f"/biological/{new_entity.id}", status_code=303)

@app.post("/biological/{entity_id}/add_text")
async def biological_add_text(
    request: Request,
    entity_id: int,
    title: str = Form(...),
    content: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    РЕАЛИЗАЦИЯ ИНФОРМАЦИОННОЙ МОДЕЛИ:
    Сборка <Ресурса> = <Объект> + <Модальность> + <Связь>
    """
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
        
    # 1. Создаем <Описание модальности> (Текст)
    new_text = TextContent(
        title=title, 
        content=content, 
        feature_data={}
    )
    db.add(new_text)
    await db.flush() # Получаем ID нового текста (new_text.id) без полного коммита транзакции
    
    # 2. Создаем связующее звено
    relation = EntityRelation(
        source_id=new_text.id,
        source_type="text_content",
        target_id=entity_id,
        target_type="biological_entity",
        relation_type="описание объекта"
    )
    db.add(relation)
    await db.commit()
    
    return RedirectResponse(url=f"/biological/{entity_id}", status_code=303)

@app.get("/biological/{entity_id}", response_class=HTMLResponse)
async def biological_edit(request: Request, entity_id: int, db: AsyncSession = Depends(get_db)):
    """Карточка объекта: просмотр и управление связанными ресурсами"""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
        
    bot_online = await is_bot_online_redis()
    
    result = await db.execute(select(BiologicalEntity).where(BiologicalEntity.id == entity_id))
    entity = result.scalars().first()
    
    if not entity:
        raise HTTPException(status_code=404, detail="Объект не найден")

    # ИСПРАВЛЕНО: Теперь ищем от текста (source) к объекту (target)
    text_query = (
        select(TextContent)
        .join(EntityRelation, (EntityRelation.source_id == TextContent.id) & (EntityRelation.source_type == 'text_content'))
        .where((EntityRelation.target_id == entity_id) & (EntityRelation.target_type == 'biological_entity'))
    )
    texts = (await db.execute(text_query)).scalars().all()

    # ИСПРАВЛЕНО: Теперь ищем от картинки (source) к объекту (target)
    image_query = (
        select(ImageContent, EntityIdentifier.file_path)
        .join(EntityRelation, (EntityRelation.source_id == ImageContent.id) & (EntityRelation.source_type == 'image_content'))
        .outerjoin(EntityIdentifierLink, (EntityIdentifierLink.entity_id == ImageContent.id) & (EntityIdentifierLink.entity_type == 'image_content'))
        .outerjoin(EntityIdentifier, EntityIdentifier.id == EntityIdentifierLink.identifier_id)
        .where((EntityRelation.target_id == entity_id) & (EntityRelation.target_type == 'biological_entity'))
    )
    images_result = await db.execute(image_query)
    
    # Формируем удобный список словарей для шаблона: [{"data": ImageContent, "url": "https..."}]
    images =[{"data": img, "url": url} for img, url in images_result.all()]

    geo_links_query = (
        select(EntityGeo)
        .where((EntityGeo.entity_id == entity_id) & (EntityGeo.entity_type == 'biological_entity'))
    )
    links = (await db.execute(geo_links_query)).scalars().all()
    
    locations = []

    for link in links:
        geo_id = link.geographical_entity_id
        geo_res = await db.execute(select(GeographicalEntity).where(GeographicalEntity.id == geo_id))
        geo_obj = geo_res.scalars().first()
        if not geo_obj:
            continue

        location_item = {
            "name_ru": geo_obj.name_ru,
            "type": geo_obj.type or "Локация",
            "is_map": False,
            "geo_id": geo_id,
            "feature_data": geo_obj.feature_data  # добавляем
        }

        # Проверяем карту (как раньше)
        map_link_query = select(EntityGeo).where(
            EntityGeo.entity_type == 'map_content',
            EntityGeo.geographical_entity_id == geo_id
        )
        map_link = (await db.execute(map_link_query)).scalars().first()
        if map_link:
            map_res = await db.execute(select(MapContent).where(MapContent.id == map_link.entity_id))
            map_obj = map_res.scalars().first()
            if map_obj:
                location_item["is_map"] = True
                location_item["map_id"] = map_obj.id
                # Если у карты тоже есть feature_data, можно добавить:
                # location_item["map_feature_data"] = map_obj.feature_data
        locations.append(location_item)

    return templates.TemplateResponse("biological_edit.html", {
        "request": request, 
        "active_page": "biological", 
        "bot_online": bot_online, 
        "entity": entity,
        "texts": texts,
        "images": images,
        "locations": locations
    })

@app.post("/biological/{entity_id}/add_image")
async def biological_add_image(
    request: Request,
    entity_id: int,
    title: str = Form(...),
    image_url: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Добавление изображения с сохранением названий объекта в entity_identifier
    """
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
        
    # 1. Сначала достаем информацию об объекте, чтобы узнать его названия
    result = await db.execute(select(BiologicalEntity).where(BiologicalEntity.id == entity_id))
    entity = result.scalars().first()
    
    if not entity:
        raise HTTPException(status_code=404, detail="Объект не найден")

    # 2. Создаем ImageContent
    new_image = ImageContent(
        title=title,
        description="Добавлено через админ-панель",
        feature_data={"source": "Admin Panel"} 
    )
    db.add(new_image)
    await db.flush() 
    
    # 3. Привязываем картинку к биологическому объекту (relation)
    relation = EntityRelation(
        source_id=new_image.id,
        source_type="image_content",
        target_id=entity_id,
        target_type="biological_entity",
        relation_type="изображение объекта"
    )
    db.add(relation)

    # 4. Создаем запись в entity_identifier
    # ИСПОЛЬЗУЕМ ДАННЫЕ ИЗ entity, КОТОРЫЕ ДОСТАЛИ ВЫШЕ
    new_identifier = EntityIdentifier(
        file_path=image_url,
        name_ru=entity.common_name_ru,    # Название из карточки объекта
        name_latin=entity.scientific_name # Латынь из карточки объекта
    )
    db.add(new_identifier)
    await db.flush() 

    # 5. Связываем картинку с её новым идентификатором
    identifier_link = EntityIdentifierLink(
        entity_id=new_image.id,
        entity_type="image_content",
        identifier_id=new_identifier.id
    )
    db.add(identifier_link)

    await db.commit() 
    
    return RedirectResponse(url=f"/biological/{entity_id}", status_code=303)

@app.post("/resource/delete/image/{image_id}")
async def delete_image_resource(
    request: Request,
    image_id: int,
    entity_id: int = Form(...), # Чтобы знать, куда вернуться
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    # 1. Удаляем связи из entity_relation
    await db.execute(delete(EntityRelation).where(
        (EntityRelation.source_id == image_id) & (EntityRelation.source_type == 'image_content')
    ))

    # 2. Находим и удаляем идентификаторы (ссылки)
    # Сначала найдем ID идентификатора через линк
    link_result = await db.execute(select(EntityIdentifierLink).where(
        (EntityIdentifierLink.entity_id == image_id) & (EntityIdentifierLink.entity_type == 'image_content')
    ))
    links = link_result.scalars().all()
    
    for link in links:
        await db.execute(delete(EntityIdentifier).where(EntityIdentifier.id == link.identifier_id))
    
    # 3. Удаляем сами линки
    await db.execute(delete(EntityIdentifierLink).where(
        (EntityIdentifierLink.entity_id == image_id) & (EntityIdentifierLink.entity_type == 'image_content')
    ))

    # 4. Удаляем саму запись ImageContent
    await db.execute(delete(ImageContent).where(ImageContent.id == image_id))

    await db.commit()
    return RedirectResponse(url=f"/biological/{entity_id}", status_code=303)

@app.post("/resource/delete/text/{text_id}")
async def delete_text_modality(
    request: Request,
    text_id: int,
    entity_id: int = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # Временно отключаем проверку аутентификации для отладки
    # if not request.session.get("user_id"):
    #     return RedirectResponse(url="/login")
    request.session["user_id"] = "debug_admin"

    # 1. Удаляем связь из entity_relation (разрываем связку Ресурса)
    await db.execute(delete(EntityRelation).where(
        (EntityRelation.source_id == text_id) & (EntityRelation.source_type == 'text_content')
    ))

    # 2. Удаляем саму текстовую модальность из text_content
    await db.execute(delete(TextContent).where(TextContent.id == text_id))

    await db.commit()
    return RedirectResponse(url=f"/biological/{entity_id}", status_code=303)

@app.post("/biological/get-map-html")
async def get_map_html(data: dict = Body(...), db: AsyncSession = Depends(get_db)):
    map_id = data.get("map_id")
    result = await db.execute(select(MapContent).where(MapContent.id == map_id))
    map_obj = result.scalars().first()
    if not map_obj:
        return {"html": "<p>Карта не найдена</p>"}
    
    # Преобразуем PostGIS геометрию в GeoJSON
    geojson_data = await db.scalar(select(func.ST_AsGeoJSON(map_obj.geometry)))
    if not geojson_data:
        return {"html": "<p>Геометрия отсутствует</p>"}
    
    geometry_geojson = json.loads(geojson_data)
    m = folium.Map(location=[53.2, 107.3], zoom_start=9, tiles="OpenStreetMap")
    folium.GeoJson(geometry_geojson).add_to(m)
    return {"html": m._repr_html_()}

# ==========================================
# CMS: ДОСТОПРИМЕЧАТЕЛЬНОСТИ (Географические объекты)
# ==========================================

@app.get("/geographical", response_class=HTMLResponse)
async def geographical_list(
    request: Request,
    search: str = None,
    filter_type: str = None,
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    
    bot_online = await is_bot_online_redis()
    
    # Базовый запрос
    query = select(GeographicalEntity)

    # 1. Применяем текстовый поиск (по русскому названию)
    if search:
        query = query.where(GeographicalEntity.name_ru.ilike(f"%{search}%"))

    # 2. Применяем фильтр по категории
    if filter_type and filter_type != "all":
        if filter_type == "natural":
            query = query.where(GeographicalEntity.type.ilike("%природ%"))
        elif filter_type == "cultural":
            query = query.where(GeographicalEntity.type.ilike("%культур%"))
        elif filter_type == "historical":
            query = query.where(GeographicalEntity.type.ilike("%истори%"))

    # Сортировка от новых к старым
    query = query.order_by(GeographicalEntity.id.desc())
    
    # Ограничиваем количество записей для предотвращения таймаута
    query = query.limit(1000)
    
    result = await db.execute(query)
    entities = result.scalars().all()

    return templates.TemplateResponse("geographical_list.html", {
        "request": request,
        "active_page": "geographical",
        "bot_online": bot_online,
        "entities": entities,
        "search": search or "",
        "filter_type": filter_type or "all"
    })

@app.get("/geographical/new", response_class=HTMLResponse)
async def geographical_new(request: Request):
    """Страница с формой создания нового объекта"""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
        
    bot_online = await is_bot_online_redis()
    return templates.TemplateResponse("geographical_form.html", {
        "request": request,
        "active_page": "geographical",
        "bot_online": bot_online,
        "entity": None
    })

@app.post("/geographical/save")
async def geographical_save(
    request: Request,
    name_ru: str = Form(...),
    type: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db)
):
    """Сохранение базового описания достопримечательности в базу"""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
        
    # 1. Создаем сам объект (Географический объект)
    new_entity = GeographicalEntity(
        name_ru=name_ru,
        type=type,
        description=description,
        feature_data={}
    )
    db.add(new_entity)
    await db.commit()
    
    # После создания возвращаем пользователя к карточке
    return RedirectResponse(url=f"/geographical/{new_entity.id}", status_code=303)

@app.get("/geographical/{entity_id}", response_class=HTMLResponse)
async def geographical_edit(request: Request, entity_id: int, db: AsyncSession = Depends(get_db)):
    """Карточка достопримечательности: просмотр и управление связанными ресурсами"""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
        
    bot_online = await is_bot_online_redis()
    
    result = await db.execute(select(GeographicalEntity).where(GeographicalEntity.id == entity_id))
    entity = result.scalars().first()
    
    if not entity:
        raise HTTPException(status_code=404, detail="Достопримечательность не найдена")

    # Ищем текстовые модальности
    text_query = (
        select(TextContent)
        .join(EntityRelation, (EntityRelation.source_id == TextContent.id) & (EntityRelation.source_type == 'text_content'))
        .where((EntityRelation.target_id == entity_id) & (EntityRelation.target_type == 'geographical_entity'))
    )
    texts = (await db.execute(text_query)).scalars().all()

    # Ищем изображения
    image_query = (
        select(ImageContent, EntityIdentifier.file_path)
        .join(EntityRelation, (EntityRelation.source_id == ImageContent.id) & (EntityRelation.source_type == 'image_content'))
        .outerjoin(EntityIdentifierLink, (EntityIdentifierLink.entity_id == ImageContent.id) & (EntityIdentifierLink.entity_type == 'image_content'))
        .outerjoin(EntityIdentifier, EntityIdentifier.id == EntityIdentifierLink.identifier_id)
        .where((EntityRelation.target_id == entity_id) & (EntityRelation.target_type == 'geographical_entity'))
    )
    images_result = await db.execute(image_query)
    
    # Формируем удобный список словарей для шаблона: [{"data": ImageContent, "url": "https..."}]
    images =[{"data": img, "url": url} for img, url in images_result.all()]

    # Ищем географические привязки
    geo_links_query = (
        select(EntityGeo)
        .where((EntityGeo.entity_id == entity_id) & (EntityGeo.entity_type == 'geographical_entity'))
    )
    links = (await db.execute(geo_links_query)).scalars().all()
    
    locations = []

    for link in links:
        geo_id = link.geographical_entity_id
        geo_res = await db.execute(select(GeographicalEntity).where(GeographicalEntity.id == geo_id))
        geo_obj = geo_res.scalars().first()
        if not geo_obj:
            continue

        location_item = {
            "name_ru": geo_obj.name_ru,
            "type": geo_obj.type or "Локация",
            "is_map": False,
            "geo_id": geo_id,
            "feature_data": geo_obj.feature_data
        }

        # Проверяем карту
        map_link_query = select(EntityGeo).where(
            EntityGeo.entity_type == 'map_content',
            EntityGeo.geographical_entity_id == geo_id
        )
        map_link = (await db.execute(map_link_query)).scalars().first()
        if map_link:
            map_res = await db.execute(select(MapContent).where(MapContent.id == map_link.entity_id))
            map_obj = map_res.scalars().first()
            if map_obj:
                location_item["is_map"] = True
                location_item["map_id"] = map_obj.id
        locations.append(location_item)

    return templates.TemplateResponse("geographical_edit.html", {
        "request": request,
        "active_page": "geographical",
        "bot_online": bot_online,
        "entity": entity,
        "texts": texts,
        "images": images,
        "locations": locations
    })

@app.post("/geographical/{entity_id}/add_text")
async def geographical_add_text(
    request: Request,
    entity_id: int,
    title: str = Form(...),
    content: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Добавление текстовой модальности к достопримечательности
    """
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
        
    # 1. Создаем TextContent
    new_text = TextContent(
        title=title,
        content=content,
        feature_data={}
    )
    db.add(new_text)
    await db.flush()
    
    # 2. Создаем связующее звено
    relation = EntityRelation(
        source_id=new_text.id,
        source_type="text_content",
        target_id=entity_id,
        target_type="geographical_entity",
        relation_type="описание объекта"
    )
    db.add(relation)
    await db.commit()
    
    return RedirectResponse(url=f"/geographical/{entity_id}", status_code=303)

@app.post("/geographical/{entity_id}/add_image")
async def geographical_add_image(
    request: Request,
    entity_id: int,
    title: str = Form(...),
    image_url: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Добавление изображения к достопримечательности
    """
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
        
    # 1. Сначала достаем информацию об объекте, чтобы узнать его названия
    result = await db.execute(select(GeographicalEntity).where(GeographicalEntity.id == entity_id))
    entity = result.scalars().first()
    
    if not entity:
        raise HTTPException(status_code=404, detail="Достопримечательность не найдена")

    # 2. Создаем ImageContent
    new_image = ImageContent(
        title=title,
        description="Добавлено через админ-панель",
        feature_data={"source": "Admin Panel"}
    )
    db.add(new_image)
    await db.flush()
    
    # 3. Привязываем картинку к географическому объекту (relation)
    relation = EntityRelation(
        source_id=new_image.id,
        source_type="image_content",
        target_id=entity_id,
        target_type="geographical_entity",
        relation_type="изображение объекта"
    )
    db.add(relation)

    # 4. Создаем запись в entity_identifier
    new_identifier = EntityIdentifier(
        file_path=image_url,
        name_ru=entity.name_ru
    )
    db.add(new_identifier)
    await db.flush()

    # 5. Связываем картинку с её новым идентификатором
    identifier_link = EntityIdentifierLink(
        entity_id=new_image.id,
        entity_type="image_content",
        identifier_id=new_identifier.id
    )
    db.add(identifier_link)

    await db.commit()
    
    return RedirectResponse(url=f"/geographical/{entity_id}", status_code=303)

@app.post("/geographical/resource/delete/text/{text_id}")
async def delete_geographical_text_resource(
    request: Request,
    text_id: int,
    entity_id: int = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    # 1. Удаляем связь из entity_relation
    await db.execute(delete(EntityRelation).where(
        (EntityRelation.source_id == text_id) & (EntityRelation.source_type == 'text_content')
    ))

    # 2. Удаляем саму текстовую модальность из text_content
    await db.execute(delete(TextContent).where(TextContent.id == text_id))

    await db.commit()
    return RedirectResponse(url=f"/geographical/{entity_id}", status_code=303)

@app.post("/geographical/resource/delete/image/{image_id}")
async def delete_geographical_image_resource(
    request: Request,
    image_id: int,
    entity_id: int = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    # 1. Удаляем связи из entity_relation
    await db.execute(delete(EntityRelation).where(
        (EntityRelation.source_id == image_id) & (EntityRelation.source_type == 'image_content')
    ))

    # 2. Находим и удаляем идентификаторы (ссылки)
    link_result = await db.execute(select(EntityIdentifierLink).where(
        (EntityIdentifierLink.entity_id == image_id) & (EntityIdentifierLink.entity_type == 'image_content')
    ))
    links = link_result.scalars().all()
    
    for link in links:
        await db.execute(delete(EntityIdentifier).where(EntityIdentifier.id == link.identifier_id))
    
    # 3. Удаляем сами линки
    await db.execute(delete(EntityIdentifierLink).where(
        (EntityIdentifierLink.entity_id == image_id) & (EntityIdentifierLink.entity_type == 'image_content')
    ))

    # 4. Удаляем саму запись ImageContent
    await db.execute(delete(ImageContent).where(ImageContent.id == image_id))

    await db.commit()
    return RedirectResponse(url=f"/geographical/{entity_id}", status_code=303)

@app.post("/geographical/get-map-html")
async def get_geographical_map_html(data: dict = Body(...), db: AsyncSession = Depends(get_db)):
    map_id = data.get("map_id")
    result = await db.execute(select(MapContent).where(MapContent.id == map_id))
    map_obj = result.scalars().first()
    if not map_obj:
        return {"html": "<p>Карта не найдена</p>"}
    
    # Преобразуем PostGIS геометрию в GeoJSON
    geojson_data = await db.scalar(select(func.ST_AsGeoJSON(map_obj.geometry)))
    if not geojson_data:
        return {"html": "<p>Геометрия отсутствует</p>"}
    
    geometry_geojson = json.loads(geojson_data)
    m = folium.Map(location=[53.2, 107.3], zoom_start=9, tiles="OpenStreetMap")
    folium.GeoJson(geometry_geojson).add_to(m)
    return {"html": m._repr_html_()}

@app.get("/testing", response_class=HTMLResponse)
async def testing_list(request: Request, db: AsyncSession = Depends(get_db), admin_db = Depends(get_admin_db)):
    user_id = request.session.get("user_id")
    if not user_id: return RedirectResponse(url="/login")
    
    # Загружаем ВСЕ объекты для модалки
    res = await db.execute(select(BiologicalEntity).order_by(BiologicalEntity.common_name_ru))
    objects = res.scalars().all()
    
    # История тестов из SQLite
    my_tests = admin_db.query(TestSession).filter(TestSession.user_id == user_id).order_by(TestSession.created_at.desc()).all()
    
    bot_online = await hb.is_alive()
    return templates.TemplateResponse("testing.html", {
        "request": request,
        "active_page": "testing",
        "bot_online": bot_online,
        "objects": objects,
        "tests": my_tests
    })

@app.post("/testing/start")
async def start_new_test(
    request: Request, 
    mode: str = Form(...), 
    objects: list[str] = Form(None), 
    admin_db = Depends(get_admin_db)
):
    user_id = request.session.get("user_id")
    if not user_id: return RedirectResponse(url="/login")

    target_url = f"{TEST_API_BASE.strip()}/start"
    
    # 1. Формируем список параметров как список кортежей (для повторяющихся ключей)
    # Это создаст структуру: ?mode=llm&objs=Нерпа&objs=Омуль
    query_params = [("mode", mode)]
    
    if objects:
        for obj_name in objects:
            query_params.append(("objs", obj_name))

    print(f">>> ЗАПУСК ТЕСТА: {target_url}")
    print(f">>> QUERY PARAMS: {query_params}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Отправляем POST, но все данные в params. Тело будет пустым.
            resp = await client.post(
                target_url,
                params=query_params, 
                headers={
                    "Authorization": f"Bearer {TEST_TOKEN.strip()}",
                    "Content-Type": "application/json"
                }
            )
            
            print(f"<<< ОТВЕТ API: {resp.status_code} | {resp.text}")

            if resp.status_code == 200:
                data = resp.json()
                new_session = TestSession(
                    session_id=data['session_id'],
                    user_id=user_id,
                    mode=mode,
                    status="running",
                    tested_objects=objects if objects else ["Все объекты"]
                )
                admin_db.add(new_session)
                admin_db.commit()
                return RedirectResponse(url="/testing", status_code=303)
            else:
                return HTMLResponse(
                    content=f"<h3>Ошибка API ({resp.status_code}):</h3><pre>{resp.text}</pre>", 
                    status_code=resp.status_code
                )
                
        except Exception as e:
            return HTMLResponse(content=f"<h3>Ошибка соединения: {str(e)}</h3>", status_code=500)

@app.get("/testing/check/{session_id}")
async def check_test_status(session_id: str, admin_db = Depends(get_admin_db)):
    # 1. Сначала ищем в нашей локальной базе
    test = admin_db.query(TestSession).filter(TestSession.session_id == session_id).first()
    if not test: 
        return {"error": "Not found"}

    # --- ВОТ ТУТ ДОБАВЛЯЕМ ПРОВЕРКУ ---
    # Если мы уже знаем, что всё готово и отчет скачан - просто возвращаем это
    if test.status == 'completed' and test.results:
        return {
            "status": test.status, 
            "progress": 100, 
            "stats": test.stats,
            "local": True # Пометка для отладки, что данные из нашей базы
        }
    # ---------------------------------

    # Только если тест еще идет или результаты не скачаны, идем во внешнее API
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            s_resp = await client.get(
                f"{TEST_API_BASE.strip()}/status/{session_id}", 
                headers={"Authorization": f"Bearer {TEST_TOKEN}"}
            )
            if s_resp.status_code == 200:
                data = s_resp.json()
                test.status = data.get('status')
                test.progress = data.get('progress', 0)

                if test.status == 'completed' and not test.results:
                    # Скачиваем один раз и сохраняем навсегда
                    r_resp = await client.get(
                        f"{TEST_API_BASE.strip()}/result/{session_id}/json", 
                        headers={"Authorization": f"Bearer {TEST_TOKEN}"}
                    )
                    if r_resp.status_code == 200:
                        test.results = r_resp.json().get('results')
                        test.stats = r_resp.json().get('stats')

                admin_db.commit()
                return {"status": test.status, "progress": test.progress, "stats": test.stats}
        except Exception as e:
            print(f"Ошибка опроса: {e}")
    
    return {"status": test.status, "progress": test.progress}

@app.get("/testing/results/{session_id}")
async def get_test_results_api(session_id: str, admin_db = Depends(get_admin_db)):
    test = admin_db.query(TestSession).filter(TestSession.session_id == session_id).first()
    if not test or not test.results:
        raise HTTPException(status_code=404, detail="Результаты не найдены")
    
    return {
        "mode": test.mode,
        "stats": test.stats,
        "results": test.results,
        "objects": test.tested_objects
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)