import time
import logging
from dataclasses import dataclass
from typing import List, Optional

from ..domain.entities import SearchRequest, SearchResponse, ResourceCriteria, ObjectResult, ResourceResult
from ..adapters.search_repository import SearchRepository

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.propagate = True

@dataclass
class SearchUseCase:
    _repository: SearchRepository

    def execute(self, request: SearchRequest) -> SearchResponse:
        start_time = time.time()
        debug = {}

        logger.info(f"SearchUseCase.execute START")
        logger.info(f"request.object: {request.object}")
        logger.info(f"request.resource: {request.resource}")
        logger.info(f"request.modality_type: {request.modality_type}")

        objects: List[ObjectResult] = []
        object_ids: Optional[List[int]] = None

        if request.object:
            obj_start = time.time()
            objects = self._repository.find_objects_by_criteria(
                request.object, limit=request.limit, offset=request.offset
            )
            debug['objects_query_time'] = time.time() - obj_start
            object_ids = [obj.id for obj in objects] if objects else None
            logger.info(f"Found {len(objects)} objects")
        else:
            logger.info("No object criteria provided, skipping object search")

        resources: List[ResourceResult] = []
        if request.object and not objects:
            debug['resources_query_time'] = 0.0
            debug['resources_skipped'] = True
        else:
            resource_criteria = request.resource if request.resource else ResourceCriteria()
            res_start = time.time()
            resources = self._repository.find_resources_by_criteria(
                resource_criteria, object_ids, limit=request.limit * 2, offset=request.offset
            )
            debug['resources_query_time_raw'] = time.time() - res_start
            
            if request.modality_type:
                filter_start = time.time()
                resources = [r for r in resources if r.modality_type == request.modality_type]
                debug['resources_filter_time'] = time.time() - filter_start
            
            resources = resources[:request.limit]
            debug['resources_query_time'] = debug.get('resources_query_time_raw', 0)
            logger.info(f"Found {len(resources)} resources after modality filter")

        debug['total_time'] = time.time() - start_time

        response = SearchResponse(
            object_criteria=request.object,
            resource_criteria=request.resource,
            modality_filter=request.modality_type,
            objects=objects,
            resources=resources,
        )
        
        if request.debug:
            response.debug_info = debug
            
        return response