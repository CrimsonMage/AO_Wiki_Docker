#!/usr/bin/env python3
"""Build the archive's database: one SQLite file with full-text search.

    python3 -I build/build_db.py OUT.sqlite [--with-aou]

Sources (all under data/):
  recipes/        the AO recipe-bot recipes (Nadybot RECIPE_MODULE, GPL-3.0): AO markup .txt and .json
  items.tsv       item id <TAB> name, from the game's item database
  item_texts.json item descriptions that are tradeskill instructions (the game's own recipe texts)
  aou/guides.json AO-Universe's tradeskill guides; only with --with-aou (see README: permission)

Every entry is stored as safe HTML: AO markup is parsed, only colours, bold/italic/underline and
item links survive, everything else is escaped. Item links point to /item/<id>.
"""
import html
import json
import os
import re
import csv
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datasets import BOT_GUIDES, DATASETS, GROUPS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
COLOR = re.compile(r"#?([0-9a-fA-F]{6})$")
NADY = {"highlight": "FFFF00", "lime": "00FF00", "yellow": "FFFF00", "cyan": "00FFFF", "blue": "8CB5FF", "green": "00DE42",
        "red": "FF0000", "orange": "FFA500", "white": "FFFFFF", "grey": "AAAAAA"}
TOKEN = re.compile(r"""(<font\s+color\s*=\s*['"]?#?[0-9a-fA-F]{6}['"]?\s*>|</font>|<a\s+href\s*=\s*['"]itemref://\d+/\d+/\d+['"]\s*>|</a>|"""
                   r"""<br\s*/?>|</?[biu]>|<img[^>]*>|</?center>|<end>|<(?:highlight|lime|yellow|cyan|blue|green|red|orange|white|grey)>|<symbol>|<pagebreak>|<tab>)""", re.I)


def ao_to_html(t):
    """AO / bot markup -> (safe html, plain text, [item ids])"""
    t = t.replace("\r", "")
    ids = []

    def link(m):
        ids.append(int(m.group(2)))
        return '<a href="itemref://%s/%s/1">%s</a>' % (m.group(2), m.group(2), m.group(1))
    t = re.sub(r'#L\s+"([^"]+)"\s+"(\d+)"', link, t)
    t = re.sub(r'#L\s+"([^"]+)"\s+"[^"]*"', lambda m: m.group(1), t)
    t = re.sub(r"<a\s+href\s*=\s*['\"]?(?:chatcmd|text|tell|skillid|user)[^>]*>(.*?)</a>", r"\1", t, flags=re.S | re.I)
    t = re.sub(r"<header2?>", "<font color=#FFFF00>", t, flags=re.I)
    out, plain, stack = [], [], []

    def seg(txt):  # text between known tags: unknown tags are dropped, the rest escaped
        return re.sub(r"</?[a-zA-Z][^<>]{0,120}>", "", txt)
    pos = 0
    for m in TOKEN.finditer(t):
        txt = seg(t[pos:m.start()])
        out.append(html.escape(txt).replace("\n", "<br>"))
        plain.append(txt)
        pos = m.end()
        tok = m.group(0)
        low = tok.lower()
        if low.startswith("<font"):
            c = re.search(r"([0-9a-fA-F]{6})", tok).group(1)
            out.append('<span style="color:#%s">' % c); stack.append("</span>")
        elif low.startswith("<a"):
            a, b, q = re.search(r"itemref://(\d+)/(\d+)/(\d+)", tok).groups()
            ids.append(int(a))
            out.append('<a class="item" href="/item/%s?ql=%s">' % (a, q)); stack.append("</a>")
        elif low in ("</font>", "</a>", "<end>", "</b>", "</i>", "</u>"):
            if stack: out.append(stack.pop())
        elif low.startswith("<br"):
            out.append("<br>"); plain.append("\n")
        elif low in ("<b>", "<i>", "<u>"):
            tag = low[1]
            out.append("<%s>" % tag); stack.append("</%s>" % tag)
        elif low.strip("<>") in NADY:
            out.append('<span style="color:#%s">' % NADY[low.strip("<>")]); stack.append("</span>")
        elif low == "<symbol>":
            out.append("!"); plain.append("!")
        elif low in ("<tab>",):
            out.append("&emsp;")
        # img, center, pagebreak, header: dropped
    txt = seg(t[pos:])
    out.append(html.escape(txt).replace("\n", "<br>"))
    plain.append(txt)
    out.extend(reversed(stack))
    h = "".join(out)
    h = re.sub(r"(<br>\s*){3,}", "<br><br>", h)
    return h, re.sub(r"\n{3,}", "\n\n", "".join(plain)).strip(), ids


def bot_recipes():
    d = os.path.join(DATA, "recipes")
    for fn in sorted(os.listdir(d), key=lambda f: (int(re.sub(r"\D", "", f) or 0), f)):
        p = os.path.join(d, fn)
        rid = int(re.sub(r"\D", "", fn) or 0)
        if fn.endswith(".txt") and rid:
            lines = open(p, encoding="utf-8", errors="replace").read().split("\n")
            name = lines[0].strip()[6:].strip() or "Unknown"
            author = lines[1].strip()[8:].strip() if len(lines) > 1 else ""
            body = re.sub(r"^\s*</font>", "", "\n".join(lines[2:]))
            yield rid, name, author, body
        elif fn.endswith(".json"):
            j = json.load(open(p, encoding="utf-8"))
            by = {i["alias"]: i for i in j["items"]}
            res = {s["result"] for s in j["steps"]}
            ref = lambda a: '<a href="itemref://%d/%d/%d">%s</a>' % (by[a]["item_id"], by[a]["item_id"], by[a].get("ql", 1), a) if a in by else a
            rule = "<font color=#FFFF00>------------------------------</font>"
            a = [rule, "<font color=#FF0000>Ingredients</font>", rule, "<font color=#009B00>"]
            a += ["%s (QL %s)" % (ref(k), v.get("ql", "?")) for k, v in by.items() if k not in res]
            a += ["</font>", rule, "<font color=#FF0000>Recipe</font>", rule, "<font color=#009B00>"]
            for n, s in enumerate(j["steps"], 1):
                a.append("Step %d: %s <font color=#FFFFFF>+</font> %s <font color=#FFFFFF>=</font> %s" % (n, ref(s["source"]), ref(s["target"]), ref(s["result"])))
                if s.get("skills"):
                    a.append("<font color=#FFFF00>Skills: %s</font>" % s["skills"])
            a.append("</font>")
            yield rid, j.get("name", "?"), j.get("author", ""), "\n".join(a)


def load_csv(path, cols=None, sep=","):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        lines = [ln for ln in f if not ln.startswith("#") and ln.strip()]
    rows = list(csv.reader(lines, delimiter=sep))
    if cols is None:
        cols, rows = rows[0], rows[1:]
    cols = [c.strip() for c in cols]
    return cols, [r + [""] * (len(cols) - len(r)) if len(r) < len(cols) else r[:len(cols)] for r in rows]


def q(name):
    return '"%s"' % name.replace('"', '""')


def load_datasets(db, names):
    """the bot datasets (build/datasets.py): one table each (ds_<name>, all TEXT), joins resolved,
    item-id columns indexed for the item pages, searchable rows in the second full-text index"""
    db.executescript("""
      CREATE TABLE datasets (name TEXT PRIMARY KEY, title TEXT, grp TEXT, ord INTEGER, descr TEXT, file TEXT,
                             cols TEXT, item TEXT, pf TEXT, skill TEXT, label TEXT, rows INTEGER);
      CREATE TABLE ds_item_refs (item_id INTEGER, ds TEXT, rid INTEGER);
      CREATE VIRTUAL TABLE rows_fts USING fts5(ds UNINDEXED, rid UNINDEXED, label, text, tokenize = 'unicode61 remove_diacritics 2');
    """)
    nds = nrows = 0
    loaded = {}
    for i, d in enumerate(DATASETS):
        path = os.path.join(DATA, "nadybot", d["file"])
        if not os.path.exists(path):
            print("  missing", d["file"]); continue
        cols, rows = load_csv(path, d.get("cols"), d.get("sep", ","))
        t = "ds_" + d["name"]
        db.execute("CREATE TABLE %s (%s)" % (q(t), ", ".join("%s TEXT" % q(c) for c in cols)))
        db.executemany("INSERT INTO %s VALUES (%s)" % (q(t), ",".join("?" * len(cols))), rows)
        loaded[d["name"]] = (d, cols)
    # joins: extra columns looked up in another dataset
    for name, (d, cols) in loaded.items():
        for new, (key, other, okey, oval) in d.get("join", {}).items():
            if other not in loaded:
                continue
            t, o = q("ds_" + name), q("ds_" + other)
            db.execute("ALTER TABLE %s ADD COLUMN %s TEXT" % (t, q(new)))
            db.execute("UPDATE %s SET %s = (SELECT %s FROM %s WHERE %s.%s = %s.%s LIMIT 1)" % (t, q(new), q(oval), o, o, q(okey), t, q(key)))
            cols.append(new)
    # items the game table lacks get the bot's item names (aodb)
    if "items_ql" in loaded:
        for lo, hi, nm in db.execute('SELECT lowid, highid, name FROM ds_items_ql').fetchall():
            for x in (lo, hi):
                if x and x.isdigit() and int(x) not in names:
                    names[int(x)] = nm
                    db.execute("INSERT OR IGNORE INTO items VALUES (?, ?)", (int(x), nm))
    # nano programs (spells, not items): the item-modifier table also lists what they buff; name them
    db.execute("CREATE TABLE nano_programs (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    for sql in ("SELECT id, name FROM ds_nano_buffs", "SELECT nano_id, nano_name FROM ds_nanos"):
        try:
            for i, nm in db.execute(sql).fetchall():
                if i and str(i).isdigit() and nm and int(i) not in names:
                    db.execute("INSERT OR IGNORE INTO nano_programs VALUES (?, ?)", (int(i), nm))
        except sqlite3.Error:
            pass
    # item icons (the bots' item table names an icon for each low / high id; data/icons/<icon>.png)
    db.execute("CREATE TABLE item_icons (item_id INTEGER PRIMARY KEY, icon INTEGER)")
    if "items_ql" in loaded:
        for lo, hi, icon in db.execute("SELECT lowid, highid, icon FROM ds_items_ql").fetchall():
            if icon and str(icon).isdigit():
                for x in (lo, hi):
                    if x and str(x).isdigit():
                        db.execute("INSERT OR IGNORE INTO item_icons VALUES (?, ?)", (int(x), int(icon)))
    pf_names = {r[0]: r[1] for r in db.execute("SELECT id, long_name FROM ds_playfields")} if "playfields" in loaded else {}
    for name, (d, cols) in loaded.items():
        t = q("ds_" + name)
        rows = db.execute("SELECT rowid, * FROM %s" % t).fetchall()
        refs = []
        for r in rows:
            rid, vals = r[0], dict(zip(cols, r[1:]))
            for c in d.get("item", []):
                v = vals.get(c) or ""
                if v.isdigit():
                    refs.append((int(v), name, rid))
            if d.get("search"):
                label = " \u00b7 ".join(str(vals.get(c) or "") for c in d.get("label", []) if vals.get(c))
                extra = [names.get(int(vals[c]), "") for c in d.get("item", []) if (vals.get(c) or "").isdigit()]
                extra += [pf_names.get(vals[c], "") for c in d.get("pf", []) if vals.get(c)]
                text = " ".join(str(v) for v in vals.values() if v) + " " + " ".join(extra)
                db.execute("INSERT INTO rows_fts VALUES (?, ?, ?, ?)", (name, rid, label, text))
        db.executemany("INSERT INTO ds_item_refs VALUES (?, ?, ?)", refs)
        db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            name, d["title"], d["group"], DATASETS.index(d), d["desc"], d["file"], json.dumps(cols), json.dumps(d.get("item", [])),
            json.dumps(d.get("pf", [])), json.dumps(d.get("skill", [])), json.dumps(d.get("label", [])), len(rows)))
        nds += 1
        nrows += len(rows)
    db.execute("CREATE INDEX ds_item_refs_item ON ds_item_refs (item_id)")
    print("  datasets: %d, rows: %d" % (nds, nrows))
    return nds, nrows


def main():
    out = sys.argv[1]
    with_aou = "--with-aou" in sys.argv
    if os.path.exists(out):
        os.remove(out)
    db = sqlite3.connect(out)
    db.executescript("""
      CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
      CREATE TABLE entries (key TEXT PRIMARY KEY, kind TEXT, num INTEGER, name TEXT, author TEXT, source TEXT,
                            url TEXT, html TEXT, plain TEXT);
      CREATE TABLE entry_items (key TEXT, item_id INTEGER);
      CREATE VIRTUAL TABLE fts USING fts5(key UNINDEXED, name, plain, items, tokenize = 'unicode61 remove_diacritics 2');
      CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
    """)
    names = {}
    with open(os.path.join(DATA, "items.tsv"), encoding="utf-8") as f:
        for line in f:
            i, _, n = line.rstrip("\r\n").partition("\t")  # \r too: a CRLF checkout must not change the names
            if i.isdigit():
                names[int(i)] = n
    db.executemany("INSERT INTO items VALUES (?, ?)", names.items())

    def add(kind, num, name, author, source, url, ao):
        h, plain, ids = ao_to_html(ao)
        key = "%s-%d" % (kind, num)
        ids = sorted(set(ids))
        db.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?)", (key, kind, num, name, author, source, url, h, plain))
        db.executemany("INSERT INTO entry_items VALUES (?, ?)", [(key, i) for i in ids])
        db.execute("INSERT INTO fts VALUES (?,?,?,?)", (key, name, plain, " ".join(names.get(i, "") for i in ids)))

    n = {"recipe": 0, "text": 0, "guide": 0}
    for rid, name, author, body in bot_recipes():
        add("recipe", rid, name, author, "AO recipe bots (Nadybot recipe module, GPL-3.0)", "", body); n["recipe"] += 1
    for r in json.load(open(os.path.join(DATA, "item_texts.json"), encoding="utf-8")):
        body = '<a href="itemref://%d/%d/1">%s</a>\n\n%s' % (r["id"], r["id"], r["name"], r["text"])
        add("text", r["id"], r["name"], "", "The game's own item description", "", body); n["text"] += 1
    gp = os.path.join(DATA, "aou", "guides.json")
    if with_aou and os.path.exists(gp):
        seen = set()
        for g in json.load(open(gp, encoding="utf-8")):
            if g["id"] in seen:  # a guide can sit in two folders
                continue
            seen.add(g["id"])
            add("guide", g["id"], g["name"], g["author"], "AO-Universe tradeskill guide (%s)" % g["part"], g["url"], g["ao"]); n["guide"] += 1
    # ---- the bot's own guides (GUIDE_MODULE): entries like the recipes
    gd = os.path.join(DATA, "nadybot", BOT_GUIDES)
    n["botguide"] = 0
    if os.path.isdir(gd):
        for i, fn in enumerate(sorted(f for f in os.listdir(gd) if f.endswith(".txt")), 1):
            title = fn[:-4].replace("_", " ").title()
            add("botguide", i, title, "", "AO bot guide (Nadybot guide module, GPL-3.0)", "", open(os.path.join(gd, fn), encoding="utf-8", errors="replace").read())
            n["botguide"] += 1
    nd = load_datasets(db, names)
    db.executemany("INSERT INTO meta VALUES (?, ?)", [("count_" + k, str(v)) for k, v in n.items()] +
                   [("items", str(db.execute("SELECT count(*) FROM items").fetchone()[0])), ("datasets", str(nd[0])), ("dataset_rows", str(nd[1]))])
    db.commit()
    db.execute("VACUUM")
    db.close()
    print("built %s: %s, %d item names" % (out, n, len(names)))


if __name__ == "__main__":
    main()
