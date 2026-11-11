#!/usr/bin/env python3
"""Turn extracted game data into this archive's plain data files (run once, by the maintainer).

    python3 -I build/import_data.py ITEM_NAMES.lua ITEM_TEXTS.lua [AOU_GUIDES.lua]

  ITEM_NAMES.lua   return { [id] = "Name", ... }               -> data/items.tsv  (id <TAB> name)
  ITEM_TEXTS.lua   return { { id, name, text }, ... }          -> data/item_texts.json
  AOU_GUIDES.lua   return { { id, name, author, part, url, items, ao, text }, ... }
                                                               -> data/aou/guides.json (optional)

The inputs are plain Lua tables exported from the game's item database (item names and the
item descriptions that are tradeskill instructions) and, optionally, AO-Universe's guides.
Nothing here talks to the game client.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STR = r'"((?:[^"\\]|\\.)*)"'


def unlua(s):
    return re.sub(r'\\(.)', lambda m: {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(m.group(1), m.group(1)), s)


def items(path):
    out = []
    for m in re.finditer(r'\[(\d+)\] = ' + STR, open(path, encoding="utf-8").read()):
        out.append((int(m.group(1)), unlua(m.group(2))))
    with open(os.path.join(ROOT, "data", "items.tsv"), "w", encoding="utf-8") as f:
        for i, n in out:
            f.write("%d\t%s\n" % (i, n.replace("\t", " ").replace("\n", " ")))
    print("items:", len(out))


def item_texts(path):
    out = []
    for m in re.finditer(r'\{ id = (\d+), name = ' + STR + r', text = ' + STR + r' \}', open(path, encoding="utf-8").read()):
        out.append({"id": int(m.group(1)), "name": unlua(m.group(2)), "text": unlua(m.group(3))})
    json.dump(out, open(os.path.join(ROOT, "data", "item_texts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("item texts:", len(out))


def guides(path):
    src = open(path, encoding="utf-8").read()
    out = []
    pat = (r'\{ id = (\d+), name = ' + STR + r', author = ' + STR + r', part = ' + STR + r', url = ' + STR +
           r', items = \{ (.*?) \}, ao = ' + STR + r', text = ' + STR + r' \}')
    for m in re.finditer(pat, src, re.S):
        its = [unlua(x) for x in re.findall(STR, m.group(6))]
        out.append({"id": int(m.group(1)), "name": unlua(m.group(2)), "author": unlua(m.group(3)), "part": unlua(m.group(4)),
                    "url": unlua(m.group(5)), "items": its, "ao": unlua(m.group(7))})
    os.makedirs(os.path.join(ROOT, "data", "aou"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "data", "aou", "guides.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("AO-Universe guides:", len(out))


if __name__ == "__main__":
    items(sys.argv[1])
    item_texts(sys.argv[2])
    if len(sys.argv) > 3:
        guides(sys.argv[3])
