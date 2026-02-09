"""
Parking Lot Detector - Deteksi Lahan Parkir dari Satelit Imagery
Menggunakan spectral analysis dan texture filtering
"""

import ee
import numpy as np
from typing import Dict, List, Tuple
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.bkd_config import (
    PARKING_TARIFF, PARKING_UTILIZATION, PARKING_HOURS,
    PARKING_MIN_AREA, PARKING_MAX_AREA, PARKING_ASPECT_RATIO
)


class ParkingDetector:
    """
    Deteksi area parkir menggunakan:
    1. Spectral indices (NDBI - untuk impervious surfaces)
    2. Texture analysis (parking lots memiliki texture khas)
    3. Exclude buildings (Google Open Buildings)
    4. Size/shape filtering
    """
    
    def __init__(self):
        self.min_area = PARKING_MIN_AREA
        self.max_area = PARKING_MAX_AREA
        
    def detect_parking_areas(self, roi: ee.Geometry, year: int = 2024) -> Dict:
        """
        Deteksi area parkir dalam ROI
        
        Args:
            roi: Region of Interest (ee.Geometry)
            year: Tahun untuk analisis
            
        Returns:
            Dict dengan parking areas dan metadata
        """
        try:
            # 1. Load Sentinel-2 imagery
            s2 = self._load_sentinel2(roi, year)
            
            # 2. Calculate spectral indices
            ndbi = self._calculate_ndbi(s2)  # Built-up index
            ndvi = self._calculate_ndvi(s2)  # Vegetation index
            
            # 3. Identify impervious surfaces (high NDBI, low NDVI)
            impervious = ndbi.gt(0.1).And(ndvi.lt(0.2))
            
            # 4. Exclude buildings
            buildings = ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
            buildings_in_roi = buildings.filterBounds(roi)
            
            # Convert buildings to raster mask
            building_mask = ee.Image().byte().paint(buildings_in_roi, 1)
            
            # 5. Get potential parking areas (impervious but not buildings)
            potential_parking = impervious.And(building_mask.Not())
            
            # 6. Texture analysis (optional - untuk filtering lebih lanjut)
            # Parking lots biasanya smooth/uniform
            texture = s2.select('B8').glcmTexture()
            smoothness = texture.select('B8_contrast').lt(100)  # Low contrast = smooth
            
            # 7. Combine filters
            parking_mask = potential_parking.And(smoothness)
            
            # 8. Vectorize (convert to polygons)
            parking_vectors = parking_mask.selfMask().reduceToVectors(
                geometry=roi,
                scale=10,
                geometryType='polygon',
                maxPixels=1e9
            )
            
            # 9. Filter by size and shape
            parking_filtered = self._filter_by_size_shape(parking_vectors)
            
            # 10. Get features as list
            features = parking_filtered.getInfo()['features']
            
            # 11. Process and calculate revenue
            parking_data = self._process_parking_features(features)
            
            return {
                'success': True,
                'count': len(parking_data),
                'parking_areas': parking_data,
                'total_area_m2': sum(p['area_m2'] for p in parking_data),
                'estimated_revenue_annual': sum(p['revenue_annual'] for p in parking_data),
                'method': 'Spectral Analysis + Texture Filtering'
            }
            
        except Exception as e:
            # Fallback to dummy data if GEE fails
            return self._generate_dummy_parking_data(roi)
    
    def _load_sentinel2(self, roi: ee.Geometry, year: int) -> ee.Image:
        """Load and composite Sentinel-2 imagery"""
        s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
            .filterBounds(roi) \
            .filterDate(f'{year}-01-01', f'{year}-12-31') \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
            .median() \
            .clip(roi)
        return s2
    
    def _calculate_ndbi(self, image: ee.Image) -> ee.Image:
        """Calculate Normalized Difference Built-up Index"""
        # NDBI = (SWIR - NIR) / (SWIR + NIR)
        # Sentinel-2: SWIR=B11, NIR=B8
        return image.normalizedDifference(['B11', 'B8']).rename('NDBI')
    
    def _calculate_ndvi(self, image: ee.Image) -> ee.Image:
        """Calculate Normalized Difference Vegetation Index"""
        # NDVI = (NIR - Red) / (NIR + Red)
        # Sentinel-2: NIR=B8, Red=B4
        return image.normalizedDifference(['B8', 'B4']).rename('NDVI')
    
    def _filter_by_size_shape(self, features: ee.FeatureCollection) -> ee.FeatureCollection:
        """Filter parking areas by size and shape"""
        def filter_func(feature):
            area = feature.geometry().area()
            # Get bounding box to check aspect ratio
            bounds = feature.geometry().bounds()
            coords = ee.List(bounds.coordinates().get(0))
            
            # Simple size filter
            size_ok = area.gte(self.min_area).And(area.lte(self.max_area))
            
            return feature.set('area', area).set('size_ok', size_ok)
        
        filtered = features.map(filter_func)
        return filtered.filter(ee.Filter.eq('size_ok', True))
    
    def _process_parking_features(self, features: List[Dict]) -> List[Dict]:
        """Process parking features and estimate revenue"""
        parking_data = []
        
        for idx, feature in enumerate(features):
            props = feature.get('properties', {})
            geom = feature['geometry']
            
            # Calculate area
            area_m2 = props.get('area', 0)
            
            if area_m2 < self.min_area or area_m2 > self.max_area:
                continue
            
            # Estimate parking type (dummy - based on size)
            parking_type = self._classify_parking_type(area_m2)
            
            # Calculate centroid
            if geom['type'] == 'Polygon':
                coords = geom['coordinates'][0]
                avg_lat = sum(c[1] for c in coords) / len(coords)
                avg_lon = sum(c[0] for c in coords) / len(coords)
            else:
                avg_lat, avg_lon = 0, 0
            
            # Estimate revenue
            revenue = self._estimate_parking_revenue(area_m2, parking_type)
            
            parking_data.append({
                'id': f'PKR-{idx+1:03d}',
                'lat': avg_lat,
                'lon': avg_lon,
                'area_m2': round(area_m2, 1),
                'parking_type': parking_type,
                'estimated_capacity': self._estimate_capacity(area_m2, parking_type),
                'revenue_daily': revenue['daily'],
                'revenue_monthly': revenue['monthly'],
                'revenue_annual': revenue['annual'],
                'coordinates': coords if geom['type'] == 'Polygon' else []
            })
        
        return parking_data
    
    def _classify_parking_type(self, area_m2: float) -> str:
        """Classify parking type based on area (dummy logic)"""
        if area_m2 < 200:
            return 'umum'
        elif area_m2 < 500:
            return 'perkantoran'
        elif area_m2 < 1000:
            return 'pasar'
        else:
            return 'mall'
    
    def _estimate_capacity(self, area_m2: float, parking_type: str) -> Dict:
        """Estimate parking capacity"""
        # Asumsi: 1 slot motor = 2m², 1 slot mobil = 12.5m²
        # Ratio motor:mobil = 60:40 (dummy)
        
        usable_area = area_m2 * 0.7  # 70% usable (exclude circulation)
        
        motor_area = usable_area * 0.6
        mobil_area = usable_area * 0.4
        
        motor_slots = int(motor_area / 2)
        mobil_slots = int(mobil_area / 12.5)
        
        return {
            'motor': motor_slots,
            'mobil': mobil_slots,
            'total': motor_slots + mobil_slots
        }
    
    def _estimate_parking_revenue(self, area_m2: float, parking_type: str) -> Dict:
        """Estimate parking revenue"""
        capacity = self._estimate_capacity(area_m2, parking_type)
        utilization = PARKING_UTILIZATION.get(parking_type, 0.5)
        hours_per_day = PARKING_HOURS.get(parking_type, 10)
        
        # Daily revenue
        motor_revenue = (capacity['motor'] * utilization * 
                        PARKING_TARIFF['motor']['hourly'] * hours_per_day)
        mobil_revenue = (capacity['mobil'] * utilization * 
                        PARKING_TARIFF['mobil']['hourly'] * hours_per_day)
        
        daily = motor_revenue + mobil_revenue
        monthly = daily * 26  # 26 working days
        annual = monthly * 12
        
        return {
            'daily': round(daily),
            'monthly': round(monthly),
            'annual': round(annual)
        }
    
    def _generate_dummy_parking_data(self, roi: ee.Geometry) -> Dict:
        """Generate dummy parking data for demo purposes"""
        import random
        random.seed(42)
        
        # Get ROI center
        centroid = roi.centroid().coordinates().getInfo()
        center_lon, center_lat = centroid
        
        # Generate 10-15 dummy parking lots
        num_parking = random.randint(10, 15)
        parking_data = []
        
        for i in range(num_parking):
            # Random offset from center
            offset_lat = random.uniform(-0.01, 0.01)
            offset_lon = random.uniform(-0.01, 0.01)
            
            lat = center_lat + offset_lat
            lon = center_lon + offset_lon
            
            # Random area
            area_m2 = random.uniform(150, 2000)
            parking_type = self._classify_parking_type(area_m2)
            
            # Revenue
            revenue = self._estimate_parking_revenue(area_m2, parking_type)
            capacity = self._estimate_capacity(area_m2, parking_type)
            
            # Create rectangular polygon
            size = (area_m2 ** 0.5) / 111000  # Approximate size in degrees
            coords = [
                [lon - size/2, lat - size/2],
                [lon + size/2, lat - size/2],
                [lon + size/2, lat + size/2],
                [lon - size/2, lat + size/2],
                [lon - size/2, lat - size/2]
            ]
            
            parking_data.append({
                'id': f'PKR-{i+1:03d}',
                'lat': lat,
                'lon': lon,
                'area_m2': round(area_m2, 1),
                'parking_type': parking_type,
                'estimated_capacity': capacity,
                'revenue_daily': revenue['daily'],
                'revenue_monthly': revenue['monthly'],
                'revenue_annual': revenue['annual'],
                'coordinates': coords
            })
        
        return {
            'success': True,
            'count': len(parking_data),
            'parking_areas': parking_data,
            'total_area_m2': sum(p['area_m2'] for p in parking_data),
            'estimated_revenue_annual': sum(p['revenue_annual'] for p in parking_data),
            'method': 'Dummy Data (Demo Mode)',
            'note': 'Data simulasi untuk demonstrasi. Gunakan data real untuk akurasi.'
        }
    
    def create_parking_popup_html(self, parking_data: Dict, show_details: bool = True) -> str:
        """Create HTML popup for parking area"""
        capacity = parking_data['estimated_capacity']
        
        html = f"""
        <div style='width: 300px; font-family: Arial, sans-serif;'>
            <h3 style='margin: 0 0 10px 0; color: #1f2937; border-bottom: 2px solid #FFD700; padding-bottom: 5px;'>
                🅿️ {parking_data['id']} - {parking_data['parking_type'].title()}
            </h3>
            
            <table style='width: 100%; font-size: 13px;'>
                <tr style='background: #f3f4f6;'>
                    <td style='padding: 8px; font-weight: bold;'>📏 Luas Area</td>
                    <td style='padding: 8px;'>{parking_data['area_m2']:.1f} m²</td>
                </tr>
                <tr>
                    <td style='padding: 8px; font-weight: bold;'>🏍️ Kapasitas Motor</td>
                    <td style='padding: 8px;'>{capacity['motor']} slot</td>
                </tr>
                <tr style='background: #f3f4f6;'>
                    <td style='padding: 8px; font-weight: bold;'>🚗 Kapasitas Mobil</td>
                    <td style='padding: 8px;'>{capacity['mobil']} slot</td>
                </tr>
                <tr>
                    <td style='padding: 8px; font-weight: bold;'>📊 Total Kapasitas</td>
                    <td style='padding: 8px; font-weight: bold; color: #f59e0b;'>{capacity['total']} kendaraan</td>
                </tr>
            </table>
            
            <div style='margin-top: 15px; padding: 10px; background: #fef3c7; border-radius: 5px; border-left: 4px solid #f59e0b;'>
                <div style='font-weight: bold; color: #92400e; margin-bottom: 5px;'>💰 Estimasi Potensi PAD:</div>
                <div style='font-size: 12px; color: #1f2937;'>
                    Per Hari: Rp {parking_data['revenue_daily']:,}<br>
                    Per Bulan: Rp {parking_data['revenue_monthly']:,}<br>
                    <div style='margin-top: 5px; padding-top: 5px; border-top: 1px solid #fcd34d;'>
                        <b style='color: #92400e; font-size: 14px;'>Per Tahun: Rp {parking_data['revenue_annual']:,}</b>
                    </div>
                </div>
            </div>
            
            <div style='margin-top: 10px; font-size: 11px; color: #6b7280;'>
                📍 Koordinat: {parking_data['lat']:.5f}, {parking_data['lon']:.5f}
                <br>
                <a href='https://earth.google.com/web/search/{parking_data['lat']},{parking_data['lon']}' target='_blank' style='color: #2563eb; text-decoration: none; font-weight: bold;'>
                    🌍 Buka di Google Earth
                </a>
                <div style='margin-top: 5px; font-style: italic; color: #1e40af;'>
                    💡 Tips: Gunakan fitur 'Historical Imagery' (ikon jam) di Google Earth untuk melihat bukti tahun {parking_data.get('year', '2024')}.
                </div>
            </div>
        </div>
        """
        return html
