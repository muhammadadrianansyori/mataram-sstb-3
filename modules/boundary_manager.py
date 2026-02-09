"""
Boundary Manager Module - Handle Administrative Boundaries
Manages loading, caching, and querying of GeoJSON boundary data
"""

import geopandas as gpd
import json
from typing import List, Dict, Optional
from shapely.geometry import Point, shape
import functools

class BoundaryManager:
    """
    Manages administrative boundary data from GeoJSON
    Provides spatial filtering and querying capabilities
    """
    
    def __init__(self, geojson_path: str):
        self.geojson_path = geojson_path
        self._gdf = None
        self._load_boundaries()
    
    def _load_boundaries(self):
        try:
            from modules.boundary_cache import load_boundaries_cached
            self._gdf = load_boundaries_cached(self.geojson_path)
        except Exception as e:
            print(f"❌ Error loading boundaries: {e}")
            self._gdf = None
    
    def get_boundaries_by_district(self, district_name: str) -> List[Dict]:
        if self._gdf is None: return []
        
        district_map = {
            'Ampenan': 'AMPENAN', 'Cakranegara': 'CAKRANEGARA', 'Mataram': 'MATARAM',
            'Selaparang': 'SELAPARANG', 'Sekarbela': 'SEKARBELA', 'Sandubaya': 'SANDUBAYA'
        }
        kecamatan_name = district_map.get(district_name, district_name.upper())
        filtered = self._gdf[self._gdf['nmkec'] == kecamatan_name]
        
        features = []
        for idx, row in filtered.iterrows():
            feature = {
                'type': 'Feature',
                'properties': {
                    'nmkec': row['nmkec'], 'nmdesa': row['nmdesa'],
                    'nmsls': row['nmsls'], 'kdkec': row['kdkec'], 'kddesa': row['kddesa']
                },
                'geometry': json.loads(gpd.GeoSeries([row['geometry']]).to_json())['features'][0]['geometry']
            }
            features.append(feature)
        return features
    
    def get_kelurahan_list(self, district_name: str) -> List[str]:
        if self._gdf is None: return []
        district_map = {'Ampenan': 'AMPENAN', 'Cakranegara': 'CAKRANEGARA', 'Mataram': 'MATARAM', 
                        'Selaparang': 'SELAPARANG', 'Sekarbela': 'SEKARBELA', 'Sandubaya': 'SANDUBAYA'}
        kecamatan_name = district_map.get(district_name, district_name.upper())
        filtered = self._gdf[self._gdf['nmkec'] == kecamatan_name]
        return sorted(filtered['nmdesa'].unique().tolist())
    
    def get_lingkungan_list(self, district_name: str, kelurahan_names: List[str] = None) -> List[str]:
        if self._gdf is None: return []
        district_map = {'Ampenan': 'AMPENAN', 'Cakranegara': 'CAKRANEGARA', 'Mataram': 'MATARAM', 
                        'Selaparang': 'SELAPARANG', 'Sekarbela': 'SEKARBELA', 'Sandubaya': 'SANDUBAYA'}
        kecamatan_name = district_map.get(district_name, district_name.upper())
        df = self._gdf[self._gdf['nmkec'] == kecamatan_name]
        if kelurahan_names:
            df = df[df['nmdesa'].isin(kelurahan_names)]
            
        lingkungan_set = set()
        for nmsls in df['nmsls']:
            if 'LINGKUNGAN' in nmsls:
                parts = nmsls.split(' LINGKUNGAN ')
                if len(parts) > 1: lingkungan_set.add(parts[1].strip())
            else:
                lingkungan_set.add(nmsls.strip())
        return sorted(list(lingkungan_set))

    def get_rt_list(self, district_name: str, kelurahan_names: List[str], lingkungan_names: List[str]) -> List[str]:
        if self._gdf is None: return []
        district_map = {'Ampenan': 'AMPENAN', 'Cakranegara': 'CAKRANEGARA', 'Mataram': 'MATARAM', 
                        'Selaparang': 'SELAPARANG', 'Sekarbela': 'SEKARBELA', 'Sandubaya': 'SANDUBAYA'}
        kecamatan_name = district_map.get(district_name, district_name.upper())
        df = self._gdf[(self._gdf['nmkec'] == kecamatan_name) & (self._gdf['nmdesa'].isin(kelurahan_names))]
        
        rt_set = set()
        for nmsls in df['nmsls']:
            current_lingkungan = nmsls.split(' LINGKUNGAN ')[1].strip() if ' LINGKUNGAN ' in nmsls else nmsls.strip()
            current_rt = nmsls.split(' LINGKUNGAN ')[0].strip() if ' LINGKUNGAN ' in nmsls else nmsls.strip()
            if current_lingkungan in lingkungan_names:
                rt_set.add(current_rt)
        return sorted(list(rt_set))

    def get_all_sls_in_district(self, district_name: str) -> List[str]:
        """Metode baru untuk pencarian global"""
        if self._gdf is None: return []
        district_map = {'Ampenan': 'AMPENAN', 'Cakranegara': 'CAKRANEGARA', 'Mataram': 'MATARAM', 
                        'Selaparang': 'SELAPARANG', 'Sekarbela': 'SEKARBELA', 'Sandubaya': 'SANDUBAYA'}
        kecamatan_name = district_map.get(district_name, district_name.upper())
        df = self._gdf[self._gdf['nmkec'] == kecamatan_name]
        return sorted(df['nmsls'].unique().tolist())

    def get_parent_info_by_sls(self, sls_name: str, district_name: str) -> Dict[str, str]:
        """Metode baru untuk sinkronisasi otomatis filter"""
        if self._gdf is None: return {}
        district_map = {'Ampenan': 'AMPENAN', 'Cakranegara': 'CAKRANEGARA', 'Mataram': 'MATARAM'}
        kec_name = district_map.get(district_name, district_name.upper())
        match = self._gdf[(self._gdf['nmsls'] == sls_name) & (self._gdf['nmkec'] == kec_name)]
        if not match.empty:
            row = match.iloc[0]
            ling = sls_name.split(' LINGKUNGAN ')[1].strip() if ' LINGKUNGAN ' in sls_name else sls_name.strip()
            return {'kelurahan': row['nmdesa'], 'lingkungan': ling}
        return {}

    def spatial_filter(self, detections: List[Dict], district_name: str, kelurahan_names: List[str] = None, lingkungan_names: List[str] = None, rt_names: List[str] = None) -> List[Dict]:
        if self._gdf is None: return detections
        if kelurahan_names and len(kelurahan_names) > 0:
            filtered_gdf = self._gdf[self._gdf['nmdesa'].isin(kelurahan_names)]
        else:
            district_map = {'Ampenan': 'AMPENAN', 'Mataram': 'MATARAM', 'Cakranegara': 'CAKRANEGARA'}
            kecamatan_name = district_map.get(district_name, district_name.upper())
            filtered_gdf = self._gdf[self._gdf['nmkec'] == kecamatan_name]
        
        if lingkungan_names:
            pattern_lingkungan = '|'.join([f"LINGKUNGAN {x}$|^{x}$" for x in lingkungan_names])
            filtered_gdf = filtered_gdf[filtered_gdf['nmsls'].str.contains(pattern_lingkungan, regex=True, na=False)]
            if rt_names:
                pattern_rt = '|'.join([f"^{x} LINGKUNGAN|^{x}$" for x in rt_names])
                filtered_gdf = filtered_gdf[filtered_gdf['nmsls'].str.contains(pattern_rt, regex=True, na=False)]
        
        if filtered_gdf.empty: return []
        merged_boundary = filtered_gdf.geometry.unary_union
        
        filtered_detections = []
        for det in detections:
            if merged_boundary.contains(Point(det['lon'], det['lat'])): filtered_detections.append(det)
        return filtered_detections
