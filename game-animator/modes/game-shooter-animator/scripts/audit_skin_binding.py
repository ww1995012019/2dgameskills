#!/usr/bin/env python3
"""Audit explicitly registered artwork landmarks and shared source seams.

This is a geometry contract for custom linear-blend skinning, not anatomical
recognition. A shared painted point may not become two points after skinning.
Only supplied points are measured; unmarked seams, hidden texture, garment
ownership, mesh interiors and actual visual quality still require inspection.

    python scripts/audit_skin_binding.py binding_manifest.json
    python scripts/audit_skin_binding.py --check binding_audit.json

The manifest archives source images, actual isolated RGBA frames, bone matrices,
landmark influences and shared-boundary influences. Paths are portable relative
paths inside its directory. Source and frame pixels are never modified.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw

SCHEMA_VERSION = 1
SEAM_TOLERANCE_PX = .5
LANDMARK_TOLERANCE_PX = 1.
SOLID_ALPHA = 96
LIMITS = {
    "seam_tolerance_px": SEAM_TOLERANCE_PX,
    "landmark_tolerance_px": LANDMARK_TOLERANCE_PX,
    "meaning": "C0 continuity of declared shared source points and registered landmark alignment only",
}


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def number(value, context):
    require(type(value) in (int, float) and math.isfinite(value), f"{context}: finite number required")
    return float(value)


def vector(value, size, context):
    require(isinstance(value, list) and len(value) == size, f"{context}: {size} coordinates required")
    return [number(v, context) for v in value]


def identifier(value, context):
    require(isinstance(value, str) and value.strip(), f"{context}: nonempty identifier required")
    return value


def collection(value, context, kind=dict):
    require(isinstance(value, kind) and value, f"{context}: nonempty {kind.__name__} required")
    return value


def local_path(root, value):
    require(isinstance(value, str) and value and not Path(value).is_absolute(),
            "asset path must be relative to the manifest")
    path = (root / value).resolve()
    require(path.is_relative_to(root.resolve()), f"asset outside manifest directory: {value}")
    require(path.is_file(), f"missing asset: {value}")
    return path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def influences(value, context):
    collection(value, context, list)
    seen, out = set(), []
    for row in value:
        require(isinstance(row, list) and len(row) == 2, f"{context}: [bone index, weight] required")
        bone, weight = row
        require(type(bone) is int and bone >= 0 and bone not in seen, f"{context}: unique nonnegative bone index required")
        weight = number(weight, context)
        require(weight >= 0, f"{context}: negative influence")
        seen.add(bone)
        out.append((bone, weight))
    require(abs(sum(w for _, w in out) - 1) <= 1e-6, f"{context}: influences must sum to one")
    return out


def mapped(point, weights, matrices, context):
    x, y = point
    out = [0., 0.]
    for bone, weight in weights:
        require(bone < len(matrices), f"{context}: bone index {bone} outside matrix array")
        a, b, c, d, e, f = matrices[bone]
        out[0] += (a * x + c * y + e) * weight
        out[1] += (b * x + d * y + f) * weight
    require(all(math.isfinite(v) for v in out), f"{context}: nonfinite transformed point")
    return out


def inspect_manifest(manifest):
    """Return an auditable result, including failures, or reject invalid evidence."""
    manifest = Path(manifest).resolve()
    require(manifest.is_file(), "missing binding manifest")
    root = manifest.parent
    try:
        doc = json.loads(manifest.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        raise ContractError(f"invalid manifest: {error}") from error
    require(isinstance(doc, dict) and type(doc.get("schema_version")) is int
            and doc["schema_version"] == SCHEMA_VERSION, "binding manifest schema_version must be 1")
    assets = {manifest.name: digest(manifest)}
    sources = {}
    for name, value in collection(doc.get("sources"), "sources").items():
        identifier(name, "source")
        path = local_path(root, value)
        try:
            with Image.open(path) as image:
                sources[name] = image.convert("RGBA")
        except (OSError, ValueError) as error:
            raise ContractError(f"invalid source image {value}: {error}") from error
        assets[path.relative_to(root).as_posix()] = digest(path)
    parts = collection(doc.get("parts"), "parts")
    for name, part in parts.items():
        identifier(name, "part")
        require(isinstance(part, dict) and part.get("source") in sources, f"{name}: valid source required")
    landmarks, seen, covered = [], set(), set()
    for row in collection(doc.get("landmarks"), "landmarks", list):
        require(isinstance(row, dict), "landmark must be an object")
        ident = identifier(row.get("id"), "landmark id")
        require(ident not in seen, f"duplicate landmark: {ident}")
        seen.add(ident)
        part = row.get("part")
        require(part in parts, f"{ident}: unknown part")
        covered.add(part)
        joint = identifier(row.get("joint"), f"{ident} joint")
        point = vector(row.get("point"), 2, ident)
        source = sources[parts[part]["source"]]
        require(0 <= point[0] < source.width and 0 <= point[1] < source.height, f"{ident}: landmark outside source")
        landmarks.append(dict(id=ident, part=part, joint=joint, point=point,
                              influences=influences(row.get("influences"), ident)))
    require(covered == set(parts), f"parts without registered landmarks: {sorted(set(parts) - covered)}")
    seams, seen = [], set()
    for row in collection(doc.get("seams"), "seams", list):
        require(isinstance(row, dict), "seam must be an object")
        ident = identifier(row.get("id"), "seam id")
        require(ident not in seen, f"duplicate seam: {ident}")
        seen.add(ident)
        pair = row.get("parts")
        require(isinstance(pair, list) and len(pair) == 2 and pair[0] != pair[1]
                and all(p in parts for p in pair), f"{ident}: two distinct known parts required")
        source_id = parts[pair[0]]["source"]
        require(parts[pair[1]]["source"] == source_id, f"{ident}: shared seam must use the same source image")
        source, samples = sources[source_id], []
        for sample in collection(row.get("samples"), f"{ident} samples", list):
            require(isinstance(sample, dict), f"{ident}: sample must be an object")
            point = vector(sample.get("point"), 2, ident)
            x, y = point
            require(0 <= x < source.width and 0 <= y < source.height, f"{ident}: seam point outside source")
            # All neighbours participating in bilinear texture sampling must be
            # painted. A valid original gap between legs is not a garment seam.
            neighbours = {(min(source.width - 1, xx), min(source.height - 1, yy))
                          for xx in (math.floor(x), math.ceil(x)) for yy in (math.floor(y), math.ceil(y))}
            require(all(source.getpixel(p)[3] > SOLID_ALPHA for p in neighbours),
                    f"{ident}: source seam point is transparent; cannot assert shared fabric")
            by_part = sample.get("influences")
            require(isinstance(by_part, dict) and set(by_part) == set(pair), f"{ident}: influences for both seam parts required")
            samples.append(dict(point=point, influences={p: influences(by_part[p], ident) for p in pair}))
        seams.append(dict(id=ident, parts=pair, source=source_id, samples=samples))
    failures, measurements, clip_frames = [], [], {}
    for clip, data in collection(doc.get("clips"), "clips").items():
        identifier(clip, "clip")
        require(isinstance(data, dict), f"{clip}: clip must be an object")
        frames = collection(data.get("frames"), f"{clip} frames", list)
        clip_frames[clip] = len(frames)
        for frame, data in enumerate(frames):
            context = f"{clip} frame {frame}"
            require(isinstance(data, dict), f"{context}: frame must be an object")
            path = local_path(root, data.get("image"))
            try:
                with Image.open(path) as image:
                    require(image.mode == "RGBA", f"{context}: actual isolated RGBA frame required")
                    low, high = image.getchannel("A").getextrema()
                    require(low < SOLID_ALPHA < high, f"{context}: isolated character and transparent background required")
            except OSError as error:
                raise ContractError(f"{context}: invalid frame image: {error}") from error
            assets[path.relative_to(root).as_posix()] = digest(path)
            matrices = collection(data.get("matrices"), f"{context} matrices")
            require(set(matrices) == set(parts), f"{context}: matrices for exactly all declared parts required")
            prepared = {}
            for part in parts:
                prepared[part] = [vector(m, 6, f"{context} {part} matrix")
                                  for m in collection(matrices[part], f"{context} {part} matrices", list)]
                require(all(abs(m[0] * m[3] - m[1] * m[2]) > 1e-12 for m in prepared[part]),
                        f"{context}: degenerate skin matrix")
            skeleton = collection(data.get("skeleton"), f"{context} skeleton")
            for row in landmarks:
                require(row["joint"] in skeleton, f"{context}: missing skeleton joint {row['joint']}")
                expected = vector(skeleton[row["joint"]], 2, f"{context} {row['joint']}")
                actual = mapped(row["point"], row["influences"], prepared[row["part"]], context)
                error = math.dist(actual, expected)
                result = dict(clip=clip, frame=frame, kind="landmark", id=row["id"],
                              part=row["part"], error_px=error, actual=actual, expected=expected)
                measurements.append(result)
                if error > LANDMARK_TOLERANCE_PX:
                    failures.append(result)
            for row in seams:
                for sample_index, sample in enumerate(row["samples"]):
                    a, b = [mapped(sample["point"], sample["influences"][p], prepared[p], context) for p in row["parts"]]
                    result = dict(clip=clip, frame=frame, kind="seam", id=row["id"],
                                  sample=sample_index, source=sample["point"], parts=row["parts"],
                                  error_px=math.dist(a, b), a=a, b=b)
                    measurements.append(result)
                    if result["error_px"] > SEAM_TOLERANCE_PX:
                        failures.append(result)
    scope = dict(clips=len(clip_frames), frames=sum(clip_frames.values()), clip_frames=clip_frames,
                 landmarks=len(landmarks), seam_samples=sum(len(s["samples"]) for s in seams))
    payload = dict(schema_version=SCHEMA_VERSION, status="fail" if failures else "pass",
                   visual_status="pending", limits=LIMITS, scope=scope, failures=failures,
                   measurements=measurements, assets=assets)
    payload["audit_id"] = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return payload, doc


def _cell(image, points=(), size=240, crop=None):
    if crop is None:
        crop = image.getbbox() or (0, 0, image.width, image.height)
    x0, y0, x1, y1 = crop
    # Invalid transforms can send geometry far outside the frame. Keep the
    # diagnostic allocation bounded while retaining exact numbers in the JSON.
    side = min(max(image.size) * 2, max(8, x1 - x0, y1 - y0))
    center_x = max(-image.width, min(image.width * 2, x0 / 2 + x1 / 2))
    center_y = max(-image.height, min(image.height * 2, y0 / 2 + y1 / 2))
    left, top = center_x - side / 2, center_y - side / 2
    box = tuple(round(x) for x in (left, top, left + side, top + side))
    out = Image.new("RGBA", (size, size), (30, 45, 51, 255))
    out.alpha_composite(image.crop(box).resize((size, size), Image.Resampling.LANCZOS))
    draw = ImageDraw.Draw(out)
    def xy(p):
        return tuple(max(-size * 4, min(size * 5, (p[i] - box[i]) * size / (box[i + 2] - box[i]))) for i in range(2))
    for a, b, color in points:
        x, y = xy(a)
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=color)
        if b is not None:
            draw.line((*xy(a), *xy(b)), fill=color, width=2)
    return out


def review_sheets(manifest, report, doc, output):
    """Source correspondence and actual frame crops, deliberately no visual verdict."""
    root, size = Path(manifest).resolve().parent, 240
    out, names = Path(output), []
    frames = [(clip, i, f) for clip, c in doc["clips"].items() for i, f in enumerate(c["frames"])]
    planned = ["binding_review_sources.png"] + [f"binding_review_{i:03d}.png" for i in range(math.ceil(len(frames) / 6))]
    protected = {(root / p).resolve() for p in report["assets"]}
    require(not any((out / p).resolve() in protected for p in planned),
            "review output would overwrite input evidence")
    sources = list(doc["sources"])
    sheet = Image.new("RGBA", (size * min(4, len(sources)), (size + 24) * math.ceil(len(sources) / 4)), (22, 30, 35, 255))
    draw = ImageDraw.Draw(sheet)
    for index, source_id in enumerate(sources):
        with Image.open(root / doc["sources"][source_id]) as image:
            points = [(row["point"], None, "#6deada") for row in doc["landmarks"]
                      if doc["parts"][row["part"]]["source"] == source_id]
            for seam in doc["seams"]:
                if doc["parts"][seam["parts"][0]]["source"] == source_id:
                    points += [(s["point"], None, "#ffcd47") for s in seam["samples"]]
            x, y = index % 4 * size, index // 4 * (size + 24)
            draw.text((x + 4, y + 4), f"SOURCE {source_id}: landmarks / shared fabric", fill="white")
            sheet.alpha_composite(_cell(image.convert("RGBA"), points), (x, y + 24))
    name = "binding_review_sources.png"
    sheet.convert("RGB").save(out / name)
    names.append(name)
    for start in range(0, len(frames), 6):
        group = frames[start:start + 6]
        sheet = Image.new("RGBA", (size * 3, (size + 24) * len(group)), (22, 30, 35, 255))
        draw = ImageDraw.Draw(sheet)
        for row_index, (clip, frame, data) in enumerate(group):
            values = [m for m in report["measurements"] if m["clip"] == clip and m["frame"] == frame]
            seams = [v for v in values if v["kind"] == "seam"]
            points = [(v["a"], v["b"], "#ff6767" if v["error_px"] > SEAM_TOLERANCE_PX else "#f7d465") for v in seams]
            points += [(v["actual"], v["expected"], "#ff6767" if v["error_px"] > LANDMARK_TOLERANCE_PX else "#6deada")
                       for v in values if v["kind"] == "landmark"]
            focus = [p for v in seams for p in (v["a"], v["b"])] or [v["actual"] for v in values]
            crop = (min(p[0] for p in focus) - 35, min(p[1] for p in focus) - 35,
                    max(p[0] for p in focus) + 35, max(p[1] for p in focus) + 35)
            with Image.open(root / data["image"]) as image:
                image = image.convert("RGBA")
                y = row_index * (size + 24)
                maximum = max(v["error_px"] for v in values)
                draw.text((4, y + 4), f"{clip} #{frame}: full / seam crop / actual mapping, max {maximum:.3f}px", fill="white")
                for col, cell in enumerate((_cell(image), _cell(image, crop=crop), _cell(image, points, crop=crop))):
                    sheet.alpha_composite(cell, (col * size, y + 24))
        name = f"binding_review_{start // 6:03d}.png"
        sheet.convert("RGB").save(out / name)
        names.append(name)
    return names


def write_audit(manifest, output=None, sheets=True):
    manifest = Path(manifest).resolve()
    output = Path(output).resolve() if output else manifest.parent / "binding_audit.json"
    require(output != manifest, "audit output cannot overwrite its input manifest")
    require(output.suffix.lower() == ".json", "audit report must be a JSON file")
    # Protect declared inputs even if a later validation error prevents their
    # inclusion in the completed asset manifest. Output must never repair or
    # overwrite the source evidence it is judging.
    declared = set()
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            if isinstance(raw.get("sources"), dict):
                declared.update(v for v in raw["sources"].values() if isinstance(v, str))
            if isinstance(raw.get("clips"), dict):
                for clip in raw["clips"].values():
                    if isinstance(clip, dict) and isinstance(clip.get("frames"), list):
                        declared.update(f["image"] for f in clip["frames"]
                                        if isinstance(f, dict) and isinstance(f.get("image"), str))
    except (OSError, ValueError):
        pass
    require(output not in {(manifest.parent / p).resolve() for p in declared},
            "audit output would overwrite input evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        report, doc = inspect_manifest(manifest)
        require(output not in {(manifest.parent / p).resolve() for p in report["assets"]},
                "audit output would overwrite input evidence")
        if sheets:
            report["review_sheets"] = review_sheets(manifest, report, doc, output.parent)
            report["review_sheet_assets"] = {name: digest(output.parent / name) for name in report["review_sheets"]}
    except (ContractError, OSError, ValueError, TypeError, KeyError) as error:
        report = dict(schema_version=SCHEMA_VERSION, status="invalid", visual_status="pending",
                      errors=[str(error)], failures=[], assets={}, scope={})
        report["audit_id"] = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    report["manifest"] = os.path.relpath(manifest, output.parent)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return report


def audit_current(report_path):
    """Recompute geometry and every evidence hash, refusing forged or stale passes."""
    try:
        path = Path(report_path).resolve()
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved.get("status") != "pass" or saved.get("schema_version") != SCHEMA_VERSION:
            return 1
        sheets = saved.get("review_sheets", [])
        sheet_assets = saved.get("review_sheet_assets", {})
        if (not isinstance(sheets, list) or len(set(sheets)) != len(sheets)
                or not isinstance(sheet_assets, dict) or set(sheets) != set(sheet_assets)):
            return 1
        if any(digest(local_path(path.parent, name)) != sheet_assets[name] for name in sheets):
            return 1
        manifest = (path.parent / saved["manifest"]).resolve()
        current, _ = inspect_manifest(manifest)
        return 0 if (current["status"] == "pass" and current["audit_id"] == saved.get("audit_id")
                     and current["assets"] == saved.get("assets") and current["scope"] == saved.get("scope")) else 1
    except (OSError, ValueError, TypeError, KeyError):
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", nargs="?")
    parser.add_argument("--out", help="report path; default: manifest directory/binding_audit.json")
    parser.add_argument("--check", metavar="REPORT", help="check a current numeric audit without recording acceptance")
    args = parser.parse_args()
    if args.check:
        if args.manifest or args.out:
            parser.error("--check takes only a report path")
        result = audit_current(args.check)
        print("binding audit: current numeric pass; visual review still required" if result == 0
              else "binding audit: failed, stale, invalid or missing evidence")
        return result
    if not args.manifest:
        parser.error("manifest or --check REPORT required")
    try:
        report = write_audit(args.manifest, args.out)
    except (ContractError, OSError, ValueError) as error:
        print(f"binding audit: invalid output: {error}")
        return 1
    print(f"binding audit: {report['status']}; {len(report['failures'])} numeric failure(s); visual review pending")
    for error in report.get("errors", []):
        print(error)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
