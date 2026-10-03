"""สร้างแทร็กเสียง SFX (whoosh ตอนเปลี่ยนช็อต) ด้วยการสังเคราะห์เสียง
ไม่ต้องใช้ไฟล์เสียงภายนอก จึงไม่มีปัญหาลิขสิทธิ์"""
import math
import random
import wave
from array import array

RATE = 48000


def _whoosh(duration=0.4, volume=0.35):
    """เสียงลมวูบ: noise ผ่าน low-pass ที่กวาดความถี่ขึ้นแล้วลง"""
    n = int(RATE * duration)
    rnd = random.Random(7)
    y, out = 0.0, []
    for i in range(n):
        p = i / n
        env = math.sin(math.pi * p) ** 2
        alpha = 0.02 + 0.35 * math.sin(math.pi * p)  # ยิ่งมาก เสียงยิ่งแหลม
        y += alpha * (rnd.uniform(-1, 1) - y)
        out.append(y * env * volume * 2.2)
    return out


def write_sfx_track(path, duration, cut_times, min_gap=3.0, volume=0.35):
    total = int(RATE * (duration + 1))
    track = array("h", bytes(2 * total))  # 16-bit เงียบทั้งแทร็ก
    sound = _whoosh(volume=volume)
    lead = int(RATE * 0.15)  # ให้เสียงพีคตรงจังหวะตัดพอดี

    last = -min_gap
    for t in cut_times:
        if t - last < min_gap:
            continue
        last = t
        start = max(0, int(RATE * t) - lead)
        for i, v in enumerate(sound):
            if start + i < total:
                mixed = track[start + i] + int(v * 32767)
                track[start + i] = max(-32768, min(32767, mixed))

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(track.tobytes())
