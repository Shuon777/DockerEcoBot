# search_api/use_cases/place_search_use_case.py
import logging
from typing import List, Optional, Dict, Any
from ..domain.entities import ObjectResult, ResourceResult
from ..domain.place_entities import PlaceSearchResponse
from ..adapters.search_repository import SearchRepository
from ..services.geo_map_service import GeoMapService
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
        
        region_name = props.get('region', '')
        exact_location = props.get('exact_location', '')
        
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
        
        subtypes = props.get('subtypes', [])
        if subtypes and self._is_cyrillic(subtypes[0]):
            return subtypes[0].capitalize()
        
        db_id = obj.db_id if hasattr(obj, 'db_id') else str(obj.db_id)
        return db_id

    def _is_cyrillic(self, text: str) -> bool:
        if not text:
            return False
        return any('\u0400' <= char <= '\u04FF' for char in text)

    def _is_cyrillic(self, text: str) -> bool:
        return any('\u0400' <= char <= '\u04FF' for char in text)

    def execute(
    self, place_name: str, subtypes: List[str], modality_type: Optional[str] = None,
    buffer_radius_km: float = 10.0, limit: int = 20, offset: int = 0,
    search_type: str = "near"
) -> PlaceSearchResponse:
        logger.info(f"Place search: {place_name}, search_type={search_type}")
        geometry = self._repository.find_place_geometry(place_name)
        if not geometry:
            return PlaceSearchResponse(objects=[], resources=[], used_geometry={}, total_objects=0)
        
        geom_type = geometry.get('type', 'Point')
        effective_search_type = search_type

        if search_type == "inside" and geom_type != 'Polygon' and geom_type != 'MultiPolygon':
                logger.warning(
                    f"Place '{place_name}' has {geom_type} geometry, "
                    f"changing search_type from 'inside' to 'near' with buffer={buffer_radius_km}km"
                )
                effective_search_type = "near"
        objects, _ = self._repository.find_objects_with_geometry_by_subtypes(
            geometry, subtypes, buffer_radius_km, limit, offset, effective_search_type
        )
        
        # остальной код метода без изменений
        obj_results = []
        grouped = {}
        for obj in objects:
            geojson = getattr(obj, '_geometry_geojson', None)
            if not geojson:
                continue
            geojson_key = json.dumps(geojson, sort_keys=True)
            if geojson_key not in grouped:
                grouped[geojson_key] = {"geojson": geojson, "objects": []}
            grouped[geojson_key]["objects"].append(obj)

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
                        if hasattr(syn, 'synonym'):
                            synonyms_list.append(syn.synonym)
                        else:
                            synonyms_list.append(str(syn))
                obj_type_name = o.object_type.name if o.object_type else 'Unknown'
                obj_results.append(ObjectResult(
                    id=o.id, db_id=o.db_id, object_type=obj_type_name,
                    properties=o.object_properties, synonyms=synonyms_list
                ))

        map_name = f"place_{place_name.replace(' ', '_')}"
        map_result = self._geo_service.draw_custom_geometries(map_objects, map_name)
        for obj in obj_results:
            obj.properties['static_map'] = map_result.get('static_map')
            obj.properties['interactive_map'] = map_result.get('interactive_map')

        return PlaceSearchResponse(
            objects=obj_results, resources=[],
            used_geometry=geometry, total_objects=len(obj_results)
        )