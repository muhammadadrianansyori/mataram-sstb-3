@echo off
REM Launcher untuk BKD PAD Monitoring System
REM Menjalankan aplikasi Streamlit

echo ========================================
echo BKD PAD Monitoring System
echo Kota Mataram
echo ========================================
echo.

REM Check if virtual environment exists
if exist ".venv_bkd\Scripts\activate.bat" goto venv
goto global

:venv
echo Mengaktifkan virtual environment (.venv_bkd)...
call .venv_bkd\Scripts\activate.bat
goto run

:global
echo Virtual environment tidak ditemukan.
echo Menggunakan Python global...
goto run

:run
echo.
echo Menjalankan aplikasi BKD...
echo.
echo Aplikasi akan terbuka di browser Anda.
echo Tekan Ctrl+C untuk menghentikan aplikasi.
echo.

REM Run Streamlit
python -m streamlit run app_bkd.py

pause

