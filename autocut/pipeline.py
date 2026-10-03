"""ขั้นตอนตัดต่ออัตโนมัติทั้งหมด"""
import json
import os
import shutil
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import edit_plan, render, sfx, silence, subtitles, transcribe
from .ffmpeg_utils import probe, run


def default_font():
    """ใช้ Kanit ถ้ามีไฟล์ในโฟลเดอร์ fonts/ (Docker โหลดมาให้) ไม่งั้นใช้ฟอนต์ไทยของ Windows"""
    if os.environ.get("YODEDIT_FONT"):
        return os.environ["YODEDIT_FONT"]
    return "Kanit" if (render.FONTS_DIR / "Kanit-Bold.ttf").exists() else "Leelawadee UI"


@dataclass
class Options:
    aspects: list = field(default_factory=lambda: ["9:16"])  # 9:16, 16:9, 1:1, 4:5
    reframe: str = "crop"            # crop = ครอปกลางภาพ, blur = พื้นหลังเบลอ
    target_seconds: float = 0        # 0 = ไม่จำกัดความยาว
    cut_silence: bool = True
    silence_db: float = 0            # 0 = หาค่าอัตโนมัติจากคลิป
    min_silence: float = 0.5
    remove_fillers: bool = True
    subtitles: bool = True
    subtitle_style: str = "pop"      # pop / karaoke / box
    language: str = "th"             # "" = ตรวจจับภาษาอัตโนมัติ
    whisper_model: str = "thai"      # thai = Thonburian Whisper, หรือ large-v3-turbo / medium / small
    zoom: bool = True
    zoom_amount: float = 1.15
    sfx: bool = True
    normalize_audio: bool = True
    fps: int = 30
    font: str = field(default_factory=lambda: default_font())

    @classmethod
    def from_dict(cls, d):
        known = {f.name for f in fields(cls)}
        opts = cls(**{k: v for k, v in d.items() if k in known})
        opts.aspects = [a for a in opts.aspects if a in render.ASPECTS] or ["9:16"]
        if opts.reframe not in ("crop", "blur"):
            opts.reframe = "crop"
        return opts


def process(input_path, job_dir, opts: Options, progress=lambda pct, msg: None):
    """คืนค่า {"outputs": [{"aspect", "video", "srt"}], "duration_in", "duration_out", ...}"""
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    src = str(Path(input_path).resolve())

    progress(2, "กำลังอ่านไฟล์วิดีโอ")
    info = probe(src)
    if not info["has_video"] or not info["has_audio"]:
        raise RuntimeError("ไฟล์ต้องมีทั้งภาพและเสียง")
    duration = info["duration"]

    progress(5, "กำลังแยกเสียง")
    audio = job_dir / "audio.wav"
    run(["-i", src, "-vn", "-ac", "1", "-ar", "16000", audio])

    # 1) ถอดเสียง (ใช้ทั้งทำซับ, ตัดคำฟุ่มเฟือย, เลือกช่วงสำคัญ)
    words, sentences, lang, warnings = [], [], opts.language, []
    if opts.subtitles or opts.remove_fillers or opts.target_seconds:
        progress(8, "กำลังถอดเสียงเป็นข้อความ (ครั้งแรกจะโหลดโมเดล อาจใช้เวลาสักพัก)")
        result = transcribe.transcribe(audio, opts.language, opts.whisper_model)
        if result is None:
            warnings.append("ยังไม่ได้ติดตั้ง faster-whisper จึงข้ามการทำซับและตัดคำฟุ่มเฟือย")
        else:
            words, sentences, lang = result["words"], result["sentences"], result["language"]

    # 2) ตัดช่วงเงียบ
    progress(30, "กำลังหาช่วงเงียบ")
    if opts.cut_silence:
        keep = silence.detect_speech(audio, duration, opts.silence_db, opts.min_silence)
        if words:
            keep = edit_plan.protect_words(keep, words, duration)
    else:
        keep = [(0.0, duration)]
    if opts.remove_fillers and words:
        keep = edit_plan.remove_fillers(keep, words)
    keep = edit_plan.fit_to_target(keep, words, opts.target_seconds, sentences)
    if not keep:
        raise RuntimeError("ไม่พบช่วงที่มีเสียงพูด ลองลดค่า 'ระดับเสียงเงียบ' (เช่น -45)")

    shots, cut_times = edit_plan.make_shots(keep, sentences, opts.zoom, opts.zoom_amount)
    out_words = edit_plan.remap_words(words, keep)
    duration_out = sum(e - s for s, e in keep)

    # เก็บ timeline เป็นข้อมูลกลาง ใช้ render ได้ทุกสัดส่วนจอ และต่อยอดเป็น editor ได้
    (job_dir / "plan.json").write_text(json.dumps({
        "options": asdict(opts), "language": lang, "source": info,
        "keep": keep, "shots": shots, "cut_times": cut_times,
        "sentences": sentences, "words": out_words,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    sfx_name = None
    if opts.sfx and cut_times:
        sfx_name = "sfx.wav"
        sfx.write_sfx_track(job_dir / sfx_name, duration_out, cut_times)

    srt_name = None
    if out_words:
        srt_name = "subtitles.srt"
        subtitles.write_srt(out_words, job_dir / srt_name)

    # 3) เรนเดอร์ทีละสัดส่วนจอ
    outputs = []
    span = 60 / len(opts.aspects)
    for ai, aspect in enumerate(opts.aspects):
        base = 35 + ai * span
        tag = aspect.replace(":", "x")
        ass_name = None
        if opts.subtitles and out_words:
            ass_name = f"subs_{tag}.ass"
            w, h = render.ASPECTS[aspect]
            subtitles.write_ass(out_words, job_dir / ass_name, w, h, opts.font, opts.subtitle_style)

        def shot_progress(done, total, base=base, aspect=aspect):
            progress(base + span * 0.85 * done / total, f"[{aspect}] กำลังตัดช็อต {done}/{total}")

        video_name = f"output_{tag}.mp4"
        render.render_aspect(
            src, shots, aspect, job_dir, job_dir / video_name,
            mode=opts.reframe, fps=opts.fps, ass_name=ass_name, sfx_name=sfx_name,
            normalize=opts.normalize_audio, progress=shot_progress,
        )
        # ลบไฟล์ช็อตชั่วคราว (ใหญ่กว่าผลลัพธ์หลายเท่า)
        shutil.rmtree(job_dir / f"shots_{tag}", ignore_errors=True)
        (job_dir / f"joined_{tag}.mkv").unlink(missing_ok=True)
        progress(base + span, f"[{aspect}] เสร็จแล้ว")
        outputs.append({"aspect": aspect, "video": video_name, "srt": srt_name})

    progress(100, "เสร็จเรียบร้อย")
    return {
        "outputs": outputs,
        "duration_in": duration,
        "duration_out": duration_out,
        "cuts": len(keep) - 1,
        "language": lang,
        "warnings": warnings,
    }
