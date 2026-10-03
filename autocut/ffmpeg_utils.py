"""ตัวช่วยเรียก ffmpeg"""
import re
import shutil
import subprocess

_FFMPEG = None


def ffmpeg_bin() -> str:
    """หา ffmpeg จาก PATH ก่อน ถ้าไม่มีใช้ตัวที่มากับแพ็กเกจ imageio-ffmpeg"""
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    path = shutil.which("ffmpeg")
    if not path:
        try:
            import imageio_ffmpeg
            path = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError as e:
            raise RuntimeError(
                "ไม่พบ ffmpeg - ติดตั้งด้วย `pip install imageio-ffmpeg` "
                "หรือติดตั้ง ffmpeg ให้อยู่ใน PATH"
            ) from e
    _FFMPEG = path
    return path


def run(args, cwd=None, check=True) -> str:
    """รัน ffmpeg แล้วคืนค่า stderr (ffmpeg เขียน log ลง stderr)"""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", *map(str, args)]
    r = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and r.returncode != 0:
        raise RuntimeError("ffmpeg ล้มเหลว:\n" + r.stderr[-3000:])
    return r.stderr


def probe(path) -> dict:
    """อ่านความยาว ขนาดภาพ และเช็กว่ามีเสียงไหม (ไม่ต้องใช้ ffprobe)"""
    err = run(["-i", path], check=False)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if not m:
        raise RuntimeError("อ่านไฟล์วิดีโอไม่ได้:\n" + err[-1500:])
    duration = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    v = re.search(r"Stream.*Video:.*?(\d{2,5})x(\d{2,5})", err)
    width, height = (int(v[1]), int(v[2])) if v else (0, 0)
    # วิดีโอจากมือถือมักถ่ายแนวตั้งแต่เก็บเป็นแนวนอน + rotate 90
    rot = re.search(r"rotat\w*\s*[:=]\s*(-?\d+)", err)
    if rot and abs(int(rot[1])) % 180 == 90:
        width, height = height, width
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "has_video": bool(v),
        "has_audio": "Audio:" in err,
    }
