import ee
import streamlit as st
import os
import json
from google.oauth2 import service_account

def initialize_gee():
    """
    Menginisialisasi Google Earth Engine dengan strategi fallback dan penanganan Streamlit Secrets.
    Sangat penting: Menyertakan scopes Earth Engine secara eksplisit.
    """
    # Strategi 0: Cek Streamlit Secrets (Paling Utama untuk Cloud Deployment)
    try:
        if "gee_service_account" in st.secrets:
            try:
                # Ambil info service account dari secrets
                sa_info = dict(st.secrets["gee_service_account"])
                
                # Masalah umum di Streamlit: Karakter \n pada private_key sering ter-escape menjadi \\n
                if 'private_key' in sa_info:
                    sa_info['private_key'] = sa_info['private_key'].replace('\\n', '\n')
                
                # Tambahkan scope Earth Engine secara eksplisit agar tidak 'invalid_scope'
                scopes = ['https://www.googleapis.com/auth/earthengine']
                
                # Gunakan google-auth untuk membuat kredensial yang valid
                credentials = service_account.Credentials.from_service_account_info(
                    sa_info, 
                    scopes=scopes
                )
                
                # Inisialisasi dengan project_id yang ada di file JSON
                project_id = sa_info.get("project_id", "ee-streamlit-mataram")
                
                ee.Initialize(credentials=credentials, project=project_id)
                st.success(f"✅ Terhubung via Streamlit Secrets (Project: {project_id})")
                return True
                
            except Exception as e:
                st.error(f"❌ Autentikasi Gagal: {e}")
                st.code(f"Debug Info: {type(e).__name__}")
                return False
    except Exception as e:
        # Lanjut ke strategi berikutnya jika bukan di Streamlit Cloud
        pass

    # Strategi 1: Cek environment variables (untuk deployment manual lainnya)
    if os.environ.get('GEE_SERVICE_ACCOUNT'):
        try:
            sa_info = json.loads(os.environ.get('GEE_SERVICE_ACCOUNT'))
            if 'private_key' in sa_info:
                sa_info['private_key'] = sa_info['private_key'].replace('\\n', '\n')
            
            scopes = ['https://www.googleapis.com/auth/earthengine']
            credentials = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
            ee.Initialize(credentials=credentials, project=sa_info.get('project_id'))
            return True
        except:
            pass

    # Strategi 2: Cek kredensial lokal (untuk development di komputer sendiri)
    try:
        # Mencoba inisialisasi default (misal gcloud auth)
        ee.Initialize(project="mataram-sstb")
        return True
    except:
        return False

# Fungsi tambahan (jika diperlukan oleh modul lain)
def get_gee_status():
    """Mengecek apakah GEE sudah terinisialisasi"""
    try:
        ee.Projection('EPSG:4326')
        return True
    except:
        return False
