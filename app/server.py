#!/usr/bin/env python3
"""AO Wiki: an offline search over Anarchy Online recipes, guides, item texts and
the bot datasets (loot, locations, nanos, implants, perks, ...).

    python3 app/server.py [--db archive.sqlite] [--port 8080]

Standard library only, no JavaScript, no outside requests: everything comes from the SQLite file
built by build/build_db.py.
Pages:  /?q=           search (entries, items, data rows)
        /e/<key>       a recipe / guide / item text / bot guide
        /item/<id>     an item and everything that mentions it
        /data          the datasets;  /d/<name>?q=&p=  one (filter, pages);  /d/<name>/<row>  one row
        /level?l=&with=&mission=   level lookup: team / PvP ranges, XP / SK, mission QLs (the bots' !level)
        /maps          planet maps and zone maps;  /map/<zone>  a zone map with markers;  /planet/<slug>
Media (from --media, default data/ next to app/ or /app/media): /icons/<id>.png /maps/<zone>.jpg /planet/<slug>.jpg
JSON:   /api/search?q=&limit=  /api/entry/<key>  /api/item/<id>  /api/datasets  /api/d/<name>?q=&p=
        /api/d/<name>/<row>  /api/stats  /healthz
"""
import argparse
import html
import json
import os
import re
import sqlite3
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
import sys  # noqa: E402
sys.path.insert(0, HERE)
try:
    from tools import TOOLS  # the bot lookups (GPL-3.0, app/tools/)
except Exception as _e:  # a broken tool must not take the site down
    TOOLS, TOOLS_ERROR = {}, repr(_e)
else:
    TOOLS_ERROR = None
KIND = {"recipe": "Bot recipe", "guide": "AO-Universe guide", "text": "Game item text", "botguide": "Bot guide"}
PAGE = 50
local = threading.local()
DB_PATH = None
MEDIA = None  # folder with icons/, maps/ (+ index.json), planet/ and planet_extra/ (+ index.json)
_maps = {}


def zone_maps():
    """zone id -> {name, x0, z0, x1, z1, w, h} for the zone maps that exist"""
    if not _maps and MEDIA:
        try:
            for k, v in json.load(open(os.path.join(MEDIA, "maps", "index.json"))).items():
                _maps[int(k)] = v
        except (OSError, ValueError):
            pass
    return _maps


def planet_maps():
    out = {}
    for folder in ("planet", "planet_extra"):
        try:
            for k, v in json.load(open(os.path.join(MEDIA, folder, "index.json"))).items():
                out[k] = dict(v, folder=folder)
        except (OSError, ValueError, TypeError):
            pass
    return out


def icon_of(iid):
    r = db().execute("SELECT icon FROM item_icons WHERE item_id = ?", (iid,)).fetchone()
    if r and MEDIA and os.path.exists(os.path.join(MEDIA, "icons", "%d.png" % r[0])):
        return r[0]


def icon_img(iid, cls="icon"):
    ic = icon_of(iid)
    return "<img class='%s' src='/icons/%d.png' alt='' width='32' height='32'>" % (cls, ic) if ic else ""
E = html.escape
ENTRY_KEY = r"(?:recipe|guide|text|botguide)-\d+"


def db():
    c = getattr(local, "db", None)
    if c is None:
        c = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True, check_same_thread=False)
        c.row_factory = sqlite3.Row
        local.db = c
    return c


def fts_query(q):
    # words -> prefix terms, ANDed; anything else is dropped so user input never reaches FTS syntax
    words = re.findall(r"[\w']+", q.lower())
    return " ".join('"%s"*' % w.replace('"', "") for w in words[:8])


# ---------------------------------------------------------------- datasets ----
_ds = {}


def datasets():
    if not _ds:
        for r in db().execute("SELECT * FROM datasets ORDER BY ord"):
            d = dict(r)
            for k in ("cols", "item", "pf", "skill", "label"):
                d[k] = json.loads(d[k])
            _ds[d["name"]] = d
    return _ds


_lookups = {}


def lookup(kind):
    """id -> name maps for playfields and skills (from the datasets themselves)"""
    if kind not in _lookups:
        m = {}
        try:
            if kind == "pf":
                m = {r[0]: r[1] for r in db().execute("SELECT id, long_name FROM ds_playfields")}
            elif kind == "skill":
                m = {r[0]: r[1] for r in db().execute("SELECT id, name FROM ds_skills")}
        except sqlite3.Error:
            pass
        _lookups[kind] = m
    return _lookups[kind]


def item_name(i):
    r = db().execute("SELECT name FROM items WHERE id = ?", (i,)).fetchone()
    if r:
        return r[0]
    r = db().execute("SELECT name FROM nano_programs WHERE id = ?", (i,)).fetchone()
    return ("Nano program: " + r[0]) if r else None


def ds_rows(name, q="", page=0):
    d = datasets()[name]
    t = '"ds_%s"' % name
    where, args = "", []
    if q:
        cat = " || ' ' || ".join('coalesce("%s", \'\')' % c.replace('"', '""') for c in d["cols"])
        where, args = "WHERE lower(%s) LIKE ?" % cat, ["%" + q.lower() + "%"]
    total = db().execute("SELECT count(*) FROM %s %s" % (t, where), args).fetchone()[0]
    rows = db().execute("SELECT rowid AS _row, * FROM %s %s ORDER BY rowid LIMIT ? OFFSET ?" % (t, where), args + [PAGE, page * PAGE]).fetchall()
    return total, [dict(r) for r in rows]


def ds_row(name, rid):
    r = db().execute('SELECT rowid AS _row, * FROM "ds_%s" WHERE rowid = ?' % name, (rid,)).fetchone()
    return dict(r) if r else None


# ---------------------------------------------------------------- search ----
def search(q, limit=50):
    q = q.strip()
    out = {"entries": [], "items": [], "data": []}
    if len(q) < 2:
        return out
    like = "%" + q.lower() + "%"
    seen = set()
    for r in db().execute("SELECT key, kind, name, source FROM entries WHERE lower(name) LIKE ? ORDER BY length(name) LIMIT ?", (like, limit)):
        out["entries"].append(dict(r, why="name")); seen.add(r["key"])
    fq = fts_query(q)
    if fq:
        for r in db().execute("SELECT e.key, e.kind, e.name, e.source FROM fts JOIN entries e ON e.key = fts.key "
                              "WHERE fts MATCH ? ORDER BY bm25(fts, 0, 10, 1, 4) LIMIT ?", (fq, limit * 2)):
            if r["key"] not in seen and len(out["entries"]) < limit:
                out["entries"].append(dict(r, why="mentions")); seen.add(r["key"])
        ds = datasets()
        for r in db().execute("SELECT ds, rid, label FROM rows_fts WHERE rows_fts MATCH ? ORDER BY bm25(rows_fts, 0, 0, 10, 1) LIMIT ?", (fq, limit)):
            if r["ds"] in ds:
                out["data"].append({"dataset": r["ds"], "title": ds[r["ds"]]["title"], "row": r["rid"], "label": r["label"]})
    for r in db().execute("SELECT id, name FROM items WHERE lower(name) LIKE ? ORDER BY length(name), id LIMIT 300", (like,)):
        if len(out["items"]) >= 20:
            break
        if not any(x["name"] == r["name"] for x in out["items"]):  # one per name (QL variants share it)
            out["items"].append(dict(r))
    return out


def entry(key):
    r = db().execute("SELECT * FROM entries WHERE key = ?", (key,)).fetchone()
    if not r:
        return None
    e = dict(r)
    e["items"] = [dict(x) for x in db().execute(
        "SELECT i.id, i.name FROM entry_items ei JOIN items i ON i.id = ei.item_id WHERE ei.key = ? ORDER BY i.name", (key,))]
    return e


def item(iid):
    r = db().execute("SELECT id, name FROM items WHERE id = ?", (iid,)).fetchone()
    if not r:  # a nano program (spell) the datasets mention
        r = db().execute("SELECT id, 'Nano program: ' || name AS name FROM nano_programs WHERE id = ?", (iid,)).fetchone()
    if not r:
        return None
    it = dict(r)
    try:
        ql = db().execute("SELECT lowid, highid, lowql, highql, slot, froob_friendly FROM ds_items_ql WHERE lowid = ? OR highid = ? LIMIT 1",
                          (str(iid), str(iid))).fetchone()
        it["ql"] = dict(ql) if ql else None
    except sqlite3.Error:
        it["ql"] = None
    it["entries"] = [dict(x) for x in db().execute(
        "SELECT e.key, e.kind, e.name, e.source FROM entry_items ei JOIN entries e ON e.key = ei.key WHERE ei.item_id = ? "
        "ORDER BY e.kind, e.name", (iid,))]
    data = {}
    for x in db().execute("SELECT ds, rid FROM ds_item_refs WHERE item_id = ? ORDER BY ds, rid", (iid,)):
        if x["ds"] == "items_ql":
            continue
        rows = data.setdefault(x["ds"], [])
        if len(rows) < 60:
            rows.append(ds_row(x["ds"], x["rid"]))
    it["data"] = data
    return it


def stats():
    m = {r["k"]: r["v"] for r in db().execute("SELECT k, v FROM meta")}
    g = lambda k: int(m.get(k, 0))
    return {"recipes": g("count_recipe"), "guides": g("count_guide"), "item_texts": g("count_text"), "bot_guides": g("count_botguide"),
            "items": g("items"), "datasets": g("datasets"), "dataset_rows": g("dataset_rows")}


# ---------------------------------------------------------------- pages ----
def page(title, body, q=""):
    s = stats()
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title><link rel="stylesheet" href="/static/style.css"></head><body>
<header><a class="brand" href="/">AO Wiki</a><nav><a href="/">Search</a><a href="/data">Data</a><a href="/level">Levels</a><a href="/tools">Lookups</a><a href="/maps">Maps</a></nav>
<form action="/" method="get"><input type="search" name="q" value="%s" placeholder="Item, recipe, boss, nano, place..." autofocus>
<button>Search</button></form></header>
<main>%s</main>
<footer>%d bot recipes &middot; %d AO-Universe guides &middot; %d game item texts &middot; %d bot guides &middot;
%d datasets (%s rows) &middot; %s item names.<br>
Recipes, bot guides and datasets: the AO bots (Nadybot / Budabot, GPL-3.0). Guides &copy; their authors on ao-universe.com.
Anarchy Online and its item data &copy; Funcom. Unofficial fan archive; it never connects to the game.</footer>
</body></html>""" % (E(title), E(q), body, s["recipes"], s["guides"], s["item_texts"], s["bot_guides"], s["datasets"],
                     "{:,}".format(s["dataset_rows"]), "{:,}".format(s["items"]))


def tag(kind):
    return '<span class="tag %s">%s</span>' % (kind, KIND.get(kind, kind))


def cell(d, col, v):
    """one dataset value, with ids turned into names / links"""
    if v is None or v == "":
        return ""
    v = str(v)
    if col in d["item"] and v.isdigit() and v != "0":
        n = item_name(int(v))
        return "<a class='item' href='/item/%s'>%s</a>" % (v, E(n) if n else v)
    if col in d["pf"] and (v in lookup("pf") or (v.isdigit() and int(v) in zone_maps())):
        nm = lookup("pf").get(v) or zone_maps().get(int(v), {}).get("name", v)
        if v.isdigit() and int(v) in zone_maps():
            return "<a href='/map/%s'>%s</a> <span class='dim'>(%s)</span>" % (v, E(nm), E(v))
        return "%s <span class='dim'>(%s)</span>" % (E(nm), E(v))
    if col in d["skill"] and v in lookup("skill"):
        return "%s <span class='dim'>(%s)</span>" % (E(lookup("skill")[v]), E(v))
    return E(v).replace("\\n", "<br>").replace("\n", "<br>")


def table(d, rows, link_rows=True, hide=()):
    cols = [c for c in d["cols"] if c not in hide]
    head = "".join("<th>%s</th>" % E(c) for c in cols)
    body = "".join("<tr>%s%s</tr>" % (
        "<td><a href='/d/%s/%d'>#%d</a></td>" % (d["name"], r["_row"], r["_row"]) if link_rows else "",
        "".join("<td%s>%s</td>" % (" class='n'" if len(str(r.get(c) or "")) <= 12 and c not in d["item"] else "", cell(d, c, r.get(c)))
                for c in cols)) for r in rows)
    return "<div class='scroll'><table><thead><tr>%s%s</tr></thead><tbody>%s</tbody></table></div>" % (
        "<th></th>" if link_rows else "", head, body)


def results_html(q, res):
    if not q:
        s = stats()
        return ("<section class='intro'><h1>Search the Anarchy Online archive</h1>"
                "<p>Type an item, recipe, boss, nano, place or perk. Recipes and guides come first, then items, then rows from the "
                "<a href='/data'>datasets</a>. Every item links to everything that mentions it.</p>"
                "<p class='dim'>%d recipes, %d guides, %d game texts, %d bot guides and %d datasets with %s rows, all offline.</p>"
                "<p class='dim'>Try: <a href='/?q=carbonum'>carbonum</a> &middot; <a href='/?q=tarasque'>tarasque</a> "
                "&middot; <a href='/?q=solar-powered'>solar-powered</a> &middot; <a href='/?q=ofab'>ofab</a> "
                "&middot; <a href='/?q=reet'>reet</a> &middot; <a href='/?q=composite'>composite</a></p></section>"
                % (s["recipes"], s["guides"], s["item_texts"], s["bot_guides"], s["datasets"], "{:,}".format(s["dataset_rows"])))
    parts = []
    lm = re.fullmatch(r"\s*(?:level|lvl|lev|l)?\s*(\d{1,3})\s*", q, re.I)
    if lm and level(int(lm.group(1))):
        parts.append(level_card(level(int(lm.group(1)))) + "<p><a href='/level?l=%s'>Level lookup &rarr;</a></p>" % lm.group(1))
    if res["entries"]:
        parts.append("<h2>Recipes and guides</h2><ul class='results'>%s</ul>" % "".join(
            "<li><a href='/e/%s'>%s</a> %s%s</li>" % (E(r["key"]), E(r["name"]), tag(r["kind"]),
                                                      " <span class='dim'>mentions it</span>" if r["why"] == "mentions" else "")
            for r in res["entries"]))
    if res["items"]:
        parts.append("<h2>Items</h2><ul class='results cols'>%s</ul>" % "".join(
            "<li>%s<a class='item' href='/item/%d'>%s</a></li>" % (icon_img(r["id"], "icon sm"), r["id"], E(r["name"])) for r in res["items"]))
    if res["data"]:
        parts.append("<h2>In the datasets</h2><ul class='results'>%s</ul>" % "".join(
            "<li><a href='/d/%s/%d'>%s</a> <span class='tag data'>%s</span></li>" % (
                E(r["dataset"]), r["row"], E(r["label"] or "#%d" % r["row"]), E(r["title"])) for r in res["data"]))
    if not parts:
        return "<p class='dim'>Nothing found for &ldquo;%s&rdquo;.</p>" % E(q)
    return "<p class='dim'>Results for &ldquo;%s&rdquo;</p>%s" % (E(q), "".join(parts))


def entry_html(e):
    meta = [E(e["source"])]
    if e["author"]:
        meta.insert(0, "by " + E(e["author"]))
    if e["url"]:
        meta.append("original: <span class='url'>%s</span>" % E(e["url"]))
    items = "".join("<li><a href='/item/%d'>%s</a></li>" % (i["id"], E(i["name"])) for i in e["items"])
    return ("<div class='split'><article class='ao'><h1>%s</h1><p class='meta'>%s %s</p><div class='body'>%s</div></article>"
            "%s</div>" % (E(e["name"]), tag(e["kind"]), " &middot; ".join(meta), e["html"],
                          "<aside><h2>Items in it</h2><ul class='items'>%s</ul></aside>" % items if items else ""))


def item_html(it, ql):
    ds = datasets()
    li = "".join("<li><a href='/e/%s'>%s</a> %s</li>" % (E(x["key"]), E(x["name"]), tag(x["kind"])) for x in it["entries"])
    meta = ["item %d" % it["id"]]
    if it.get("ql"):
        g = it["ql"]
        meta.append("QL %s&ndash;%s (ids %s / %s)" % (E(g["lowql"] or "?"), E(g["highql"] or "?"), E(g["lowid"]), E(g["highid"])))
        if g.get("slot"):
            meta.append("slot " + E(g["slot"]))
    if ql and ql != "1":
        meta.append("linked at QL " + E(ql))
    # where it comes from and what it is first; raw stat tables last
    LAST = ("item_buffs", "item_types", "item_groups", "weapon_attributes", "what_locks", "symbiant_clusters",
            "symbiant_abilities", "symbiant_professions")
    order = sorted((n for n in it["data"] if n in ds), key=lambda n: (n in LAST, LAST.index(n) if n in LAST else ds[n]["ord"]))
    def own_cols(n, rows):  # item columns that only ever hold this item: left out
        return [c for c in ds[n]["item"] if all(str(r.get(c)) == str(it["id"]) for r in rows)]
    data = "".join("<h2>%s <span class='dim'>(%s)</span></h2>%s" % (
        E(ds[n]["title"]), "<a href='/d/%s'>dataset</a>" % n, table(ds[n], it["data"][n], hide=own_cols(n, it["data"][n]))) for n in order)
    return ("<article class='ao'><h1>%s%s</h1><p class='meta'>%s &middot; <a href='/?q=%s'>search for this name</a></p>"
            "<h2>Recipes and guides</h2>%s%s</article>" % (
                icon_img(it["id"]), E(it["name"]), " &middot; ".join(meta), urllib.parse.quote_plus(it["name"]),
                "<ul class='results'>%s</ul>" % li if li else "<p class='dim'>None mention it.</p>", data))


# ---------------------------------------------------------------- levels ----
# the bots' level table (LEVEL_MODULE/levels.csv): team and PvP ranges per level, XP (SK from 200),
# tokens, daily mission XP, the 11 mission-slider QLs, max AI level, max LE research, XP-giving mob levels
def level(n):
    try:
        r = db().execute('SELECT * FROM "ds_levels" WHERE CAST(level AS INTEGER) = ?', (int(n),)).fetchone()
    except (sqlite3.Error, ValueError):
        return None
    if not r:
        return None
    d = {k: r[k] for k in r.keys()}
    out = {k: int(d[k]) if str(d[k]).lstrip("-").isdigit() else d[k] for k in d}
    out["missions"] = [int(x) for x in str(d["missions"]).split(",") if x.strip().isdigit()]
    return out


def can_team(a, b):
    la, lb = level(a), level(b)
    return bool(la and lb and la["teamMin"] <= b <= la["teamMax"] and lb["teamMin"] <= a <= lb["teamMax"])


def can_pvp(a, b):
    la, lb = level(a), level(b)
    return bool(la and lb and la["pvpMin"] <= b <= la["pvpMax"] and lb["pvpMin"] <= a <= lb["pvpMax"])


def mission_levels(ql):
    """levels whose mission slider reaches QL `ql` (lowest to highest slider QL)"""
    out = []
    for r in db().execute('SELECT level, missions FROM "ds_levels" ORDER BY CAST(level AS INTEGER)'):
        m = [int(x) for x in str(r[1]).split(",") if x.strip().isdigit()]
        if m and min(m) <= ql <= max(m):
            out.append(int(r[0]))
    return out


def ranges(levels):
    """[1,2,3,7,8] -> '1-3, 7-8'"""
    out, start, prev = [], None, None
    for x in levels + [None]:
        if start is None:
            start = prev = x
        elif x is not None and x == prev + 1:
            prev = x
        else:
            out.append(str(start) if start == prev else "%d\u2013%d" % (start, prev))
            start = prev = x
    return ", ".join(o for o in out if o != "None")


def level_card(L):
    xs = "SK" if L["level"] >= 200 else "XP"
    nxt = ("{:,} %s to level %d" % (xs, L["level"] + 1)).format(L["xpsk"]) if L["xpsk"] else "max level"
    rows = [("Team with", "levels %d\u2013%d" % (L["teamMin"], L["teamMax"])),
            ("PvP with", "levels %d\u2013%d" % (L["pvpMin"], L["pvpMax"])),
            ("Next level", nxt),
            ("Mission QLs (slider)", ", ".join(map(str, L["missions"]))),
            ("Mobs that give XP", "levels %d\u2013%d" % (L["mob_min"], L["mob_max"])),
            ("Tokens per token board level", str(L["tokens"])),
            ("Daily mission XP", "%s%%" % L["daily_mission_xp"]),
            ("Max AI level", str(L["max_ai_level"])), ("Max LE research", str(L["max_le_level"]))]
    return ("<div class='levelcard'><h2>Level %d</h2><table class='kv'>%s</table></div>" % (
        L["level"], "".join("<tr><th>%s</th><td>%s</td></tr>" % (E(k), E(v)) for k, v in rows)))


def level_html(qs):
    g = lambda k: (qs.get(k) or [""])[0].strip()
    lv, w, mq = g("l"), g("with"), g("mission")
    out = ["<article class='ao'><h1>Level lookup</h1><p class='dim'>Team and PvP ranges, XP / SK, mission QLs: the "
           "bots' <code>!level</code>, <code>!team</code> and <code>!missions</code>.</p>"
           "<form class='filter' action='/level' method='get'>"
           "<input type='number' name='l' min='1' max='220' value='%s' placeholder='Level'>"
           "<input type='number' name='with' min='1' max='220' value='%s' placeholder='Team / PvP with level (optional)'>"
           "<button>Look up</button></form>"
           "<form class='filter' action='/level' method='get'><input type='number' name='mission' min='1' max='300' value='%s' "
           "placeholder='Who can roll missions of QL ...'><button>Missions</button></form>" % (E(lv), E(w), E(mq))]
    if lv.isdigit():
        L = level(int(lv))
        if not L:
            out.append("<p class='dim'>No level %s (1\u2013220).</p>" % E(lv))
        else:
            out.append(level_card(L))
            if w.isdigit() and level(int(w)):
                a, b = int(lv), int(w)
                out.append("<p class='verdict'>Level %d and level %d: <b>%s</b> team, <b>%s</b> fight in PvP.</p>" % (
                    a, b, "can" if can_team(a, b) else "cannot", "can" if can_pvp(a, b) else "cannot"))
    if mq.isdigit():
        lv_ = mission_levels(int(mq))
        out.append("<p class='verdict'>QL %s missions: levels <b>%s</b> can roll them on the mission slider.</p>" % (
            E(mq), E(ranges(lv_)) if lv_ else "none"))
    out.append("<p class='dim'>Data: the bots' level table, <a href='/d/levels'>all 220 levels</a>.</p></article>")
    return "".join(out)


# ---------------------------------------------------------------- maps ----
# points of interest per zone: datasets with a zone id and x / y coordinates (AO's map coordinates:
# x east, y north, the same frame as the zone map images)
POI = [("whereis", "playfield_id", "xcoord", "ycoord", ("name",), "where"),
       ("dynacamps", "playfield_id", "x_coord", "y_coord", ("mob", "min_ql", "max_ql"), "dyna"),
       ("tower_sites", "playfield_id", "x_coord", "y_coord", ("site_name", "min_ql", "max_ql"), "tower")]
POI_KIND = {"where": "Where is", "dyna": "Dyna camp", "tower": "Tower site"}


def zone_pois(zone):
    out = []
    for ds, zc, xc, yc, label, kind in POI:
        if ds not in datasets():
            continue
        cols = ", ".join('"%s"' % c for c in (xc, yc) + label)
        for r in db().execute('SELECT rowid, %s FROM "ds_%s" WHERE "%s" = ?' % (cols, ds, zc), (str(zone),)):
            try:
                x, y = float(r[1]), float(r[2])
            except (TypeError, ValueError):
                continue
            vals = [str(v) for v in r[3:] if v not in (None, "")]
            name = vals[0] if vals else "#%d" % r[0]
            if len(vals) == 3:
                name += " (QL %s\u2013%s)" % (vals[1], vals[2])
            out.append({"kind": kind, "ds": ds, "row": r[0], "name": name, "x": x, "y": y})
    return out


def maps_html(q):
    pm = planet_maps()
    cards = "".join("<li><a href='/planet/%s'>%s</a> <span class='dim'>&middot; %d&times;%d%s</span></li>" % (
        k, E(v["name"]), v["w"], v["h"], " &middot; player-made, local copy only" if v["third_party"] else "") for k, v in pm.items())
    zm = zone_maps()
    rows = sorted(zm.items(), key=lambda kv: kv[1]["name"].lower())
    if q:
        rows = [kv for kv in rows if q.lower() in kv[1]["name"].lower() or q == str(kv[0])]
    zl = "".join("<li><a href='/map/%d'>%s</a> <span class='dim'>%d</span></li>" % (k, E(v["name"]), k) for k, v in rows)
    return ("<article class='ao'><h1>Maps</h1><h2>Planet maps</h2><ul class='results'>%s</ul>"
            "<h2>Zone maps <span class='dim'>(%d)</span></h2>"
            "<p class='dim'>Drawn top-down from the game's terrain and collision data, north up. Zones with places, dyna camps "
            "or tower sites in the datasets show them as markers.</p>"
            "<form class='filter' action='/maps' method='get'><input type='search' name='q' value='%s' placeholder='Filter zones'>"
            "<button>Filter</button></form><ul class='results cols'>%s</ul></article>" % (
                cards or "<li class='dim'>none</li>", len(zm), E(q), zl or "<li class='dim'>no zone matches</li>"))


def zone_html(zone, m):
    pois = zone_pois(zone)
    dots, legend = [], []
    for i, p in enumerate(pois, 1):
        left = (p["x"] - m["x0"]) / (m["x1"] - m["x0"]) * 100
        top = (m["z1"] - p["y"]) / (m["z1"] - m["z0"]) * 100
        if not (-1 <= left <= 101 and -1 <= top <= 101):
            continue
        tip = "%d. %s: %s (%.0f, %.0f)" % (i, POI_KIND[p["kind"]], p["name"], p["x"], p["y"])
        dots.append("<a class='poi %s' href='/d/%s/%d' style='left:%.2f%%;top:%.2f%%' title='%s'><span>%d</span></a>" % (
            p["kind"], p["ds"], p["row"], left, top, E(tip), i))
        legend.append("<li><span class='key %s'>%d</span> <a href='/d/%s/%d'>%s</a> <span class='dim'>%s &middot; %.0f, %.0f</span></li>" % (
            p["kind"], i, p["ds"], p["row"], E(p["name"]), POI_KIND[p["kind"]], p["x"], p["y"]))
    size = "%.0f &times; %.0f m" % (m["x1"] - m["x0"], m["z1"] - m["z0"])
    return ("<article class='ao'><h1>%s <span class='dim'>%d</span></h1><p class='meta'>%s &middot; north up &middot; "
            "x %.0f&ndash;%.0f, y %.0f&ndash;%.0f &middot; <a href='/maps/%d.jpg'>full image</a></p>"
            "<div class='mapwrap'><img src='/maps/%d.jpg' alt='Map of %s' width='%d' height='%d'>%s</div>"
            "%s</article>" % (
                E(m["name"]), zone, size, m["x0"], m["x1"], m["z0"], m["z1"], zone, zone, E(m["name"]), m["w"], m["h"], "".join(dots),
                "<h2>On this map</h2><ul class='results legend'>%s</ul>" % "".join(legend) if legend else
                "<p class='dim'>No places from the datasets in this zone.</p>"))


def planet_html(slug, v):
    return ("<article class='ao'><h1>%s</h1><p class='meta'>%d &times; %d%s &middot; <a href='/planet/%s.jpg'>full image</a></p>"
            "<div class='scroll'><img class='planet' src='/planet/%s.jpg' alt='%s' width='%d' height='%d'></div></article>" % (
                E(v["name"]), v["w"], v["h"], " &middot; player-made map shipped with the game; this copy is local only" if v["third_party"] else
                " &middot; Funcom's map from the game", slug, slug, E(v["name"]), v["w"], v["h"]))


# ---------------------------------------------------------------- bot lookups ----
def tool_params(t, qs):
    """form values -> typed params; None for empty; ValueError on bad numbers"""
    p, given = {}, False
    for f in t["fields"]:
        raw = (qs.get(f["name"]) or [""])[0].strip()[:200]
        if raw == "":
            p[f["name"]] = None
            continue
        given = True
        if f["type"] in ("int", "item"):
            p[f["name"]] = int(raw)
        elif f["type"] == "float":
            p[f["name"]] = float(raw)
        else:
            p[f["name"]] = raw
    return p, given


def tool_form(t, qs):
    parts = []
    for f in t["fields"]:
        v = (qs.get(f["name"]) or [f.get("default", "")])[0]
        lab = "<label>%s" % E(f["label"])
        if f["type"] == "select":
            opts = "".join("<option value='%s'%s>%s</option>" % (E(str(o[0])), " selected" if str(o[0]) == str(v) else "", E(str(o[1])))
                           for o in f.get("options", []))
            parts.append("%s<select name='%s'>%s</select></label>" % (lab, E(f["name"]), opts))
        else:
            typ = "number" if f["type"] in ("int", "float", "item") else "text"
            step = " step='any'" if f["type"] == "float" else ""
            parts.append("%s<input type='%s'%s name='%s' value='%s'></label>" % (lab, typ, step, E(f["name"]), E(str(v))))
    return "<form class='toolform' action='/tool/%s' method='get'>%s<button>Look up</button></form>" % (t["name"], "".join(parts))


def tools_html():
    groups = {}
    for t in TOOLS.values():
        groups.setdefault(t["group"], []).append(t)
    out = ["<article class='ao'><h1>Lookups</h1><p class='dim'>The calculations the chat bots answered, ported from Nadybot "
           "(GPL-3.0). Every one works offline.</p>"]
    if TOOLS_ERROR:
        out.append("<p class='verdict'>Some lookups failed to load: %s</p>" % E(TOOLS_ERROR))
    for g in sorted(groups):
        out.append("<h2>%s</h2><ul class='results'>%s</ul>" % (E(g), "".join(
            "<li><a href='/tool/%s'>%s</a> <span class='tag data'>%s</span> <span class='dim'>%s</span></li>" % (
                t["name"], E(t["title"]), E(t.get("bot", "")), E(t["desc"])) for t in sorted(groups[g], key=lambda t: t["title"]))))
    return "".join(out) + "</article>"


def tool_html(t, qs):
    body = ""
    try:
        p, given = tool_params(t, qs)
        if given or not t["fields"]:
            body = t["run"](db(), p)["html"]
    except ValueError as ex:
        body = "<p class='verdict'>%s</p>" % E(str(ex))
    return ("<article class='ao'><h1>%s <span class='tag data'>%s</span></h1><p class='meta'>%s</p>%s<div class='toolout'>%s</div>"
            "<p class='dim'><a href='/tools'>All lookups</a></p></article>" % (E(t["title"]), E(t.get("bot", "")), E(t["desc"]), tool_form(t, qs), body))


def data_index_html():
    groups = {}
    for d in datasets().values():
        groups.setdefault(d["grp"], []).append(d)
    out = ["<h1>Datasets</h1><p class='dim'>The data the AO chat bots carried (Nadybot / Budabot modules, GPL-3.0), "
           "browsable and filterable. Item, zone and skill ids show as names.</p>"]
    for g, ds in groups.items():
        out.append("<h2>%s</h2><ul class='results'>%s</ul>" % (E(g), "".join(
            "<li><a href='/d/%s'>%s</a> <span class='dim'>&middot; %s rows &middot; %s</span></li>" % (
                d["name"], E(d["title"]), "{:,}".format(d["rows"]), E(d["descr"])) for d in ds)))
    return "<article class='ao'>%s</article>" % "".join(out)


def dataset_html(d, q, p, total, rows):
    pages = max(1, (total + PAGE - 1) // PAGE)
    qs = lambda n: "?%s" % urllib.parse.urlencode({k: v for k, v in (("q", q), ("p", n)) if v})
    nav = "<p class='pager'>%s <span class='dim'>page %d of %d &middot; %s rows</span> %s</p>" % (
        "<a href='/d/%s%s'>&larr; previous</a>" % (d["name"], qs(p - 1)) if p > 0 else "",
        p + 1, pages, "{:,}".format(total),
        "<a href='/d/%s%s'>next &rarr;</a>" % (d["name"], qs(p + 1)) if p + 1 < pages else "")
    return ("<article class='ao'><h1>%s</h1><p class='meta'>%s &middot; <span class='dim'>%s</span></p>"
            "<form class='filter' action='/d/%s' method='get'><input type='search' name='q' value='%s' placeholder='Filter rows'>"
            "<button>Filter</button></form>%s%s%s</article>" % (
                E(d["title"]), E(d["descr"]), E(d["file"]), d["name"], E(q), nav, table(d, rows), nav if len(rows) > 15 else ""))


def row_html(d, r):
    body = "".join("<tr><th>%s</th><td>%s</td></tr>" % (E(c), cell(d, c, r.get(c))) for c in d["cols"])
    return ("<article class='ao'><h1>%s <span class='dim'>#%d</span></h1><p class='meta'><a href='/d/%s'>%s</a></p>"
            "<table class='kv'>%s</table></article>" % (E(" · ".join(str(r.get(c)) for c in d["label"] if r.get(c)) or d["title"]),
                                                       r["_row"], d["name"], E(d["title"]), body))


class H(BaseHTTPRequestHandler):
    server_version = "AOWiki"

    def send(self, code, body, ctype="text/html; charset=utf-8", cache=False):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        if cache:
            self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self'; form-action 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(b)

    def js(self, obj, code=200):
        self.send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def nf(self, what="Not found"):
        return self.send(404, page("Not found", "<p>%s</p>" % E(what)))

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        qs = urllib.parse.parse_qs(u.query)
        q = (qs.get("q") or [""])[0][:100]
        p = u.path
        num = lambda k, dflt=0: max(0, int((qs.get(k) or [str(dflt)])[0] or dflt))
        try:
            if p == "/":
                return self.send(200, page(("%s - " % q if q else "") + "AO Wiki", results_html(q, search(q) if q else None), q))
            if p == "/static/style.css":
                return self.send(200, open(os.path.join(HERE, "static", "style.css"), "rb").read(), "text/css; charset=utf-8")
            m = re.fullmatch(r"/e/(%s)" % ENTRY_KEY, p)
            if m:
                e = entry(m.group(1))
                return self.send(200, page(e["name"], entry_html(e))) if e else self.nf("No such entry.")
            m = re.fullmatch(r"/item/(\d+)", p)
            if m:
                it = item(int(m.group(1)))
                return self.send(200, page(it["name"], item_html(it, (qs.get("ql") or [""])[0][:6]))) if it else self.nf("No such item.")
            m = re.fullmatch(r"/(icons|maps|planet)/([a-z0-9\-]+)\.(png|jpg)", p)
            if m and MEDIA:
                folder = m.group(1)
                path = os.path.join(MEDIA, folder, m.group(2) + "." + m.group(3))
                if folder == "planet" and not os.path.exists(path):
                    path = os.path.join(MEDIA, "planet_extra", m.group(2) + "." + m.group(3))
                if os.path.isfile(path):
                    return self.send(200, open(path, "rb").read(), "image/png" if m.group(3) == "png" else "image/jpeg", cache=True)
                return self.nf()
            if p == "/tools":
                return self.send(200, page("Lookups", tools_html()))
            m = re.fullmatch(r"/tool/([a-z0-9_]+)", p)
            if m and m.group(1) in TOOLS:
                t = TOOLS[m.group(1)]
                return self.send(200, page(t["title"], tool_html(t, qs)))
            m = re.fullmatch(r"/api/tool/([a-z0-9_]+)", p)
            if m and m.group(1) in TOOLS:
                t = TOOLS[m.group(1)]
                try:
                    tp, _ = tool_params(t, qs)
                    return self.js({"tool": t["name"], "params": tp, "result": t["run"](db(), tp)["data"]})
                except ValueError as ex:
                    return self.js({"error": str(ex)}, 400)
            if p == "/api/tools":
                return self.js([{k: t[k] for k in ("name", "title", "group", "desc", "bot")} | {"fields": [
                    {k: v for k, v in f.items()} for f in t["fields"]]} for t in TOOLS.values()])
            if p == "/level":
                return self.send(200, page("Level lookup", level_html(qs)))
            m = re.fullmatch(r"/api/level/(\d+)", p)
            if m:
                L = level(int(m.group(1)))
                if not L:
                    return self.js({"error": "no such level"}, 404)
                w = (qs.get("with") or [""])[0]
                if w.isdigit():
                    L = dict(L, with_level=int(w), can_team=can_team(L["level"], int(w)), can_pvp=can_pvp(L["level"], int(w)))
                return self.js(L)
            m = re.fullmatch(r"/api/missions/(\d+)", p)
            if m:
                return self.js({"ql": int(m.group(1)), "levels": mission_levels(int(m.group(1)))})
            if p == "/maps":
                return self.send(200, page("Maps", maps_html(q)))
            m = re.fullmatch(r"/map/(\d+)", p)
            if m and int(m.group(1)) in zone_maps():
                z = int(m.group(1))
                return self.send(200, page(zone_maps()[z]["name"], zone_html(z, zone_maps()[z])))
            m = re.fullmatch(r"/planet/([a-z0-9\-]+)", p)
            if m and m.group(1) in planet_maps():
                return self.send(200, page(planet_maps()[m.group(1)]["name"], planet_html(m.group(1), planet_maps()[m.group(1)])))
            if p == "/api/maps":
                return self.js({"zones": zone_maps(), "planet": planet_maps()})
            m = re.fullmatch(r"/api/map/(\d+)", p)
            if m and int(m.group(1)) in zone_maps():
                return self.js(dict(zone_maps()[int(m.group(1))], id=int(m.group(1)), points=zone_pois(int(m.group(1)))))
            if p == "/data":
                return self.send(200, page("Datasets", data_index_html()))
            m = re.fullmatch(r"/d/([a-z0-9_]+)", p)
            if m and m.group(1) in datasets():
                d = datasets()[m.group(1)]
                pg = num("p")
                total, rows = ds_rows(d["name"], q, pg)
                return self.send(200, page(d["title"], dataset_html(d, q, pg, total, rows), ""))
            m = re.fullmatch(r"/d/([a-z0-9_]+)/(\d+)", p)
            if m and m.group(1) in datasets():
                d = datasets()[m.group(1)]
                r = ds_row(d["name"], int(m.group(2)))
                return self.send(200, page(d["title"], row_html(d, r))) if r else self.nf("No such row.")
            # ---- JSON
            if p == "/api/search":
                return self.js({"query": q, **search(q, max(1, min(200, num("limit", 50))))})
            m = re.fullmatch(r"/api/entry/(%s)" % ENTRY_KEY, p)
            if m:
                e = entry(m.group(1))
                return self.js(e) if e else self.js({"error": "not found"}, 404)
            m = re.fullmatch(r"/api/item/(\d+)", p)
            if m:
                it = item(int(m.group(1)))
                return self.js(it) if it else self.js({"error": "not found"}, 404)
            if p == "/api/datasets":
                return self.js([{k: d[k] for k in ("name", "title", "grp", "descr", "cols", "rows")} for d in datasets().values()])
            m = re.fullmatch(r"/api/d/([a-z0-9_]+)", p)
            if m and m.group(1) in datasets():
                total, rows = ds_rows(m.group(1), q, num("p"))
                return self.js({"dataset": m.group(1), "query": q, "page": num("p"), "page_size": PAGE, "total": total, "rows": rows})
            m = re.fullmatch(r"/api/d/([a-z0-9_]+)/(\d+)", p)
            if m and m.group(1) in datasets():
                r = ds_row(m.group(1), int(m.group(2)))
                return self.js(r) if r else self.js({"error": "not found"}, 404)
            if p == "/api/stats":
                return self.js(stats())
            if p == "/healthz":
                return self.send(200, "ok", "text/plain")
            return self.nf()
        except (ValueError, sqlite3.Error) as ex:
            return self.send(400, page("Error", "<p>%s</p>" % E(str(ex))))


def main():
    global DB_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("ARCHIVE_DB", "/app/archive.sqlite"))
    ap.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    ap.add_argument("--media", default=os.environ.get("ARCHIVE_MEDIA") or next(
        (d for d in ("/app/media", os.path.join(os.path.dirname(HERE), "data")) if os.path.isdir(d)), None))
    a = ap.parse_args()
    DB_PATH = a.db
    global MEDIA
    MEDIA = a.media
    print("AO Wiki on http://%s:%d  (%s)" % (a.host, a.port, json.dumps(stats())), flush=True)
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()


if __name__ == "__main__":
    main()
