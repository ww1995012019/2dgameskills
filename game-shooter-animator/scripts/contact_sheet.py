"""Render clips into a single labelled contact sheet for eyeballing poses.

    python contact_sheet.py --character hero.json --clips walk,run --size 192 --out sheet.png
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))

from sprite_anim.motions import build_clips  # noqa: E402
from sprite_anim.render import Renderer, frame_count, frame_time, to_u8  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character")
    ap.add_argument("--clips", default="idle,walk,run")
    ap.add_argument("--size", type=int, default=192)
    ap.add_argument("--pixel", action="store_true")
    ap.add_argument("--zoom", type=int, default=1)
    ap.add_argument("--max-frames", type=int, default=10)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--cols", type=int, default=0)
    ap.add_argument("--out", default="contact.png")
    ap.add_argument("--list", action="store_true", help="print clip names")
    a = ap.parse_args()
    spec = json.load(open(a.character, encoding="utf-8")) if a.character else {}
    if a.character:
        spec["_dir"] = os.path.dirname(os.path.abspath(a.character))
    clips = build_clips(spec, a.fps)
    r = Renderer(spec, a.size, a.pixel, clips=clips)
    names = [n for n in a.clips.split(",") if n] if a.clips != "all" else list(clips)
    unknown = [n for n in names if n not in clips]
    if unknown:
        sys.exit(f"unknown clips: {unknown}\navailable: {list(clips)}")
    cell = a.size * a.zoom
    cols = a.cols or a.max_frames
    rows = len(names)
    sheet = Image.new("RGBA", (cols * cell, rows * (cell + 14)), (58, 62, 74, 255))
    print("clips:", ",".join(clips)) if a.list else None
    d = ImageDraw.Draw(sheet)
    for ri, name in enumerate(names):
        c = clips[name]
        n = frame_count(c, a.fps)
        y = ri * (cell + 14)
        d.text((3, y + 1), f"{name} ({n}f @ {a.fps})", fill=(255, 255, 255, 255))
        for k in range(min(cols, a.max_frames)):
            i = round(k * (n - 1) / max(1, min(cols, a.max_frames) - 1))
            f = r.render(c, frame_time(c, i, n, a.fps), c.duration / n)
            im = Image.fromarray(to_u8(f), "RGBA")
            if a.zoom > 1:
                im = im.resize((cell, cell), Image.NEAREST)
            sheet.alpha_composite(im, (k * cell, y + 14))
    sheet.convert("RGB").save(a.out)
    print(a.out, sheet.size)


if __name__ == "__main__":
    main()
