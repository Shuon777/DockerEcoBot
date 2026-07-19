import pytest
from unittest.mock import Mock
from datetime import datetime
from search_api.use_cases import SearchUseCase, SearchAndBuildUseCase
from search_api.domain.entities import (
    SearchRequest, ObjectCriteria, ResourceCriteria,
    ObjectResult, ResourceResult, SearchResponse
)
from search_api.services.response_builder import ResponseBuilder

class TestSearchUseCase:
    def test_execute_with_object_only(self):
        repo = Mock()
        use_case = SearchUseCase(repo)
        
        object_criteria = ObjectCriteria(db_id='test_001')
        request = SearchRequest(object=object_criteria, debug=True)
        
        expected_objects = [
            ObjectResult(id=1, db_id='test_001', object_type='Test', properties={}, synonyms=[])
        ]
        repo.find_objects_by_criteria.return_value = (expected_objects, 1)
        repo.find_resources_by_criteria.return_value = ([], 0)
        
        response = use_case.execute(request)
        
        assert response.objects == expected_objects
        assert response.total_objects == 1
        assert response.pagination is not None
        assert response.pagination.total == 1
        assert response.pagination.has_more is False
        assert response.debug_info is not None
        repo.find_objects_by_criteria.assert_called_once_with(object_criteria, limit=20, offset=0)

    def test_execute_with_resource_only(self):
        repo = Mock()
        use_case = SearchUseCase(repo)
        
        resource_criteria = ResourceCriteria(title='Test Resource')
        request = SearchRequest(resource=resource_criteria)
        
        expected_resources = [
            ResourceResult(id=1, title='Test Resource', uri=None, author=None, source=None, modality_type='Текст', content={})
        ]
        repo.find_objects_by_criteria.return_value = ([], 0)
        repo.find_resources_by_criteria.return_value = (expected_resources, 1)
        
        response = use_case.execute(request)
        
        assert response.resources == expected_resources
        assert response.total_resources == 1
        # Без object criteria пагинация не вычисляется
        assert response.pagination is None
        repo.find_resources_by_criteria.assert_called_once()

    def test_execute_with_object_and_resource(self):
        repo = Mock()
        use_case = SearchUseCase(repo)
        
        object_criteria = ObjectCriteria(db_id='test_001')
        resource_criteria = ResourceCriteria(title='Test')
        request = SearchRequest(object=object_criteria, resource=resource_criteria)
        
        expected_objects = [ObjectResult(id=1, db_id='test_001', object_type='Test', properties={}, synonyms=[])]
        expected_resources = [ResourceResult(id=1, title='Test', uri=None, author=None, source=None, modality_type='Текст', content={})]
        
        repo.find_objects_by_criteria.return_value = (expected_objects, 1)
        repo.find_resources_by_criteria.return_value = (expected_resources, 1)
        
        response = use_case.execute(request)
        
        assert response.objects == expected_objects
        assert response.resources == expected_resources
        assert response.pagination is not None
        assert response.pagination.total == 1

    def test_execute_with_pagination_has_more(self):
        repo = Mock()
        use_case = SearchUseCase(repo)
        
        object_criteria = ObjectCriteria(db_id='test_001')
        request = SearchRequest(object=object_criteria, limit=5, offset=0)
        
        expected_objects = [ObjectResult(id=i, db_id=f'test_{i}', object_type='Test', properties={}, synonyms=[]) for i in range(5)]
        repo.find_objects_by_criteria.return_value = (expected_objects, 45)
        repo.find_resources_by_criteria.return_value = ([], 0)
        
        response = use_case.execute(request)
        
        assert response.pagination is not None
        assert response.pagination.total == 45
        assert response.pagination.limit == 5
        assert response.pagination.offset == 0
        assert response.pagination.next_offset == 5
        assert response.pagination.has_more is True

    def test_execute_with_pagination_last_page(self):
        repo = Mock()
        use_case = SearchUseCase(repo)
        
        object_criteria = ObjectCriteria(db_id='test_001')
        request = SearchRequest(object=object_criteria, limit=10, offset=40)
        
        expected_objects = [ObjectResult(id=i, db_id=f'test_{i}', object_type='Test', properties={}, synonyms=[]) for i in range(5)]
        repo.find_objects_by_criteria.return_value = (expected_objects, 45)
        repo.find_resources_by_criteria.return_value = ([], 0)
        
        response = use_case.execute(request)
        
        assert response.pagination is not None
        assert response.pagination.total == 45
        assert response.pagination.next_offset == 50
        assert response.pagination.has_more is False

class TestSearchAndBuildUseCase:
    def test_execute_with_cache_miss(self, mock_redis):
        search_use_case = Mock()
        response_builder = Mock()
        
        use_case = SearchAndBuildUseCase(search_use_case, response_builder, mock_redis)
        
        request = SearchRequest(user_query='test', use_llm_answer=True)
        search_response = SearchResponse(
            object_criteria=None,
            resource_criteria=None,
            modality_filter=None,
            objects=[],
            resources=[]
        )
        search_use_case.execute.return_value = search_response
        response_builder.build.return_value = {'result': 'success'}
        
        result = use_case.execute(request)
        
        assert result == {'result': 'success'}
        search_use_case.execute.assert_called_once_with(request)
        mock_redis.set.assert_called_once()

    def test_execute_with_cache_hit(self, mock_redis):
        search_use_case = Mock()
        response_builder = Mock()
        
        cached_result = {'cached': 'result'}
        mock_redis.get.return_value = (True, cached_result)
        
        use_case = SearchAndBuildUseCase(search_use_case, response_builder, mock_redis)
        
        request = SearchRequest()
        result = use_case.execute(request)
        
        assert result == cached_result
        search_use_case.execute.assert_not_called()