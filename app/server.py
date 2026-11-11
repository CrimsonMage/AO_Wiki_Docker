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
KIND = {"recipe": "Bot recipe", "guide": "AO-Universe guide", "text": "Game item text", "botguide": "Bot guide"}
PAGE = 50
local = threading.local()
DB_PATH = None
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
<header><a class="brand" href="/">AO Wiki</a><nav><a href="/">Search</a><a href="/data">Data</a></nav>
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
    if col in d["pf"] and v in lookup("pf"):
        return "%s <span class='dim'>(%s)</span>" % (E(lookup("pf")[v]), E(v))
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
    if res["entries"]:
        parts.append("<h2>Recipes and guides</h2><ul class='results'>%s</ul>" % "".join(
            "<li><a href='/e/%s'>%s</a> %s%s</li>" % (E(r["key"]), E(r["name"]), tag(r["kind"]),
                                                      " <span class='dim'>mentions it</span>" if r["why"] == "mentions" else "")
            for r in res["entries"]))
    if res["items"]:
        parts.append("<h2>Items</h2><ul class='results cols'>%s</ul>" % "".join(
            "<li><a class='item' href='/item/%d'>%s</a></li>" % (r["id"], E(r["name"])) for r in res["items"]))
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
    return ("<article class='ao'><h1>%s</h1><p class='meta'>%s &middot; <a href='/?q=%s'>search for this name</a></p>"
            "<h2>Recipes and guides</h2>%s%s</article>" % (
                E(it["name"]), " &middot; ".join(meta), urllib.parse.quote_plus(it["name"]),
                "<ul class='results'>%s</ul>" % li if li else "<p class='dim'>None mention it.</p>", data))


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

    def send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
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
    a = ap.parse_args()
    DB_PATH = a.db
    print("AO Wiki on http://%s:%d  (%s)" % (a.host, a.port, json.dumps(stats())), flush=True)
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()


if __name__ == "__main__":
    main()
