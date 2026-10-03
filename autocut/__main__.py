"""ใช้งานผ่าน command line:  python -m autocut input.mp4 --aspect 9:16 16:9"""
import argparse
import json
from pathlib import Path

from .pipeline import Options, process


def main():
    p = argparse.ArgumentParser(description="ตัดต่อวิดีโออัตโนมัติ")
    p.add_argument("input")
    p.add_argument("--out", default="output")
    p.add_argument("--aspect", nargs="+", default=["9:16"], help="9:16 16:9 1:1 4:5")
    p.add_argument("--reframe", default="crop", choices=["crop", "blur"])
    p.add_argument("--target", type=float, default=0, help="ความยาวที่ต้องการ (วินาที)")
    p.add_argument("--lang", default="th")
    p.add_argument("--model", default="thai")
    p.add_argument("--style", default="pop", choices=["pop", "karaoke", "box"])
    p.add_argument("--no-subs", action="store_true")
    p.add_argument("--no-zoom", action="store_true")
    p.add_argument("--no-sfx", action="store_true")
    a = p.parse_args()

    opts = Options(
        aspects=a.aspect, reframe=a.reframe, target_seconds=a.target, language=a.lang,
        whisper_model=a.model, subtitle_style=a.style, subtitles=not a.no_subs, zoom=not a.no_zoom, sfx=not a.no_sfx,
    )
    result = process(a.input, Path(a.out), opts,
                     progress=lambda pct, msg: print(f"[{pct:5.1f}%] {msg}"))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
