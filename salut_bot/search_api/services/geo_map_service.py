import os
from typing import Dict, Any, List, Tuple

import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import contextily as ctx
from shapely.geometry import shape, GeometryCollection, mapping
from shapely.geometry import shape, GeometryCollection, mapping
from shapely.geometry.base import BaseGeometry
from typing import Tuple
from ..domain.value_objects import GeoContent, MapLinks


class GeoMapService:
    def __init__(self, maps_dir: str, domain: str):
        self.maps_dir = maps_dir
        self.domain = domain
        os.makedirs(maps_dir, exist_ok=True)
        ctx.user_agent = "YourAppName/1.0 (your-email@example.com)"

    def generate_static_map(self, geojson: Dict[str, Any], name: str) -> str:
        geom = shape(geojson)
        static_url, _ = self._draw_geometry(geom, name)
        return static_url

    def enrich_geo_content(self, geojson: Dict[str, Any], name: str) -> GeoContent:
        static_url = self.generate_static_map(geojson, name)
        interactive_url = self.generate_interactive_map(geojson, name)
        geom = shape(geojson)
        return GeoContent(
            geojson=geojson,
            geometry_type=geom.geom_type,
            map_links=MapLinks(static=static_url, interactive=interactive_url)
        )

    def _draw_geometry(self, geometry: BaseGeometry, name: str) -> Tuple[str, str]:
        if isinstance(geometry, GeometryCollection):
            geometries = list(geometry.geoms)
        else:
            geometries = [geometry]
        gdf = gpd.GeoDataFrame([{"geometry": g} for g in geometries], crs="EPSG:4326").to_crs(epsg=3857)
        fig, ax = plt.subplots(figsize=(10, 10), dpi=500)
        for idx, row in gdf.iterrows():
            geom = row.geometry
            if geom.geom_type == "Point":
                gpd.GeoDataFrame([row], crs=gdf.crs).plot(ax=ax, marker='o', markersize=80, color='red', edgecolor='darkred', linewidth=1.5, alpha=0.7, zorder=10)
            else:
                gpd.GeoDataFrame([row], crs=gdf.crs).plot(ax=ax, facecolor='white', edgecolor='darkblue', linewidth=2, alpha=0.5, zorder=5)
        if geometries:
            bounds = gdf.total_bounds
            buffer = max(3000, (bounds[2] - bounds[0]) * 0.1)
            ax.set_xlim(bounds[0] - buffer, bounds[2] + buffer)
            ax.set_ylim(bounds[1] - buffer, bounds[3] + buffer)
        self._add_basemap(ax)
        ax.axis('off')
        filename = f"{name}.jpeg"
        filepath = os.path.join(self.maps_dir, filename)
        plt.savefig(filepath, format='jpeg', dpi=500, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        return f"{self.domain}/maps/{filename}", None
    
    def _add_basemap(self, ax: plt.Axes) -> None:
        for source in [
            ctx.providers.Esri.WorldImagery,
            ctx.providers.CartoDB.Positron,
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Physical_Map/MapServer/tile/{z}/{y}/{x}",
            ctx.providers.OpenStreetMap.Mapnik,
        ]:
            try:
                ctx.add_basemap(ax, source=source)
                return
            except Exception:
                continue

    def generate_interactive_map(self, geojson: Dict[str, Any], name: str) -> str:
        geom = shape(geojson)
        centroid = geom.centroid
        m = folium.Map(location=[centroid.y, centroid.x], zoom_start=9,
                    tiles='OpenStreetMap', attributionControl=True, 
        tiles_kwds={
            'headers': {
                'Referer': self.domain,
                'User-Agent': 'YourAppName/1.0'
            }
        })
        folium.GeoJson(mapping(geom), tooltip=name, name=name).add_to(m)
        filename = f"webapp_{name}.html"
        filepath = os.path.join(self.maps_dir, filename)
        m.save(filepath)
        return f"{self.domain}/maps/{filename}"

    def draw_custom_geometries(self, objects: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
        if not objects:
            return {"status": "error", "message": "Нет объектов для отрисовки"}
        geometries = []
        tooltips = []
        popups = []
        for obj in objects:
            geojson = obj.get("geojson")
            if not geojson:
                continue
            geom = shape(geojson)
            geometries.append(geom)
            tooltips.append(obj.get("tooltip", obj.get("name", "Без имени")))
            popups.append(obj.get("popup", obj.get("name", "Без имени")))
        if not geometries:
            return {"status": "error", "message": "Нет валидных геометрий"}
        combined = GeometryCollection(geometries)
        static_map, _ = self._draw_geometry(combined, name)
        centroid = combined.centroid
        m = folium.Map(location=[centroid.y, centroid.x], zoom_start=9,
                    tiles='OpenStreetMap', attributionControl=False)
        for geom, tooltip_text, popup_html in zip(geometries, tooltips, popups):
            folium.GeoJson(mapping(geom), tooltip=tooltip_text,
                        popup=folium.Popup(popup_html, max_width=400)).add_to(m)
        filename_html = f"webapp_{name}.html"
        filepath_html = os.path.join(self.maps_dir, filename_html)
        m.save(filepath_html)
        interactive_map_url = f"{self.domain}/maps/{filename_html}"
        return {"static_map": static_map, "interactive_map": interactive_map_url}
