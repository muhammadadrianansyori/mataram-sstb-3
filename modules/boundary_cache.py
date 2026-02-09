"""
Boundary Cache Module - Performance Optimization
Implements caching for boundary data to avoid repeated file I/O
"""

import streamlit as st
import geopandas as gpd
from typing import Optional

@st.cache_data(ttl=3600)
def load_boundaries_cached(geojson_path: str) -> Optional[gpd.GeoDataFrame]:
    """
    Load GeoJSON boundaries with LRU caching
    
    Args:
        geojson_path: Path to GeoJSON file
    
    Returns:
        GeoDataFrame or None if error
    """
    try:
        gdf = gpd.read_file(geojson_path)
        return gdf
    except Exception as e:
        print(f"Error loading boundaries: {e}")
        return None

def get_district_boundaries_cached(geojson_path: str, district_code: str) -> Optional[gpd.GeoDataFrame]:
    """
    Get boundaries for specific district with caching
    
    Args:
        geojson_path: Path to GeoJSON file
        district_code: Kecamatan code (e.g., '010' for Ampenan)
    
    Returns:
        Filtered GeoDataFrame or None
    """
    gdf = load_boundaries_cached(geojson_path)
    
    if gdf is None:
        return None
    
    return gdf[gdf['kdkec'] == district_code]

def clear_cache():
    """Clear all cached boundary data"""
    load_boundaries_cached.cache_clear()
    get_district_boundaries_cached.cache_clear()
    print("✅ Boundary cache cleared")
