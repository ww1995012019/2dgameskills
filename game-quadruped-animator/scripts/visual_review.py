#!/usr/bin/env python3
"""Actual rendered frames + silhouettes, with floor and sampled four-paw contacts."""
import argparse, json
from pathlib import Path
from PIL import Image, ImageDraw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path")
    a = p.parse_args()
    root = Path(a.path)
    doc = json.loads((root / "animations.json").read_text())
    trace = json.loads((root / "rig_trace.json").read_text())
    out = root / "review"
    out.mkdir(exist_ok=True)
    cell = 160
    index = []
    for name, c in doc["clips"].items():
        files = sorted((root / "frames" / name).glob("*.png"))
        sheet = Image.new("RGB", (cell * 8, cell * 2 + 55), "#364550")
        d = ImageDraw.Draw(sheet)
        d.text(
            (4, 4),
            name + " | colour + silhouette | floor is orange; foot dots: hn hf fn ff",
            fill="white",
        )
        for k in range(8):
            i = round(k * (len(files) - 1) / 7)
            im = (
                Image.open(files[i])
                .convert("RGBA")
                .resize(
                    (cell, cell),
                    (
                        Image.Resampling.NEAREST
                        if doc["frame_size"] <= 96
                        else Image.Resampling.LANCZOS
                    ),
                )
            )
            silhouette = Image.new("RGBA", im.size, "black")
            silhouette.putalpha(im.getchannel("A"))
            for row, image in enumerate((im, silhouette)):
                top = 25 + row * cell
                ground = top + doc["pivot"][1] / doc["frame_size"] * cell
                d.line((k * cell, ground, (k + 1) * cell, ground), fill="#ba9062")
                sheet.paste(image, (k * cell, top), image)
            d.text((k * cell + 4, 25), str(i), fill="white")
            for j, leg in enumerate(doc["legs"]):
                active = trace["traces"][name]["contacts"][leg][i]
                x = k * cell + 8 + j * 14
                d.ellipse(
                    (x, 2 * cell + 31, x + 8, 2 * cell + 39),
                    fill="#9ed69d" if active else "#18252f",
                )
        file = name + ".png"
        sheet.save(out / file)
        index.append(dict(file=file, clip=name))
    (out / "index.json").write_text(json.dumps(index, indent=1))
    print(f"{len(index)} review sheets in {out}; inspect each, then record a human verdict")


if __name__ == "__main__":
    main()
