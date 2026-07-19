# search_api/use_cases/place_search_use_case.py
import logging
import time
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from ..domain.entities import ObjectResult, ResourceResult, ResourceCriteria, ObjectCriteria, Pagination
from ..domain.place_entities import PlaceSearchResponse
from ..adapters.search_repository import SearchRepository
from ..services.geo_map_service import GeoMapService
from ..infrastructure.database import get_session
import json

logger = logging.getLogger(__name__)

class PlaceSearchUseCase:
    def __init__(self, repository: SearchRepository, geo_service: GeoMapService):
        self._repository = repository
        self._geo_service = geo_service

    def _get_display_name(self, obj) -> str:
        synonyms = []
        if hasattr(obj, 'synonyms') and obj.synonyms:
            for syn in obj.synonyms:
                if hasattr(syn, 'synonym'):
                    synonyms.append(syn.synonym)
                elif isinstance(syn, str):
                    synonyms.append(syn)
                elif isinstance(syn, dict) and 'synonym' in syn:
                    synonyms.append(syn['synonym'])
        props = {}
        if hasattr(obj, 'object_properties') and obj.object_properties:
            props = obj.object_properties
        # Ключи - кириллица, как у db_importer/DialogService (раньше тут были
        # английские region/exact_location, которые никогда не совпадали с реальным
        # JSONB-ключом - см. tasks/normalizaciya_registra_v_katalogah.md).
        region_name = props.get('Географическая зона', '')
        exact_location = props.get('Детальное расположение', '')
        for syn in synonyms:
            if self._is_cyrillic(syn):
                return syn.capitalize()
        if region_name and self._is_cyrillic(region_name):
            return region_name.split(',')[0].capitalize()
        if exact_location and self._is_cyrillic(exact_location):
            parts = exact_location.split(',')
            if parts:
                return parts[0].capitalize()
        if synonyms:
            return synonyms[0].capitalize()
        subtypes = props.get('Подтип объекта', [])
        if subtypes and self._is_cyrillic(subtypes[0]):
            return subtypes[0].capitalize()
        db_id = obj.db_id if hasattr(obj, 'db_id') else str(obj.db_id)
        return db_id

    def _is_cyrillic(self, text: str) -> bool:
        if not text:
            return False
        return any('\u0400' <= char <= '\u04FF' for char in text)

    def _count_objects_with_geometry(
        self, geometry_geojson: Dict[str, Any], subtypes: List[str],
        buffer_radius_km: float, search_type: str = "near",
        object_criteria: Optional[ObjectCriteria] = None
    ) -> int:
        """Подсчитывает общее количество объектов, подходящих под гео-запрос (без LIMIT/OFFSET)."""
        geom_json_str = json.dumps(geometry_geojson)
        buffer_meters = buffer_radius_km * 1000.0

        if search_type == "inside":
            spatial_cond = "ST_Within(gv.geometry, ig.geom)"
        elif search_type == "near":
            spatial_cond = "ST_DWithin(gv.geometry, ig.geom, :buffer)"
        else:
            spatial_cond = "(ST_Within(gv.geometry, ig.geom) OR ST_DWithin(gv.geometry, ig.geom, :buffer))"

        base_conditions = [f"m.modality_type = 'Геоданные'", spatial_cond]
        params = {'geom': geom_json_str, 'buffer': buffer_meters}

        if object_criteria and (object_criteria.object_type or object_criteria.properties or object_criteria.name_synonyms or object_criteria.db_id):
            if object_criteria.object_type:
                base_conditions.append("ot.name = :object_type")
                params['object_type'] = object_criteria.object_type
            if object_criteria.db_id:
                base_conditions.append("o.db_id = :db_id")
                params['db_id'] = object_criteria.db_id
            if object_criteria.properties:
                for key, val in object_criteria.properties.items():
                    param_name = f"prop_{key.replace(' ', '_').replace('-', '_')}"
                    if isinstance(val, str):
                        base_conditions.append(f"o.object_properties->>'{key}' = :{param_name}")
                        params[param_name] = val
                    elif isinstance(val, list):
                        items = "', '".join(val)
                        base_conditions.append(f"o.object_properties->'{key}' ?| ARRAY['{items}']")
        else:
            base_conditions.append(
                "(o.object_properties->>'Подтип объекта' = ANY(:subtypes) "
                "OR o.object_properties->'Подтип объекта' ?| :subtypes)"
            )
            params['subtypes'] = subtypes

        where_clause = " AND ".join(base_conditions)

        sql = text(f"""
            WITH input_geom AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326) AS geom)
            SELECT COUNT(DISTINCT o.id) as total
            FROM eco_assistant.object o
            JOIN eco_assistant.object_type ot ON o.object_type_id = ot.id
            JOIN eco_assistant.resource_object ro ON o.id = ro.object_id
            JOIN eco_assistant.resource_value rv ON ro.resource_id = rv.resource_id
            JOIN eco_assistant.modality m ON rv.modality_id = m.id
            JOIN eco_assistant.geodata_value gv ON rv.value_id = gv.id
            CROSS JOIN input_geom ig
            WHERE {where_clause}
        """)

        session = get_session()
        with session:
            row = session.execute(sql, params).first()
            return row.total if row else 0

    def execute(
        self, place_name: str, subtypes: List[str], modality_type: Optional[str] = None,
        buffer_radius_km: float = 10.0, limit: int = 20, offset: int = 0,
        search_type: str = "near", object_criteria: Optional[ObjectCriteria] = None
    ) -> PlaceSearchResponse:
        total_start = time.time()
        logger.info(f"Place search start: {place_name}, search_type={search_type}")

        geom_start = time.time()
        geometry = self._repository.find_place_geometry(place_name)
        geom_time = time.time() - geom_start
        if not geometry:
            return PlaceSearchResponse(objects=[], resources=[], used_geometry={}, total_objects=0)

        geom_type = geometry.get('type', 'Point')
        effective_search_type = search_type
        if search_type == "inside" and geom_type not in ('Polygon', 'MultiPolygon'):
            effective_search_type = "near"

        # Получаем общее количество объектов (до LIMIT/OFFSET)
        total_objects = self._count_objects_with_geometry(
            geometry, subtypes, buffer_radius_km, effective_search_type, object_criteria
        )

        objects_search_start = time.time()
        if object_criteria and (object_criteria.object_type or object_criteria.properties or object_criteria.name_synonyms or object_criteria.db_id):
            objects, object_ids = self._repository.find_objects_with_geometry_by_criteria(
                geometry, object_criteria, buffer_radius_km, limit, offset, effective_search_type
            )
        else:
            objects, object_ids = self._repository.find_objects_with_geometry_by_subtypes(
                geometry, subtypes, buffer_radius_km, limit, offset, effective_search_type
            )
        objects_search_time = time.time() - objects_search_start

        grouping_start = time.time()
        obj_results = []
        grouped = {}
        all_object_ids = []
        for obj in objects:
            all_object_ids.append(obj.id)
            geojson = getattr(obj, '_geometry_geojson', None)
            if not geojson:
                continue
            key = json.dumps(geojson, sort_keys=True)
            if key not in grouped:
                grouped[key] = {"geojson": geojson, "objects": []}
            grouped[key]["objects"].append(obj)

        map_objects = []
        for group in grouped.values():
            objs = group["objects"]
            display_names = [self._get_display_name(o) for o in objs]
            popup_text = "<br>".join(display_names[:15])
            if len(display_names) > 15:
                popup_text += f"<br>... и ещё {len(display_names)-15}"
            map_objects.append({
                "geojson": group["geojson"],
                "tooltip": f"{len(objs)} объектов",
                "popup": popup_text,
                "name": display_names[0]
            })
            for o in objs:
                synonyms_list = []
                if hasattr(o, 'synonyms'):
                    for syn in o.synonyms:
                        synonyms_list.append(syn.synonym if hasattr(syn, 'synonym') else str(syn))
                obj_type_name = o.object_type.name if o.object_type else 'Unknown'
                obj_results.append(ObjectResult(
                    id=o.id, db_id=o.db_id, object_type=obj_type_name,
                    properties=o.object_properties, synonyms=synonyms_list
                ))
        grouping_time = time.time() - grouping_start

        resources = []
        if all_object_ids:
            resources_start = time.time()
            resource_criteria = ResourceCriteria(modality_type=modality_type)
            resources, _ = self._repository.find_resources_by_criteria(
                resource_criteria, all_object_ids, limit=limit, offset=offset
            )
            resources_time = time.time() - resources_start
            logger.info(f"Resources query took {resources_time:.4f}s, found {len(resources)}")

        filtered_resources = []
        for r in resources:
            if r.modality_type == "Геоданные":
                if isinstance(r.content, dict) and 'geojson' in r.content:
                    content_without_geojson = {
                        'map_links': r.content.get('map_links', {})
                    }
                    if 'geometry_type' in r.content:
                        content_without_geojson['geometry_type'] = r.content['geometry_type']
                    r.content = content_without_geojson
            filtered_resources.append(r)

        map_name = f"place_{place_name.replace(' ', '_')}"
        draw_start = time.time()
        map_result = self._geo_service.draw_custom_geometries(map_objects, map_name)
        draw_time = time.time() - draw_start

        geo_resource = ResourceResult(
            id=-1,
            title=f"Карта объектов: {place_name}",
            uri=None,
            author=None,
            source=None,
            modality_type="Геоданные",
            content={
                "map_links": {
                    "static": map_result.get("static_map"),
                    "interactive": map_result.get("interactive_map")
                }
            },
            features=None,
            resource_type="Динамически вычисляемый",
            external_id=None
        )

        all_resources = [geo_resource] + filtered_resources

        # Вычисляем пагинацию
        next_offset = offset + limit
        has_more = next_offset < total_objects
        pagination = Pagination(
            total=total_objects,
            limit=limit,
            offset=offset,
            next_offset=next_offset,
            has_more=has_more
        )

        total_time = time.time() - total_start
        logger.info(f"Place search total time: {total_time:.4f}s")

        return PlaceSearchResponse(
            objects=obj_results,
            resources=all_resources,
            used_geometry=geometry,
            total_objects=total_objects,
            pagination=pagination,
        )