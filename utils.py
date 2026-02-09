import ee
import streamlit as st
import os
import json
from google.oauth2 import service_account

def initialize_gee():
    """
    Menginisialisasi Google Earth Engine dengan strategi fallback dan penanganan Streamlit Secrets.
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
                
                # Gunakan google-auth untuk membuat kredensial yang valid
                credentials = service_account.Credentials.from_service_account_info(sa_info)
                
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
        # Jika bukan di Streamlit Cloud atau secrets tidak ada, lanjut ke strategi berikutnya
        pass

    # Strategi 1: Cek environment variables (untuk deployment manual)
    if os.environ.get('GEE_SERVICE_ACCOUNT'):
        try:
            sa_info = json.loads(os.environ.get('GEE_SERVICE_ACCOUNT'))
            if 'private_key' in sa_info:
                sa_info['private_key'] = sa_info['private_key'].replace('\\n', '\n')
            credentials = service_account.Credentials.from_service_account_info(sa_info)
            ee.Initialize(credentials=credentials, project=sa_info.get('project_id'))
            st.success("✅ Terhubung via Environment Variable")
            return True
        except:
            pass

    # Strategi 2: Cek kredensial lokal (untuk development)
    try:
        # Coba inisialisasi default (gcloud auth)
        ee.Initialize(project="mataram-sstb")
        st.success("✅ Terhubung ke Google Earth Engine (Lokal/Default)")
        return True
    except Exception as e1:
        # Cek jika project tidak ditemukan
        if "project" in str(e1).lower():
            cred_path = os.path.expanduser("~/.config/earthengine/credentials")
            if os.path.exists(cred_path):
                try:
                    with open(cred_path, 'r') as f:
                        creds = json.load(f)
                        project = creds.get('project_id') or creds.get('project')
                        if project:
                            ee.Initialize(project=project)
                            st.success(f"✅ Terhubung menggunakan project: {project}")
                            return True
                except:
                    pass
        
        # Jika semua gagal, tampilkan panduan troubleshooting
        st.warning("⚠️ Earth Engine belum terkonfigurasi.")
        with st.expander("🔧 Cara Konfigurasi (Streamlit Cloud)"):
            st.markdown("""
            Untuk menjalankan di Streamlit Cloud, Anda perlu menambahkan **Secrets**:
            1. Buka Dashboard Streamlit Cloud -> Settings -> Secrets
            2. Tambahkan isi file JSON Service Account Anda seperti ini:
            ```toml
            [gee_service_account]
            type = "service_account"
            project_id = "your-project-id"
            private_key_id = "..."
            private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
            client_email = "..."
            client_id = "..."
            # ... tambahkan semua field dari JSON Anda
            ```
            **Penting:** Gunakan `\\n` (dua backslash) untuk karakter baris baru di dalam `private_key`.
            """)
        return False
