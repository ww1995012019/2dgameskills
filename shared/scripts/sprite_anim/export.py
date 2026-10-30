# Shared by both skills. Edit the copy in the repo's shared/ folder, then run dev/sync_shared.py.
"""Frames -> sheets, trimmed atlas pages, manifests and engine import files."""
import base64
import hashlib
import json
import os

import numpy as np
from PIL import Image

MAX_PAGE = 4096
PAD = 2


def bleed(a, iters=4):
    """Flood RGB into transparent pixels. Without this, bilinear filtering samples black
    neighbours and every sprite gets a dark halo when scaled or rotated in the engine."""
    rgb = a[..., :3].astype(np.float32)
    known = a[..., 3] > 0
    for _ in range(iters):
        nb = np.zeros_like(rgb)
        cnt = np.zeros(known.shape, dtype=np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            s = np.roll(np.roll(known, dy, 0), dx, 1)
            nb += np.roll(np.roll(rgb * known[..., None], dy, 0), dx, 1)
            cnt += s
        grow = (cnt > 0) & ~known
        rgb[grow] = nb[grow] / cnt[grow][:, None]
        known = known | grow
    out = a.copy()
    out[..., :3] = rgb.astype(np.uint8)
    return out


def trim(a):
    m = a[..., 3] > 0
    if not m.any():
        return 0, 0, 1, 1
    ys, xs = np.where(m.any(1))[0], np.where(m.any(0))[0]
    return int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1


def write_frames(root, name, frames):
    d = os.path.join(root, "frames", name)
    os.makedirs(d, exist_ok=True)
    for i, f in enumerate(frames):
        Image.fromarray(f, "RGBA").save(os.path.join(d, f"{name}_{i:03d}.png"), compress_level=6)


def write_sheet(root, name, frames, size):
    """Per-clip sheet, wrapped to a grid. A clip with more frames than fit in MAX_PAGE squared
    (long clips at 512 px) still gets one sheet, flagged here; the atlas pages stay in bounds."""
    d = os.path.join(root, "sheets")
    os.makedirs(d, exist_ok=True)
    cols = min(len(frames), MAX_PAGE // size)
    rows = (len(frames) + cols - 1) // cols
    if rows * size > MAX_PAGE:
        print(f"[warn] sheets/{name}.png is {cols * size}x{rows * size}, over {MAX_PAGE}: use the atlas "
              "on mobile, or lower this clip's fps with --fps-override")
    sheet = Image.new("RGBA", (cols * size, rows * size), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(Image.fromarray(f, "RGBA"), ((i % cols) * size, (i // cols) * size))
    sheet.save(os.path.join(d, f"{name}.png"), compress_level=6)
    return cols, rows


def pack(sprites):
    """Shelf packer over trimmed frames, tallest first. Spills onto new pages at MAX_PAGE."""
    order = sorted(range(len(sprites)), key=lambda i: -sprites[i]["h"])
    pages, cur = [], None
    area = sum((sprites[i]["w"] + PAD) * (sprites[i]["h"] + PAD) for i in order)
    side = min(MAX_PAGE, int(area ** 0.5 * 1.12) + 8)

    def new_page():
        return dict(w=side, x=PAD, y=PAD, shelf=0, items=[], maxx=0, maxy=0)

    cur = new_page()
    for i in order:
        s = sprites[i]
        if cur["x"] + s["w"] + PAD > cur["w"]:
            cur["x"] = PAD
            cur["y"] += cur["shelf"] + PAD
            cur["shelf"] = 0
        if cur["y"] + s["h"] + PAD > MAX_PAGE:
            pages.append(cur)
            cur = new_page()
        s["x"], s["y"], s["page"] = cur["x"], cur["y"], len(pages)
        cur["x"] += s["w"] + PAD
        cur["shelf"] = max(cur["shelf"], s["h"])
        cur["maxx"] = max(cur["maxx"], s["x"] + s["w"] + PAD)
        cur["maxy"] = max(cur["maxy"], s["y"] + s["h"] + PAD)
        cur["items"].append(i)
    pages.append(cur)
    return pages


def build_atlas(root, all_clips, size, prefix="atlas"):
    """all_clips: {name: {frames:[u8 arrays], ...}}. Identical frames share one region."""
    sprites, by_hash, frame_refs = [], {}, {}
    for name, c in all_clips.items():
        refs = []
        for f in c["frames"]:
            key = hashlib.blake2b(f.tobytes(), digest_size=16).digest()
            if key not in by_hash:
                x0, y0, x1, y1 = trim(f)
                by_hash[key] = len(sprites)
                sprites.append(dict(ox=x0, oy=y0, w=x1 - x0, h=y1 - y0, img=f[y0:y1, x0:x1]))
            refs.append(by_hash[key])
        frame_refs[name] = refs
    pages = pack(sprites)
    files = []
    for pi, pg in enumerate(pages):
        im = Image.new("RGBA", (pg["maxx"], pg["maxy"]), (0, 0, 0, 0))
        buf = np.array(im)
        for i in pg["items"]:
            s = sprites[i]
            buf[s["y"]:s["y"] + s["h"], s["x"]:s["x"] + s["w"]] = s["img"]
        fn = f"{prefix}_{pi}.png" if len(pages) > 1 else f"{prefix}.png"
        Image.fromarray(bleed(buf), "RGBA").save(os.path.join(root, fn), compress_level=7)
        files.append(dict(file=fn, w=pg["maxx"], h=pg["maxy"]))
    return sprites, frame_refs, files


def texturepacker_json(root, sprites, frame_refs, files, size, pivot, prefix="atlas"):
    """JSON-hash format (Phaser 3, PixiJS, Cocos via plugin); one file per page."""
    for pi, pf in enumerate(files):
        frames, anims = {}, {}
        for name, refs in frame_refs.items():
            lst = []
            for i, r in enumerate(refs):
                s = sprites[r]
                if s["page"] != pi:
                    continue
                key = f"{name}_{i:03d}"
                frames[key] = dict(
                    frame=dict(x=s["x"], y=s["y"], w=s["w"], h=s["h"]), rotated=False,
                    trimmed=True, spriteSourceSize=dict(x=s["ox"], y=s["oy"], w=s["w"], h=s["h"]),
                    sourceSize=dict(w=size, h=size),
                    pivot=dict(x=round(pivot[0] / size, 4), y=round(pivot[1] / size, 4)))
                lst.append(key)
            if lst:
                anims[name] = lst
        doc = dict(frames=frames, animations=anims,
                   meta=dict(app="game-sprite-animator", image=pf["file"], format="RGBA8888",
                             size=dict(w=pf["w"], h=pf["h"]), scale="1"))
        with open(os.path.join(root, pf["file"].replace(".png", ".json")), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False)


def manifest(sprites, frame_refs, files, clips_meta, size, pivot, character):
    """animations.json: the engine-neutral source of truth."""
    regions = [dict(page=s["page"], x=s["x"], y=s["y"], w=s["w"], h=s["h"], ox=s["ox"], oy=s["oy"]) for s in sprites]
    clips = {n: dict(m, frames=frame_refs[n]) for n, m in clips_meta.items()}
    return dict(character=character, frame_size=size, pivot=list(pivot), pages=files,
                regions=regions, clips=clips)


def godot_tres(root, doc):
    pages, regions = doc["pages"], doc["regions"]
    size = doc["frame_size"]
    subs, used = [], {}
    n = 0
    anims = []
    for name, c in doc["clips"].items():
        fr = []
        for r in c["frames"]:
            if r not in used:
                g = regions[r]
                sid = f"a{n}"
                n += 1
                used[r] = sid
                subs.append(
                    f'[sub_resource type="AtlasTexture" id="{sid}"]\n'
                    f'atlas = ExtResource("{g["page"] + 1}")\n'
                    f'region = Rect2({g["x"]}, {g["y"]}, {g["w"]}, {g["h"]})\n'
                    f'margin = Rect2({g["ox"]}, {g["oy"]}, {size - g["w"]}, {size - g["h"]})\n')
            fr.append(f'{{"duration": 1.0, "texture": SubResource("{used[r]}")}}')
        anims.append('{"frames": [' + ", ".join(fr) + f'], "loop": {"true" if c["loop"] else "false"}, '
                     f'"name": &"{name}", "speed": {float(c["fps"])}}}')
    head = f'[gd_resource type="SpriteFrames" load_steps={len(subs) + len(pages) + 1} format=3]\n\n'
    ext = "".join(f'[ext_resource type="Texture2D" path="res://{p["file"]}" id="{i + 1}"]\n' for i, p in enumerate(pages))
    body = "\n".join(subs)
    with open(os.path.join(root, "engine", "godot", "sprite_frames.tres"), "w", encoding="utf-8") as fh:
        fh.write(head + ext + "\n" + body + "\n[resource]\nanimations = [" + ", ".join(anims) + "]\n")


def cocos_plist(root, doc):
    """Cocos Creator / cocos2d-x SpriteAtlas (.plist format 2), one per page."""
    size = doc["frame_size"]
    for pi, pg in enumerate(doc["pages"]):
        ent = []
        seen = set()
        for name, c in doc["clips"].items():
            for i, r in enumerate(c["frames"]):
                g = doc["regions"][r]
                key = f"{name}_{i:03d}.png"
                if g["page"] != pi or key in seen:
                    continue
                seen.add(key)
                ox = g["ox"] + g["w"] / 2 - size / 2
                oy = size / 2 - (g["oy"] + g["h"] / 2)
                ent.append(
                    f"<key>{key}</key><dict>"
                    f"<key>frame</key><string>{{{{{g['x']},{g['y']}}},{{{g['w']},{g['h']}}}}}</string>"
                    f"<key>offset</key><string>{{{ox:g},{oy:g}}}</string><key>rotated</key><false/>"
                    f"<key>sourceColorRect</key><string>{{{{{g['ox']},{g['oy']}}},{{{g['w']},{g['h']}}}}}</string>"
                    f"<key>sourceSize</key><string>{{{size},{size}}}</string></dict>\n")
        xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
               '<plist version="1.0"><dict><key>frames</key><dict>\n' + "".join(ent) + "</dict>"
               f"<key>metadata</key><dict><key>format</key><integer>2</integer>"
               f"<key>size</key><string>{{{pg['w']},{pg['h']}}}</string>"
               f"<key>textureFileName</key><string>{pg['file']}</string></dict></dict></plist>\n")
        fn = pg["file"].replace(".png", ".plist")
        with open(os.path.join(root, "engine", "cocos", fn), "w", encoding="utf-8") as fh:
            fh.write(xml)


def css_keyframes(root, doc, sheets):
    """Pure CSS playback for H5 pages. Keyframes address grid cells directly, so this works
    with the wrapped per-clip sheets (a single-row steps() strip would blow past texture
    limits on phones)."""
    size = doc["frame_size"]
    rules = [f".sprite{{width:{size}px;height:{size}px;background-repeat:no-repeat;image-rendering:auto}}\n"]
    for name, c in doc["clips"].items():
        if name not in sheets or c.get("layer", "full") != "full":
            continue        # CSS has no way to sync two layers, so only whole-body clips apply
        cols, rows = sheets[name]
        n = len(c["frames"])
        dur = n / c["fps"]
        kf = []
        for i in range(n):
            pct = i / n * 100
            kf.append(f"{pct:.3f}%{{background-position:-{(i % cols) * size}px -{(i // cols) * size}px}}")
        kf.append(f"100%{{background-position:-{((n - 1) % cols) * size}px -{((n - 1) // cols) * size}px}}")
        loop = "infinite" if c["loop"] else "1 forwards"
        rules.append(f"@keyframes sp-{name}{{{''.join(kf)}}}\n"
                     f".sprite.{name}{{background-image:url(../../sheets/{name}.png);"
                     f"background-size:{cols * size}px {rows * size}px;"
                     f"animation:sp-{name} {dur:.3f}s step-end {loop}}}\n")
    with open(os.path.join(root, "engine", "web", "sprites.css"), "w", encoding="utf-8") as fh:
        fh.write("".join(rules))


def preview_html(root, template, player_js, doc, fx_doc, title):
    def b64(path):
        with open(path, "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode()

    data = dict(doc=doc, images=[b64(os.path.join(root, p["file"])) for p in doc["pages"]],
                fx=fx_doc, fx_images=[b64(os.path.join(root, p["file"])) for p in fx_doc["pages"]] if fx_doc else [],
                title=title)
    with open(template, encoding="utf-8") as fh:
        html = fh.read()
    with open(player_js, encoding="utf-8") as fh:
        html = html.replace("/*__PLAYER__*/", fh.read())
    html = html.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__TITLE__", title)
    with open(os.path.join(root, "preview.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
