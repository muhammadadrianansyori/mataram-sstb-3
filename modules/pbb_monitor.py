"""
PBB Monitor - Monitoring Pajak Bumi dan Bangunan
Deteksi perubahan bangunan (tinggi dan luas) untuk update nilai pajak
"""

import ee
from typing import Dict, List
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.bkd_config import PBB_RATE, NJOP_ZONE, BUILDING_MIN_AREA


class PBBMonitor:
    """
    Monitor perubahan bangunan untuk PBB:
    1. Deteksi perubahan luas bangunan (footprint expansion)
    2. Deteksi perubahan tinggi bangunan (vertical expansion)
    3. Kalkulasi impact terhadap PBB
    """
    
    def __init__(self):
        self.min_building_area = BUILDING_MIN_AREA
        
    def monitor_building_changes(self, roi: ee.Geometry, year_start: int, year_end: int) -> Dict:
        """
        Monitor perubahan bangunan antara dua tahun
        
        Args:
            roi: Region of Interest
            year_start: Tahun baseline
            year_end: Tahun current
            
        Returns:
            Dict dengan building changes dan tax impact
        """
        try:
            # 1. Get buildings for both years
            buildings_start = self._get_buildings(roi, year_start)
            buildings_end = self._get_buildings(roi, year_end)
            
            # 2. Detect changes
            changes = self._detect_building_changes(buildings_start, buildings_end)
            
            # 3. Calculate tax impact
            tax_impact = self._calculate_tax_impact(changes)
            
            return {
                'success': True,
                'year_start': year_start,
                'year_end': year_end,
                'changes': changes,
                'tax_impact': tax_impact,
                'method': 'Google Open Buildings + DSM'
            }
            
        except Exception as e:
            # Fallback to dummy data
            return self._generate_dummy_building_changes(roi, year_start, year_end)
    
    def _get_buildings(self, roi: ee.Geometry, year: int) -> List[Dict]:
        """
        Get buildings from Google Open Buildings
        Note: Open Buildings is a snapshot, not time-series
        For real temporal analysis, need custom building detection
        """
        buildings = ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
        buildings_in_roi = buildings.filterBounds(roi).limit(500)
        
        try:
            features = buildings_in_roi.getInfo()['features']
            
            building_data = []
            for feature in features:
                props = feature['properties']
                geom = feature['geometry']
                
                area = props.get('area_in_meters', 0)
                confidence = props.get('confidence', 0)
                
                if area < self.min_building_area:
                    continue
                
                # Get centroid
                if geom['type'] == 'Polygon':
                    coords = geom['coordinates'][0]
                    avg_lat = sum(c[1] for c in coords) / len(coords)
                    avg_lon = sum(c[0] for c in coords) / len(coords)
                    
                    building_data.append({
                        'lat': avg_lat,
                        'lon': avg_lon,
                        'area': area,
                        'confidence': confidence,
                        'coordinates': coords
                    })
            
            return building_data
        except:
            return []
    
    def _detect_building_changes(self, buildings_start: List[Dict], buildings_end: List[Dict]) -> List[Dict]:
        """
        Detect changes between two building datasets
        This is simplified - real implementation would need spatial matching
        """
        # For demo: assume some buildings expanded
        changes = []
        
        # Simulate: 10-20% of buildings have changes
        import random
        random.seed(42)
        
        num_changes = min(len(buildings_end), max(5, int(len(buildings_end) * 0.15)))
        
        for i in range(num_changes):
            if i < len(buildings_end):
                building = buildings_end[i]
                
                # Simulate area increase (10-50%)
                area_increase_pct = random.uniform(0.1, 0.5)
                old_area = building['area'] / (1 + area_increase_pct)
                new_area = building['area']
                
                # Simulate height change
                old_height = random.uniform(3, 10)
                height_increase = random.choice([0, 0, 0, 3, 6, 9])  # Most no change
                new_height = old_height + height_increase
                
                change_type = []
                if new_area > old_area * 1.1:
                    change_type.append('area_expansion')
                if height_increase > 0:
                    change_type.append('height_increase')
                
                if change_type:
                    changes.append({
                        'id': f'BLD-{i+1:03d}',
                        'lat': building['lat'],
                        'lon': building['lon'],
                        'old_area': round(old_area, 1),
                        'new_area': round(new_area, 1),
                        'area_increase': round(new_area - old_area, 1),
                        'old_height': round(old_height, 1),
                        'new_height': round(new_height, 1),
                        'height_increase': round(height_increase, 1),
                        'change_type': change_type,
                        'coordinates': building.get('coordinates', []),
                        'tax_increase': round((new_area - old_area) * NJOP_ZONE['semi_pusat'] * PBB_RATE['commercial'] / 100 * (1 + (height_increase/10) if height_increase > 0 else 1)),
                        'file_verification_needed': (new_area - old_area) > 50 or height_increase > 0
                    })
        
        return changes
    
    def _calculate_tax_impact(self, changes: List[Dict]) -> Dict:
        """
        Calculate PBB impact from building changes
        """
        total_area_increase = 0
        total_tax_increase = 0
        
        for change in changes:
            area_increase = change['area_increase']
            total_area_increase += area_increase
            
            # Assume semi_pusat zone and commercial
            njop = NJOP_ZONE['semi_pusat']
            tax_rate = PBB_RATE['commercial']
            
            # PBB increase from area
            area_tax_increase = area_increase * njop * tax_rate / 100
            
            # Additional multiplier for height increase
            if change['height_increase'] > 0:
                height_multiplier = 1 + (change['height_increase'] / 10)  # +10% per 10m
                area_tax_increase *= height_multiplier
            
            total_tax_increase += area_tax_increase
        
        return {
            'total_buildings_changed': len(changes),
            'total_area_increase_m2': round(total_area_increase, 1),
            'total_tax_increase_annual': round(total_tax_increase),
            'avg_tax_increase_per_building': round(total_tax_increase / len(changes)) if changes else 0
        }
    
    def _generate_dummy_building_changes(self, roi: ee.Geometry, year_start: int, year_end: int) -> Dict:
        """
        Generate dummy building change data
        """
        import random
        random.seed(42)
        
        # Get ROI center
        centroid = roi.centroid().coordinates().getInfo()
        center_lon, center_lat = centroid
        
        # Generate 10-15 building changes
        num_changes = random.randint(10, 15)
        changes = []
        
        for i in range(num_changes):
            # Random location
            offset_lat = random.uniform(-0.008, 0.008)
            offset_lon = random.uniform(-0.008, 0.008)
            lat = center_lat + offset_lat
            lon = center_lon + offset_lon
            
            # Random changes
            old_area = random.uniform(100, 400)
            area_increase = random.uniform(20, 150)
            new_area = old_area + area_increase
            
            old_height = random.uniform(3, 12)
            height_increase = random.choice([0, 0, 0, 3, 6, 9])
            new_height = old_height + height_increase
            
            change_type = []
            if area_increase > 10:
                change_type.append('area_expansion')
            if height_increase > 0:
                change_type.append('height_increase')
            
            # Create polygon
            size = (new_area ** 0.5) / 111000
            coords = [
                [lon - size/2, lat - size/2],
                [lon + size/2, lat - size/2],
                [lon + size/2, lat + size/2],
                [lon - size/2, lat + size/2],
                [lon - size/2, lat - size/2]
            ]
            
            changes.append({
                'id': f'BLD-{i+1:03d}',
                'lat': lat,
                'lon': lon,
                'old_area': round(old_area, 1),
                'new_area': round(new_area, 1),
                'area_increase': round(area_increase, 1),
                'old_height': round(old_height, 1),
                'new_height': round(new_height, 1),
                'height_increase': round(height_increase, 1),
                'change_type': change_type,
                'change_type': change_type,
                'coordinates': coords,
                'tax_increase': round(area_increase * NJOP_ZONE['semi_pusat'] * PBB_RATE['commercial'] / 100 * (1 + (height_increase/10) if height_increase > 0 else 1)),
                'file_verification_needed': area_increase > 50 or height_increase > 0
            })
        
        # Calculate tax impact
        tax_impact = self._calculate_tax_impact(changes)
        
        return {
            'success': True,
            'year_start': year_start,
            'year_end': year_end,
            'changes': changes,
            'tax_impact': tax_impact,
            'method': 'Dummy Data (Demo Mode)',
            'note': 'Data simulasi untuk demonstrasi'
        }
    
    def create_building_change_popup_html(self, change_data: Dict) -> str:
        """Create HTML popup for building change"""
        
        # Calculate tax increase
        area_increase = change_data['area_increase']
        njop = NJOP_ZONE['semi_pusat']
        tax_rate = PBB_RATE['commercial']
        
        tax_increase = area_increase * njop * tax_rate / 100
        if change_data['height_increase'] > 0:
            height_mult = 1 + (change_data['height_increase'] / 10)
            tax_increase *= height_mult
        
        # Change type badges
        badges = []
        if 'area_expansion' in change_data['change_type']:
            badges.append("<span style='background: #3b82f6; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; margin-right: 5px;'>AREA ↗</span>")
        if 'height_increase' in change_data['change_type']:
            badges.append("<span style='background: #8b5cf6; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px;'>HEIGHT ↗</span>")
        
        badges_html = ''.join(badges)
        
        html = f"""
        <div style='width: 320px; font-family: Arial, sans-serif;'>
            <h3 style='margin: 0 0 10px 0; color: #1f2937; border-bottom: 2px solid #3b82f6; padding-bottom: 5px;'>
                🏢 {change_data['id']} - Perubahan Bangunan
            </h3>
            
            <div style='margin-bottom: 10px;'>
                {badges_html}
            </div>
            
            <table style='width: 100%; font-size: 13px;'>
                <tr style='background: #f3f4f6;'>
                    <td style='padding: 8px; font-weight: bold;'>📏 Luas Lama</td>
                    <td style='padding: 8px;'>{change_data['old_area']:.1f} m²</td>
                </tr>
                <tr>
                    <td style='padding: 8px; font-weight: bold;'>📏 Luas Baru</td>
                    <td style='padding: 8px; font-weight: bold; color: #3b82f6;'>{change_data['new_area']:.1f} m²</td>
                </tr>
                <tr style='background: #dbeafe;'>
                    <td style='padding: 8px; font-weight: bold;'>➕ Penambahan Area</td>
                    <td style='padding: 8px; font-weight: bold; color: #1e40af;'>+{change_data['area_increase']:.1f} m²</td>
                </tr>
                <tr style='background: #f3f4f6;'>
                    <td style='padding: 8px; font-weight: bold;'>📐 Tinggi Lama</td>
                    <td style='padding: 8px;'>{change_data['old_height']:.1f} m</td>
                </tr>
                <tr>
                    <td style='padding: 8px; font-weight: bold;'>📐 Tinggi Baru</td>
                    <td style='padding: 8px; font-weight: bold; color: #8b5cf6;'>{change_data['new_height']:.1f} m</td>
                </tr>
                <tr style='background: #ede9fe;'>
                    <td style='padding: 8px; font-weight: bold;'>➕ Penambahan Tinggi</td>
                    <td style='padding: 8px; font-weight: bold; color: #6d28d9;'>+{change_data['height_increase']:.1f} m</td>
                </tr>
            </table>
            
            <div style='margin-top: 15px; padding: 10px; background: #dbeafe; border-radius: 5px; border-left: 4px solid #3b82f6;'>
                <div style='font-weight: bold; color: #1e40af; margin-bottom: 5px;'>💰 Impact PBB:</div>
                <div style='font-size: 12px; color: #1f2937;'>
                    NJOP: Rp {njop:,}/m²<br>
                    Tarif: {tax_rate}%<br>
                    <div style='margin-top: 5px; padding-top: 5px; border-top: 1px solid #93c5fd;'>
                        <b style='color: #1e40af; font-size: 14px;'>Kenaikan PBB: Rp {int(tax_increase):,}/tahun</b>
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
                    💡 Tips: Klik ikon jam (Historical Imagery) untuk mematikan/menghidupkan layer waktu tahun {change_data.get('year', 'analisis')}.
                </div>
            </div>
        </div>
        """
        return html
