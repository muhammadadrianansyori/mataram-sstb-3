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
        """
        Initialize boundary manager with GeoJSON file
        
        Args:
            geojson_path: Path to GeoJSON file containing boundaries
        """
        self.geojson_path = geojson_path
        self._gdf = None
        self._load_boundaries()
    
    def _load_boundaries(self):
        """Load GeoJSON data into GeoDataFrame with caching"""
        try:
            from modules.boundary_cache import load_boundaries_cached
            self._gdf = load_boundaries_cached(self.geojson_path)
            if self._gdf is not None:
                print(f"✅ Loaded {len(self._gdf)} boundary features (Cached)")
        except Exception as e:
            print(f"❌ Error loading boundaries: {e}")
            self._gdf = None
    
    def get_boundaries_by_district(self, district_name: str) -> List[Dict]:
        """
        Get all boundaries for a specific district (kecamatan)
        
        Args:
            district_name: Name of district (e.g., 'Ampenan')
        
        Returns:
            List of boundary features as GeoJSON-like dicts
        """
        if self._gdf is None:
            return []
        
        # Map district names to kecamatan codes
        district_map = {
            'Ampenan': 'AMPENAN',
            'Cakranegara': 'CAKRANEGARA',
            'Mataram': 'MATARAM',
            'Selaparang': 'SELAPARANG',
            'Sekarbela': 'SEKARBELA',
            'Sandubaya': 'SANDUBAYA'
        }
        
        kecamatan_name = district_map.get(district_name, district_name.upper())
        
        # Filter by kecamatan
        filtered = self._gdf[self._gdf['nmkec'] == kecamatan_name]
        
        # Convert to GeoJSON-like format
        features = []
        for idx, row in filtered.iterrows():
            feature = {
                'type': 'Feature',
                'properties': {
                    'nmkec': row['nmkec'],
                    'nmdesa': row['nmdesa'],
                    'nmsls': row['nmsls'],
                    'kdkec': row['kdkec'],
                    'kddesa': row['kddesa']
                },
                'geometry': json.loads(gpd.GeoSeries([row['geometry']]).to_json())['features'][0]['geometry']
            }
            features.append(feature)
        
        return features
    
    def get_kelurahan_list(self, district_name: str) -> List[str]:
        """
        Get list of kelurahan names for a district
        
        Args:
            district_name: Name of district
        
        Returns:
            List of unique kelurahan names
        """
        if self._gdf is None:
            return []
        
        district_map = {
            'Ampenan': 'AMPENAN',
            'Cakranegara': 'CAKRANEGARA',
            'Mataram': 'MATARAM',
            'Selaparang': 'SELAPARANG',
            'Sekarbela': 'SEKARBELA',
            'Sandubaya': 'SANDUBAYA'
        }
        
        kecamatan_name = district_map.get(district_name, district_name.upper())
        filtered = self._gdf[self._gdf['nmkec'] == kecamatan_name]
        
        # Get unique kelurahan names
        kelurahan_list = sorted(filtered['nmdesa'].unique().tolist())
        return kelurahan_list
    
    def get_boundary_by_kelurahan(self, kelurahan_name: str) -> Optional[Dict]:
        """
        Get boundary for a specific kelurahan
        
        Args:
            kelurahan_name: Name of kelurahan
        
        Returns:
            Boundary feature as GeoJSON-like dict or None
        """
        if self._gdf is None:
            return None
        
        filtered = self._gdf[self._gdf['nmdesa'] == kelurahan_name]
        
        if len(filtered) == 0:
            return None
        
        # Merge all polygons for this kelurahan
        merged_geom = filtered.geometry.unary_union
        
        feature = {
            'type': 'Feature',
            'properties': {
                'nmdesa': kelurahan_name
            },
            'geometry': json.loads(gpd.GeoSeries([merged_geom]).to_json())['features'][0]['geometry']
        }
        
        return feature
    
    def get_lingkungan_list(self, district_name: str, kelurahan_names: List[str] = None) -> List[str]:
        """
        Get unique 'Lingkungan' names from nmsls field
        
        Args:
            district_name: Name of district
            kelurahan_names: Optional list of kelurahan names to filter by
            
        Returns:
            List of unique Lingkungan names
        """
        if self._gdf is None:
            return []
            
        # Filter by district first
        district_map = {
            'Ampenan': 'AMPENAN',
            'Cakranegara': 'CAKRANEGARA',
            'Mataram': 'MATARAM',
            'Selaparang': 'SELAPARANG',
            'Sekarbela': 'SEKARBELA',
            'Sandubaya': 'SANDUBAYA'
        }
        kecamatan_name = district_map.get(district_name, district_name.upper())
        df = self._gdf[self._gdf['nmkec'] == kecamatan_name]
        
        # Filter by kelurahan if provided
        if kelurahan_names:
            df = df[df['nmdesa'].isin(kelurahan_names)]
            
        # Parse Lingkungan from nmsls
        lingkungan_set = set()
        for nmsls in df['nmsls']:
            if 'LINGKUNGAN' in nmsls:
                # Format: "RT 001 LINGKUNGAN NAME" -> "NAME"
                parts = nmsls.split(' LINGKUNGAN ')
                if len(parts) > 1:
                    lingkungan_set.add(parts[1].strip())
            else:
                # Fallback for non-standard names (e.g. "SAWAH")
                lingkungan_set.add(nmsls.strip())
                
        return sorted(list(lingkungan_set))

    def get_rt_list(self, district_name: str, kelurahan_names: List[str], lingkungan_names: List[str]) -> List[str]:
        """
        Get unique RT names from nmsls field based on selected Lingkungan
        
        Args:
            district_name: Name of district
            kelurahan_names: List of kelurahan names
            lingkungan_names: List of lingkungan names
            
        Returns:
            List of unique RT names (e.g., "RT 001")
        """
        if self._gdf is None:
            return []
            
        # Base filter by district and kelurahan (mandatory for RT context)
        district_map = {
            'Ampenan': 'AMPENAN',
            'Cakranegara': 'CAKRANEGARA',
            'Mataram': 'MATARAM',
            'Selaparang': 'SELAPARANG',
            'Sekarbela': 'SEKARBELA',
            'Sandubaya': 'SANDUBAYA'
        }
        kecamatan_name = district_map.get(district_name, district_name.upper())
        df = self._gdf[
            (self._gdf['nmkec'] == kecamatan_name) & 
            (self._gdf['nmdesa'].isin(kelurahan_names))
        ]
        
        rt_set = set()
        for nmsls in df['nmsls']:
            # Check if this nmsls belongs to any selected Lingkungan
            is_match = False
            current_lingkungan = ""
            current_rt = ""
            
            if 'LINGKUNGAN' in nmsls:
                parts = nmsls.split(' LINGKUNGAN ')
                if len(parts) > 1:
                    current_rt = parts[0].strip()
                    current_lingkungan = parts[1].strip()
            else:
                current_lingkungan = nmsls.strip()
                current_rt = nmsls.strip() # For 'SAWAH', RT is also 'SAWAH'
            
            if current_lingkungan in lingkungan_names:
                rt_set.add(current_rt)
                
        return sorted(list(rt_set))

    def get_all_sls_in_district(self, district_name: str) -> List[str]:
        """Get all SLS (RT/Lingkungan names) in a district for global search"""
        if self._gdf is None: return []
        
        district_map = {'Ampenan': 'AMPENAN', 'Cakranegara': 'CAKRANEGARA', 'Mataram': 'MATARAM', 
                        'Selaparang': 'SELAPARANG', 'Sekarbela': 'SEKARBELA', 'Sandubaya': 'SANDUBAYA'}
        kecamatan_name = district_map.get(district_name, district_name.upper())
        df = self._gdf[self._gdf['nmkec'] == kecamatan_name]
        
        # Result combined list of nmsls
        return sorted(df['nmsls'].unique().tolist())

    def get_parent_info_by_sls(self, sls_name: str, district_name: str) -> Dict[str, str]:
        """Find Kelurahan and Lingkungan for a given SLS name"""
        if self._gdf is None: return {}
        
        # Filter by SLS and District
        district_map = {'Ampenan': 'AMPENAN', 'Cakranegara': 'CAKRANEGARA', 'Mataram': 'MATARAM', 
                        'Selaparang': 'SELAPARANG', 'Sekarbela': 'SEKARBELA', 'Sandubaya': 'SANDUBAYA'}
        kec_name = district_map.get(district_name, district_name.upper())
        
        match = self._gdf[(self._gdf['nmsls'] == sls_name) & (self._gdf['nmkec'] == kec_name)]
        if len(match) > 0:
            row = match.iloc[0]
            kel = row['nmdesa']
            ling = ""
            if 'LINGKUNGAN' in sls_name:
                parts = sls_name.split(' LINGKUNGAN ')
                if len(parts) > 1: ling = parts[1].strip()
            else:
                ling = sls_name.strip()
            
            return {'kelurahan': kel, 'lingkungan': ling}
        return {}

    def spatial_filter(self, detections: List[Dict], district_name: str, kelurahan_names: List[str] = None, lingkungan_names: List[str] = None, rt_names: List[str] = None) -> List[Dict]:
        """
        Filter detections with granular control (District -> Kelurahan -> Lingkungan -> RT)
        """
        if self._gdf is None:
            return detections
            
        # Start filtering GeoDataFrame
        if kelurahan_names and len(kelurahan_names) > 0:
            filtered_gdf = self._gdf[self._gdf['nmdesa'].isin(kelurahan_names)]
        else:
            # If no kelurahan selected, filter by district
            district_map = {
                'Ampenan': 'AMPENAN',
                'Cakranegara': 'CAKRANEGARA',
                'Mataram': 'MATARAM',
                'Selaparang': 'SELAPARANG',
                'Sekarbela': 'SEKARBELA',
                'Sandubaya': 'SANDUBAYA'
            }
            kecamatan_name = district_map.get(district_name, district_name.upper())
            filtered_gdf = self._gdf[self._gdf['nmkec'] == kecamatan_name]
        
        # Apply Lingkungan/RT filters if present
        if lingkungan_names:
            # We need to filter rows where nmsls contains the environment name
            # Since strict equality won't work for "RT 001 LINGKUNGAN X", we construct a somewhat complex filter or iterate
            
            # Efficient approach: Filter by string matching
            # Pattern: " LINGKUNGAN {name}$" OR equals "{name}"
            pattern_lingkungan = '|'.join([f"LINGKUNGAN {x}$|^{x}$" for x in lingkungan_names])
            filtered_gdf = filtered_gdf[filtered_gdf['nmsls'].str.contains(pattern_lingkungan, regex=True, na=False)]
            
            if rt_names:
                # Further refine by RT part
                # Pattern: "^{rt} LINGKUNGAN" OR "^{rt}$"
                pattern_rt = '|'.join([f"^{x} LINGKUNGAN|^{x}$" for x in rt_names])
                filtered_gdf = filtered_gdf[filtered_gdf['nmsls'].str.contains(pattern_rt, regex=True, na=False)]
        
        if len(filtered_gdf) == 0:
            return []
        
        # Merge boundaries
        # Use simple unary_union. For high complexity polygons this might be slow, but for local filtering it's acceptable.
        try:
            merged_boundary = filtered_gdf.geometry.unary_union
        except:
             # Fallback if union fails (rare)
            return []
        
        # Filter detections
        filtered_detections = []
        for detection in detections:
            try:
                point = Point(detection['lon'], detection['lat'])
                if merged_boundary.contains(point):
                    filtered_detections.append(detection)
            except:
                filtered_detections.append(detection)
        
        return filtered_detections
    
    def get_boundary_geojson(self, district_name: str) -> Dict:
        """
        Get boundaries as complete GeoJSON FeatureCollection
        
        Args:
            district_name: Name of district
        
        Returns:
            GeoJSON FeatureCollection
        """
        features = self.get_boundaries_by_district(district_name)
        
        return {
            'type': 'FeatureCollection',
            'features': features
        }
