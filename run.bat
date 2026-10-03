@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  echo กำลังสร้าง virtual environment และติดตั้งแพ็กเกจ - ครั้งแรกเท่านั้น...
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
echo เปิดเบราว์เซอร์ที่ http://localhost:8000
start "" http://localhost:8000
.venv\Scripts\python -m uvicorn server:app --port 8000
