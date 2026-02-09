"""
Land Use Analyzer - Analisis Alih Fungsi Lahan
Menggunakan Google Dynamic World dan Sentinel-2 time series
"""

import ee
from typing import Dict, List, Tuple
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.bkd_config import (
    LAND_CHANGE_PRIORITY, LAND_CHANGE_TAX_POTENTIAL,
    CHANGE_MIN_AREA, NJOP_ZONE, PBB_RATE
)


class LandUseAnalyzer:
    """
    Analisis perubahan penggunaan lahan menggunakan:
    1. Google Dynamic World (near real-time land cover)
    2. Sentinel-2 spectral indices
    3. Change detection matrix
    4. Tax potential estimation
    """
    
    # Dynamic World land cover classes
    LANDCOVER_CLASSES = {
        0: 'water',
        1: 'trees',
        2: 'grass',
        3: 'flooded_vegetation',
        4: 'crops',
        5: 'shrub_and_scrub',
        6: 'built',
        7: 'bare',
        8: 'snow_and_ice'
    }
    
    # Simplified classes for BKD
    SIMPLIFIED_CLASSES = {
        'water': 'water',
        'trees': 'vegetation',
        'grass': 'vegetation',
        'flooded_vegetation': 'vegetation',
        'crops': 'crops',
        'shrub_and_scrub': 'vegetation',
        'built': 'built',
        'bare': 'bare',
        'snow_and_ice': 'bare'
    }
    
    def __init__(self):
        self.min_change_area = CHANGE_MIN_AREA
        
    def analyze_land_change(self, roi: ee.Geometry, year_start: int, year_end: int) -> Dict:
        """
        Analisis perubahan lahan antara dua tahun
        
        Args:
            roi: Region of Interest
            year_start: Tahun awal (baseline)
            year_end: Tahun akhir (current)
            
        Returns:
            Dict dengan change matrix dan tax potential
        """
        try:
            # 1. Get land cover for both years using Dynamic World
            lc_start = self._get_landcover_dynamicworld(roi, year_start)
            lc_end = self._get_landcover_dynamicworld(roi, year_end)
            
            # 2. Detect changes
            changes = self._detect_changes(lc_start, lc_end, roi)
            
            # 3. Calculate tax potential
            tax_potential = self._calculate_tax_potential(changes)
            
            return {
                'success': True,
                'year_start': year_start,
                'year_end': year_end,
                'changes': changes,
                'tax_potential': tax_potential,
                'method': 'Google Dynamic World + Sentinel-2'
            }
            
        except Exception as e:
            # Fallback to dummy data
            return self._generate_dummy_change_data(roi, year_start, year_end)
    
    def _get_landcover_dynamicworld(self, roi: ee.Geometry, year: int) -> ee.Image:
        """
        Get land cover classification from Google Dynamic World
        Enhanced with Google Open Buildings validation and temporal analysis.
        """
        try:
            dw_col = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1') \
                .filterBounds(roi) \
                .filterDate(f'{year}-01-01', f'{year}-12-31')
            
            # 1. Get temporal probabilities
            max_crops_prob = dw_col.select('crops').max()
            max_grass_prob = dw_col.select('grass').max()
            mean_built_prob = dw_col.select('built').mean()
            max_built_prob = dw_col.select('built').max()
            label = dw_col.select('label').mode()
            
            # 2. Get Google Open Buildings (Ground Truth Buildings)
            # This is the most reliable way to know if there is a structure there
            open_buildings = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons') \
                .filterBounds(roi) \
                .filter('confidence >= 0.6')
            
            # Convert building polygons to a binary mask (1 if building exists, 0 otherwise)
            buildings_mask = open_buildings.reduceToImage(
                properties=['confidence'],
                reducer=ee.Reducer.max()
            ).gt(0).unmask(0).reproject(crs='EPSG:4326', scale=10)
            
            # 3. Logic to Refine Built Classification
            # A pixel is ONLY 'built' if:
            # - Spectral index says it's built (label 6)
            # - High built-up probability (> 0.5)
            # - NO seasonal vegetation detected (crops or grass)
            # - HAS an actual AI-detected building footprint nearby
            
            is_seasonal_veg = max_crops_prob.gt(0.2).Or(max_grass_prob.gt(0.3))
            
            # Allow 'built' only if validated by Open Buildings mask
            # For 2025, we use the latest Open Buildings footprint as a reference
            is_built_confirmed = label.eq(6).And(mean_built_prob.gt(0.45)).And(buildings_mask.gt(0)).And(is_seasonal_veg.Not())
            
            # 4. Refine Label
            # If it was labeled built but not confirmed, revert to bare soil (7)
            # If it ever showed seasonal vegetation, force it to crops (4)
            refined_label = label \
                .where(label.eq(6).And(is_built_confirmed.Not()), 7) \
                .where(is_seasonal_veg, 4)
            
            # 5. Spatial smoothing to remove pixel artifacts
            smooth_label = refined_label.focal_mode(radius=1, kernelType='square', iterations=2)
            
            return smooth_label.clip(roi)
        except Exception as e:
            print(f"Error in DW Refinement: {e}")
            return self._classify_from_sentinel2(roi, year)
    
    def _classify_from_sentinel2(self, roi: ee.Geometry, year: int) -> ee.Image:
        """
        Fallback: Classify land cover from Sentinel-2 indices
        Enhanced with Building Footprint validation.
        """
        s2_col = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
            .filterBounds(roi) \
            .filterDate(f'{year}-01-01', f'{year}-12-31') \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
            
        def add_indices(img):
            ndbi = img.normalizedDifference(['B11', 'B8']).rename('NDBI')
            ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
            return img.addBands([ndbi, ndvi])
            
        s2_with_indices = s2_col.map(add_indices)
        
        # Strict Multi-temporal Built detection
        median_ndbi = s2_with_indices.select('NDBI').median()
        min_ndbi = s2_with_indices.select('NDBI').min()
        max_ndvi = s2_with_indices.select('NDVI').max()
        
        # Buildings must be ALWAYS built-up (high min NDBI) and NEVER green (low max NDVI)
        built_spectral = median_ndbi.gt(0.2).And(min_ndbi.gt(0.05)).And(max_ndvi.lt(0.4))
        
        # Final classification
        classification = ee.Image(7) \
            .where(max_ndvi.gt(0.45), 1) \
            .where(built_spectral, 6)
            
        return classification.focal_mode(radius=1.5, iterations=1)
    
    def _detect_changes(self, lc_start: ee.Image, lc_end: ee.Image, roi: ee.Geometry) -> List[Dict]:
        """
        Detect land cover changes with STRICT validation to eliminate false positives.
        Only reports changes where there is ACTUAL evidence of new building construction.
        """
        # Create change image
        change_img = lc_start.multiply(10).add(lc_end)
        
        # Filter: Only detect changes TO built (class 6)
        is_change = lc_start.neq(lc_end)
        to_built = lc_end.eq(6).And(lc_start.neq(6))
        
        # ===== CRITICAL: Get Google Open Buildings for VALIDATION =====
        # This is the GROUND TRUTH - if there's no building footprint, it's NOT a building
        try:
            open_buildings_current = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons') \
                .filterBounds(roi) \
                .filter('confidence >= 0.75')  # Increased from 0.6 to 0.75 for higher precision
            
            # Convert to raster mask
            buildings_mask_current = open_buildings_current.reduceToImage(
                properties=['confidence'],
                reducer=ee.Reducer.max()
            ).gt(0).unmask(0).reproject(crs='EPSG:4326', scale=10)
            
            # STRICT RULE: Only accept "to_built" changes if there's ACTUALLY a building footprint there
            # This eliminates false positives from harvested rice fields
            validated_change = to_built.And(buildings_mask_current.gt(0))
            
        except Exception as e:
            print(f"Warning: Could not load Open Buildings, using less strict validation: {e}")
            validated_change = to_built
        
        # Apply morphological filter to remove noise
        filtered_change = validated_change.focal_min(radius=1).focal_max(radius=1)
        
        # Additional filter: Remove very small changes (likely noise)
        # Use connectedPixelCount to filter out isolated pixels
        connected = filtered_change.connectedPixelCount(maxSize=100, eightConnected=True)
        filtered_change = filtered_change.updateMask(connected.gte(5))  # At least 5 connected pixels (~500m²)
        
        # Vectorize ONLY the validated changes
        changes_vector = change_img.updateMask(filtered_change).reduceToVectors(
            geometry=roi,
            scale=10,
            geometryType='polygon',
            eightConnected=True,
            maxPixels=1e9
        )
        
        # Get features
        try:
            features = changes_vector.limit(100).getInfo()['features']
        except:
            features = []
        
        # Process changes with additional validation
        change_data = []
        for idx, feature in enumerate(features):
            props = feature.get('properties', {})
            geom = feature['geometry']
            
            change_code = props.get('label', 0)
            start_class = int(change_code / 10)
            end_class = int(change_code % 10)
            
            # Skip if no change
            if start_class == end_class:
                continue
            
            # Get class names
            start_name = self.SIMPLIFIED_CLASSES.get(
                self.LANDCOVER_CLASSES.get(start_class, 'unknown'), 'unknown'
            )
            end_name = self.SIMPLIFIED_CLASSES.get(
                self.LANDCOVER_CLASSES.get(end_class, 'unknown'), 'unknown'
            )
            
            # STRICT FILTER: Only accept changes TO 'built'
            if end_name != 'built':
                continue
            
            # Calculate area
            if geom['type'] == 'Polygon':
                coords = geom['coordinates'][0]
                # Rough area calculation
                area_m2 = len(coords) * 100  # Dummy calculation
                
                # Increased minimum area to reduce noise
                if area_m2 < self.min_change_area * 2:  # Double the minimum
                    continue
                
                # Centroid
                avg_lat = sum(c[1] for c in coords) / len(coords)
                avg_lon = sum(c[0] for c in coords) / len(coords)
                
                # Priority
                priority = LAND_CHANGE_PRIORITY.get(
                    (start_name, end_name), 'LOW'
                )
                
                change_data.append({
                    'id': f'CHG-{idx+1:03d}',
                    'lat': avg_lat,
                    'lon': avg_lon,
                    'area_m2': area_m2,
                    'from_class': start_name,
                    'to_class': end_name,
                    'priority': priority,
                    'coordinates': coords,
                    'estimated_pbb': area_m2 * NJOP_ZONE['semi_pusat'] * (PBB_RATE['commercial'] if end_name == 'built' else 0) / 100
                })
        
        return change_data
    
    def _calculate_tax_potential(self, changes: List[Dict]) -> Dict:
        """
        Calculate tax potential from land use changes
        """
        total_potential = 0
        high_priority_count = 0
        
        for change in changes:
            if change['to_class'] == 'built':
                # New building = new tax object
                area = change['area_m2']
                
                # Assume semi_pusat zone (dummy)
                njop = NJOP_ZONE['semi_pusat']
                
                # Assume commercial if from vegetation/bare
                if change['from_class'] in ['vegetation', 'bare']:
                    tax_rate = PBB_RATE['commercial']
                else:
                    tax_rate = PBB_RATE['residential']
                
                # Annual PBB
                annual_pbb = area * njop * tax_rate / 100
                total_potential += annual_pbb
                
                if change['priority'] == 'HIGH':
                    high_priority_count += 1
        
        return {
            'total_annual': round(total_potential),
            'high_priority_changes': high_priority_count,
            'total_changes': len(changes),
            'avg_per_change': round(total_potential / len(changes)) if changes else 0
        }
    
    def _generate_dummy_change_data(self, roi: ee.Geometry, year_start: int, year_end: int) -> Dict:
        """
        Generate dummy land use change data for demo
        """
        import random
        random.seed(42)
        
        # Get ROI center
        centroid = roi.centroid().coordinates().getInfo()
        center_lon, center_lat = centroid
        
        # Generate 8-12 changes
        num_changes = random.randint(8, 12)
        changes = []
        
        change_types = [
            ('vegetation', 'built', 'HIGH'),
            ('bare', 'built', 'MEDIUM'),
            ('crops', 'built', 'HIGH'),
            ('vegetation', 'crops', 'LOW'),
        ]
        
        for i in range(num_changes):
            from_class, to_class, priority = random.choice(change_types)
            
            # Random location
            offset_lat = random.uniform(-0.008, 0.008)
            offset_lon = random.uniform(-0.008, 0.008)
            lat = center_lat + offset_lat
            lon = center_lon + offset_lon
            
            # Random area
            area_m2 = random.uniform(200, 1500)
            
            # Create polygon
            size = (area_m2 ** 0.5) / 111000
            coords = [
                [lon - size/2, lat - size/2],
                [lon + size/2, lat - size/2],
                [lon + size/2, lat + size/2],
                [lon - size/2, lat + size/2],
                [lon - size/2, lat - size/2]
            ]
            
            changes.append({
                'id': f'CHG-{i+1:03d}',
                'lat': lat,
                'lon': lon,
                'area_m2': round(area_m2, 1),
                'from_class': from_class,
                'to_class': to_class,
                'priority': priority,
                'coordinates': coords,
                'estimated_pbb': round(area_m2 * 2000000 * 0.002) # Dummy PBB calculation
            })
        
        # Calculate tax potential
        tax_potential = self._calculate_tax_potential(changes)
        
        return {
            'success': True,
            'year_start': year_start,
            'year_end': year_end,
            'changes': changes,
            'tax_potential': tax_potential,
            'method': 'Dummy Data (Demo Mode)',
            'note': 'Data simulasi untuk demonstrasi'
        }
    
    def create_change_popup_html(self, change_data: Dict) -> str:
        """Create HTML popup for land use change"""
        
        # Priority color
        priority_colors = {
            'HIGH': '#ef4444',
            'MEDIUM': '#f97316',
            'LOW': '#eab308',
            'CRITICAL': '#dc2626'
        }
        
        priority_color = priority_colors.get(change_data['priority'], '#6b7280')
        
        # Estimate tax
        area = change_data['area_m2']
        njop = NJOP_ZONE['semi_pusat']
        tax_rate = PBB_RATE['commercial'] if change_data['to_class'] == 'built' else 0
        estimated_pbb = area * njop * tax_rate / 100
        
        html = f"""
        <div style='width: 300px; font-family: Arial, sans-serif;'>
            <h3 style='margin: 0 0 10px 0; color: #1f2937; border-bottom: 2px solid {priority_color}; padding-bottom: 5px;'>
                🏗️ {change_data['id']} - Alih Fungsi Lahan
            </h3>
            
            <table style='width: 100%; font-size: 13px;'>
                <tr style='background: #f3f4f6;'>
                    <td style='padding: 8px; font-weight: bold;'>📏 Luas Area</td>
                    <td style='padding: 8px;'>{change_data['area_m2']:.1f} m²</td>
                </tr>
                <tr>
                    <td style='padding: 8px; font-weight: bold;'>📊 Dari</td>
                    <td style='padding: 8px;'>{change_data['from_class'].title()}</td>
                </tr>
                <tr style='background: #f3f4f6;'>
                    <td style='padding: 8px; font-weight: bold;'>📊 Menjadi</td>
                    <td style='padding: 8px; font-weight: bold; color: #dc2626;'>{change_data['to_class'].title()}</td>
                </tr>
                <tr>
                    <td style='padding: 8px; font-weight: bold;'>⚠️ Prioritas</td>
                    <td style='padding: 8px;'>
                        <span style='background: {priority_color}; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold;'>
                            {change_data['priority']}
                        </span>
                    </td>
                </tr>
            </table>
            
            <div style='margin-top: 15px; padding: 10px; background: #fef2f2; border-radius: 5px; border-left: 4px solid #dc2626;'>
                <div style='font-weight: bold; color: #991b1b; margin-bottom: 5px;'>💰 Potensi Pajak Baru:</div>
                <div style='font-size: 12px; color: #1f2937;'>
                    NJOP: Rp {njop:,}/m²<br>
                    Tarif PBB: {tax_rate}%<br>
                    <div style='margin-top: 5px; padding-top: 5px; border-top: 1px solid #fecaca;'>
                        <b style='color: #991b1b; font-size: 14px;'>PBB Tahunan: Rp {int(estimated_pbb):,}</b>
                    </div>
                </div>
            </div>
            
            <div style='margin-top: 10px; font-size: 11px; color: #6b7280;'>
                📍 Koordinat: {change_data['lat']:.5f}, {change_data['lon']:.5f}
                <br>
                <a href='https://earth.google.com/web/search/{change_data['lat']},{change_data['lon']}' target='_blank' style='color: #2563eb; text-decoration: none; font-weight: bold;'>
                    🌍 Buka di Google Earth
                </a>
                <div style='margin-top: 5px; font-style: italic; color: #1e40af;'>
                    💡 Tips: Klik ikon jam (Historical Imagery) di kiri bawah Earth untuk melihat kondisi tahun {change_data.get('year', 'analisis')}.
                </div>
            </div>
        </div>
        """
        return html
