@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem ดาวน์โหลด Thonburian Whisper (biodatlab/distill-whisper-th-large-v3) แล้วแปลงให้ใช้กับ faster-whisper
rem ทำครั้งเดียว ใช้พื้นที่ดาวน์โหลดประมาณ 3.5 GB ผลลัพธ์ประมาณ 800 MB
if exist models\whisper-th-distill-large-v3\model.bin (
  echo มีโมเดลภาษาไทยอยู่แล้ว
  goto :eof
)
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install transformers
.venv\Scripts\ct2-transformers-converter --model biodatlab/distill-whisper-th-large-v3 --output_dir models\whisper-th-distill-large-v3 --quantization int8 --copy_files tokenizer.json preprocessor_config.json
