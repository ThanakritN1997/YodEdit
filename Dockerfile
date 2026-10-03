# YodEdit - ใช้ได้กับ Hugging Face Spaces, Render, Railway, VPS
#   docker build -t yodedit .
#   docker run -p 7860:7860 yodedit

# ---------- ขั้นที่ 1: แปลงโมเดลถอดเสียงภาษาไทย (Thonburian Whisper) ----------
# ใช้ torch แค่ตอนแปลง ไม่ติดไปกับ image จริง
FROM python:3.11-slim AS model
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir transformers ctranslate2==4.8.2
RUN ct2-transformers-converter --model biodatlab/distill-whisper-th-large-v3 \
      --output_dir /models/whisper-th-distill-large-v3 --quantization int8 \
      --copy_files tokenizer.json preprocessor_config.json \
 && rm -rf /root/.cache/huggingface

# ---------- ขั้นที่ 2: ตัวแอป ----------
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1 \
    PORT=7860 \
    YODEDIT_FONT=Kanit

# ฟอนต์ไทยสำหรับซับ (Kanit, Google Fonts / OFL) + ฟอนต์ไทยสำรองของระบบ
RUN apt-get update \
 && apt-get install -y --no-install-recommends fontconfig fonts-thai-tlwg curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && python -c "import pythainlp.corpus as c; c.thai_words()"

RUN mkdir -p fonts \
 && curl -fsSL -o fonts/Kanit-Bold.ttf https://github.com/google/fonts/raw/main/ofl/kanit/Kanit-Bold.ttf \
 && curl -fsSL -o fonts/Kanit-SemiBold.ttf https://github.com/google/fonts/raw/main/ofl/kanit/Kanit-SemiBold.ttf

COPY --from=model /models ./models
COPY . .
RUN mkdir -p jobs && chown -R user:user /app
USER user
ENV HOME=/home/user

EXPOSE 7860
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
