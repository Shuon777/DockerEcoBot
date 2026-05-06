# search_api/routes/place_search.py
import logging
from flask import Blueprint, request, jsonify, current_app
from ..use_cases.place_search_use_case import PlaceSearchUseCase
from ..adapters.sqlalchemy_repository import SQLAlchemySearchRepository
from ..infrastructure.database import get_session
from ..services.geo_map_service import GeoMapService

place_search_bp = Blueprint('place_search', __name__, url_prefix='/search')
logger = logging.getLogger(__name__)

def _get_repository():
    return SQLAlchemySearchRepository(get_session)

@place_search_bp.route('/place/objects', methods=['POST'])
def search_objects_near_place():
    data = request.get_json() or {}
    place_name = data.get('place_name')
    if not place_name:
        return jsonify({'error': 'place_name is required'}), 400

    subtypes = data.get('subtypes', ['Достопримечательности'])
    modality_type = data.get('modality_type')
    buffer_radius_km = data.get('buffer_radius_km', 10.0)
    limit = data.get('limit', 20)
    offset = data.get('offset', 0)

    config = current_app.config.get('SEARCH_CONFIG')
    geo_service = GeoMapService(config.maps_dir, config.domain)
    use_case = PlaceSearchUseCase(_get_repository(), geo_service)
    result = use_case.execute(
        place_name=place_name, subtypes=subtypes,
        modality_type=modality_type, buffer_radius_km=buffer_radius_km,
        limit=limit, offset=offset
    )

    return jsonify({
        'place_name': place_name,
        'used_geometry': result.used_geometry,
        'total_objects': result.total_objects,
        'objects': [{
            'id': o.id, 'db_id': o.db_id, 'type': o.object_type,
            'properties': o.properties, 'synonyms': o.synonyms
        } for o in result.objects],
        'resources': [{'id': r.id, 'title': r.title, 'uri': r.uri} for r in result.resources]
    }), 200