import requests
import json
from typing import List, Dict
import ee

class OSMBridge:
    """
    Bridge to fetch Points of Interest (POI) from OpenStreetMap
    to assist satellite detection accuracy.
    """
    
    def __init__(self):
        self.overpass_url = "http://overpass-api.de/api/interpreter"
        
    def fetch_parking_related_pois(self, roi_geometry: ee.Geometry) -> List[Dict]:
        """
        Fetch POIs that likely have parking areas (shops, hotels, amenities)
        """
        try:
            # Get bounding box from EE geometry
            bbox = roi_geometry.bounds().getInfo()['coordinates'][0]
            # BBOX format for Overpass: (min_lat, min_lon, max_lat, max_lon)
            lons = [c[0] for c in bbox]
            lats = [c[1] for c in bbox]
            min_lat, min_lon = min(lats), min(lons)
            max_lat, max_lon = max(lats), max(lons)
            
            # Query for shops, hotels, and amenities
            query = f"""
            [out:json][timeout:25];
            (
              node["shop"~"supermarket|convenience|mall"]({min_lat},{min_lon},{max_lat},{max_lon});
              way["shop"~"supermarket|convenience|mall"]({min_lat},{min_lon},{max_lat},{max_lon});
              node["amenity"~"bank|restaurant|fast_food|cafe|hospital"]({min_lat},{min_lon},{max_lat},{max_lon});
              way["amenity"~"bank|restaurant|fast_food|cafe|hospital"]({min_lat},{min_lon},{max_lat},{max_lon});
              node["tourism"~"hotel|guest_house"]({min_lat},{min_lon},{max_lat},{max_lon});
              way["tourism"~"hotel|guest_house"]({min_lat},{min_lon},{max_lat},{max_lon});
            );
            out center;
            """
            
            response = requests.get(self.overpass_url, params={'data': query})
            data = response.json()
            
            pois = []
            for element in data.get('elements', []):
                # Normalize lat/lon depending on node vs way (center)
                lat = element.get('lat') if 'lat' in element else element.get('center', {}).get('lat')
                lon = element.get('lon') if 'lon' in element else element.get('center', {}).get('lon')
                
                tags = element.get('tags', {})
                name = tags.get('name', 'Bisnis Ritel/Layanan')
                category = tags.get('shop') or tags.get('amenity') or tags.get('tourism') or 'Business'
                
                if lat and lon:
                    pois.append({
                        'name': name,
                        'category': category.replace('_', ' ').title(),
                        'lat': lat,
                        'lon': lon,
                        'source': 'OpenStreetMap'
                    })
            
            return pois
        except Exception as e:
            print(f"OSM Fetch Error: {e}")
            return []

if __name__ == "__main__":
    # Test fetch
    bridge = OSMBridge()
    # Simple test ROI around Mataram Mall
    test_roi = ee.Geometry.Point([116.1165, -8.5895]).buffer(500)
    results = bridge.fetch_parking_related_pois(test_roi)
    print(f"Found {len(results)} POIs")
    for r in results[:5]:
        print(f"- {r['name']} ({r['category']})")
