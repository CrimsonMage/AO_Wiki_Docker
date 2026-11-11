#!/usr/bin/env python3
"""Stitch Anarchy Online's planet maps from an AO install into whole images.

    python3 build/import_planetmaps.py "/path/to/Anarchy Online"

Reads cd_image/textures/PlanetMap/*/<index>.txt (Name, File, TextureSize, Size, Tiles, FilePos ...)
and the .bin files they point at (the tiles are PNG or JPEG, TextureSize pixels square, column by column, top to bottom);
each map's largest level becomes one JPEG.

  Funcom's own maps (the default Rubi-Ka map, the Shadowlands)  -> data/planet/        (published)
  Player-made maps shipped with the game (Saavick's, Dovve's)   -> data/planet_extra/  (not published:
       their authors gave no license; see the README. The server shows them when present.)
Needs Pillow (pip install pillow).
"""
import io
import json
import os
import re
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THIRD_PARTY = ("saavick", "dovve")


def levels(txt):
    """the map's blocks: [{file, tex, size, tiles, pos[]}], in file order (small to large)"""
    name = re.search(r'^Name\s+"([^"]+)"', txt, re.M)
    out, cur = [], None
    for line in txt.replace("\r", "").split("\n"):
        w = line.split()
        if not w:
            continue
        if w[0] == "File":
            cur = {"file": w[1], "pos": []}; out.append(cur)
        elif cur is None:
            continue
        elif w[0] == "TextureSize":
            cur["tex"] = int(w[1])
        elif w[0] == "Size":
            cur["size"] = (int(w[1]), int(w[2]))
        elif w[0] == "Tiles":
            cur["tiles"] = (int(w[1]), int(w[2]))
        elif w[0] == "FilePos":
            cur["pos"].append(int(w[1]))
    return (name.group(1) if name else "map"), out


def stitch(base, lv):
    data = open(os.path.join(base, lv["file"]), "rb").read()
    tx, ty = lv["tiles"]
    t = lv["tex"]
    img = Image.new("RGB", (tx * t, ty * t), (0, 0, 0))
    ends = lv["pos"][1:] + [len(data)]
    for k, (a, b) in enumerate(zip(lv["pos"], ends)):
        if k >= tx * ty:
            break
        chunk = data[a:b]
        try:
            tile = Image.open(io.BytesIO(chunk)).convert("RGB")
        except Exception:
            continue  # an empty tile
        img.paste(tile, ((k // ty) * t, (k % ty) * t))  # tiles run column by column
    w, h = lv["size"]
    return img.crop((0, 0, min(w, img.width), min(h, img.height)))


def main():
    ao = sys.argv[1]
    pm = os.path.join(ao, "cd_image", "textures", "PlanetMap")
    made = {}
    for d in sorted(os.listdir(pm)):
        sub = os.path.join(pm, d)
        if not os.path.isdir(sub):
            continue
        for f in sorted(os.listdir(sub)):
            if not f.endswith(".txt") or f.lower() == "readme.txt":
                continue
            txt = open(os.path.join(sub, f), encoding="latin-1").read()
            if "FilePos" not in txt:
                continue
            name, lvs = levels(txt)
            lvs = [lv for lv in lvs if lv.get("tiles") and lv.get("pos")]
            if not lvs:
                continue
            third = any(s in (name + d).lower() for s in THIRD_PARTY)
            outdir = os.path.join(ROOT, "data", "planet_extra" if third else "planet")
            os.makedirs(outdir, exist_ok=True)
            # the largest level only (the Shadowlands keeps its two zoom levels in two files: same map)
            lv = max(lvs, key=lambda x: x["size"][0] * x["size"][1])
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            img = stitch(pm, lv)
            img.save(os.path.join(outdir, slug + ".jpg"), quality=85, optimize=True, progressive=True)
            made[slug] = {"name": name, "w": img.width, "h": img.height, "third_party": third, "folder": d}
            print("%-40s %5dx%-5d %s" % (slug, img.width, img.height, "data/planet_extra" if third else "data/planet"))
    for folder, third in (("planet", False), ("planet_extra", True)):
        sub = {k: v for k, v in made.items() if v["third_party"] == third}
        if sub:
            json.dump(sub, open(os.path.join(ROOT, "data", folder, "index.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
