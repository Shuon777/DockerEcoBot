from .search import search_bp
from .place_search import place_search_bp

all_blueprints = [
    search_bp,
    place_search_bp,
]

__all__ = ['all_blueprints', 'search_bp', 'place_search_bp']
