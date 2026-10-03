"""เว็บเซิร์ฟเวอร์ YodEdit
รัน:  python -m uvicorn server:app --port 8000   แล้วเปิด http://localhost:8000
"""
import json
import os
import queue
import shutil
import threading
import time
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from autocut.pipeline import Options, process

BASE = Path(__file__).resolve().parent
JOBS_DIR = BASE / "jobs"
JOBS_DIR.mkdir(exist_ok=True)
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
KEEP_HOURS = float(os.environ.get("KEEP_HOURS", "6"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "500"))

app = FastAPI(title="YodEdit")
jobs: dict[str, dict] = {}
job_queue: "queue.Queue[str]" = queue.Queue()


def cleanup_old_jobs():
    """ลบวิดีโอและผลลัพธ์ที่เก่ากว่า KEEP_HOURS ชั่วโมง ไม่ให้พื้นที่เต็ม"""
    cutoff = time.time() - KEEP_HOURS * 3600
    for d in JOBS_DIR.iterdir():
        if d.is_dir() and d.stat().st_mtime < cutoff and jobs.get(d.name, {}).get("status") != "running":
            shutil.rmtree(d, ignore_errors=True)
            jobs.pop(d.name, None)


def worker():
    """ประมวลผลทีละงานตามคิว (วิดีโอใช้ CPU หนัก ไม่ควรทำพร้อมกันหลายงาน)"""
    while True:
        job_id = job_queue.get()
        cleanup_old_jobs()
        job = jobs[job_id]
        job["status"] = "running"

        def progress(pct, msg):
            job["progress"] = round(pct, 1)
            job["message"] = msg

        try:
            job["result"] = process(job["input"], JOBS_DIR / job_id, job["options"], progress)
            job["status"] = "done"
        except Exception as e:  # noqa: BLE001 - ส่งข้อความผิดพลาดกลับไปให้หน้าเว็บ
            traceback.print_exc()
            job["status"] = "error"
            job["message"] = str(e)[-800:]
        finally:
            job_queue.task_done()


threading.Thread(target=worker, daemon=True).start()


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...), options: str = Form("{}")):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in VIDEO_EXT:
        raise HTTPException(400, "รองรับเฉพาะไฟล์วิดีโอ: " + ", ".join(sorted(VIDEO_EXT)))
    try:
        opts = Options.from_dict(json.loads(options))
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"ตัวเลือกไม่ถูกต้อง: {e}") from e

    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir()
    dst = job_dir / f"input{ext}"
    size, limit = 0, MAX_UPLOAD_MB * 1024 * 1024
    with open(dst, "wb") as f:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                f.close()
                shutil.rmtree(job_dir, ignore_errors=True)
                raise HTTPException(413, f"ไฟล์ใหญ่เกิน {MAX_UPLOAD_MB} MB")
            f.write(chunk)

    jobs[job_id] = {
        "status": "queued", "progress": 0, "message": "รอคิว",
        "input": str(dst), "options": opts, "result": None,
    }
    job_queue.put(job_id)
    return {"id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "ไม่พบงาน")
    return {k: job[k] for k in ("status", "progress", "message", "result")}


@app.get("/api/jobs/{job_id}/files/{name}")
def job_file(job_id: str, name: str):
    job = jobs.get(job_id)
    allowed = set()
    if job and job["result"]:
        for o in job["result"]["outputs"]:
            allowed.update(x for x in (o["video"], o["srt"]) if x)
    if name not in allowed:
        raise HTTPException(404, "ไม่พบไฟล์")
    return FileResponse(JOBS_DIR / job_id / name, filename=name)


app.mount("/", StaticFiles(directory=BASE / "static", html=True), name="static")
