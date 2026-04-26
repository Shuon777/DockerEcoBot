import os
import secrets
import httpx
import uvicorn
import requests
import folium
from shapely import wkb
import json

from typing import List
from fastapi import FastAPI, Request, Depends, Body, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, delete, or_, create_engine, insert, text as sql_text
from sqlalchemy.orm import sessionmaker
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone

from database import get_db
from models.models import ErrorLog, BiologicalEntity, TextContent, ImageContent, EntityRelation, EntityIdentifier, EntityIdentifierLink, GeographicalEntity, EntityGeo, MapContent
from models.admin_models import AdminBase, TestSession
from models.eco_assistant_models import (
    Object, ObjectType, ObjectNameSynonym, object_name_synonym_link,
    Modality, TextValue, ImageValue, GeodataValue,
    Resource, ResourceValue, resource_object_table,
    Author, Source, ReliabilityLevel, Bibliographic, Creation,
    ResourceStatic, SupportMetadata,
    ObjectProperty, ResourceFeature,
)
from heartbeat import BotHeartbeat
from dotenv import load_dotenv

# Константы типов объектов в eco_assistant.object_type
BIO_OBJECT_TYPE_ID = 1  # «Объект флоры и фауны»
GEO_OBJECT_TYPE_ID = 2  # «Географический объект»

app = FastAPI()
load_dotenv()

app.mount("/admin/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["tojson"] = lambda value, indent=None, **_: json.dumps(value, ensure_ascii=False, indent=indent)
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
# CMS: ФЛОРА И ФАУНА (eco_assistant схема)
# ==========================================

@app.get("/biological", response_class=HTMLResponse)
async def biological_list(
    request: Request,
    search: str = None,
    filter_type: str = None,
    filter_resources: str = None,
    sort_by: str = "default",
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    bot_online = await is_bot_online_redis()

    # 1. Счётчики ресурсов по каждому объекту
    counts_raw = await db.execute(sql_text("""
        SELECT ro.object_id,
               COUNT(DISTINCT CASE WHEN m.modality_type = 'Текст'        THEN ro.resource_id END) AS text_count,
               COUNT(DISTINCT CASE WHEN m.modality_type = 'Изображение'  THEN ro.resource_id END) AS image_count,
               COUNT(DISTINCT CASE WHEN m.modality_type = 'Геоданные'    THEN ro.resource_id END) AS geo_count
        FROM eco_assistant.resource_object ro
        JOIN eco_assistant.resource_value rv ON rv.resource_id = ro.resource_id
        JOIN eco_assistant.modality m ON m.id = rv.modality_id
        JOIN eco_assistant.object o ON o.id = ro.object_id
        WHERE o.object_type_id = :otid
        GROUP BY ro.object_id
    """), {"otid": BIO_OBJECT_TYPE_ID})
    resource_counts: dict[int, dict] = {
        row.object_id: {"text": int(row.text_count), "image": int(row.image_count), "geo": int(row.geo_count)}
        for row in counts_raw
    }

    # 2. Глобальная статистика (включая разбивку Флора/Фауна)
    stats_raw = await db.execute(sql_text("""
        WITH rs AS (
            SELECT o.id, o.object_properties,
                   COUNT(DISTINCT CASE WHEN m.modality_type = 'Текст'        THEN ro.resource_id END) AS txt,
                   COUNT(DISTINCT CASE WHEN m.modality_type = 'Изображение'  THEN ro.resource_id END) AS img,
                   COUNT(DISTINCT CASE WHEN m.modality_type = 'Геоданные'    THEN ro.resource_id END) AS geo
            FROM eco_assistant.object o
            LEFT JOIN eco_assistant.resource_object ro ON ro.object_id = o.id
            LEFT JOIN eco_assistant.resource_value rv ON rv.resource_id = ro.resource_id
            LEFT JOIN eco_assistant.modality m ON m.id = rv.modality_id
            WHERE o.object_type_id = :otid
            GROUP BY o.id, o.object_properties
        )
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE txt  > 0) AS has_text,
               COUNT(*) FILTER (WHERE img  > 0) AS has_image,
               COUNT(*) FILTER (WHERE geo  > 0) AS has_geo,
               COUNT(*) FILTER (WHERE txt = 0 AND img = 0 AND geo = 0) AS no_resources,
               COUNT(*) FILTER (WHERE object_properties->>'Тип ОФФ' = 'Объект флоры') AS flora_count,
               COUNT(*) FILTER (WHERE object_properties->>'Тип ОФФ' = 'Объект фауны') AS fauna_count
        FROM rs
    """), {"otid": BIO_OBJECT_TYPE_ID})
    sr = stats_raw.first()
    stats = {
        "total":        int(sr.total),
        "has_text":     int(sr.has_text),
        "has_image":    int(sr.has_image),
        "has_geo":      int(sr.has_geo),
        "no_resources": int(sr.no_resources),
        "flora":        int(sr.flora_count),
        "fauna":        int(sr.fauna_count),
    }

    # 3. Основной запрос
    total_res_sq = (
        select(func.count(func.distinct(resource_object_table.c.resource_id)))
        .where(resource_object_table.c.object_id == Object.id)
        .correlate(Object)
        .scalar_subquery()
    )
    query = (
        select(Object.id, Object.db_id, Object.object_properties,
               func.array_agg(ObjectNameSynonym.synonym).label("synonyms"),
               total_res_sq.label("total_resources"))
        .join(object_name_synonym_link, object_name_synonym_link.c.object_id == Object.id, isouter=True)
        .join(ObjectNameSynonym, ObjectNameSynonym.id == object_name_synonym_link.c.synonym_id, isouter=True)
        .where(Object.object_type_id == BIO_OBJECT_TYPE_ID)
        .group_by(Object.id)
    )

    # 4. Фильтры
    if filter_type and filter_type != "all":
        type_val = "Объект флоры" if filter_type == "flora" else "Объект фауны"
        query = query.where(
            func.jsonb_path_exists(
                Object.object_properties,
                sql_text("""'$."Тип ОФФ" ? (@ == $val)'"""),
                func.jsonb_build_object("val", type_val),
            )
        )

    if filter_resources == "none":
        query = query.where(
            Object.id.notin_(select(resource_object_table.c.object_id).distinct())
        )
    elif filter_resources in ("has_text", "has_image", "has_geo"):
        key = {"has_text": "text", "has_image": "image", "has_geo": "geo"}[filter_resources]
        ids_with = [oid for oid, c in resource_counts.items() if c[key] > 0]
        query = query.where(Object.id.in_(ids_with) if ids_with else sql_text("false"))

    if search:
        matching_ids = (
            select(object_name_synonym_link.c.object_id)
            .join(ObjectNameSynonym, ObjectNameSynonym.id == object_name_synonym_link.c.synonym_id)
            .where(ObjectNameSynonym.synonym.ilike(f"%{search}%"))
        )
        query = query.where(Object.id.in_(matching_ids))

    # 5. Сортировка
    if sort_by == "no_resources":
        query = query.order_by(total_res_sq.asc(), Object.id.desc())
    elif sort_by == "rich":
        query = query.order_by(total_res_sq.desc(), Object.id.desc())
    elif sort_by == "old":
        query = query.order_by(Object.id.asc())
    else:
        query = query.order_by(Object.id.desc())

    # 6. Пагинация
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total_items = await db.scalar(count_query)
    page_size = 50
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    query = query.limit(page_size).offset((page - 1) * page_size)
    rows = (await db.execute(query)).all()

    entities = []
    for row in rows:
        synonyms = [s for s in (row.synonyms or []) if s]
        props = row.object_properties or {}
        c = resource_counts.get(row.id, {"text": 0, "image": 0, "geo": 0})
        entities.append({
            "id": row.id,
            "db_id": row.db_id,
            "name_ru": _primary_synonym(synonyms),
            "synonyms": synonyms,
            "object_properties": props,
            "bio_type": props.get("Тип ОФФ", "") if isinstance(props, dict) else "",
            "scientific_name": props.get("scientific_name", "") if isinstance(props, dict) else "",
            "text_count": c["text"],
            "image_count": c["image"],
            "geo_count": c["geo"],
            "total_resources": int(row.total_resources or 0),
        })

    return templates.TemplateResponse("biological_list.html", {
        "request": request,
        "active_page": "biological",
        "bot_online": bot_online,
        "entities": entities,
        "search": search or "",
        "filter_type": filter_type or "all",
        "filter_resources": filter_resources or "",
        "sort_by": sort_by,
        "stats": stats,
        "page": page,
        "total_pages": total_pages,
        "total_items": total_items,
    })


@app.get("/biological/new", response_class=HTMLResponse)
async def biological_new(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    bot_online = await is_bot_online_redis()

    subtypes_options = await get_property_values(db, BIO_OBJECT_TYPE_ID, "subtypes")
    region_options = await get_property_values(db, BIO_OBJECT_TYPE_ID, "region")
    baikal_relation_options = await get_property_values(db, BIO_OBJECT_TYPE_ID, "baikal_relation")
    authors = (await db.execute(select(Author.name).order_by(Author.name))).scalars().all()
    sources = (await db.execute(select(Source.name).order_by(Source.name))).scalars().all()
    reliability_options = (await db.execute(select(ReliabilityLevel.name).order_by(ReliabilityLevel.name))).scalars().all()

    return templates.TemplateResponse("biological_form.html", {
        "request": request,
        "active_page": "biological",
        "bot_online": bot_online,
        "entity": None,
        "subtypes_options": sorted(subtypes_options, key=str.lower),
        "region_options": sorted(region_options, key=str.lower),
        "baikal_relation_options": baikal_relation_options,
        "authors": authors,
        "sources": sources,
        "reliability_options": reliability_options,
    })


@app.post("/biological/save")
async def biological_save(
    request: Request,
    name_ru: str = Form(...),
    bio_type: str = Form(...),
    subtypes: str = Form(""),
    scientific_name: str = Form(""),
    conservation_status: str = Form(""),
    region: str = Form(""),
    baikal_relation: str = Form(""),
    description: str = Form(""),
    author: str = Form(""),
    source: str = Form(""),
    date: str = Form(""),
    reliability: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    obj = Object(
        db_id=f"BIO_OBJ_{secrets.token_hex(6)}",
        object_type_id=BIO_OBJECT_TYPE_ID,
        object_properties=_build_bio_object_properties(
            bio_type.strip(),
            _parse_subtypes(subtypes),
            scientific_name.strip() or None,
            conservation_status.strip() or None,
            region.strip() or None,
            baikal_relation.strip() or None,
        ),
    )
    db.add(obj)
    await db.flush()

    syn = ObjectNameSynonym(synonym=name_ru, language="ru")
    db.add(syn)
    await db.flush()
    await db.execute(insert(object_name_synonym_link).values(object_id=obj.id, synonym_id=syn.id))

    if description.strip():
        parsed_date = None
        if date.strip():
            try:
                parsed_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
            except ValueError:
                parsed_date = None
        res = await _create_resource_scaffold(
            db, title=name_ru, author_name=author.strip(),
            source_name=source.strip(), reliability_name=reliability.strip(), date_value=parsed_date,
        )
        await _attach_text_to_object(db, object_id=obj.id, resource=res, structured_data={"description": description})

    await db.commit()
    return RedirectResponse(url=f"/biological/{obj.id}", status_code=303)


@app.get("/biological/{object_id}", response_class=HTMLResponse)
async def biological_edit(request: Request, object_id: int, db: AsyncSession = Depends(get_db)):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    bot_online = await is_bot_online_redis()

    obj = (await db.execute(select(Object).where(Object.id == object_id))).scalar()
    if not obj or obj.object_type_id != BIO_OBJECT_TYPE_ID:
        raise HTTPException(status_code=404, detail="Биологический объект не найден")

    synonyms = (await db.execute(
        select(ObjectNameSynonym.synonym)
        .join(object_name_synonym_link, object_name_synonym_link.c.synonym_id == ObjectNameSynonym.id)
        .where(object_name_synonym_link.c.object_id == object_id)
    )).scalars().all()

    props = obj.object_properties or {}
    entity = {
        "id": obj.id,
        "db_id": obj.db_id,
        "name_ru": _primary_synonym(list(synonyms)),
        "synonyms": list(synonyms),
        "object_properties": props,
        "bio_type": props.get("Тип ОФФ", "") if isinstance(props, dict) else "",
        "scientific_name": props.get("scientific_name", "") if isinstance(props, dict) else "",
        "conservation_status": props.get("conservation_status", "") if isinstance(props, dict) else "",
        "subtypes": props.get("subtypes", []) if isinstance(props, dict) else [],
    }

    texts_q = (
        select(Resource.id.label("resource_id"), Resource.title, Resource.features, TextValue.structured_data)
        .join(ResourceValue, ResourceValue.resource_id == Resource.id)
        .join(Modality, Modality.id == ResourceValue.modality_id)
        .join(TextValue, TextValue.id == ResourceValue.value_id)
        .join(resource_object_table, resource_object_table.c.resource_id == Resource.id)
        .where(resource_object_table.c.object_id == object_id)
        .where(Modality.modality_type == "Текст")
        .order_by(Resource.id.desc())
    )
    texts = []
    for row in (await db.execute(texts_q)).all():
        sd = row.structured_data or {}
        content = sd.get("description") if isinstance(sd, dict) else None
        texts.append({
            "id": row.resource_id,
            "title": row.title or "Без заголовка",
            "content": content,
            "structured_data": sd if isinstance(sd, dict) and not (len(sd) == 1 and "description" in sd) else None,
            "feature_data": row.features or {},
        })

    images_q = (
        select(Resource.id.label("resource_id"), Resource.title, Resource.features, ImageValue.url, ImageValue.file_path)
        .join(ResourceValue, ResourceValue.resource_id == Resource.id)
        .join(Modality, Modality.id == ResourceValue.modality_id)
        .join(ImageValue, ImageValue.id == ResourceValue.value_id)
        .join(resource_object_table, resource_object_table.c.resource_id == Resource.id)
        .where(resource_object_table.c.object_id == object_id)
        .where(Modality.modality_type == "Изображение")
        .order_by(Resource.id.desc())
    )
    images = []
    for row in (await db.execute(images_q)).all():
        url = row.url or row.file_path or ""
        images.append({
            "data": {"id": row.resource_id, "title": row.title or "Без названия", "feature_data": row.features or {}},
            "url": url,
        })

    geos_q = (
        select(Resource.id.label("resource_id"), Resource.title, Resource.features,
               GeodataValue.id.label("geodata_id"), GeodataValue.geometry_type)
        .join(ResourceValue, ResourceValue.resource_id == Resource.id)
        .join(Modality, Modality.id == ResourceValue.modality_id)
        .join(GeodataValue, GeodataValue.id == ResourceValue.value_id)
        .join(resource_object_table, resource_object_table.c.resource_id == Resource.id)
        .where(resource_object_table.c.object_id == object_id)
        .where(Modality.modality_type == "Геоданные")
        .order_by(Resource.id.desc())
    )
    locations = []
    for row in (await db.execute(geos_q)).all():
        locations.append({
            "resource_id": row.resource_id,
            "geodata_id": row.geodata_id,
            "name_ru": row.title or "Ареал",
            "type": row.geometry_type or "Геометрия",
            "is_map": True,
            "geo_id": row.geodata_id,
            "map_id": row.geodata_id,
            "feature_data": row.features or {},
        })

    avail_props_rows = (await db.execute(
        select(ObjectProperty)
        .where(ObjectProperty.object_type_id == BIO_OBJECT_TYPE_ID)
        .order_by(ObjectProperty.property_name)
    )).scalars().all()
    available_properties = [
        {"id": p.id, "name": p.property_name, "values": list(p.property_values or [])}
        for p in avail_props_rows
    ]
    text_features = await _get_modality_features(db, "Текст")
    image_features = await _get_modality_features(db, "Изображение")
    geo_features = await _get_modality_features(db, "Геоданные")

    return templates.TemplateResponse("biological_edit.html", {
        "request": request,
        "active_page": "biological",
        "bot_online": bot_online,
        "entity": entity,
        "texts": texts,
        "images": images,
        "locations": locations,
        "available_properties": available_properties,
        "text_features": text_features,
        "image_features": image_features,
        "geo_features": geo_features,
    })


@app.post("/biological/{object_id}/add_text")
async def biological_add_text(
    request: Request,
    object_id: int,
    title: str = Form(...),
    content: str = Form(...),
    author: str = Form(""),
    source: str = Form(""),
    date: str = Form(""),
    reliability: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await _ensure_bio_object_exists(db, object_id)
    parsed_date = None
    if date.strip():
        try:
            parsed_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
        except ValueError:
            parsed_date = None
    res = await _create_resource_scaffold(
        db, title=title, author_name=author.strip(),
        source_name=source.strip(), reliability_name=reliability.strip(), date_value=parsed_date,
    )
    await _attach_text_to_object(db, object_id=object_id, resource=res, structured_data={"description": content})
    await db.commit()
    return RedirectResponse(url=f"/biological/{object_id}", status_code=303)


@app.post("/biological/{object_id}/add_image")
async def biological_add_image(
    request: Request,
    object_id: int,
    title: str = Form(...),
    image_url: str = Form(...),
    author: str = Form(""),
    source: str = Form(""),
    date: str = Form(""),
    reliability: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await _ensure_bio_object_exists(db, object_id)
    parsed_date = None
    if date.strip():
        try:
            parsed_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
        except ValueError:
            parsed_date = None
    fmt = image_url.rsplit(".", 1)[-1].lower() if "." in image_url.rsplit("/", 1)[-1] else None
    res = await _create_resource_scaffold(
        db, title=title, author_name=author.strip(),
        source_name=source.strip(), reliability_name=reliability.strip(), date_value=parsed_date,
    )
    await _attach_image_to_object(db, object_id=object_id, resource=res, url=image_url, file_path=None, fmt=fmt)
    await db.commit()
    return RedirectResponse(url=f"/biological/{object_id}", status_code=303)


@app.post("/biological/{object_id}/add_geo")
async def biological_add_geo(
    request: Request,
    object_id: int,
    title: str = Form(...),
    geojson: str = Form(...),
    author: str = Form(""),
    source: str = Form(""),
    date: str = Form(""),
    reliability: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await _ensure_bio_object_exists(db, object_id)
    try:
        parsed_geojson = json.loads(geojson)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Некорректный GeoJSON: {exc}")
    parsed_date = None
    if date.strip():
        try:
            parsed_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
        except ValueError:
            parsed_date = None
    res = await _create_resource_scaffold(
        db, title=title, author_name=author.strip(),
        source_name=source.strip(), reliability_name=reliability.strip(), date_value=parsed_date,
    )
    await _attach_geodata_to_object(db, object_id=object_id, resource=res, geojson=parsed_geojson,
                                    relation_type="ареал обитания вида")
    await db.commit()
    return RedirectResponse(url=f"/biological/{object_id}", status_code=303)


@app.post("/biological/resource/delete/text/{resource_id}")
async def delete_biological_text_resource(
    request: Request,
    resource_id: int,
    entity_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await _delete_resource_with_values(db, resource_id)
    await db.commit()
    return RedirectResponse(url=f"/biological/{entity_id}", status_code=303)


@app.post("/biological/resource/delete/image/{resource_id}")
async def delete_biological_image_resource(
    request: Request,
    resource_id: int,
    entity_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await _delete_resource_with_values(db, resource_id)
    await db.commit()
    return RedirectResponse(url=f"/biological/{entity_id}", status_code=303)


@app.post("/biological/resource/delete/geo/{resource_id}")
async def delete_biological_geo_resource(
    request: Request,
    resource_id: int,
    entity_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await _delete_resource_with_values(db, resource_id)
    await db.commit()
    return RedirectResponse(url=f"/biological/{entity_id}", status_code=303)


@app.post("/biological/resource/edit/text/{resource_id}")
async def edit_biological_text_resource(
    request: Request,
    resource_id: int,
    entity_id: int = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    res = (await db.execute(select(Resource).where(Resource.id == resource_id))).scalar()
    if not res:
        raise HTTPException(status_code=404)
    res.title = title
    rv = (await db.execute(select(ResourceValue).where(ResourceValue.resource_id == resource_id))).scalar()
    if rv:
        tv = (await db.execute(select(TextValue).where(TextValue.id == rv.value_id))).scalar()
        if tv:
            tv.structured_data = {"description": content}
    await db.commit()
    return RedirectResponse(url=f"/biological/{entity_id}", status_code=303)


@app.post("/biological/resource/edit/image/{resource_id}")
async def edit_biological_image_resource(
    request: Request,
    resource_id: int,
    entity_id: int = Form(...),
    title: str = Form(...),
    image_url: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    res = (await db.execute(select(Resource).where(Resource.id == resource_id))).scalar()
    if not res:
        raise HTTPException(status_code=404)
    res.title = title
    rv = (await db.execute(select(ResourceValue).where(ResourceValue.resource_id == resource_id))).scalar()
    if rv:
        iv = (await db.execute(select(ImageValue).where(ImageValue.id == rv.value_id))).scalar()
        if iv:
            iv.url = image_url
    await db.commit()
    return RedirectResponse(url=f"/biological/{entity_id}", status_code=303)


@app.post("/biological/resource/edit/geo/{resource_id}")
async def edit_biological_geo_resource(
    request: Request,
    resource_id: int,
    entity_id: int = Form(...),
    title: str = Form(...),
    geojson: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    try:
        json.loads(geojson)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Некорректный GeoJSON: {exc}")
    res = (await db.execute(select(Resource).where(Resource.id == resource_id))).scalar()
    if not res:
        raise HTTPException(status_code=404)
    res.title = title
    rv = (await db.execute(select(ResourceValue).where(ResourceValue.resource_id == resource_id))).scalar()
    if rv:
        await db.execute(
            sql_text("UPDATE eco_assistant.geodata_value SET geometry = ST_SetSRID(ST_GeomFromGeoJSON(:gj), 4326) WHERE id = :id"),
            {"gj": geojson, "id": rv.value_id},
        )
    await db.commit()
    return RedirectResponse(url=f"/biological/{entity_id}", status_code=303)


@app.post("/biological/get-map-html")
async def get_biological_map_html(data: dict = Body(...), db: AsyncSession = Depends(get_db)):
    geodata_id = data.get("geodata_id") or data.get("map_id")
    if not geodata_id:
        return {"html": "<p>Идентификатор геоданных не указан</p>"}
    gv = (await db.execute(select(GeodataValue).where(GeodataValue.id == int(geodata_id)))).scalar()
    if not gv:
        return {"html": "<p>Геометрия не найдена</p>"}
    geojson_data = await db.scalar(select(func.ST_AsGeoJSON(gv.geometry)))
    if not geojson_data:
        return {"html": "<p>Геометрия отсутствует</p>"}
    geometry_geojson = json.loads(geojson_data)
    bounds = _geojson_bounds(geometry_geojson)
    m = folium.Map(tiles="OpenStreetMap")
    if bounds:
        sw, ne = bounds
        if sw == ne:
            buf = 0.02
            m.fit_bounds([[sw[0] - buf, sw[1] - buf], [ne[0] + buf, ne[1] + buf]])
        else:
            m.fit_bounds([sw, ne], padding=(30, 30))
    else:
        m.location = [53.5, 108.0]
        m.zoom_start = 9
    folium.GeoJson(geometry_geojson, style_function=lambda f: {
        "color": "#10b981", "weight": 3, "fillColor": "#34d399", "fillOpacity": 0.3
    }).add_to(m)
    return {"html": m._repr_html_()}


@app.get("/biological/resource/geo/{geodata_id}/geojson")
async def get_bio_geo_resource_geojson(geodata_id: int, db: AsyncSession = Depends(get_db)):
    geojson_str = await db.scalar(
        select(func.ST_AsGeoJSON(GeodataValue.geometry)).where(GeodataValue.id == geodata_id)
    )
    if not geojson_str:
        raise HTTPException(status_code=404, detail="Геометрия не найдена")
    return {"geojson": json.loads(geojson_str)}


@app.post("/resource/delete/image/{image_id}")
async def delete_image_resource(
    request: Request,
    image_id: int,
    entity_id: int = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await db.execute(delete(EntityRelation).where(
        (EntityRelation.source_id == image_id) & (EntityRelation.source_type == 'image_content')
    ))
    link_result = await db.execute(select(EntityIdentifierLink).where(
        (EntityIdentifierLink.entity_id == image_id) & (EntityIdentifierLink.entity_type == 'image_content')
    ))
    links = link_result.scalars().all()
    for link in links:
        await db.execute(delete(EntityIdentifier).where(EntityIdentifier.id == link.identifier_id))
    await db.execute(delete(EntityIdentifierLink).where(
        (EntityIdentifierLink.entity_id == image_id) & (EntityIdentifierLink.entity_type == 'image_content')
    ))
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
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await db.execute(delete(EntityRelation).where(
        (EntityRelation.source_id == text_id) & (EntityRelation.source_type == 'text_content')
    ))
    await db.execute(delete(TextContent).where(TextContent.id == text_id))
    await db.commit()
    return RedirectResponse(url=f"/biological/{entity_id}", status_code=303)

# ==========================================
# HELPERS: работа со схемой eco_assistant
# ==========================================

async def get_property_values(db: AsyncSession, object_type_id: int, property_name: str) -> list[str]:
    """Вернуть массив допустимых значений свойства из справочника object_property."""
    q = select(ObjectProperty.property_values).where(
        ObjectProperty.object_type_id == object_type_id,
        ObjectProperty.property_name == property_name,
    )
    row = (await db.execute(q)).first()
    return list(row[0]) if row and row[0] else []


async def get_property_counts(db: AsyncSession, object_type_id: int, property_name: str) -> list[tuple[str, int]]:
    """
    Для справочника (object_type_id, property_name) вернуть список (value, count),
    где count — реальное количество объектов, у которых это значение встречается в
    object.object_properties->property_name (JSONB массив).
    Значения, не встречающиеся ни разу, включаются с count=0.
    """
    allowed = await get_property_values(db, object_type_id, property_name)
    if not allowed:
        return []

    q = sql_text(
        """
        SELECT v AS value, COUNT(*) AS cnt
        FROM eco_assistant.object o,
             jsonb_array_elements_text(COALESCE(o.object_properties->:pname, '[]'::jsonb)) AS v
        WHERE o.object_type_id = :otid
        GROUP BY v
        """
    )
    res = await db.execute(q, {"otid": object_type_id, "pname": property_name})
    counts = {row.value: row.cnt for row in res}
    return [(val, counts.get(val, 0)) for val in allowed]


async def get_modality_id(db: AsyncSession, modality_type: str) -> int:
    """Вернуть id модальности по её типу (Текст, Изображение, Геоданные)."""
    q = select(Modality.id).where(Modality.modality_type == modality_type)
    row = (await db.execute(q)).scalar()
    if row is None:
        raise HTTPException(status_code=500, detail=f"Модальность '{modality_type}' не зарегистрирована в eco_assistant.modality")
    return row


async def _get_modality_features(db: AsyncSession, modality_type: str) -> list:
    """Вернуть список признаков (из resource_feature) для указанной модальности."""
    try:
        mod_id = await get_modality_id(db, modality_type)
        rows = (await db.execute(
            select(ResourceFeature)
            .where(ResourceFeature.modality_id == mod_id)
            .order_by(ResourceFeature.feature_name)
        )).scalars().all()
        return [{"id": f.id, "name": f.feature_name, "values": list(f.feature_values or [])} for f in rows]
    except Exception:
        return []


async def get_or_create(db: AsyncSession, model, **kwargs):
    """Найти существующую запись по kwargs или создать новую. Применяется для простых справочников (Author, Source, ReliabilityLevel)."""
    q = select(model).filter_by(**kwargs)
    inst = (await db.execute(q)).scalar_one_or_none()
    if inst:
        return inst
    inst = model(**kwargs)
    db.add(inst)
    await db.flush()
    return inst


def _parse_subtypes(raw: str | None) -> list[str]:
    """Разобрать строку подтипов (разделитель — запятая) в список без пустых значений."""
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def _build_object_properties(subtypes: list[str], region: str | None,
                             exact_location: str | None, baikal_relation: str | None) -> dict:
    """Собрать словарь object.object_properties, отбрасывая пустые поля."""
    props: dict = {}
    if subtypes:
        props["subtypes"] = subtypes
    if region:
        props["region"] = region
    if exact_location:
        props["exact_location"] = exact_location
    if baikal_relation:
        props["baikal_relation"] = baikal_relation
    return props


async def _create_resource_scaffold(db: AsyncSession, *, title: str, author_name: str,
                                     source_name: str, reliability_name: str,
                                     date_value, creation_tool: str = "Admin Panel",
                                     creation_type: str = "ручной ввод",
                                     features: dict | None = None) -> Resource:
    """
    Создать полноценный каркас ресурса: справочники автора/источника/достоверности,
    запись о создании, библиографию, статические и сопровождающие метаданные, сам Resource.
    Возвращает Resource (уже с id после flush).
    """
    author = await get_or_create(db, Author, name=(author_name or "Admin Panel"))
    source = await get_or_create(db, Source, name=(source_name or "Admin Panel"))
    reliability = await get_or_create(db, ReliabilityLevel, name=(reliability_name or "средняя"))

    creation = Creation(
        creation_type=creation_type,
        creation_tool=creation_tool,
        creation_params={},
    )
    bib = Bibliographic(
        author_id=author.id,
        date=date_value,
        source_id=source.id,
        reliability_level_id=reliability.id,
    )
    sm = SupportMetadata(parameters={})
    db.add_all([creation, bib, sm])
    await db.flush()

    rs = ResourceStatic(bibliographic_id=bib.id, creation_id=creation.id)
    db.add(rs)
    await db.flush()

    res = Resource(
        title=title,
        features=(features or {"in_stoplist": 1}),
        resource_static_id=rs.id,
        support_metadata_id=sm.id,
    )
    db.add(res)
    await db.flush()
    return res


async def _attach_text_to_object(db: AsyncSession, object_id: int, resource: Resource,
                                  structured_data: dict, relation_type: str = "описание объекта"):
    """Создать TextValue + ResourceValue + resource_object-линк для существующего Resource и Object."""
    tv = TextValue(structured_data=structured_data)
    db.add(tv)
    await db.flush()
    db.add(ResourceValue(
        resource_id=resource.id,
        modality_id=await get_modality_id(db, "Текст"),
        value_id=tv.id,
    ))
    await db.execute(insert(resource_object_table).values(
        resource_id=resource.id,
        object_id=object_id,
        relation_type=relation_type,
    ))


async def _attach_image_to_object(db: AsyncSession, object_id: int, resource: Resource,
                                   url: str, file_path: str | None, fmt: str | None,
                                   relation_type: str = "изображение объекта"):
    iv = ImageValue(url=url or None, file_path=file_path or None, format=fmt or None)
    db.add(iv)
    await db.flush()
    db.add(ResourceValue(
        resource_id=resource.id,
        modality_id=await get_modality_id(db, "Изображение"),
        value_id=iv.id,
    ))
    await db.execute(insert(resource_object_table).values(
        resource_id=resource.id,
        object_id=object_id,
        relation_type=relation_type,
    ))


async def _attach_geodata_to_object(db: AsyncSession, object_id: int, resource: Resource,
                                     geojson: dict | str, relation_type: str = "геометрия объекта"):
    """Создать GeodataValue из GeoJSON + ResourceValue + resource_object-линк."""
    geojson_str = geojson if isinstance(geojson, str) else json.dumps(geojson)
    geom_q = select(func.ST_SetSRID(func.ST_GeomFromGeoJSON(geojson_str), 4326))
    geometry_wkb = await db.scalar(geom_q)
    parsed = geojson if isinstance(geojson, dict) else json.loads(geojson_str)
    gv = GeodataValue(geometry=geometry_wkb, geometry_type=parsed.get("type"))
    db.add(gv)
    await db.flush()
    db.add(ResourceValue(
        resource_id=resource.id,
        modality_id=await get_modality_id(db, "Геоданные"),
        value_id=gv.id,
    ))
    await db.execute(insert(resource_object_table).values(
        resource_id=resource.id,
        object_id=object_id,
        relation_type=relation_type,
    ))


def _primary_synonym(synonyms: list[str]) -> str:
    """Выбрать «основное» имя объекта — самый длинный синоним (обычно самый подробный)."""
    if not synonyms:
        return "Без названия"
    return max(synonyms, key=len)


def _build_bio_object_properties(type_: str, subtypes: list[str], scientific_name: str | None,
                                  conservation_status: str | None, region: str | None,
                                  baikal_relation: str | None) -> dict:
    """Собрать словарь object.object_properties для биологического объекта."""
    props: dict = {"Тип ОФФ": type_}
    if subtypes:
        props["subtypes"] = subtypes
    if scientific_name:
        props["scientific_name"] = scientific_name
    if conservation_status:
        props["conservation_status"] = conservation_status
    if region:
        props["region"] = region
    if baikal_relation:
        props["baikal_relation"] = baikal_relation
    return props


async def _ensure_bio_object_exists(db: AsyncSession, object_id: int):
    """Проверить, что объект с данным id существует и является биологическим."""
    obj = (await db.execute(
        select(Object.id).where(Object.id == object_id, Object.object_type_id == BIO_OBJECT_TYPE_ID)
    )).scalar()
    if not obj:
        raise HTTPException(status_code=404, detail="Биологический объект не найден")


# ==========================================
# CMS: ДОСТОПРИМЕЧАТЕЛЬНОСТИ (Географические объекты)
# ==========================================

@app.get("/geographical", response_class=HTMLResponse)
async def geographical_list(
    request: Request,
    search: str = None,
    filter_subtype: List[str] = Query(default=[]),
    filter_resources: str = None,
    sort_by: str = "default",
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    bot_online = await is_bot_online_redis()

    # 1. Счетчики
    counts_raw = await db.execute(sql_text("""
        SELECT ro.object_id,
               COUNT(DISTINCT CASE WHEN m.modality_type = 'Текст'        THEN ro.resource_id END) AS text_count,
               COUNT(DISTINCT CASE WHEN m.modality_type = 'Изображение'  THEN ro.resource_id END) AS image_count,
               COUNT(DISTINCT CASE WHEN m.modality_type = 'Геоданные'    THEN ro.resource_id END) AS geo_count
        FROM eco_assistant.resource_object ro
        JOIN eco_assistant.resource_value rv ON rv.resource_id = ro.resource_id
        JOIN eco_assistant.modality m ON m.id = rv.modality_id
        JOIN eco_assistant.object o ON o.id = ro.object_id
        WHERE o.object_type_id = :otid
        GROUP BY ro.object_id
    """), {"otid": GEO_OBJECT_TYPE_ID})
    resource_counts: dict[int, dict] = {
        row.object_id: {"text": int(row.text_count), "image": int(row.image_count), "geo": int(row.geo_count)}
        for row in counts_raw
    }

    # 2. Статистика
    stats_raw = await db.execute(sql_text("""
        WITH rs AS (
            SELECT o.id,
                   COUNT(DISTINCT CASE WHEN m.modality_type = 'Текст'        THEN ro.resource_id END) AS txt,
                   COUNT(DISTINCT CASE WHEN m.modality_type = 'Изображение'  THEN ro.resource_id END) AS img,
                   COUNT(DISTINCT CASE WHEN m.modality_type = 'Геоданные'    THEN ro.resource_id END) AS geo
            FROM eco_assistant.object o
            LEFT JOIN eco_assistant.resource_object ro ON ro.object_id = o.id
            LEFT JOIN eco_assistant.resource_value rv ON rv.resource_id = ro.resource_id
            LEFT JOIN eco_assistant.modality m ON m.id = rv.modality_id
            WHERE o.object_type_id = :otid
            GROUP BY o.id
        )
        SELECT COUNT(*)                             AS total,
               COUNT(*) FILTER (WHERE txt  > 0)    AS has_text,
               COUNT(*) FILTER (WHERE img  > 0)    AS has_image,
               COUNT(*) FILTER (WHERE geo  > 0)    AS has_geo,
               COUNT(*) FILTER (WHERE txt = 0 AND img = 0 AND geo = 0) AS no_resources
        FROM rs
    """), {"otid": GEO_OBJECT_TYPE_ID})
    sr = stats_raw.first()
    stats = {
        "total":        int(sr.total),
        "has_text":     int(sr.has_text),
        "has_image":    int(sr.has_image),
        "has_geo":      int(sr.has_geo),
        "no_resources": int(sr.no_resources),
    }

    # 3. Подзапрос ресурсов (отдельно для использования в сортировке и выборке)
    total_res_sq = (
        select(func.count(func.distinct(resource_object_table.c.resource_id)))
        .where(resource_object_table.c.object_id == Object.id)
        .correlate(Object)
        .scalar_subquery()
    )

    query = (
        select(Object.id, Object.db_id, Object.object_properties,
               func.array_agg(ObjectNameSynonym.synonym).label("synonyms"),
               total_res_sq.label("total_resources"))
        .join(object_name_synonym_link, object_name_synonym_link.c.object_id == Object.id, isouter=True)
        .join(ObjectNameSynonym, ObjectNameSynonym.id == object_name_synonym_link.c.synonym_id, isouter=True)
        .where(Object.object_type_id == GEO_OBJECT_TYPE_ID)
        .group_by(Object.id)
    )

    # 4. Фильтры
    active_subtypes = [s for s in filter_subtype if s and s != "all"]
    for st in active_subtypes:
        query = query.where(
            func.jsonb_path_exists(
                Object.object_properties,
                sql_text("'$.subtypes[*] ? (@ == $val)'"),
                func.jsonb_build_object("val", st),
            )
        )

    if filter_resources == "none":
        query = query.where(
            Object.id.notin_(select(resource_object_table.c.object_id).distinct())
        )
    elif filter_resources in ("has_text", "has_image", "has_geo"):
        key = {"has_text": "text", "has_image": "image", "has_geo": "geo"}[filter_resources]
        ids_with =[oid for oid, c in resource_counts.items() if c[key] > 0]
        query = query.where(Object.id.in_(ids_with) if ids_with else sql_text("false"))

    if search:
        matching_ids = (
            select(object_name_synonym_link.c.object_id)
            .join(ObjectNameSynonym, ObjectNameSynonym.id == object_name_synonym_link.c.synonym_id)
            .where(ObjectNameSynonym.synonym.ilike(f"%{search}%"))
        )
        query = query.where(Object.id.in_(matching_ids))

    # 5. СОРТИРОВКА (надежная, с передачей самого подзапроса + вторичная по ID)
    if sort_by == "no_resources":
        query = query.order_by(total_res_sq.asc(), Object.id.desc())
    elif sort_by == "rich":
        query = query.order_by(total_res_sq.desc(), Object.id.desc())
    elif sort_by == "old":
        query = query.order_by(Object.id.asc())
    else:
        query = query.order_by(Object.id.desc())

    # 6. ПАГИНАЦИЯ
    # Считаем точное количество до применения limit/offset
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total_items = await db.scalar(count_query)

    page_size = 50
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))

    query = query.limit(page_size).offset((page - 1) * page_size)
    rows = (await db.execute(query)).all()

    entities = []
    for row in rows:
        synonyms =[s for s in (row.synonyms or []) if s]
        props = row.object_properties or {}
        c = resource_counts.get(row.id, {"text": 0, "image": 0, "geo": 0})
        entities.append({
            "id": row.id,
            "db_id": row.db_id,
            "name_ru": _primary_synonym(synonyms),
            "synonyms": synonyms,
            "object_properties": props,
            "subtypes": props.get("subtypes", []) if isinstance(props, dict) else[],
            "text_count": c["text"],
            "image_count": c["image"],
            "geo_count": c["geo"],
            "total_resources": int(row.total_resources or 0),
        })

    subtypes_stats = await get_property_counts(db, GEO_OBJECT_TYPE_ID, "subtypes")
    subtypes_stats.sort(key=lambda x: (-x[1], x[0].lower()))

    return templates.TemplateResponse("geographical_list.html", {
        "request": request,
        "active_page": "geographical",
        "bot_online": bot_online,
        "entities": entities,
        "search": search or "",
        "active_subtypes": active_subtypes,
        "filter_resources": filter_resources or "",
        "sort_by": sort_by,
        "subtypes_stats": subtypes_stats,
        "stats": stats,
        "page": page,
        "total_pages": total_pages,
        "total_items": total_items,
    })


@app.get("/geographical/new", response_class=HTMLResponse)
async def geographical_new(request: Request, db: AsyncSession = Depends(get_db)):
    """Страница с формой создания новой достопримечательности."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    bot_online = await is_bot_online_redis()

    # Опции для полей формы — из справочника object_property и существующих записей
    subtypes_options = await get_property_values(db, GEO_OBJECT_TYPE_ID, "subtypes")
    region_options = await get_property_values(db, GEO_OBJECT_TYPE_ID, "region")
    exact_location_options = await get_property_values(db, GEO_OBJECT_TYPE_ID, "exact_location")
    baikal_relation_options = await get_property_values(db, GEO_OBJECT_TYPE_ID, "baikal_relation")

    authors = (await db.execute(select(Author.name).order_by(Author.name))).scalars().all()
    sources = (await db.execute(select(Source.name).order_by(Source.name))).scalars().all()
    reliability_options = (await db.execute(select(ReliabilityLevel.name).order_by(ReliabilityLevel.name))).scalars().all()

    return templates.TemplateResponse("geographical_form.html", {
        "request": request,
        "active_page": "geographical",
        "bot_online": bot_online,
        "entity": None,
        "subtypes_options": sorted(subtypes_options, key=str.lower),
        "region_options": sorted(region_options, key=str.lower),
        "exact_location_options": exact_location_options[:200],
        "baikal_relation_options": baikal_relation_options,
        "authors": authors,
        "sources": sources,
        "reliability_options": reliability_options,
    })


@app.post("/geographical/save")
async def geographical_save(
    request: Request,
    name_ru: str = Form(...),
    subtypes: str = Form(""),
    region: str = Form(""),
    exact_location: str = Form(""),
    baikal_relation: str = Form(""),
    description: str = Form(""),
    author: str = Form(""),
    source: str = Form(""),
    date: str = Form(""),
    reliability: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Создать новую достопримечательность в eco_assistant.object + связанный ресурс-описание."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    # 1. Object + object_properties
    obj = Object(
        db_id=f"GEO_OBJ_{secrets.token_hex(6)}",
        object_type_id=GEO_OBJECT_TYPE_ID,
        object_properties=_build_object_properties(
            _parse_subtypes(subtypes),
            region.strip() or None,
            exact_location.strip() or None,
            baikal_relation.strip() or None,
        ),
    )
    db.add(obj)
    await db.flush()

    # 2. Синоним-имя + link
    syn = ObjectNameSynonym(synonym=name_ru, language="ru")
    db.add(syn)
    await db.flush()
    await db.execute(insert(object_name_synonym_link).values(object_id=obj.id, synonym_id=syn.id))

    # 3. Если задано описание — собираем Resource с текстовой модальностью
    if description.strip():
        parsed_date = None
        if date.strip():
            try:
                parsed_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
            except ValueError:
                parsed_date = None
        res = await _create_resource_scaffold(
            db,
            title=name_ru,
            author_name=author.strip(),
            source_name=source.strip(),
            reliability_name=reliability.strip(),
            date_value=parsed_date,
        )
        await _attach_text_to_object(
            db, object_id=obj.id, resource=res,
            structured_data={"description": description},
        )

    await db.commit()
    return RedirectResponse(url=f"/geographical/{obj.id}", status_code=303)


@app.get("/geographical/{object_id}", response_class=HTMLResponse)
async def geographical_edit(request: Request, object_id: int, db: AsyncSession = Depends(get_db)):
    """Карточка достопримечательности: синонимы, свойства и связанные ресурсы."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    bot_online = await is_bot_online_redis()

    # 1. Объект и синонимы
    obj = (await db.execute(select(Object).where(Object.id == object_id))).scalar()
    if not obj or obj.object_type_id != GEO_OBJECT_TYPE_ID:
        raise HTTPException(status_code=404, detail="Достопримечательность не найдена")

    synonyms = (await db.execute(
        select(ObjectNameSynonym.synonym)
        .join(object_name_synonym_link, object_name_synonym_link.c.synonym_id == ObjectNameSynonym.id)
        .where(object_name_synonym_link.c.object_id == object_id)
    )).scalars().all()

    entity = {
        "id": obj.id,
        "db_id": obj.db_id,
        "name_ru": _primary_synonym(list(synonyms)),
        "synonyms": list(synonyms),
        "object_properties": obj.object_properties or {},
        "subtypes": (obj.object_properties or {}).get("subtypes", []),
        "feature_data": obj.object_properties or {},
    }

    # 2. Текстовые ресурсы
    texts_q = (
        select(
            Resource.id.label("resource_id"),
            Resource.title,
            Resource.features,
            TextValue.structured_data,
        )
        .join(ResourceValue, ResourceValue.resource_id == Resource.id)
        .join(Modality, Modality.id == ResourceValue.modality_id)
        .join(TextValue, TextValue.id == ResourceValue.value_id)
        .join(resource_object_table, resource_object_table.c.resource_id == Resource.id)
        .where(resource_object_table.c.object_id == object_id)
        .where(Modality.modality_type == "Текст")
        .order_by(Resource.id.desc())
    )
    texts = []
    for row in (await db.execute(texts_q)).all():
        sd = row.structured_data or {}
        content = sd.get("description") if isinstance(sd, dict) else None
        texts.append({
            "id": row.resource_id,
            "title": row.title or "Без заголовка",
            "content": content,
            "structured_data": sd if isinstance(sd, dict) and not (len(sd) == 1 and "description" in sd) else None,
            "feature_data": row.features or {},
        })

    # 3. Изображения
    images_q = (
        select(
            Resource.id.label("resource_id"),
            Resource.title,
            Resource.features,
            ImageValue.url,
            ImageValue.file_path,
        )
        .join(ResourceValue, ResourceValue.resource_id == Resource.id)
        .join(Modality, Modality.id == ResourceValue.modality_id)
        .join(ImageValue, ImageValue.id == ResourceValue.value_id)
        .join(resource_object_table, resource_object_table.c.resource_id == Resource.id)
        .where(resource_object_table.c.object_id == object_id)
        .where(Modality.modality_type == "Изображение")
        .order_by(Resource.id.desc())
    )
    images = []
    for row in (await db.execute(images_q)).all():
        url = row.url or row.file_path or ""
        images.append({
            "data": {
                "id": row.resource_id,
                "title": row.title or "Без названия",
                "feature_data": row.features or {},
            },
            "url": url,
        })

    # 4. Геоданные
    geos_q = (
        select(
            Resource.id.label("resource_id"),
            Resource.title,
            Resource.features,
            GeodataValue.id.label("geodata_id"),
            GeodataValue.geometry_type,
        )
        .join(ResourceValue, ResourceValue.resource_id == Resource.id)
        .join(Modality, Modality.id == ResourceValue.modality_id)
        .join(GeodataValue, GeodataValue.id == ResourceValue.value_id)
        .join(resource_object_table, resource_object_table.c.resource_id == Resource.id)
        .where(resource_object_table.c.object_id == object_id)
        .where(Modality.modality_type == "Геоданные")
        .order_by(Resource.id.desc())
    )
    locations = []
    for row in (await db.execute(geos_q)).all():
        locations.append({
            "resource_id": row.resource_id,
            "geodata_id": row.geodata_id,
            "name_ru": row.title or "Геометрия",
            "type": row.geometry_type or "Геометрия",
            "is_map": True,
            "geo_id": row.geodata_id,
            "map_id": row.geodata_id,
            "feature_data": row.features or {},
        })

    avail_props_rows = (await db.execute(
        select(ObjectProperty)
        .where(ObjectProperty.object_type_id == GEO_OBJECT_TYPE_ID)
        .order_by(ObjectProperty.property_name)
    )).scalars().all()
    available_properties = [
        {"id": p.id, "name": p.property_name, "values": list(p.property_values or [])}
        for p in avail_props_rows
    ]
    text_features = await _get_modality_features(db, "Текст")
    image_features = await _get_modality_features(db, "Изображение")
    geo_features = await _get_modality_features(db, "Геоданные")

    return templates.TemplateResponse("geographical_edit.html", {
        "request": request,
        "active_page": "geographical",
        "bot_online": bot_online,
        "entity": entity,
        "texts": texts,
        "images": images,
        "locations": locations,
        "available_properties": available_properties,
        "text_features": text_features,
        "image_features": image_features,
        "geo_features": geo_features,
    })


@app.post("/geographical/{object_id}/add_text")
async def geographical_add_text(
    request: Request,
    object_id: int,
    title: str = Form(...),
    content: str = Form(...),
    author: str = Form(""),
    source: str = Form(""),
    date: str = Form(""),
    reliability: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Добавление текстового ресурса к достопримечательности."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    await _ensure_object_exists(db, object_id)

    parsed_date = None
    if date.strip():
        try:
            parsed_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
        except ValueError:
            parsed_date = None

    res = await _create_resource_scaffold(
        db,
        title=title,
        author_name=author.strip(),
        source_name=source.strip(),
        reliability_name=reliability.strip(),
        date_value=parsed_date,
    )
    await _attach_text_to_object(
        db, object_id=object_id, resource=res,
        structured_data={"description": content},
    )
    await db.commit()
    return RedirectResponse(url=f"/geographical/{object_id}", status_code=303)


@app.post("/geographical/{object_id}/add_image")
async def geographical_add_image(
    request: Request,
    object_id: int,
    title: str = Form(...),
    image_url: str = Form(...),
    author: str = Form(""),
    source: str = Form(""),
    date: str = Form(""),
    reliability: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Добавление изображения к достопримечательности."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    await _ensure_object_exists(db, object_id)

    parsed_date = None
    if date.strip():
        try:
            parsed_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
        except ValueError:
            parsed_date = None

    fmt = image_url.rsplit(".", 1)[-1].lower() if "." in image_url.rsplit("/", 1)[-1] else None
    res = await _create_resource_scaffold(
        db,
        title=title,
        author_name=author.strip(),
        source_name=source.strip(),
        reliability_name=reliability.strip(),
        date_value=parsed_date,
    )
    await _attach_image_to_object(
        db, object_id=object_id, resource=res,
        url=image_url, file_path=None, fmt=fmt,
    )
    await db.commit()
    return RedirectResponse(url=f"/geographical/{object_id}", status_code=303)


@app.post("/geographical/{object_id}/add_geo")
async def geographical_add_geo(
    request: Request,
    object_id: int,
    title: str = Form(...),
    geojson: str = Form(...),
    author: str = Form(""),
    source: str = Form(""),
    date: str = Form(""),
    reliability: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Добавление геоданных (GeoJSON) к достопримечательности."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")

    await _ensure_object_exists(db, object_id)

    try:
        parsed_geojson = json.loads(geojson)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Некорректный GeoJSON: {exc}")

    parsed_date = None
    if date.strip():
        try:
            parsed_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
        except ValueError:
            parsed_date = None

    res = await _create_resource_scaffold(
        db,
        title=title,
        author_name=author.strip(),
        source_name=source.strip(),
        reliability_name=reliability.strip(),
        date_value=parsed_date,
    )
    await _attach_geodata_to_object(db, object_id=object_id, resource=res, geojson=parsed_geojson)
    await db.commit()
    return RedirectResponse(url=f"/geographical/{object_id}", status_code=303)


async def _delete_resource_with_values(db: AsyncSession, resource_id: int):
    """Удалить Resource и все связанные value-записи (text_value / image_value / geodata_value)."""
    rvs = (await db.execute(
        select(ResourceValue.modality_id, ResourceValue.value_id)
        .where(ResourceValue.resource_id == resource_id)
    )).all()
    for modality_id, value_id in rvs:
        if value_id is None:
            continue
        mod = (await db.execute(select(Modality).where(Modality.id == modality_id))).scalar()
        if not mod:
            continue
        value_table = {
            "text_value": TextValue,
            "image_value": ImageValue,
            "geodata_value": GeodataValue,
        }.get(mod.value_table_name)
        if value_table is None:
            continue
        await db.execute(delete(value_table).where(value_table.id == value_id))
    # Resource удалит resource_value и resource_object каскадом
    await db.execute(delete(Resource).where(Resource.id == resource_id))


async def _ensure_object_exists(db: AsyncSession, object_id: int):
    obj = (await db.execute(
        select(Object.id).where(Object.id == object_id, Object.object_type_id == GEO_OBJECT_TYPE_ID)
    )).scalar()
    if not obj:
        raise HTTPException(status_code=404, detail="Достопримечательность не найдена")


@app.post("/geographical/resource/delete/text/{resource_id}")
async def delete_geographical_text_resource(
    request: Request,
    resource_id: int,
    entity_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await _delete_resource_with_values(db, resource_id)
    await db.commit()
    return RedirectResponse(url=f"/geographical/{entity_id}", status_code=303)


@app.post("/geographical/resource/delete/image/{resource_id}")
async def delete_geographical_image_resource(
    request: Request,
    resource_id: int,
    entity_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await _delete_resource_with_values(db, resource_id)
    await db.commit()
    return RedirectResponse(url=f"/geographical/{entity_id}", status_code=303)


@app.post("/geographical/resource/delete/geo/{resource_id}")
async def delete_geographical_geo_resource(
    request: Request,
    resource_id: int,
    entity_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await _delete_resource_with_values(db, resource_id)
    await db.commit()
    return RedirectResponse(url=f"/geographical/{entity_id}", status_code=303)


def _geojson_bounds(geojson: dict):
    """Вернуть [[minLat, minLng], [maxLat, maxLng]] из GeoJSON-геометрии."""
    coords: list[tuple[float, float]] = []

    def _extract(obj):
        if isinstance(obj, list):
            if obj and isinstance(obj[0], (int, float)):
                coords.append((obj[1], obj[0]))  # (lat, lng)
            else:
                for item in obj:
                    _extract(item)
        elif isinstance(obj, dict):
            for v in obj.values():
                _extract(v)

    _extract(geojson)
    if not coords:
        return None
    lats = [c[0] for c in coords]
    lngs = [c[1] for c in coords]
    return [[min(lats), min(lngs)], [max(lats), max(lngs)]]


@app.post("/geographical/get-map-html")
async def get_geographical_map_html(data: dict = Body(...), db: AsyncSession = Depends(get_db)):
    """Отрисовать геометрию из eco_assistant.geodata_value в виде HTML-карты (folium)."""
    geodata_id = data.get("geodata_id") or data.get("map_id")
    if not geodata_id:
        return {"html": "<p>Идентификатор геоданных не указан</p>"}

    gv = (await db.execute(select(GeodataValue).where(GeodataValue.id == int(geodata_id)))).scalar()
    if not gv:
        return {"html": "<p>Геометрия не найдена</p>"}

    geojson_data = await db.scalar(select(func.ST_AsGeoJSON(gv.geometry)))
    if not geojson_data:
        return {"html": "<p>Геометрия отсутствует</p>"}

    geometry_geojson = json.loads(geojson_data)
    bounds = _geojson_bounds(geometry_geojson)
    m = folium.Map(tiles="OpenStreetMap")
    if bounds:
        sw, ne = bounds
        # Для точки добавить буфер, чтобы не было нулевого зума
        if sw == ne:
            buf = 0.02
            m.fit_bounds([[sw[0] - buf, sw[1] - buf], [ne[0] + buf, ne[1] + buf]])
        else:
            m.fit_bounds([sw, ne], padding=(30, 30))
    else:
        m.location = [53.2, 107.3]
        m.zoom_start = 9
    folium.GeoJson(geometry_geojson, style_function=lambda f: {
        "color": "#2563eb", "weight": 3, "fillColor": "#3b82f6", "fillOpacity": 0.25
    }).add_to(m)
    return {"html": m._repr_html_()}


@app.get("/geographical/resource/geo/{geodata_id}/geojson")
async def get_geo_resource_geojson(geodata_id: int, db: AsyncSession = Depends(get_db)):
    """Вернуть GeoJSON геометрии для редактирования в модальном окне."""
    geojson_str = await db.scalar(
        select(func.ST_AsGeoJSON(GeodataValue.geometry)).where(GeodataValue.id == geodata_id)
    )
    if not geojson_str:
        raise HTTPException(status_code=404, detail="Геометрия не найдена")
    return {"geojson": json.loads(geojson_str)}


@app.post("/geographical/resource/edit/text/{resource_id}")
async def edit_geographical_text_resource(
    request: Request,
    resource_id: int,
    entity_id: int = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Обновить заголовок и содержимое текстового ресурса."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    res = (await db.execute(select(Resource).where(Resource.id == resource_id))).scalar()
    if not res:
        raise HTTPException(status_code=404)
    res.title = title
    rv = (await db.execute(select(ResourceValue).where(ResourceValue.resource_id == resource_id))).scalar()
    if rv:
        tv = (await db.execute(select(TextValue).where(TextValue.id == rv.value_id))).scalar()
        if tv:
            tv.structured_data = {"description": content}
    await db.commit()
    return RedirectResponse(url=f"/geographical/{entity_id}", status_code=303)


@app.post("/geographical/resource/edit/image/{resource_id}")
async def edit_geographical_image_resource(
    request: Request,
    resource_id: int,
    entity_id: int = Form(...),
    title: str = Form(...),
    image_url: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Обновить заголовок и URL изображения."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    res = (await db.execute(select(Resource).where(Resource.id == resource_id))).scalar()
    if not res:
        raise HTTPException(status_code=404)
    res.title = title
    rv = (await db.execute(select(ResourceValue).where(ResourceValue.resource_id == resource_id))).scalar()
    if rv:
        iv = (await db.execute(select(ImageValue).where(ImageValue.id == rv.value_id))).scalar()
        if iv:
            iv.url = image_url
    await db.commit()
    return RedirectResponse(url=f"/geographical/{entity_id}", status_code=303)


@app.post("/geographical/resource/edit/geo/{resource_id}")
async def edit_geographical_geo_resource(
    request: Request,
    resource_id: int,
    entity_id: int = Form(...),
    title: str = Form(...),
    geojson: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Обновить заголовок и геометрию геоданных."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    try:
        json.loads(geojson)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Некорректный GeoJSON: {exc}")
    res = (await db.execute(select(Resource).where(Resource.id == resource_id))).scalar()
    if not res:
        raise HTTPException(status_code=404)
    res.title = title
    rv = (await db.execute(select(ResourceValue).where(ResourceValue.resource_id == resource_id))).scalar()
    if rv:
        await db.execute(
            sql_text(
                "UPDATE eco_assistant.geodata_value "
                "SET geometry = ST_SetSRID(ST_GeomFromGeoJSON(:gj), 4326) "
                "WHERE id = :id"
            ),
            {"gj": geojson, "id": rv.value_id},
        )
    await db.commit()
    return RedirectResponse(url=f"/geographical/{entity_id}", status_code=303)

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


# ==========================================
# CMS: КАТАЛОГ СВОЙСТВ (ObjectProperty)
# ==========================================

@app.get("/properties", response_class=HTMLResponse)
async def properties_list_page(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    bot_online = await is_bot_online_redis()
    object_types = (await db.execute(select(ObjectType).order_by(ObjectType.id))).scalars().all()
    properties = (await db.execute(
        select(ObjectProperty).order_by(ObjectProperty.object_type_id, ObjectProperty.property_name)
    )).scalars().all()
    return templates.TemplateResponse("properties_list.html", {
        "request": request,
        "active_page": "properties",
        "bot_online": bot_online,
        "object_types": object_types,
        "properties": properties,
    })


@app.post("/properties/new")
async def properties_new(
    request: Request,
    object_type_id: int = Form(...),
    property_name: str = Form(...),
    property_values: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    values_list = [v.strip() for v in property_values.split(",") if v.strip()]
    prop = ObjectProperty(
        object_type_id=object_type_id,
        property_name=property_name.strip(),
        property_values=values_list,
    )
    db.add(prop)
    await db.commit()
    return RedirectResponse(url="/properties", status_code=303)


@app.post("/properties/{prop_id}/edit")
async def properties_edit(
    request: Request,
    prop_id: int,
    property_values: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    prop = (await db.execute(select(ObjectProperty).where(ObjectProperty.id == prop_id))).scalar()
    if not prop:
        raise HTTPException(status_code=404)
    prop.property_values = [v.strip() for v in property_values.split(",") if v.strip()]
    await db.commit()
    return RedirectResponse(url="/properties", status_code=303)


@app.post("/properties/{prop_id}/delete")
async def properties_delete(
    request: Request,
    prop_id: int,
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await db.execute(delete(ObjectProperty).where(ObjectProperty.id == prop_id))
    await db.commit()
    return RedirectResponse(url="/properties", status_code=303)


# ==========================================
# CMS: КАТАЛОГ ПРИЗНАКОВ (ResourceFeature)
# ==========================================

@app.get("/features", response_class=HTMLResponse)
async def features_list_page(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    bot_online = await is_bot_online_redis()
    modalities = (await db.execute(select(Modality).order_by(Modality.id))).scalars().all()
    features = (await db.execute(
        select(ResourceFeature).order_by(ResourceFeature.modality_id, ResourceFeature.feature_name)
    )).scalars().all()
    return templates.TemplateResponse("features_list.html", {
        "request": request,
        "active_page": "features",
        "bot_online": bot_online,
        "modalities": modalities,
        "features": features,
    })


@app.post("/features/new")
async def features_new(
    request: Request,
    modality_id: int = Form(...),
    feature_name: str = Form(...),
    feature_values: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    values_list = [v.strip() for v in feature_values.split(",") if v.strip()]
    feat = ResourceFeature(
        modality_id=modality_id,
        feature_name=feature_name.strip(),
        feature_values=values_list,
    )
    db.add(feat)
    await db.commit()
    return RedirectResponse(url="/features", status_code=303)


@app.post("/features/{feat_id}/edit")
async def features_edit(
    request: Request,
    feat_id: int,
    feature_values: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    feat = (await db.execute(select(ResourceFeature).where(ResourceFeature.id == feat_id))).scalar()
    if not feat:
        raise HTTPException(status_code=404)
    feat.feature_values = [v.strip() for v in feature_values.split(",") if v.strip()]
    await db.commit()
    return RedirectResponse(url="/features", status_code=303)


@app.post("/features/{feat_id}/delete")
async def features_delete(
    request: Request,
    feat_id: int,
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    await db.execute(delete(ResourceFeature).where(ResourceFeature.id == feat_id))
    await db.commit()
    return RedirectResponse(url="/features", status_code=303)


# ==========================================
# CMS: ОБНОВЛЕНИЕ СВОЙСТВ ОБЪЕКТА
# ==========================================

@app.post("/biological/{object_id}/set_property")
async def biological_set_property(
    request: Request,
    object_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return {"ok": False, "error": "unauthorized"}
    obj = (await db.execute(
        select(Object).where(Object.id == object_id, Object.object_type_id == BIO_OBJECT_TYPE_ID)
    )).scalar()
    if not obj:
        raise HTTPException(status_code=404)
    current = dict(obj.object_properties or {})
    for k, v in (data.get("properties") or {}).items():
        if v is None or v == "" or v == []:
            current.pop(k, None)
        else:
            current[k] = v
    obj.object_properties = current
    await db.commit()
    return {"ok": True}


@app.post("/geographical/{object_id}/set_property")
async def geographical_set_property(
    request: Request,
    object_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return {"ok": False, "error": "unauthorized"}
    obj = (await db.execute(
        select(Object).where(Object.id == object_id, Object.object_type_id == GEO_OBJECT_TYPE_ID)
    )).scalar()
    if not obj:
        raise HTTPException(status_code=404)
    current = dict(obj.object_properties or {})
    for k, v in (data.get("properties") or {}).items():
        if v is None or v == "" or v == []:
            current.pop(k, None)
        else:
            current[k] = v
    obj.object_properties = current
    await db.commit()
    return {"ok": True}


# ==========================================
# CMS: ОБНОВЛЕНИЕ ПРИЗНАКОВ РЕСУРСА
# ==========================================

@app.post("/resource/{resource_id}/update_features")
async def resource_update_features(
    request: Request,
    resource_id: int,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("user_id"):
        return {"ok": False, "error": "unauthorized"}
    res = (await db.execute(select(Resource).where(Resource.id == resource_id))).scalar()
    if not res:
        raise HTTPException(status_code=404)
    new_features = {k: v for k, v in (data.get("features") or {}).items() if v is not None and v != ""}
    res.features = new_features
    await db.commit()
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)