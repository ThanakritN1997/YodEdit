"""เรนเดอร์วิดีโอ: ตัดช็อต -> ปรับสัดส่วนจอ -> ซูม -> ต่อคลิป -> ใส่ซับ + SFX"""
import shutil
from pathlib import Path

from .ffmpeg_utils import run

ASPECTS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}

FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"


def _frame_filter(w, h, mode, z0, z1, dur, fps):
    """filter_complex สำหรับ 1 ช็อต: ได้ภาพขนาด w x h ออกมาที่ [v]
    ซูมค่อย ๆ เปลี่ยนจาก z0 ไป z1 ตลอดความยาวช็อต"""
    if mode == "blur":  # วางภาพเต็มไว้กลางจอ + พื้นหลังเบลอ
        base = (
            f"[0:v]split[a][b];"
            f"[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=25:2[bg];"
            f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
    else:  # crop: ครอปกลางภาพให้เต็มจอ (เหมาะกับคลิปคนพูด)
        base = f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    base += f",fps={fps}"
    if max(z0, z1) > 1.001:
        zexpr = f"{z0}+({z1 - z0:.4f})*min(t/{max(dur, 0.1):.3f},1)"
        base += (f",scale=w='trunc({w}*({zexpr})/2)*2':h=-2:eval=frame:flags=bicubic"
                 f",crop={w}:{h}")
    return base + ",setsar=1,format=yuv420p[v]"


def render_shot(src, shot, out_path, w, h, mode, fps):
    dur = shot["end"] - shot["start"]
    run([
        "-ss", f"{shot['start']:.3f}", "-i", src, "-t", f"{dur:.3f}",
        "-filter_complex",
        _frame_filter(w, h, mode, shot["zoom_from"], shot["zoom_to"], dur, fps),
        "-map", "[v]", "-map", "0:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
        out_path,
    ])


def render_aspect(src, shots, aspect, work_dir, out_path, *, mode="crop", fps=30,
                  ass_name=None, sfx_name=None, normalize=True, progress=None):
    """เรนเดอร์ 1 สัดส่วนจอ ไฟล์ทั้งหมดอยู่ใน work_dir (ใช้ชื่อไฟล์แบบ relative
    เพราะ filter ass ของ ffmpeg บน Windows มีปัญหากับ path ที่มี C:\\)"""
    w, h = ASPECTS[aspect]
    work_dir = Path(work_dir)
    tag = aspect.replace(":", "x")
    shot_dir = work_dir / f"shots_{tag}"
    shot_dir.mkdir(exist_ok=True)

    names = []
    for i, shot in enumerate(shots):
        name = f"shot_{i:04d}.mkv"
        render_shot(src, shot, shot_dir / name, w, h, mode, fps)
        names.append(name)
        if progress:
            progress(i + 1, len(shots))

    (shot_dir / "list.txt").write_text(
        "".join(f"file '{n}'\n" for n in names), encoding="utf-8"
    )
    joined = f"joined_{tag}.mkv"
    run(["-f", "concat", "-safe", "0", "-i", f"shots_{tag}/list.txt", "-c", "copy", joined],
        cwd=work_dir)

    args = ["-i", joined]
    if sfx_name:
        args += ["-i", sfx_name]

    if ass_name:
        fontsdir = ""
        fonts = list(FONTS_DIR.glob("*.[ot]tf")) if FONTS_DIR.is_dir() else []
        if fonts:  # คัดลอกฟอนต์ในโฟลเดอร์ fonts/ มาไว้ข้างงาน เพื่อใช้ path แบบ relative
            local = work_dir / "fonts"
            local.mkdir(exist_ok=True)
            for f in fonts:
                shutil.copy2(f, local / f.name)
            fontsdir = ":fontsdir=fonts"
        vf = f"[0:v]ass={ass_name}{fontsdir}[v]"
    else:
        vf = "[0:v]null[v]"

    af = "[0:a]anull[a0]"
    if sfx_name:
        af = "[1:a]aresample=48000,aformat=channel_layouts=stereo[sfx];" \
             "[0:a][sfx]amix=inputs=2:normalize=0:duration=first[a0]"
    af += ";[a0]" + ("loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000" if normalize else "anull") + "[a]"

    run([
        *args, "-filter_complex", f"{vf};{af}",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        Path(out_path).resolve(),
    ], cwd=work_dir)
