"""
BKD PAD Monitoring System - Dashboard Streamlit
Sistem monitoring Pendapatan Asli Daerah untuk Badan Keuangan Daerah
"""

import streamlit as st

import folium
from folium import plugins
import ee
from utils import initialize_gee
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from io import BytesIO

# Import BKD modules
from modules.boundary_manager import BoundaryManager
from modules.boundary_cache import load_boundaries_cached
from modules.report_generator import BKDReportGenerator

from modules.parking_detector import ParkingDetector
from modules.landuse_analyzer import LandUseAnalyzer
from modules.pbb_monitor import PBBMonitor
from config.bkd_config import (
    MATARAM_DISTRICTS, TARGET_PAD_ANNUAL, COLORS,
    PARKING_TARIFF, PBB_RATE, NJOP_ZONE
)
# Import AI Validator
from modules.ai_validator import AIValidator, get_ai_status


# Page Config
st.set_page_config(
    layout="wide",
    page_title="BKD PAD Monitoring - Kota Mataram",
    page_icon="💰"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        margin-bottom: 20px;
    }
    .metric-card {
        background: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        margin: 10px 0;
    }
    .info-box {
        padding: 15px;
        background: #f0f9ff;
        border-left: 4px solid #3b82f6;
        border-radius: 5px;
        margin: 10px 0;
    }
    .warning-box {
        padding: 15px;
        background: #fef3c7;
        border-left: 4px solid #f59e0b;
        border-radius: 5px;
        margin: 10px 0;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
        background-color: #f3f4f6;
        border-radius: 8px 8px 0 0;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="main-header">
    <h1>💰 Sistem Monitoring PAD - Badan Keuangan Daerah</h1>
    <p style='margin: 0; font-size: 16px;'>Kota Mataram | Monitoring Berbasis Satelit & Big Data</p>
</div>
""", unsafe_allow_html=True)

# Initialize GEE
gee_status = initialize_gee()

# Initialize AI Engine
ai_validator = AIValidator()
ai_status_msg = get_ai_status()


# Sidebar Configuration
st.sidebar.header("⚙️ Konfigurasi Sistem")

# 1. Year Selection (Top)
st.sidebar.header("📅 Periode Analisis")
col_year1, col_year2 = st.sidebar.columns(2)
year_baseline = col_year1.selectbox("Tahun Baseline", list(range(2015, 2026)), index=4)  # 2019
year_current = col_year2.selectbox("Tahun Current", list(range(2015, 2026)), index=9)  # 2024

# 2. District & Kelurahan Selection (Wilayah)
st.sidebar.header("📍 Wilayah Analisis")
selected_district = st.sidebar.selectbox(
    "Pilih Kecamatan",
    list(MATARAM_DISTRICTS.keys()),
    help="Pilih kecamatan untuk fokus analisis"
)

district_config = MATARAM_DISTRICTS[selected_district]

# Regional Filters (Kelurahan/Lingkungan/RT)
from modules.boundary_manager import BoundaryManager
from config.bkd_config import BOUNDARY_GEOJSON_PATH

selected_kelurahan = []
selected_lingkungan = []
selected_rt = []
boundary_mgr = None

try:
    boundary_mgr = BoundaryManager(BOUNDARY_GEOJSON_PATH)
    
    # --- NEW: Global SLS Search (No Guessing) ---
    all_sls = ["--- Cari Wilayah / RT ---"] + boundary_mgr.get_all_sls_in_district(selected_district)
    selected_global_search = st.sidebar.selectbox(
        "🔍 Cari RT Lintas Kelurahan",
        options=all_sls,
        help="Ketik untuk mencari RT/Lingkungan tertentu tanpa harus pilih kelurahan"
    )
    
    parent_info = {}
    if selected_global_search != "--- Cari Wilayah / RT ---":
        parent_info = boundary_mgr.get_parent_info_by_sls(selected_global_search, selected_district)
    
    # --- Hierarchical Filters ---
    kelurahan_list = ["--- Semua Kelurahan ---"] + boundary_mgr.get_kelurahan_list(selected_district)
    
    # Auto-index for Kelurahan if global search is used
    k_idx = 0
    if parent_info.get('kelurahan'):
        k_idx = kelurahan_list.index(parent_info['kelurahan']) if parent_info['kelurahan'] in kelurahan_list else 0

    selected_kelurahan_raw = st.sidebar.selectbox(
        "Pilih Kelurahan",
        options=kelurahan_list,
        index=k_idx,
        help="Pilih kelurahan spesifik"
    )
    
    selected_kelurahan = [] if selected_kelurahan_raw == "--- Semua Kelurahan ---" else [selected_kelurahan_raw]
    
    selected_lingkungan = []
    selected_rt = []

    if selected_kelurahan:
        ling_raw_list = ["--- Semua Lingkungan ---"] + boundary_mgr.get_lingkungan_list(selected_district, selected_kelurahan)
        
        # Auto-index for Lingkungan if global search is used
        l_idx = 0
        if parent_info.get('lingkungan'):
            l_idx = ling_raw_list.index(parent_info['lingkungan']) if parent_info['lingkungan'] in ling_raw_list else 0

        selected_lingkungan_raw = st.sidebar.selectbox(
            "Pilih Lingkungan",
            options=ling_raw_list,
            index=l_idx,
            help="Pilih lingkungan spesifik"
        )
        
        selected_lingkungan = [] if selected_lingkungan_raw == "--- Semua Lingkungan ---" else [selected_lingkungan_raw]
        
        if selected_lingkungan:
            rt_list = boundary_mgr.get_rt_list(selected_district, selected_kelurahan, selected_lingkungan)
            
            # If global search selected an RT, use it as default
            rt_defaults = []
            if selected_global_search != "--- Cari Wilayah / RT ---":
                # Extract RT part from "RT 001 LINGKUNGAN X"
                rt_part = selected_global_search.split(' LINGKUNGAN ')[0].strip() if ' LINGKUNGAN ' in selected_global_search else selected_global_search
                if rt_part in rt_list:
                    rt_defaults = [rt_part]

            selected_rt = st.sidebar.multiselect(
                "🏠 Filter RT",
                options=rt_list,
                default=rt_defaults,
                help="Pilih RT spesifik (filter terbawah)"
            )
            
            if selected_rt:
                st.sidebar.info(f"📍 Fokus: {len(selected_rt)} RT")
            else:
                st.sidebar.info(f"📍 Fokus: {selected_lingkungan_raw}")
        else:
            st.sidebar.info(f"📍 Fokus: {selected_kelurahan_raw}")
except Exception as e:
    st.sidebar.error(f"Error loading boundaries: {e}")
    selected_kelurahan = []
    selected_lingkungan = []
    selected_rt = []

# 3. Map Visual Controls (Bottom)
st.sidebar.header("🗺️ Kontrol Peta")
map_background = st.sidebar.radio(
    "Background Peta",
    ["Satelit", "Polos (Light)", "Polos (Dark)", "Hanya Batas Wilayah"],
    index=0,
    help="Pilih jenis background peta"
)

show_boundaries = st.sidebar.checkbox(
    "Tampilkan Garis Batas",
    value=True,
    help="Tampilkan garis batas wilayah di peta"
)

boundary_opacity = st.sidebar.slider(
    "Transparansi Batas",
    min_value=0.0,
    max_value=1.0,
    value=0.6,
    step=0.1
)


# Create ROI safely
roi = None
if gee_status:
    try:
        roi = ee.Geometry.Point([district_config['lon'], district_config['lat']]).buffer(district_config['radius'])
    except Exception as e:
        st.error(f"❌ Error creating ROI: {e}")

# ==========================================
# MAP HELPER FUNCTIONS
# ==========================================
def create_map_with_controls(lat, lon, zoom, background_type, show_boundaries_flag=True):
    """
    Create Folium map with user-selected background
    
    Args:
        lat: Latitude for map center
        lon: Longitude for map center
        zoom: Zoom level
        background_type: Type of background ('Satelit', 'Polos (Light)', etc.)
        show_boundaries_flag: Whether to show boundaries
    
    Returns:
        Folium Map object
    """
    # Background tiles mapping
    tiles_map = {
        "Satelit": ('https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', 'Google Satellite'),
        "Polos (Light)": ('CartoDB positron', 'CartoDB Positron'),
        "Polos (Dark)": ('CartoDB dark_matter', 'CartoDB Dark Matter'),
        "Hanya Batas Wilayah": ('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', 'Plain')
    }
    
    tile_url, attr_name = tiles_map.get(background_type, tiles_map["Satelit"])
    
    # Create map
    if tile_url.startswith('http'):
        m = folium.Map(
            location=[lat, lon],
            zoom_start=zoom,
            tiles=tile_url,
            attr=attr_name
        )
    else:
        m = folium.Map(
            location=[lat, lon],
            zoom_start=zoom,
            tiles=tile_url
        )
    
    return m

def add_boundary_overlay(m, district_name, kelurahan=None, lingkungan=None, rt=None, opacity=0.6):
    """
    Add boundary overlay to Folium map with granular filtering
    
    Args:
        m: Folium Map object
        district_name: Name of district
        kelurahan: Optional selected kelurahan (list)
        lingkungan: Optional selected lingkungan (list)
        rt: Optional selected RT (list)
        opacity: Opacity of boundary lines
    
    Returns:
        Modified Folium Map object
    """
    if boundary_mgr is None:
        return m
    
    try:
        from config.bkd_config import BOUNDARY_STYLES
        
        boundaries = boundary_mgr.get_boundaries_by_district(district_name)
        
        for boundary in boundaries:
            nmdesa = boundary['properties']['nmdesa']
            nmsls = boundary['properties']['nmsls']
            
            # CRITICAL: Prioritize most granular selection for visualization
            visible = True
            
            if rt and len(rt) > 0:
                # If RT is selected, only show matching RTs
                # Pattern match: starts with any of RT names
                is_rt_match = any(nmsls.startswith(f"{r} ") or nmsls == r for r in rt)
                if not is_rt_match:
                    visible = False
            elif lingkungan and len(lingkungan) > 0:
                # If Lingkungan is selected, only show matching Lingkungans
                is_lingkungan_match = any(f" LINGKUNGAN {l}" in nmsls or nmsls == l for l in lingkungan)
                if not is_lingkungan_match:
                    visible = False
            elif kelurahan and len(kelurahan) > 0:
                # If only Kelurahan is selected
                if nmdesa not in kelurahan:
                    visible = False
            
            if not visible:
                continue
                    
            folium.GeoJson(
                boundary,
                style_function=lambda x, op=opacity: {
                    'fillColor': 'transparent',
                    'color': '#FF6B6B',
                    'weight': 2,
                    'fillOpacity': 0,
                    'opacity': op
                },
                tooltip=folium.Tooltip(
                    f"<b>{boundary['properties']['nmsls']}</b><br>"
                    f"Kelurahan: {boundary['properties']['nmdesa']}"
                )
            ).add_to(m)
    except Exception as e:
        print(f"Error adding boundaries: {e}")
    
    return m

def add_map_legend(m, show_boundaries_flag=True):
    """
    Add legend to Folium map
    
    Args:
        m: Folium Map object
        show_boundaries_flag: Whether boundaries are shown
    
    Returns:
        Modified Folium Map object
    """
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; right: 50px; width: 220px; height: auto; 
                background-color: white; z-index:9999; font-size:13px;
                border:2px solid grey; border-radius: 5px; padding: 12px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
    <p style="margin: 0 0 8px 0; font-weight: bold; font-size: 14px; border-bottom: 1px solid #ddd; padding-bottom: 5px;">📍 Legenda</p>
    '''
    
    if show_boundaries_flag:
        legend_html += '''
        <p style="margin: 5px 0;">
            <span style="color: #FF6B6B; font-weight: bold;">━━━</span> Batas Kelurahan
        </p>
        '''
    
    legend_html += '''
    <p style="margin: 5px 0;">
        <span style="background-color: #FFD700; padding: 2px 12px; border-radius: 3px;">  </span> Lahan Parkir
    </p>
    <p style="margin: 5px 0;">
        <span style="background-color: #ef4444; padding: 2px 12px; border-radius: 3px;">  </span> Alih Fungsi Lahan
    </p>
    <p style="margin: 5px 0;">
        <span style="background-color: #3b82f6; padding: 2px 12px; border-radius: 3px;">  </span> Bangunan Baru
    </p>
    </div>
    '''
    
    m.get_root().html.add_child(folium.Element(legend_html))
    return m


# Initialize modules
parking_detector = ParkingDetector()
landuse_analyzer = LandUseAnalyzer()
pbb_monitor = PBBMonitor()

# Main Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🅿️ Lahan Parkir",
    "🏗️ Alih Fungsi Lahan",
    "🏢 Monitoring PBB",
    "📊 Dashboard PAD",
    "📄 Laporan & Export"
])

# ============================================
# TAB 1: LAHAN PARKIR
# ============================================
with tab1:
    st.header("🅿️ Monitoring Lahan Parkir")
    st.markdown("Deteksi dan kalkulasi potensi retribusi parkir dari citra satelit")
    
    if st.button("🔍 Analisis Lahan Parkir", key="btn_parking"):
        with st.spinner("Memproses data satelit (Gedung & Area Terbuka)..."):
            # Detect parking areas directly from real data
            parking_data = parking_detector.detect_parking_areas(roi, year_current)
            
            # Store in session state
            st.session_state['parking_data'] = parking_data
    
    # Display results if available
    if 'parking_data' in st.session_state:
        data = st.session_state['parking_data']
        
        # Apply spatial filter (Always apply for boundary capping)
        if boundary_mgr:
            data['parking_areas'] = boundary_mgr.spatial_filter(data['parking_areas'], selected_district, selected_kelurahan, selected_lingkungan, selected_rt)
            
            # Recalculate metrics
            data['count'] = len(data['parking_areas'])
            data['total_area_m2'] = sum(p['area_m2'] for p in data['parking_areas'])
            data['estimated_revenue_annual'] = sum(p['revenue_annual'] for p in data['parking_areas'])
        
        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🅿️ Total Area Parkir", f"{data['count']} lokasi")
        col2.metric("📏 Total Luas", f"{int(data['total_area_m2']):,} m²")
        col3.metric("💰 Potensi PAD/Tahun", f"Rp {int(data['estimated_revenue_annual']):,}")
        col4.metric("📊 Metode", data['method'].split('(')[0].strip())
        
        # Map
        st.subheader("🗺️ Peta Lokasi Parkir")
        
        # Create map with user-selected background
        m = create_map_with_controls(
            district_config['lat'],
            district_config['lon'],
            15,
            map_background,
            show_boundaries
        )
        
        # Add boundary overlay if enabled
        if show_boundaries:
            m = add_boundary_overlay(m, selected_district, selected_kelurahan, selected_lingkungan, selected_rt, boundary_opacity)
        
        # Add parking areas
        for parking in data['parking_areas']:
            if parking['coordinates']:
                # Convert coordinates
                folium_coords = [[c[1], c[0]] for c in parking['coordinates']]
                
                folium.Polygon(
                    locations=folium_coords,
                    popup=folium.Popup(
                        parking_detector.create_parking_popup_html(parking),
                        max_width=320
                    ),
                    tooltip=f"🅿️ {parking['parking_type'].title()} - {parking['area_m2']:.0f}m² - Klik untuk detail",
                    color=COLORS['parking'],
                    fill=True,
                    fillColor=COLORS['parking'],
                    fillOpacity=0.6,
                    weight=2
                ).add_to(m)
        
        # Add legend
        m = add_map_legend(m, show_boundaries)
        
        # Display map
        components.html(m._repr_html_(), height=600)
        
        # Data table
        st.subheader("📋 Detail Area Parkir")
        
        if len(data['parking_areas']) == 0:
            st.warning("⚠️ Tidak ada area parkir terdeteksi di area yang dipilih.")
        else:
            df_parking = pd.DataFrame(data['parking_areas'])
            df_parking_display = df_parking[['id', 'parking_type', 'area_m2', 'estimated_capacity', 'revenue_annual']]
            st.dataframe(df_parking_display, use_container_width=True)
            
            # Chart
            col1, col2 = st.columns(2)
            with col1:
                fig_type = px.pie(
                    df_parking,
                    names='parking_type',
                    title='Distribusi Jenis Parkir',
                    hole=0.4
                )
                st.plotly_chart(fig_type, use_container_width=True)
            
            with col2:
                fig_revenue = px.bar(
                    df_parking,
                    x='parking_type',
                    y='revenue_annual',
                    title='Potensi PAD per Jenis Parkir',
                    labels={'revenue_annual': 'PAD (Rp/tahun)', 'parking_type': 'Jenis Parkir'}
                )
                st.plotly_chart(fig_revenue, use_container_width=True)

# ============================================
# TAB 2: ALIH FUNGSI LAHAN
# ============================================
with tab2:
    st.header("🏗️ Analisis Alih Fungsi Lahan")
    st.markdown(f"Deteksi perubahan penggunaan lahan: **{year_baseline}** → **{year_current}**")
    
    if st.button("🔍 Analisis Perubahan Lahan", key="btn_landuse"):
        with st.spinner("Memproses data temporal (Sentinel-2 & Dynamic World)..."):
            # Analyze real land use change
            landuse_data = landuse_analyzer.analyze_land_change(roi, year_baseline, year_current)
            
            # --- AI VALIDATION STEP ---
            # Enrich the detected changes with AI validation
            with st.spinner("🧠 Menjalankan AI Validator (Prithvi-100M) untuk verifikasi bangunan..."):
                progress_bar = st.progress(0)
                total_changes = len(landuse_data['changes'])
                
                for idx, change in enumerate(landuse_data['changes']):
                    # Simulate fetching image chips (in real app, use geemap to get pixel array)
                    chip_start = ai_validator.get_image_chip(change['coordinates'], year_baseline) 
                    chip_end = ai_validator.get_image_chip(change['coordinates'], year_current)
                    
                    # Run AI Verification
                    ai_result = ai_validator.verify_change(chip_start, chip_end)
                    
                    # Store result in change dict
                    change['ai_validation'] = ai_result
                    progress_bar.progress((idx + 1) / total_changes)
                
                progress_bar.empty()
            # ---------------------------
            
            st.session_state['landuse_data'] = landuse_data
    
    # Display results
    if 'landuse_data' in st.session_state:
        data = st.session_state['landuse_data']
        
        # Apply spatial filter (Always apply for boundary capping)
        if boundary_mgr:
            data['changes'] = boundary_mgr.spatial_filter(data['changes'], selected_district, selected_kelurahan, selected_lingkungan, selected_rt)
            
            # Recalculate tax potential after filtering
            total_annual = sum(c.get('estimated_pbb', 0) for c in data['changes'])
            high_priority = sum(1 for c in data['changes'] if c['priority'] == 'HIGH')
            data['tax_potential'] = {
                'total_changes': len(data['changes']),
                'high_priority_changes': high_priority,
                'total_annual': total_annual,
                'avg_per_change': total_annual / len(data['changes']) if data['changes'] else 0
            }
        
        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🔄 Total Perubahan", f"{data['tax_potential']['total_changes']} area")
        col2.metric("⚠️ Prioritas Tinggi", f"{data['tax_potential']['high_priority_changes']} area")
        col3.metric("💰 Potensi Pajak Baru", f"Rp {int(data['tax_potential']['total_annual']):,}/tahun")
        col4.metric("📊 Rata-rata/Area", f"Rp {int(data['tax_potential']['avg_per_change']):,}")
        
        # Map
        st.subheader("🗺️ Peta Perubahan Lahan")
        
        # Create map with user-selected background
        m = create_map_with_controls(
            district_config['lat'],
            district_config['lon'],
            14,
            map_background,
            show_boundaries
        )
        
        # Add boundary overlay if enabled
        if show_boundaries:
            m = add_boundary_overlay(m, selected_district, selected_kelurahan, selected_lingkungan, selected_rt, boundary_opacity)
        
        # Priority colors
        priority_colors = {
            'HIGH': '#ef4444',
            'MEDIUM': '#f97316',
            'LOW': '#eab308',
            'CRITICAL': '#dc2626'
        }
        
        # Add changes
        for change in data['changes']:
            if change['coordinates']:
                folium_coords = [[c[1], c[0]] for c in change['coordinates']]
                
                color = priority_colors.get(change['priority'], '#6b7280')
                
                poly = folium.Polygon(
                    locations=folium_coords,
                    popup=folium.Popup(
                        landuse_analyzer.create_change_popup_html(change),
                        max_width=320
                    ),
                    tooltip=f"🏗️ {change['from_class']} → {change['to_class']} ({change['priority']}) - Klik untuk detail",
                    color=color,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.6,
                    weight=2
                )
                
                # Add AI Badge to popup if verified
                if 'ai_validation' in change:
                    ai = change['ai_validation']
                    if ai['verified']:
                        folium.Marker(
                           location=folium_coords[0],
                           icon=folium.Icon(color='green', icon='check', prefix='fa'),
                           tooltip=f"✅ AI Verified ({int(ai['confidence']*100)}%)"
                        ).add_to(m)

                poly.add_to(m)
        
        # Add legend
        m = add_map_legend(m, show_boundaries)
        
        components.html(m._repr_html_(), height=600)
        
        # Data table
        st.subheader("📋 Detail Perubahan Lahan")
        st.info(f"Status AI Engine: {ai_status_msg}")
        
        # Check if there are any changes
        if len(data['changes']) == 0:
            st.warning("⚠️ Tidak ada perubahan lahan terdeteksi di area yang dipilih.")
        else:
            df_changes = pd.DataFrame(data['changes'])
            
            # Extract AI data for display
            if len(data['changes']) > 0 and 'ai_validation' in data['changes'][0]:
                df_changes['AI Confidence'] = df_changes['ai_validation'].apply(lambda x: f"{int(x.get('confidence',0)*100)}%")
                df_changes['AI Status'] = df_changes['ai_validation'].apply(lambda x: x.get('status', '-'))
                
            df_changes_display = df_changes[['id', 'from_class', 'to_class', 'area_m2', 'priority', 'AI Confidence', 'AI Status']]
            st.dataframe(df_changes_display, use_container_width=True)
            
            # Charts
            col1, col2 = st.columns(2)
            with col1:
                # Change matrix
                change_matrix = df_changes.groupby(['from_class', 'to_class']).size().reset_index(name='count')
                fig_matrix = px.sunburst(
                    change_matrix,
                    path=['from_class', 'to_class'],
                    values='count',
                    title='Matriks Perubahan Lahan'
                )
                st.plotly_chart(fig_matrix, use_container_width=True)
            
            with col2:
                # Priority distribution
                priority_dist = df_changes['priority'].value_counts().reset_index()
                priority_dist.columns = ['priority', 'count']
                fig_priority = px.bar(
                    priority_dist,
                    x='priority',
                    y='count',
                    title='Distribusi Prioritas',
                    color='priority',
                    color_discrete_map=priority_colors
                )
                st.plotly_chart(fig_priority, use_container_width=True)

# ============================================
# TAB 3: MONITORING PBB
# ============================================
with tab3:
    st.header("🏢 Monitoring Perubahan Bangunan (PBB)")
    st.markdown(f"Deteksi perubahan bangunan: **{year_baseline}** → **{year_current}**")
    
    if st.button("🔍 Analisis Perubahan Bangunan", key="btn_pbb"):
        with st.spinner("Memproses data bangunan (Google Open Buildings)..."):
            # Monitor actual building changes
            pbb_data = pbb_monitor.monitor_building_changes(roi, year_baseline, year_current)
            
            st.session_state['pbb_data'] = pbb_data
    
    # Display results
    if 'pbb_data' in st.session_state:
        data = st.session_state['pbb_data']
        
        # Apply spatial filter (Always apply for boundary capping)
        if boundary_mgr:
            filtered_changes = boundary_mgr.spatial_filter(data['changes'], selected_district, selected_kelurahan, selected_lingkungan, selected_rt)
            data['changes'] = filtered_changes
            
            # Recalculate tax impact after filtering
            total_area = sum(b['area_increase'] for b in filtered_changes)
            total_tax = sum(b['tax_increase'] for b in filtered_changes)
            data['tax_impact'] = {
                'total_buildings_changed': len(filtered_changes),
                'total_area_increase_m2': total_area,
                'total_tax_increase_annual': total_tax,
                'avg_tax_increase_per_building': total_tax / len(filtered_changes) if filtered_changes else 0
            }
        
        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🏢 Bangunan Berubah", f"{data['tax_impact']['total_buildings_changed']} unit")
        col2.metric("📏 Total Penambahan Area", f"{int(data['tax_impact']['total_area_increase_m2']):,} m²")
        col3.metric("💰 Kenaikan PBB/Tahun", f"Rp {int(data['tax_impact']['total_tax_increase_annual']):,}")
        col4.metric("📊 Rata-rata/Bangunan", f"Rp {int(data['tax_impact']['avg_tax_increase_per_building']):,}")
        
        # Map
        st.subheader("🗺️ Peta Perubahan Bangunan")
        
        # Create map with user-selected background
        m = create_map_with_controls(
            district_config['lat'],
            district_config['lon'],
            15,
            map_background,
            show_boundaries
        )
        
        # Add boundary overlay if enabled
        if show_boundaries:
            m = add_boundary_overlay(m, selected_district, selected_kelurahan, selected_lingkungan, selected_rt, boundary_opacity)
        
        # Add building changes
        for building in data['changes']:
            if building['coordinates']:
                folium_coords = [[c[1], c[0]] for c in building['coordinates']]
                
                # Color based on change type
                if 'height_increase' in building['change_type']:
                    color = '#8b5cf6'  # Purple for height
                else:
                    color = '#3b82f6'  # Blue for area
                
                folium.Polygon(
                    locations=folium_coords,
                    popup=folium.Popup(
                        pbb_monitor.create_building_change_popup_html(building),
                        max_width=340
                    ),
                    tooltip=f"🏢 {building['id']} - Area: +{building['area_increase']:.0f}m², Height: +{building['height_increase']:.0f}m",
                    color=color,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.6,
                    weight=2
                ).add_to(m)
        
        # Add legend
        m = add_map_legend(m, show_boundaries)
        
        components.html(m._repr_html_(), height=600)
        
        # Data table
        st.subheader("📋 Detail Perubahan Bangunan")
        if len(data['changes']) == 0:
            st.warning("⚠️ Tidak ada perubahan bangunan terdeteksi di area yang dipilih.")
        else:
            df_buildings = pd.DataFrame(data['changes'])
            df_buildings_display = df_buildings[['id', 'old_area', 'new_area', 'area_increase', 'old_height', 'new_height', 'height_increase']]
            st.dataframe(df_buildings_display, use_container_width=True)
            
            # Charts
            col1, col2 = st.columns(2)
            with col1:
                fig_area = px.scatter(
                    df_buildings,
                    x='old_area',
                    y='new_area',
                    size='area_increase',
                    color='height_increase',
                    title='Sebaran Perubahan Area vs Tinggi',
                    labels={
                        'old_area': 'Luas Awal (m²)',
                        'new_area': 'Luas Baru (m²)',
                        'area_increase': 'Penambahan Luas',
                        'height_increase': 'Penambahan Tinggi'
                    }
                )
                st.plotly_chart(fig_area, use_container_width=True)
            
            with col2:
                # Change type distribution
                change_types = []
                for building in data['changes']:
                    for ct in building['change_type']:
                        change_types.append(ct)
                
                df_types = pd.DataFrame({'type': change_types})
                type_counts = df_types['type'].value_counts().reset_index()
                type_counts.columns = ['type', 'count']
                
                fig_types = px.pie(
                    type_counts,
                    names='type',
                    values='count',
                    title='Distribusi Jenis Perubahan',
                    hole=0.4
                )
                st.plotly_chart(fig_types, use_container_width=True)

# ============================================
# TAB 4: DASHBOARD PAD KOMPREHENSIF
# ============================================
with tab4:
    st.header("📊 Dashboard PAD Komprehensif")
    st.markdown("Ringkasan semua potensi Pendapatan Asli Daerah")
    
    # Check if all data available
    has_parking = 'parking_data' in st.session_state
    has_landuse = 'landuse_data' in st.session_state
    has_pbb = 'pbb_data' in st.session_state
    
    if not (has_parking or has_landuse or has_pbb):
        st.info("ℹ️ Jalankan analisis di tab-tab sebelumnya untuk melihat dashboard komprehensif")
    else:
        # Aggregate metrics
        total_parking_revenue = st.session_state.get('parking_data', {}).get('estimated_revenue_annual', 0)
        total_landuse_revenue = st.session_state.get('landuse_data', {}).get('tax_potential', {}).get('total_annual', 0)
        total_pbb_increase = st.session_state.get('pbb_data', {}).get('tax_impact', {}).get('total_tax_increase_annual', 0)
        
        total_pad_potential = total_parking_revenue + total_landuse_revenue + total_pbb_increase
        
        # Main metrics
        st.subheader("💰 Total Potensi PAD")
        col1, col2, col3, col4 = st.columns(4)
        
        col1.metric(
            "🅿️ Retribusi Parkir",
            f"Rp {int(total_parking_revenue):,}",
            delta=f"{int(total_parking_revenue/TARGET_PAD_ANNUAL['parking']*100)}% dari target" if total_parking_revenue > 0 else None
        )
        
        col2.metric(
            "🏗️ Pajak Baru (Alih Fungsi)",
            f"Rp {int(total_landuse_revenue):,}",
            delta=f"{int(total_landuse_revenue/TARGET_PAD_ANNUAL['land_change']*100)}% dari target" if total_landuse_revenue > 0 else None
        )
        
        col3.metric(
            "🏢 Kenaikan PBB",
            f"Rp {int(total_pbb_increase):,}",
            delta=f"{int(total_pbb_increase/TARGET_PAD_ANNUAL['pbb']*100)}% dari target" if total_pbb_increase > 0 else None
        )
        
        col4.metric(
            "💎 TOTAL POTENSI",
            f"Rp {int(total_pad_potential):,}",
            delta="Per Tahun"
        )
        
        # Visualization
        st.subheader("📈 Visualisasi PAD")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Pie chart
            pad_breakdown = pd.DataFrame({
                'Kategori': ['Retribusi Parkir', 'Pajak Baru', 'Kenaikan PBB'],
                'Nilai': [total_parking_revenue, total_landuse_revenue, total_pbb_increase]
            })
            
            fig_pie = px.pie(
                pad_breakdown,
                names='Kategori',
                values='Nilai',
                title='Komposisi Potensi PAD',
                hole=0.4,
                color_discrete_sequence=['#FFD700', '#ef4444', '#3b82f6']
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            # Bar chart vs target
            target_comparison = pd.DataFrame({
                'Kategori': ['Parkir', 'Alih Fungsi', 'PBB'],
                'Potensi': [total_parking_revenue, total_landuse_revenue, total_pbb_increase],
                'Target': [TARGET_PAD_ANNUAL['parking'], TARGET_PAD_ANNUAL['land_change'], TARGET_PAD_ANNUAL['pbb']]
            })
            
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(name='Potensi Terdeteksi', x=target_comparison['Kategori'], y=target_comparison['Potensi']))
            fig_bar.add_trace(go.Bar(name='Target Tahunan', x=target_comparison['Kategori'], y=target_comparison['Target']))
            fig_bar.update_layout(title='Potensi vs Target PAD', barmode='group')
            
            st.plotly_chart(fig_bar, use_container_width=True)
            
        # Export Report Button
        st.markdown("---")
        st.subheader("📑 Export Laporan BAPENDA")
        
        col_dl1, col_dl2 = st.columns([2, 1])
        with col_dl1:
            st.info("Unduh laporan lengkap dalam format Excel (.xlsx) dengan tabel 3 arah (Pivot Table) untuk analisis mendalam per Kecamatan, Kelurahan, hingga Lingkungan.")
        
        with col_dl2:
            if st.button("📥 Generate Excel Report"):
                with st.spinner("Menyiapkan Laporan 3 Arah..."):
                    try:
                        report_gen = BKDReportGenerator(boundary_mgr)
                        
                        # Get data from session state safely
                        p_data = st.session_state.get('parking_data', {})
                        l_data = st.session_state.get('landuse_data', {})
                        pbb_data = st.session_state.get('pbb_data', {})
                        
                        years_info = {
                            'start': year_baseline,
                            'end': year_current
                        }
                        excel_file = report_gen.generate_excel(p_data, l_data, pbb_data, years_info)
                        
                        st.download_button(
                            label="⬇️ Download Laporan (.xlsx)",
                            data=excel_file,
                            file_name=f"Laporan_Analisis_PAD_Mataram_{year_current}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                        st.success("Laporan siap diunduh!")
                        
                    except Exception as e:
                        st.error(f"Gagal membuat laporan: {str(e)}")
        
        # Summary table
        st.subheader("📋 Ringkasan Detail")
        
        summary_data = []
        
        if has_parking:
            parking = st.session_state['parking_data']
            summary_data.append({
                'Kategori': 'Retribusi Parkir',
                'Jumlah Objek': parking['count'],
                'Total Luas (m²)': int(parking['total_area_m2']),
                'Potensi PAD (Rp/tahun)': int(parking['estimated_revenue_annual']),
                'Status': '✅ Teranalisis'
            })
        
        if has_landuse:
            landuse = st.session_state['landuse_data']
            summary_data.append({
                'Kategori': 'Alih Fungsi Lahan',
                'Jumlah Objek': landuse['tax_potential']['total_changes'],
                'Total Luas (m²)': sum(c['area_m2'] for c in landuse['changes']),
                'Potensi PAD (Rp/tahun)': int(landuse['tax_potential']['total_annual']),
                'Status': '✅ Teranalisis'
            })
        
        if has_pbb:
            pbb = st.session_state['pbb_data']
            summary_data.append({
                'Kategori': 'Perubahan Bangunan (PBB)',
                'Jumlah Objek': pbb['tax_impact']['total_buildings_changed'],
                'Total Luas (m²)': int(pbb['tax_impact']['total_area_increase_m2']),
                'Potensi PAD (Rp/tahun)': int(pbb['tax_impact']['total_tax_increase_annual']),
                'Status': '✅ Teranalisis'
            })
        
        df_summary = pd.DataFrame(summary_data)
        st.dataframe(df_summary, use_container_width=True)
        
        # Recommendations
        st.subheader("💡 Rekomendasi Tindak Lanjut")
        
        recommendations = []
        
        if has_parking and total_parking_revenue > 0:
            recommendations.append("🅿️ **Parkir**: Lakukan survey lapangan untuk validasi lokasi parkir yang terdeteksi")
        
        if has_landuse:
            landuse = st.session_state['landuse_data']
            high_priority = landuse['tax_potential']['high_priority_changes']
            if high_priority > 0:
                recommendations.append(f"🏗️ **Alih Fungsi**: Prioritaskan verifikasi {high_priority} area dengan prioritas TINGGI")
        
        if has_pbb and total_pbb_increase > 0:
            recommendations.append("🏢 **PBB**: Update database SISMIOP dengan data perubahan bangunan")
        
        for idx, rec in enumerate(recommendations, 1):
            st.markdown(f"{idx}. {rec}")

# ============================================
# TAB 5: LAPORAN & EXPORT
# ============================================
with tab5:
    st.header("📄 Laporan & Export Data")
    st.markdown("Download hasil analisis dalam berbagai format")
    
    # Check data availability
    has_data = any([
        'parking_data' in st.session_state,
        'landuse_data' in st.session_state,
        'pbb_data' in st.session_state
    ])
    
    if not has_data:
        st.warning("⚠️ Belum ada data untuk di-export. Jalankan analisis terlebih dahulu.")
    else:
        st.success("✅ Data tersedia untuk export")
        
        # Export options
        st.subheader("📥 Pilih Format Export")
        
        col1, col2, col3 = st.columns(3)
        
        # CSV Export
        with col1:
            if st.button("📊 Export ke CSV", use_container_width=True):
                # Combine all data
                all_data = []
                
                if 'parking_data' in st.session_state:
                    df_parking = pd.DataFrame(st.session_state['parking_data']['parking_areas'])
                    df_parking['kategori'] = 'Parkir'
                    all_data.append(df_parking)
                
                if 'landuse_data' in st.session_state:
                    df_landuse = pd.DataFrame(st.session_state['landuse_data']['changes'])
                    df_landuse['kategori'] = 'Alih Fungsi Lahan'
                    all_data.append(df_landuse)
                
                if 'pbb_data' in st.session_state:
                    df_pbb = pd.DataFrame(st.session_state['pbb_data']['changes'])
                    df_pbb['kategori'] = 'Perubahan Bangunan'
                    all_data.append(df_pbb)
                
                if all_data:
                    df_combined = pd.concat(all_data, ignore_index=True)
                    csv = df_combined.to_csv(index=False).encode('utf-8')
                    
                    st.download_button(
                        label="⬇️ Download CSV",
                        data=csv,
                        file_name=f'bkd_pad_report_{selected_district}_{datetime.now().strftime("%Y%m%d")}.csv',
                        mime='text/csv'
                    )
        
        # Excel Export
        with col2:
            if st.button("📗 Export ke Excel", use_container_width=True):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    if 'parking_data' in st.session_state:
                        df_parking = pd.DataFrame(st.session_state['parking_data']['parking_areas'])
                        df_parking.to_excel(writer, sheet_name='Parkir', index=False)
                    
                    if 'landuse_data' in st.session_state:
                        df_landuse = pd.DataFrame(st.session_state['landuse_data']['changes'])
                        df_landuse.to_excel(writer, sheet_name='Alih Fungsi Lahan', index=False)
                    
                    if 'pbb_data' in st.session_state:
                        df_pbb = pd.DataFrame(st.session_state['pbb_data']['changes'])
                        df_pbb.to_excel(writer, sheet_name='Perubahan Bangunan', index=False)
                
                excel_data = output.getvalue()
                
                st.download_button(
                    label="⬇️ Download Excel",
                    data=excel_data,
                    file_name=f'bkd_pad_report_{selected_district}_{datetime.now().strftime("%Y%m%d")}.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
        
        # JSON Export
        with col3:
            if st.button("📋 Export ke JSON", use_container_width=True):
                import json
                
                export_data = {
                    'metadata': {
                        'district': selected_district,
                        'year_baseline': year_baseline,
                        'year_current': year_current,
                        'export_date': datetime.now().isoformat()
                    },
                    'parking': st.session_state.get('parking_data', {}),
                    'landuse': st.session_state.get('landuse_data', {}),
                    'pbb': st.session_state.get('pbb_data', {})
                }
                
                json_str = json.dumps(export_data, indent=2, ensure_ascii=False)
                
                st.download_button(
                    label="⬇️ Download JSON",
                    data=json_str,
                    file_name=f'bkd_pad_report_{selected_district}_{datetime.now().strftime("%Y%m%d")}.json',
                    mime='application/json'
                )
        
        # Preview data
        st.subheader("👁️ Preview Data")
        
        preview_option = st.selectbox(
            "Pilih data untuk preview:",
            ["Parkir", "Alih Fungsi Lahan", "Perubahan Bangunan"]
        )
        
        if preview_option == "Parkir" and 'parking_data' in st.session_state:
            df = pd.DataFrame(st.session_state['parking_data']['parking_areas'])
            st.dataframe(df, use_container_width=True)
        
        elif preview_option == "Alih Fungsi Lahan" and 'landuse_data' in st.session_state:
            df = pd.DataFrame(st.session_state['landuse_data']['changes'])
            st.dataframe(df, use_container_width=True)
        
        elif preview_option == "Perubahan Bangunan" and 'pbb_data' in st.session_state:
            df = pd.DataFrame(st.session_state['pbb_data']['changes'])
            st.dataframe(df, use_container_width=True)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #6b7280; font-size: 12px;'>
    <p>Sistem Monitoring PAD - Badan Keuangan Daerah Kota Mataram</p>
    <p>Powered by Google Earth Engine, Sentinel-2, Dynamic World | Data: Real-time</p>
</div>
""", unsafe_allow_html=True)
