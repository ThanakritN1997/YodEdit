"""ถอดเสียงเป็นข้อความพร้อมเวลาระดับคำ (faster-whisper)"""
import os
import wave
from pathlib import Path

_MODELS = {}
THAI_MODEL = Path(__file__).resolve().parent.parent / "models" / "whisper-th-distill-large-v3"

# ช่วยให้ Whisper เขียนออกมาเป็นภาษาไทย ไม่หลุดเป็นภาษาอื่น
PROMPTS = {
    "th": "สวัสดีค่ะ วันนี้จะมารีวิวและแนะนำวิธีใช้งานแบบละเอียดนะคะ",
}


def load_audio(path):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0


def transcribe(audio_path, language="th", model_size="thai"):
    """คืนค่า {"language", "words": [{"start","end","text","seg"}], "sentences": [{"start","end","text"}]}
    หรือ None ถ้ายังไม่ได้ติดตั้ง faster-whisper"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None

    device = os.environ.get("AUTOCUT_DEVICE", "cpu")  # ตั้งเป็น cuda ถ้ามีการ์ดจอ NVIDIA
    if model_size == "thai" and language not in ("th", "", None):
        model_size = "large-v3-turbo"  # โมเดลไทยถอดได้แค่ภาษาไทย
    model_name = resolve_model(model_size)
    key = (model_name, device)
    if key not in _MODELS:
        compute = "float16" if device == "cuda" else "int8"
        _MODELS[key] = WhisperModel(model_name, device=device, compute_type=compute)
    model = _MODELS[key]

    # อ่าน wav 16 kHz เอง (pipeline แยกเสียงมาให้แล้ว) เลี่ยงปัญหา PyAV บางเวอร์ชัน
    segments, info = model.transcribe(
        load_audio(audio_path),
        language=language or None,
        word_timestamps=True,
        vad_filter=True,                    # ข้ามช่วงไม่มีเสียงพูด ลดการ "มโน" ข้อความ
        vad_parameters={"min_silence_duration_ms": 300},
        condition_on_previous_text=False,   # กันการพูดวนซ้ำ
        # โมเดลไทยฝึกมาแบบไม่มี prompt ใส่แล้วจะแย่ลง
        initial_prompt=None if model_size == "thai" else PROMPTS.get(language or ""),
        beam_size=5,
    )
    lang = info.language
    words = []
    for seg in segments:
        pieces = [{"start": float(w.start), "end": float(w.end), "text": w.word}
                  for w in (seg.words or [])]
        if pieces and lang == "th":
            pieces = retokenize_thai(pieces)
        words.extend(pieces)
    sentences = split_sentences(words)
    return {"language": lang, "words": words, "sentences": sentences}


def resolve_model(name):
    """"thai" = Thonburian Whisper (โมเดลที่ฝึกมาเพื่อภาษาไทยโดยเฉพาะ) ที่แปลงไว้ในโฟลเดอร์ models/"""
    if name == "thai":
        if THAI_MODEL.is_dir():
            return str(THAI_MODEL)
        return "large-v3-turbo"
    return name


# คำลงท้ายที่มักเป็นจุดจบประโยคภาษาไทย
ENDINGS = ("นะคะ", "ค่ะ", "คะ", "ครับ", "นะครับ", "จ้า", "นะ")


def split_sentences(words, pause=0.35, max_len=7.0, min_len=1.2):
    """แบ่งประโยคจากช่วงหยุดหายใจและคำลงท้าย (โมเดลภาษาไทยคืนมาเป็นก้อนยาว 30 วินาที)
    ใส่ "seg" (ลำดับประโยค) ให้แต่ละคำด้วย"""
    sentences, cur = [], []

    def close():
        if cur:
            sentences.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                              "text": "".join(w["text"] for w in cur).strip()})

    for w in words:
        if cur:
            gap = w["start"] - cur[-1]["end"]
            length = cur[-1]["end"] - cur[0]["start"]
            ended = cur[-1]["text"].strip() in ENDINGS and length >= min_len
            if gap >= pause or ended or (length >= max_len and gap >= 0.12) or length >= max_len * 1.5:
                close()
                cur = []
        w["seg"] = len(sentences)
        cur.append(w)
    close()
    return sentences


_DICT = None
# คำในพจนานุกรมที่ทำให้ตัดคำผิดบ่อย เช่น "บอกว่า" -> "บอ|กว่า"
_BAD_WORDS = {"บอ"}
# คำพูดทั่วไปในคลิปที่พจนานุกรมไม่มี
_EXTRA_WORDS = {"เนี้ย", "มาร์ค", "รีวิว", "เซิร์ช", "น้ำตบ", "สกินแคร์", "เซรั่ม", "คลิป", "ไลฟ์", "ฟอลโล่"}


def _thai_dict():
    global _DICT
    if _DICT is None:
        from pythainlp.corpus import thai_words
        from pythainlp.util import Trie
        _DICT = Trie((set(thai_words()) - _BAD_WORDS) | _EXTRA_WORDS)
    return _DICT


def retokenize_thai(pieces):
    """Whisper คืนภาษาไทยมาเป็นชิ้นระดับตัวอักษร (เช่น "เค", "ย") จึงต้อง
    ต่อเป็นข้อความ บันทึกเวลาของแต่ละตัวอักษร แล้วตัดคำใหม่ด้วย PyThaiNLP"""
    text, starts, ends = "", [], []
    for p in pieces:
        t = p["text"]
        if not t:
            continue
        span = (p["end"] - p["start"]) / len(t)
        for k in range(len(t)):
            starts.append(p["start"] + span * k)
            ends.append(p["start"] + span * (k + 1))
        text += t

    try:
        from pythainlp.tokenize import word_tokenize
        tokens = word_tokenize(text, custom_dict=_thai_dict(), engine="newmm", keep_whitespace=True)
    except ImportError:
        tokens = text.split(" ")
        tokens = [x for tok in tokens for x in (tok, " ")][:-1]
    if "".join(tokens) != text:  # กันกรณีตัดคำแล้วข้อความไม่ตรงกัน
        return pieces

    out, pos, space = [], 0, False
    for tok in tokens:
        n = len(tok)
        if tok.isspace():
            space, pos = True, pos + n
            continue
        out.append({
            "start": starts[pos], "end": ends[pos + n - 1],
            "text": (" " if space and out else "") + tok,
        })
        space, pos = False, pos + n
    return out
