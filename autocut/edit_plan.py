"""วางแผนการตัด: ตัดคำฟุ่มเฟือย, ไม่ตัดกลางคำ, ย่อให้พอดีเวลา, แบ่งช็อตสำหรับซูม"""
from .silence import merge, subtract

FILLERS = {
    "เอ่อ", "อ่า", "อืม", "เออ", "อ้า", "เอิ่ม", "อึ่ม", "อ่ะ",
    "um", "uh", "uhm", "erm", "hmm", "ah",
}


def _norm(text):
    return text.strip().lower().strip(".,!?…'\"")


def is_filler(w):
    return _norm(w["text"]) in FILLERS


def remove_fillers(keep, words, pad=0.03):
    cuts = [(w["start"] - pad, w["end"] + pad) for w in words if is_filler(w)]
    return [seg for seg in merge(subtract(keep, cuts)) if seg[1] - seg[0] >= 0.25]


def protect_words(keep, words, duration, before=0.06, after=0.12):
    """ไม่ให้ตัดกลางคำ และเก็บคำพูดเบา ๆ ที่การหาช่วงเงียบพลาดไป
    (Whisper ได้ยินคำนั้น แปลว่ามีคนพูดจริง)"""
    spans = [(max(0.0, w["start"] - before), min(duration, w["end"] + after))
             for w in words if not is_filler(w)]
    return merge(list(keep) + spans, gap=0.3)


def _clip(segments, s, e):
    return [(max(a, s), min(b, e)) for a, b in segments if b > s and a < e]


def fit_to_target(keep, words, target, sentences=None):
    """ถ้ายาวเกินเวลาที่ต้องการ ตัดออกทีละ "ประโยค" (ไม่ตัดครึ่งประโยค)
    เก็บประโยคแรก (เปิดเรื่อง) และประโยคสุดท้าย (ปิดท้าย) ไว้เสมอ
    ที่เหลือเลือกประโยคที่พูดหนาแน่นที่สุด แล้วเรียงตามลำดับเวลาเดิม"""
    total = sum(e - s for s, e in keep)
    if not target or total <= target:
        return keep

    if sentences:
        units = []
        for i, sen in enumerate(sentences):
            parts = _clip(keep, sen["start"] - 0.12, sen["end"] + 0.22)
            length = sum(b - a for a, b in parts)
            if length <= 0:
                continue
            n = sum(1 for w in words if w.get("seg") == i)
            score = n / length * (1.0 if length >= 1.0 else 0.4)
            units.append({"parts": parts, "len": length, "score": score, "i": len(units)})
    else:  # ไม่มีข้อความ ใช้ช่วงเสียงแทน
        units = [{"parts": [seg], "len": seg[1] - seg[0], "score": 1.0, "i": i}
                 for i, seg in enumerate(keep)]
    if not units:
        return keep

    must = {units[0]["i"], units[-1]["i"]} if len(units) > 2 else set()
    chosen, used = set(), 0.0
    for u in sorted(units, key=lambda u: (u["i"] not in must, -u["score"])):
        if used + u["len"] <= target:
            chosen.add(u["i"])
            used += u["len"]
    if not chosen:
        best = max(units, key=lambda u: u["score"])
        s = best["parts"][0][0]
        return [(s, s + target)]
    picked = [p for u in units if u["i"] in chosen for p in u["parts"]]
    return merge(picked, gap=0.3)  # ช่องว่างสั้นมากไม่ต้องตัด จะได้ไม่กระตุก


def make_shots(keep, sentences=None, zoom=True, zoom_amount=1.15, min_shot=3.0):
    """1 ช็อตต่อ 1 จุดตัด ถ้าช่วงยาวจะแบ่งช็อตตรงต้นประโยคใหม่ (ไม่แบ่งกลางประโยค)
    สลับสไตล์ซูม: ค่อย ๆ ดันเข้าเบา ๆ  <->  ซูมใกล้ (punch-in) แล้วค่อย ๆ เข้าต่อ
    คืนค่า shots และเวลาที่มีการตัดจริง (สำหรับใส่ SFX)"""
    starts = sorted(s["start"] for s in (sentences or []))
    shots, cut_times, out_t = [], [], 0.0
    for i, (s, e) in enumerate(keep):
        if i > 0:
            cut_times.append(out_t)
        bounds = [s]
        for t in starts:
            if bounds[-1] + min_shot <= t <= e - min_shot:
                bounds.append(t - 0.08)
        bounds.append(e)
        for a, b in zip(bounds, bounds[1:]):
            if zoom:
                punch = len(shots) % 2 == 1
                z0 = zoom_amount if punch else 1.0
                z1 = z0 + (0.04 if punch else 0.06)
            else:
                z0 = z1 = 1.0
            shots.append({"start": a, "end": b, "zoom_from": z0, "zoom_to": z1})
            out_t += b - a
    return shots, cut_times


def remap_words(words, keep):
    """แปลงเวลาของคำจากวิดีโอต้นฉบับ เป็นเวลาในวิดีโอที่ตัดแล้ว"""
    out, offset = [], 0.0
    for s, e in keep:
        for w in words:
            mid = (w["start"] + w["end"]) / 2
            if s <= mid <= e and not is_filler(w):
                out.append({
                    "start": max(w["start"], s) - s + offset,
                    "end": min(w["end"], e) - s + offset,
                    "text": w["text"],
                    "seg": w.get("seg", 0),
                })
        offset += e - s
    return out
