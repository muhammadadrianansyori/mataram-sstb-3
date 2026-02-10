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
from modules.osm_bridge import OSMBridge


class ParkingDetector:
    """
    Deteksi area parkir menggunakan metode Hybrid:
    1. Spectral indices (NDBI - untuk impervious surfaces)
    2. Texture analysis (parking lots memiliki texture khas)
    3. POI-Assisted Detection (OpenStreetMap)
    """
    
    def __init__(self):
        self.min_area = PARKING_MIN_AREA
        self.max_area = PARKING_MAX_AREA
        self.osm = OSMBridge()
        
    def detect_parking_areas(self, roi: ee.Geometry, year: int = 2024) -> Dict:
        """
        Deteksi area parkir dalam ROI menggunakan metode Hybrid:
        1. Visual Spectral Analysis (Satelit)
        2. POI-Assisted Detection (OpenStreetMap)
        """
        try:
            # 1. Load Satellite Engine (Primary & Historical)
            s2_col = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
                .filterBounds(roi) \
                .filterDate(f'{year}-01-01', f'{year}-12-31') \
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) # Relaxed for Indo climate
            
            s2_median = s2_col.median().clip(roi)
            
            # --- PHASE A: STABLE SPECTRAL DETECTION ---
            ndbi = s2_median.normalizedDifference(['B11', 'B8'])
            dw_col = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1") \
                .filterBounds(roi) \
                .filterDate(f'{year}-01-01', f'{year}-12-31')
            dw = dw_col.median().clip(roi)
            built_prob = dw.select('built')
            
            # Identify impervious surfaces
            impervious = built_prob.gt(0.12).Or(ndbi.gt(0.01))
            
            # Exclude buildings
            buildings = ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons").filterBounds(roi)
            building_mask = ee.Image().byte().paint(buildings, 1)
            
            # PRIMARY MASK
            parking_mask = impervious.And(building_mask.Not()).selfMask()
            
            # Vectorize visual detections
            visual_vectors = ee.FeatureCollection([])
            try:
                raw_vectors = parking_mask.reduceToVectors(
                    geometry=roi, scale=10, geometryType='polygon', maxPixels=1e9
                )
                # CRITICAL: Calculate area and filter by shape
                visual_vectors = self._filter_by_size_shape(raw_vectors)
            except: pass
            
            # --- PHASE B: ACTIVITY SCORING (Confidence) ---
            # Corrected GEE stdDev calculation for ImageCollection
            activity_val = s2_col.select(['B2', 'B3', 'B4']).reduce(ee.Reducer.stdDev()).reduce(ee.Reducer.mean()).clip(roi)
            
            # --- PHASE C: POI-ASSISTED DETECTION (The "Indomaret" Bridge) ---
            # Optimized: Use vectorized reduceRegions to avoid N+1 .getInfo() calls
            osm_pois = self.osm.fetch_parking_related_pois(roi)
            poi_parking_data = []
            
            if osm_pois:
                # 1. Create FeatureCollection from POIs
                poi_features = []
                for i, poi in enumerate(osm_pois):
                    f = ee.Feature(
                        ee.Geometry.Point([poi['lon'], poi['lat']]),
                        {
                            'name': poi['name'],
                            'category': poi.get('category', 'Komersial'),
                            'orig_lat': poi['lat'],
                            'orig_lon': poi['lon']
                        }
                    )
                    poi_features.append(f)
                
                fc_pois = ee.FeatureCollection(poi_features)
                
                # 2. Batch Reduce (Single Request)
                # Calculate mean activity score for all POIs at once
                # buffer(20) is applied to each point
                def buffer_poi(f):
                    return f.buffer(20)
                
                fc_buffered = fc_pois.map(buffer_poi)
                
                # reduceRegions
                fc_with_stats = activity_val.reduceRegions(
                    collection=fc_buffered, 
                    reducer=ee.Reducer.mean(), 
                    scale=10
                )
                
                # 3. Fetch Results (Single .getInfo call)
                try:
                    results = fc_with_stats.getInfo()['features']
                except Exception as e:
                    print(f"Batch OSM reduce error: {e}")
                    results = []
                
                # 4. Process Results
                for i, res in enumerate(results):
                    props = res['properties']
                    # 'mean' is the default name from reducer
                    act_val = props.get('mean', 0)
                    if act_val is None: act_val = 0
                    
                    lat = props.get('orig_lat')
                    lon = props.get('orig_lon')
                    name = props.get('name')
                    category = props.get('category')
                    
                    # Same logic as before
                    delta = 0.0001
                    square_coords = [[lon-delta, lat-delta], [lon+delta, lat-delta], [lon+delta, lat+delta], [lon-delta, lat+delta], [lon-delta, lat-delta]]
                    
                    area_val = 65 
                    rev_est = self._estimate_parking_revenue(area_val, 'perkantoran')
                    
                    poi_parking_data.append({
                        'id': f"OSM-{i+1:03d}",
                        'name': name,
                        'lat': lat, 'lon': lon,
                        'area_m2': area_val,
                        'parking_type': 'perkantoran',
                        'estimated_capacity': self._estimate_capacity(area_val, 'perkantoran'),
                        'revenue_daily': rev_est['daily'],
                        'revenue_monthly': rev_est['monthly'],
                        'revenue_annual': rev_est['annual'],
                        'coordinates': square_coords,
                        'category': category,
                        'source': 'OpenStreetMap',
                        'activity_score': act_val,
                        'confidence': 0.95 if (act_val and act_val > 40) else 0.85
                    })

            # --- PHASE D: MERGE & PROCESS ---
            spectral_parking_data = []
            try:
                # Get detections from GEE
                features = visual_vectors.limit(100).getInfo().get('features', [])
                spectral_parking_data = self._process_parking_features(features)
            except Exception as e:
                print(f"Spectral merge error: {e}")
            
            all_parking = poi_parking_data + spectral_parking_data
            
            print(f"DEBUG V14: District Analysis Complete")
            print(f" - OSM POIs: {len(poi_parking_data)}")
            print(f" - Satellite Spectral: {len(spectral_parking_data)}")
            print(f" - Total: {len(all_parking)}")
            
            return {
                'success': True,
                'count': len(all_parking),
                'parking_areas': all_parking,
                'total_area_m2': sum(p['area_m2'] for p in all_parking),
                'estimated_revenue_annual': sum(p['revenue_annual'] for p in all_parking),
                'method': 'V14 Resurrected (Hybrid OSM+Satelit)'
            }
        
        except Exception as e:
            import traceback
            print(f"Parking Detection V14 Error: {e}")
            traceback.print_exc()
            return {'success': False, 'error': str(e), 'parking_areas': []}
    
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
        """Filter parking areas by size and shape (Road Masking)"""
        def filter_func(feature):
            geom = feature.geometry()
            area = geom.area()
            
            # ROAD MASKING LOGIC: Aspect Ratio Analysis
            # Get oriented bounding box
            bounds = geom.bounds()
            coords = ee.List(bounds.coordinates().get(0))
            
            p1 = ee.List(coords.get(0))
            p2 = ee.List(coords.get(1))
            p3 = ee.List(coords.get(2))
            
            # Calculate width and height of bounding box
            d1 = ee.Number(p1.get(0)).subtract(p2.get(0)).pow(2).add(ee.Number(p1.get(1)).subtract(p2.get(1)).pow(2)).sqrt()
            d2 = ee.Number(p2.get(0)).subtract(p3.get(0)).pow(2).add(ee.Number(p2.get(1)).subtract(p3.get(1)).pow(2)).sqrt()
            
            # Aspect ratio: min(d1, d2) / max(d1, d2)
            # Road has very low aspect ratio (long and thin)
            max_d = ee.Number(d1).max(d2)
            min_d = ee.Number(d1).min(d2)
            ratio = min_d.divide(max_d)
            
            # Filters
            size_ok = area.gte(self.min_area).And(area.lte(self.max_area))
            shape_ok = ratio.gt(PARKING_ASPECT_RATIO) # Ignore very thin polygons
            
            return feature.set('area', area).set('valid', size_ok.And(shape_ok))
        
        filtered = features.map(filter_func)
        return filtered.filter(ee.Filter.eq('valid', True))
    
    def _process_parking_features(self, features: List[Dict]) -> List[Dict]:
        """Process parking features and estimate revenue"""
        parking_data = []
        
        for idx, feature in enumerate(features):
            props = feature.get('properties', {})
            geom = feature['geometry']
            
            # Calculate area (Try props first, then local calculation)
            area_m2 = props.get('area', 0)
            
            if area_m2 == 0 and geom['type'] == 'Polygon':
                # Emergency local calculation (approximate)
                coords = geom['coordinates'][0]
                # Shoelace formula for area
                x = [c[0] for c in coords]
                y = [c[1] for c in coords]
                # Convert to meters approx (1 deg ~ 111320m at equator)
                lat_avg = sum(y) / len(y)
                m_per_deg_lat = 111320
                m_per_deg_lon = 111320 * np.cos(np.radians(lat_avg))
                
                area = 0.5 * abs(sum(x[i] * y[i+1] - x[i+1] * y[i] for i in range(len(x)-1)))
                area_m2 = area * m_per_deg_lat * m_per_deg_lon
            
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
        
        # Check for OSM source
        is_osm = parking_data.get('source') == 'OpenStreetMap'
        source_badge = "<span style='background:#10b981;color:white;padding:2px 6px;border-radius:4px;font-size:10px;margin-left:5px;'>Verified via OSM</span>" if is_osm else ""
        category_row = f"<tr><td style='padding:8px;font-weight:bold;'>🏷️ Kategori</td><td style='padding:8px;'>{parking_data.get('category', 'Komersial')}</td></tr>" if is_osm else ""

        # Activity details
        act_score = parking_data.get('activity_score', 0)
        act_label = ""
        if act_score > 120:
            act_label = "<div style='color:#10b981; font-weight:bold; font-size:11px;'>🔥 Aktivitas Kendaraan: SANGAT TINGGI</div>"
        elif act_score > 80:
            act_label = "<div style='color:#f59e0b; font-weight:bold; font-size:11px;'>🚗 Aktivitas Kendaraan: AKTIF</div>"
        
        html = f"""
        <div style='width: 300px; font-family: Arial, sans-serif;'>
            <h3 style='margin: 0 0 10px 0; color: #1f2937; border-bottom: 2px solid #FFD700; padding-bottom: 5px;'>
                🅿️ {parking_data['id']} - {parking_data.get('name', parking_data['parking_type'].title())}
                {source_badge}
            </h3>
            
            {act_label}
            
            <table style='width: 100%; font-size: 13px;'>
                {category_row}
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

                <!-- AI VALIDATION STATUS -->
                <div style='margin-top: 10px; padding-top: 5px; border-top: 1px dashed #ccc;'>
                    {self._get_ai_status_html(parking_data)}
                </div>
            </div>
        </div>
        """
        return html

    def _get_ai_status_html(self, parking_data: Dict) -> str:
        """Get HTML snippet for AI validation status"""
        ai_res = parking_data.get('ai_validation')
        
        if not ai_res:
            return """
            <div style='display: flex; align-items: center; justify-content: space-between;'>
                <span style='color: #6b7280; font-weight: bold; font-size: 11px;'>🧠 Status AI: Menunggu Validasi</span>
                <span style='font-size: 10px; background: #f3f4f6; padding: 2px 5px; border-radius: 3px;'>
                    Pilih ID <b>{id}</b> di panel bawah untuk memvalidasi
                </span>
            </div>
            """.format(id=parking_data['id'])
            
        status = ai_res.get('status', 'Unknown')
        confidence = ai_res.get('confidence', 0)
        is_verified = ai_res.get('verified', False)
        
        color = '#10b981' if is_verified else '#ef4444'
        icon = '✅' if is_verified else '❌'
        
        return f"""
        <div style='font-size: 11px; font-weight: bold; color: {color};'>
            {icon} {status} (Conf: {int(confidence*100)}%)
        </div>
        """
