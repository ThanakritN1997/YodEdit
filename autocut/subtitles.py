"""สร้างซับไตเติล: .ass (เบิร์นลงวิดีโอ มีลูกเล่น) และ .srt (อัปโหลดแยก)

สไตล์ซับ
  pop      ขึ้นทีละ 1-3 คำ ตัวใหญ่ คำที่กำลังพูดเด้งขึ้นเป็นสีเหลือง (แบบคลิปไวรัล)
  karaoke  ขึ้นทั้งวลี ไฮไลต์คำที่กำลังพูด
  box      ตัวหนังสือบนกล่องพื้นหลัง อ่านง่ายทุกพื้นภาพ
"""
import re

STYLES = ("pop", "karaoke", "box")

# สีในรูปแบบ ASS คือ &HAABBGGRR (BGR กลับด้านจาก RGB)
YELLOW = "&H0000E6FF&"
GREEN = "&H0084DC3D&"

EMPHASIS = {
    "มาก", "ที่สุด", "สุด", "ฟรี", "ห้าม", "สำคัญ", "ลด", "เพิ่ม", "ใหม่", "ง่าย", "เร็ว",
    "ถูก", "แพง", "เงิน", "บาท", "ทันที", "เทคนิค", "เคล็ดลับ", "ความลับ", "จริง", "ปัง",
    "เด็ด", "ดีมาก", "แนะนำ", "พิเศษ", "โปร", "รีวิว", "ฉ่ำ", "เป๊ะ", "ว้าว",
    "free", "best", "new", "never", "always", "secret", "must", "wow",
}

# สระ/วรรณยุกต์ไทยที่ซ้อนบนล่าง ไม่กินความกว้าง
_COMBINING = re.compile("[ัิ-ฺ็-๎]")


def visible_len(text):
    return len(_COMBINING.sub("", text.strip()))


def is_keyword(text):
    t = text.strip().lower()
    return bool(re.search(r"\d", t)) or t in EMPHASIS


def layout_for(width, height, style="pop"):
    """ขนาดตัวอักษร / ตำแหน่ง / จำนวนตัวอักษรต่อบรรทัด ตามสัดส่วนจอและสไตล์"""
    vertical = height > width * 1.1
    landscape = width > height * 1.1
    scale = {"pop": 1.0, "karaoke": 0.8, "box": 0.75}[style]
    if vertical:
        size, margin = height * 0.062 * scale, height * 0.30   # หลบปุ่มด้านล่างของ TikTok/Reels
    elif landscape:
        size, margin = height * 0.085 * scale, height * 0.08
    else:
        size, margin = height * 0.075 * scale, height * 0.14
    size = round(size)
    max_chars = max(6, int(width * 0.84 / (size * 0.56)))
    max_words = {"pop": 3, "karaoke": 7, "box": 5}[style]
    return {"size": size, "margin_v": round(margin), "max_chars": max_chars, "max_words": max_words}


def chunk_words(words, max_chars, max_words=6, max_gap=0.5):
    """จัดคำเป็นกลุ่มสั้น ๆ ไม่ข้ามประโยค และไม่ข้ามช่วงหยุดพูด"""
    chunks, cur, chars = [], [], 0
    for w in words:
        n = visible_len(w["text"])
        if cur and (
            chars + n > max_chars
            or len(cur) >= max_words
            or w["start"] - cur[-1]["end"] > max_gap
            or w.get("seg") != cur[-1].get("seg")
        ):
            chunks.append(cur)
            cur, chars = [], 0
        cur.append(w)
        chars += n
    if cur:
        chunks.append(cur)
    return chunks


def _ass_time(t):
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _srt_time(t):
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _esc(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def _style_line(style, font, size):
    outline = max(3, size // 9)
    if style == "box":
        # BorderStyle 3 = กล่องทึบ, OutlineColour คือสีกล่อง, Outline คือระยะขอบกล่อง
        return (f"Style: Main,{font},{size},&H00FFFFFF,&H00FFFFFF,&H28101010,&H00000000,"
                f"-1,0,0,0,100,100,0,0,3,{max(8, size // 5)},0,2,60,60,{{mv}},1")
    shadow = 4 if style == "pop" else 2
    return (f"Style: Main,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,"
            f"-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,60,60,{{mv}},1")


def write_ass(words, path, width, height, font="Leelawadee UI", style="pop"):
    style = style if style in STYLES else "pop"
    lay = layout_for(width, height, style)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{_style_line(style, font, lay['size']).replace('{mv}', str(lay['margin_v']))}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    chunks = chunk_words(words, lay["max_chars"], lay["max_words"])
    lines = []
    for ci, chunk in enumerate(chunks):
        next_start = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else None
        chunk_end = chunk[-1]["end"] + 0.35
        if next_start is not None:
            chunk_end = min(chunk_end, next_start)
        for i, w in enumerate(chunk):
            start = w["start"]
            end = chunk[i + 1]["start"] if i + 1 < len(chunk) else chunk_end
            if end - start < 0.01:
                continue
            parts = []
            for j, x in enumerate(chunk):
                raw = x["text"]
                lead = " " if j > 0 and raw[:1].isspace() else ""
                txt = _esc(raw.strip())
                if j == i:  # คำที่กำลังพูด
                    if style == "pop":
                        txt = (f"{{\\c{YELLOW}\\fscx122\\fscy122\\t(0,110,\\fscx106\\fscy106)}}"
                               f"{txt}{{\\r}}")
                    else:
                        txt = f"{{\\c{YELLOW}}}{txt}{{\\r}}"
                elif is_keyword(x["text"]):
                    txt = f"{{\\c{GREEN}}}{txt}{{\\r}}"
                parts.append(lead + txt)
            intro = "{\\fad(40,0)}" if i == 0 else ""
            lines.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Main,,0,0,0,,{intro}{''.join(parts)}"
            )
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")


def write_srt(words, path, max_chars=32):
    out = []
    for n, chunk in enumerate(chunk_words(words, max_chars, max_words=12, max_gap=0.8), 1):
        text = "".join(w["text"] for w in chunk).strip()
        out.append(f"{n}\n{_srt_time(chunk[0]['start'])} --> {_srt_time(chunk[-1]['end'])}\n{text}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
