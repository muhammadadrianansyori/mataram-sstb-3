# 🏛️ Sistem Monitoring PAD - BKD Kota Mataram

## 🎯 Deskripsi Sistem

Sistem monitoring **Pendapatan Asli Daerah (PAD)** berbasis satelit dan big data untuk **Badan Keuangan Daerah (BKD)** Kota Mataram. Sistem ini menggunakan teknologi geospasial modern untuk:

1. **🅿️ Monitoring Lahan Parkir** - Deteksi area parkir dan kalkulasi potensi retribusi
2. **🏗️ Analisis Alih Fungsi Lahan** - Tracking perubahan land use untuk identifikasi objek pajak baru
3. **🏢 Monitoring PBB** - Deteksi perubahan bangunan (tinggi & luas) untuk update nilai pajak

---

## 🚀 Quick Start

### Cara Termudah (Recommended):
```bash
# Klik 2x file ini:
start_bkd.bat
```

Aplikasi akan terbuka di browser secara otomatis di `http://localhost:8501`

---

## 📋 Fitur Utama

### 1. 🅿️ Tab Monitoring Lahan Parkir
- Deteksi otomatis area parkir dari citra satelit
- Estimasi kapasitas parkir (motor & mobil)
- Kalkulasi potensi retribusi parkir (harian, bulanan, tahunan)
- Peta interaktif dengan popup detail
- Export data ke CSV/Excel

**Metode:**
- Spectral analysis (NDBI untuk impervious surfaces)
- Texture filtering (parking lots memiliki pola khas)
- Exclude buildings (Google Open Buildings)
- Size/shape filtering

### 2. 🏗️ Tab Analisis Alih Fungsi Lahan
- Deteksi perubahan land cover temporal (2015-2025)
- Klasifikasi perubahan (vegetasi → bangunan, sawah → komersial, dll)
- Prioritas perubahan (HIGH/MEDIUM/LOW)
- Estimasi potensi pajak dari objek baru
- Change matrix visualization

**Metode:**
- Google Dynamic World (near real-time land cover, 10m resolution)
- Sentinel-2 time series
- Post-classification change detection

### 3. 🏢 Tab Monitoring PBB
- Deteksi perubahan luas bangunan (horizontal expansion)
- Deteksi perubahan tinggi bangunan (vertical expansion)
- Kalkulasi impact terhadap PBB
- Tracking perubahan per bangunan

**Metode:**
- Google Open Buildings V3
- ALOS World 3D DSM (Digital Surface Model)
- Temporal comparison

### 4. 🧠 AI Validator Module (Baru!)
- Validasi tingkat lanjut menggunakan **Deep Learning**
- Membedakan perubahan struktural (bangunan) vs seasonal (sawah/vegetasi)
- Menggunakan model **Prithvi-100M** (IBM/NASA)
- Mengurangi *false positives* pada deteksi alih fungsi lahan


### 4. 📊 Tab Dashboard PAD Komprehensif
- Agregasi semua potensi PAD
- Visualisasi pie chart & bar chart
- Perbandingan dengan target PAD
- Rekomendasi tindak lanjut

### 5. 📄 Tab Laporan & Export
- Export ke CSV, Excel, JSON
- Preview data sebelum download
- Metadata lengkap (kecamatan, periode, tanggal export)

---

## 🛠️ Teknologi Stack

### Data Sources (100% Open-Source & Gratis)
- **Google Earth Engine** - Platform cloud untuk analisis geospasial
- **Sentinel-2** - Satelit imagery 10m resolution (2015-sekarang)
- **Google Dynamic World** - Near real-time land cover classification
- **Google Open Buildings V3** - AI-detected building footprints
- **ALOS World 3D** - Digital Surface Model (30m resolution)

### Backend
- **Python 3.10+**
- **earthengine-api** - Google Earth Engine Python API
- **geemap** - GEE wrapper untuk Python
- **geopandas** - Spatial data processing
- **pandas** - Data manipulation

### Frontend
- **Streamlit** - Web dashboard framework
- **folium** - Interactive maps
- **plotly** - Interactive charts
- **openpyxl** - Excel export

---

## ⚙️ Konfigurasi

### Tarif & Parameter (File: `config/bkd_config.py`)

Saat ini menggunakan **data dummy** untuk development. Untuk production, update dengan data real dari BKD:

```python
# Tarif Retribusi Parkir
PARKING_TARIFF = {
    'motor': {'hourly': 2000, 'daily': 10000, 'monthly': 50000},
    'mobil': {'hourly': 5000, 'daily': 25000, 'monthly': 150000},
    'bus': {'hourly': 10000, 'daily': 50000, 'monthly': 300000}
}

# Tarif PBB (% dari NJOP)
PBB_RATE = {
    'residential': 0.1,   # 0.1%
    'commercial': 0.2,    # 0.2%
    'industrial': 0.3     # 0.3%
}

# NJOP per Zona (Rp per m²)
NJOP_ZONE = {
    'pusat_kota': 3000000,
    'semi_pusat': 2000000,
    'pinggiran': 1000000,
    'rural': 500000
}
```

**Untuk update dengan data real:**
1. Buka `config/bkd_config.py`
2. Ganti nilai-nilai dummy dengan data dari BKD
3. Restart aplikasi

### Setup AI Engine (Opsional)
Untuk hasil yang lebih akurat (mengurangi false alarm di area persawahan), aktifkan modul AI:

```bash
# Jalankan installer:
install_ai.bat
```

*Note: Membutuhkan storage ~2-3GB untuk library PyTorch & Transformers.*


---

## 📊 Mode Data

Aplikasi memiliki 2 mode:

### 1. Mode Simulasi (Default)
- Menggunakan data dummy untuk demo
- Cepat dan tidak perlu koneksi GEE
- Cocok untuk presentasi dan testing
- **Aktifkan:** Centang "Gunakan Data Simulasi" di sidebar

### 2. Mode Real
- Menggunakan data real dari Google Earth Engine
- Membutuhkan autentikasi GEE
- Lebih lambat (processing di cloud)
- Hasil lebih akurat
- **Aktifkan:** Uncheck "Gunakan Data Simulasi" di sidebar

---

## 🗺️ Kecamatan yang Tersedia

Sistem sudah dikonfigurasi untuk 6 kecamatan di Kota Mataram:

1. **Ampenan** - Zona: Semi Pusat
2. **Cakranegara** - Zona: Pusat Kota
3. **Mataram** - Zona: Pusat Kota
4. **Selaparang** - Zona: Semi Pusat
5. **Sekarbela** - Zona: Semi Pusat
6. **Sandubaya** - Zona: Pinggiran

Pilih kecamatan di sidebar untuk fokus analisis.

---

## 📈 Workflow Penggunaan

### Untuk Analisis Rutin:
1. Pilih kecamatan di sidebar
2. Set periode analisis (tahun baseline & current)
3. Jalankan analisis di setiap tab:
   - Tab 1: Klik "🔍 Analisis Lahan Parkir"
   - Tab 2: Klik "🔍 Analisis Perubahan Lahan"
   - Tab 3: Klik "🔍 Analisis Perubahan Bangunan"
4. Lihat ringkasan di Tab 4 (Dashboard PAD)
5. Export hasil di Tab 5

### Untuk Presentasi:
1. Aktifkan "Gunakan Data Simulasi"
2. Pilih kecamatan yang menarik
3. Jalankan semua analisis
4. Screenshot peta dan chart untuk dokumentasi
5. Gunakan Tab 4 untuk overview

---

## 📥 Export Data

Sistem mendukung export dalam 3 format:

### 1. CSV
- Format: Comma-separated values
- Cocok untuk: Excel, Google Sheets, analisis data
- Encoding: UTF-8

### 2. Excel (.xlsx)
- Format: Multi-sheet workbook
- Sheet 1: Data Parkir
- Sheet 2: Data Alih Fungsi Lahan
- Sheet 3: Data Perubahan Bangunan

### 3. JSON
- Format: JavaScript Object Notation
- Cocok untuk: API integration, backup, archiving
- Include: Metadata lengkap (kecamatan, periode, tanggal)

---

## 🔧 Troubleshooting

### Aplikasi Tidak Terbuka
```bash
# Cek apakah Streamlit terinstall:
python -m streamlit --version

# Jika error, install dependencies:
pip install -r requirements.txt
```

### Error "Module not found"
```bash
# Install semua dependencies:
pip install -r requirements.txt

# Atau install satu per satu:
pip install streamlit earthengine-api geemap folium pandas plotly openpyxl
```

### Peta Tidak Muncul
- Refresh browser (F5)
- Clear browser cache
- Coba browser lain (Chrome recommended)

### GEE Authentication Error
```bash
# Re-authenticate:
python -m earthengine authenticate

# Atau gunakan mode simulasi (centang di sidebar)
```

### Data Tidak Muncul
- Pastikan sudah klik tombol "🔍 Analisis..."
- Tunggu proses selesai (ada spinner)
- Cek apakah ada error di console

---

## 💡 Tips Penggunaan

### Untuk BKD:
1. **Update Tarif Berkala** - Edit `config/bkd_config.py` sesuai peraturan terbaru
2. **Validasi Lapangan** - Gunakan koordinat dari popup untuk survey
3. **Export Rutin** - Simpan hasil analisis bulanan untuk tracking
4. **Prioritas Tinggi** - Fokus pada area dengan priority HIGH di tab alih fungsi lahan

### Untuk Presentasi:
1. **Gunakan Mode Simulasi** - Lebih cepat dan stabil
2. **Screenshot Peta** - Untuk dokumentasi
3. **Highlight Metrics** - Fokus pada angka potensi PAD
4. **Tampilkan Dashboard** - Tab 4 untuk overview komprehensif

### Untuk Development:
1. **Lihat Code** - Semua modul di folder `modules/`
2. **Custom Analysis** - Tambahkan fungsi di modul yang relevan
3. **Styling** - Edit CSS di `app_bkd.py`
4. **Testing** - Gunakan data dummy untuk testing cepat

---

## 📞 Struktur File

```
d:/bps/
├── app_bkd.py              # Main application (BKD version)
├── app.py                  # Old application (legacy)
├── start_bkd.bat           # Launcher untuk BKD app
├── start.bat               # Launcher untuk old app
├── utils.py                # GEE utilities
├── requirements.txt        # Python dependencies
│
├── config/
│   └── bkd_config.py       # Konfigurasi tarif & parameter
│
├── modules/
│   ├── __init__.py
│   ├── parking_detector.py     # Modul deteksi parkir
│   ├── landuse_analyzer.py     # Modul analisis alih fungsi lahan
│   └── pbb_monitor.py          # Modul monitoring PBB
│
└── [dokumentasi lainnya]
```

---

## 🎯 Roadmap & Future Enhancements

### Phase 1 (Current) ✅
- [x] Deteksi lahan parkir
- [x] Analisis alih fungsi lahan
- [x] Monitoring PBB
- [x] Dashboard komprehensif
- [x] Export data

### Phase 2 (Future)
- [ ] Integrasi dengan database SISMIOP
- [ ] API endpoint untuk integrasi sistem lain
- [ ] Mobile app (Android/iOS)
- [ ] Automated alerts (email/WhatsApp)
- [ ] Machine learning untuk prediksi PAD

### Phase 3 (Advanced)
- [ ] Drone imagery integration
- [ ] Real-time monitoring
- [ ] Citizen reporting integration
- [ ] Advanced analytics & forecasting

---

## 📄 Lisensi & Disclaimer

**Sistem ini adalah decision support tool**, bukan pengganti survey lapangan resmi.

- Hasil analisis perlu **diverifikasi** sebelum digunakan untuk penagihan pajak
- Data satelit memiliki **limitasi resolusi** (10-30m)
- Estimasi revenue adalah **potensi teoritis**, bukan actual
- Untuk keputusan legal, tetap diperlukan **validasi lapangan**

---

## 🙏 Credits

**Data Sources:**
- Google Earth Engine
- Sentinel-2 (ESA)
- Google Dynamic World
- Google Open Buildings V3
- JAXA ALOS World 3D

**Technologies:**
- Streamlit
- Folium
- Plotly
- GeoPandas

---

**Developed for:** Badan Keuangan Daerah Kota Mataram  
**Version:** 1.0 (Beta)  
**Last Updated:** 2026-02-05
