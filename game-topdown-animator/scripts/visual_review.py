#!/usr/bin/env python3
"""Review colour + silhouette rows by direction, using the actual exported frames."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path")
    a = p.parse_args()
    root = Path(a.path)
    doc = json.loads((root / "animations.json").read_text())
    out = root / "review"
    out.mkdir(exist_ok=True)
    index = []
    cell = 112
    for action in dict.fromkeys(c["action"] for c in doc["clips"].values()):
        sheet = Image.new("RGB", (cell * 5, 8 * (cell * 2 + 22)), "#33414c")
        draw = ImageDraw.Draw(sheet)
        names = []
        for row, direction in enumerate(doc["direction_order"]):
            name = action + "_" + direction
            names.append(name)
            frames = sorted((root / "frames" / name).glob("*.png"))
            y = row * (cell * 2 + 22)
            draw.text((4, y + 3), name, fill="white")
            for col in range(5):
                i = round(col * (len(frames) - 1) / 4)
                im = Image.open(frames[i]).convert("RGBA")
                im = im.resize(
                    (cell, cell),
                    (
                        Image.Resampling.NEAREST
                        if doc["frame_size"] <= 96
                        else Image.Resampling.LANCZOS
                    ),
                )
                sheet.paste(im, (col * cell, y + 22), im)
                silhouette = Image.new("RGBA", im.size, "black")
                silhouette.putalpha(im.getchannel("A"))
                sheet.paste(silhouette, (col * cell, y + 22 + cell), silhouette)
                draw.text((col * cell + 3, y + 24), str(i), fill="#f7d391")
        file = action + ".png"
        sheet.save(out / file)
        index.append(dict(file=file, clips=names))
    (out / "index.json").write_text(json.dumps(index, indent=1))
    print(f"{len(index)} review sheets in {out}; inspect every colour/silhouette row")


if __name__ == "__main__":
    main()
