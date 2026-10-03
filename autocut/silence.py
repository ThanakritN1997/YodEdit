"""หาช่วงที่มีเสียงพูด (ตัดช่วงเงียบออก)"""
import re

from .ffmpeg_utils import run


def auto_noise_db(audio_path):
    """หาระดับ "เงียบ" จากตัวคลิปเอง: อยู่ระหว่างเสียงพื้นหลังกับเสียงพูด
    (ไมค์แต่ละตัว / ห้องแต่ละห้องดังไม่เท่ากัน ค่าตายตัวจึงตัดพลาดบ่อย)"""
    import numpy as np

    from .transcribe import load_audio
    a = load_audio(audio_path)
    frame = 800  # 50 ms ที่ 16 kHz
    n = len(a) // frame
    if n < 10:
        return -35.0
    rms = np.sqrt((a[: n * frame].reshape(n, frame) ** 2).mean(axis=1) + 1e-10)
    db = 20 * np.log10(rms)
    floor, speech = np.percentile(db, 10), np.percentile(db, 90)
    return float(np.clip(floor + 0.3 * (speech - floor), -55, -25))


def detect_speech(audio_path, duration, noise_db=0, min_silence=0.5,
                  pad_before=0.12, pad_after=0.22, min_keep=0.4):
    """คืนค่ารายการช่วงที่ควรเก็บไว้ [(start, end), ...] หน่วยวินาที

    noise_db    เสียงที่เบากว่านี้ถือว่าเงียบ (0 = หาค่าให้อัตโนมัติ)
    min_silence เงียบนานกว่านี้ถึงจะตัด
    pad_*       เว้นขอบไว้ไม่ให้เสียงขาดห้วน (ท้ายคำเสียงจะค่อย ๆ หาย จึงเว้นมากกว่า)
    """
    if not noise_db:
        noise_db = auto_noise_db(audio_path)
    err = run(["-i", audio_path, "-af",
               f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"])

    silences, start = [], None
    for line in err.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m[1]))
            continue
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            silences.append((start, float(m[1])))
            start = None
    if start is not None:
        silences.append((start, duration))

    keep, cur = [], 0.0
    for s, e in silences:
        if s > cur:
            keep.append((cur, s))
        cur = e
    if cur < duration:
        keep.append((cur, duration))

    padded = [(max(0.0, s - pad_before), min(duration, e + pad_after)) for s, e in keep]
    # ช่องว่างสั้น ๆ ไม่ต้องตัด เพราะตัดถี่เกินไปจะฟังดูกระตุก
    return [seg for seg in merge(padded, gap=0.3) if seg[1] - seg[0] >= min_keep]


def merge(segments, gap=0.05):
    out = []
    for s, e in sorted(segments):
        if out and s <= out[-1][1] + gap:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def subtract(segments, cuts):
    """เอาช่วง cuts ออกจาก segments"""
    out = []
    for s, e in segments:
        pieces = [(s, e)]
        for cs, ce in cuts:
            nxt = []
            for ps, pe in pieces:
                if ce <= ps or cs >= pe:
                    nxt.append((ps, pe))
                    continue
                if cs > ps:
                    nxt.append((ps, cs))
                if ce < pe:
                    nxt.append((ce, pe))
            pieces = nxt
        out.extend(pieces)
    return out
