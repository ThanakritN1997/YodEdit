"""เว็บเซิร์ฟเวอร์ YodEdit
รัน:  python -m uvicorn server:app --port 8000   แล้วเปิด http://localhost:8000
"""
import json
import queue
import shutil
import threading
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

app = FastAPI(title="YodEdit")
jobs: dict[str, dict] = {}
job_queue: "queue.Queue[str]" = queue.Queue()


def worker():
    """ประมวลผลทีละงานตามคิว (วิดีโอใช้ CPU หนัก ไม่ควรทำพร้อมกันหลายงาน)"""
    while True:
        job_id = job_queue.get()
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
    with open(dst, "wb") as f:
        shutil.copyfileobj(file.file, f, 1024 * 1024)

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
