@echo off
echo ====================================================
echo AI Engine Setup - PAD Monitoring Kota Mataram
echo ====================================================
echo.
echo Sedang menyiapkan instalasi Deep Learning Tools...
echo Catatan: Proses ini memerlukan koneksi internet stabil 
echo dan penyimpanan sekitar 2-3 GB.
echo.

REM Check if virtual environment exists
if exist ".venv_bkd\Scripts\activate.bat" (
    echo Mengaktifkan virtual environment (.venv_bkd)...
    call .venv_bkd\Scripts\activate.bat
) else (
    echo Virtual environment tidak ditemukan.
    echo Menggunakan Python global...
)

REM Memastikan pip terupdate
python -m pip install --upgrade pip

echo.
echo [1/3] Menginstal PyTorch (Otak AI)...
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

echo.
echo [2/3] Menginstal Hugging Face Transformers...
python -m pip install transformers accelerate safetensors

echo.
echo [3/3] Menginstal Library Pendukung...
python -m pip install pillow opencv-python scikit-image


echo.
echo ====================================================
echo INSTALASI SELESAI
echo.
echo Sekarang modul AI High-Accuracy bisa digunakan di:
echo app_bkd.py
echo ====================================================
pause
