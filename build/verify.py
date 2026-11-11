#!/usr/bin/env python3
"""Check that a built archive holds everything in data/ (run after build_db.py).

    python3 -I build/verify.py archive.sqlite [--with-aou]

Re-reads every source on its own and compares with the database:
  - every recipe file, item text and bot guide is an entry with a non-empty body
  - every CSV under data/nadybot/ is a dataset, with the same number of rows as the file
  - every column the registry relies on (item / zone / skill / label / join keys) exists
  - item ids used by the datasets that have no name (reported, not an error: some never existed in game)
  - with --with-aou: every fetched AO-Universe guide is in, once
Exit status 1 when anything is missing.
"""
import csv
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datasets import BOT_GUIDES, DATASETS  # noqa: E402

db = sqlite3.connect(sys.argv[1])
with_aou = "--with-aou" in sys.argv
bad = []


def check(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        bad.append(what)


def count(kind):
    return db.execute("SELECT count(*) FROM entries WHERE kind = ? AND length(html) > 20", (kind,)).fetchone()[0]


print("Entries")
rfiles = [f for f in os.listdir(os.path.join(DATA, "recipes")) if f[0].isdigit() and f.endswith((".txt", ".json"))]
check(count("recipe") == len(rfiles), "bot recipes: %d files, %d entries" % (len(rfiles), count("recipe")))
texts = json.load(open(os.path.join(DATA, "item_texts.json"), encoding="utf-8"))
check(count("text") == len(texts), "game item texts: %d in file, %d entries" % (len(texts), count("text")))
gfiles = [f for f in os.listdir(os.path.join(DATA, "nadybot", BOT_GUIDES)) if f.endswith(".txt")]
check(count("botguide") == len(gfiles), "bot guides: %d files, %d entries" % (len(gfiles), count("botguide")))
gp = os.path.join(DATA, "aou", "guides.json")
if with_aou:
    g = json.load(open(gp, encoding="utf-8"))
    ids = {x["id"] for x in g}
    check(count("guide") == len(ids), "AO-Universe guides: %d fetched (%d unique), %d entries" % (len(g), len(ids), count("guide")))
else:
    check(count("guide") == 0, "AO-Universe guides left out of this build (%d entries)" % count("guide"))

print("Datasets")
listed = {d["file"] for d in DATASETS}
on_disk = set()
for dp, _, fs in os.walk(os.path.join(DATA, "nadybot")):
    for f in fs:
        if f.endswith(".csv"):
            on_disk.add(os.path.relpath(os.path.join(dp, f), os.path.join(DATA, "nadybot")))
for f in sorted(on_disk - listed):
    check(False, "CSV not in build/datasets.py: %s" % f)
tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
total_file = total_db = 0
for d in DATASETS:
    path = os.path.join(DATA, "nadybot", d["file"])
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        rows = list(csv.reader([ln for ln in fh if not ln.startswith("#") and ln.strip()], delimiter=d.get("sep", ",")))
    n_file = len(rows) - (0 if d.get("cols") else 1)
    t = "ds_" + d["name"]
    if t not in tables:
        check(False, "%s: no table" % d["name"]); continue
    n_db = db.execute('SELECT count(*) FROM "%s"' % t).fetchone()[0]
    cols = {r[1] for r in db.execute('PRAGMA table_info("%s")' % t)}
    need = set(d.get("item", []) + d.get("pf", []) + d.get("skill", []) + d.get("label", []))
    for new, (key, other, okey, oval) in d.get("join", {}).items():
        need |= {new, key}
    missing = sorted(need - cols)
    total_file += n_file
    total_db += n_db
    check(n_file == n_db and not missing, "%-22s %7d rows in file, %7d in db%s" % (
        d["name"], n_file, n_db, ("; missing columns " + ", ".join(missing)) if missing else ""))
print("  rows: %d in files, %d in db" % (total_file, total_db))

print("Items")
n_items = db.execute("SELECT count(*) FROM items").fetchone()[0]
UNNAMED = "item_id NOT IN (SELECT id FROM items) AND item_id NOT IN (SELECT id FROM nano_programs)"
unnamed = db.execute("SELECT count(DISTINCT item_id) FROM ds_item_refs WHERE " + UNNAMED).fetchone()[0]
refd = db.execute("SELECT count(DISTINCT item_id) FROM ds_item_refs").fetchone()[0]
progs = db.execute("SELECT count(DISTINCT item_id) FROM ds_item_refs WHERE item_id IN (SELECT id FROM nano_programs)").fetchone()[0]
print("  %d item names, %d nano program names; %d distinct ids used by the datasets: %d nano programs, %d with no name anywhere" % (
    n_items, db.execute("SELECT count(*) FROM nano_programs").fetchone()[0], refd, progs, unnamed))
for ds, n in db.execute("SELECT ds, count(DISTINCT item_id) FROM ds_item_refs WHERE " + UNNAMED + " GROUP BY ds ORDER BY 2 DESC LIMIT 8"):
    print("     %-22s %d unnamed ids" % (ds, n))
aodb_ids = db.execute("SELECT count(*) FROM (SELECT lowid AS i FROM ds_items_ql UNION SELECT highid FROM ds_items_ql)").fetchone()[0]
aodb_named = db.execute("SELECT count(*) FROM (SELECT lowid AS i FROM ds_items_ql UNION SELECT highid FROM ds_items_ql) "
                        "WHERE CAST(i AS INTEGER) IN (SELECT id FROM items)").fetchone()[0]
check(aodb_named == aodb_ids, "bot item table: %d ids, %d named" % (aodb_ids, aodb_named))

print("Media")
icons = [f for f in os.listdir(os.path.join(DATA, "icons")) if f.endswith(".png")] if os.path.isdir(os.path.join(DATA, "icons")) else []
check(len(icons) >= 9000, "item icons: %d" % len(icons))
used = db.execute("SELECT count(DISTINCT icon) FROM item_icons").fetchone()[0]
have = sum(1 for (i,) in db.execute("SELECT DISTINCT icon FROM item_icons") if os.path.exists(os.path.join(DATA, "icons", "%d.png" % i)))
print("  %d icons used by items, %d of them present" % (used, have))
try:
    idx = json.load(open(os.path.join(DATA, "maps", "index.json")))
    miss = [z for z in idx if not os.path.exists(os.path.join(DATA, "maps", "%s.jpg" % z))]
    check(len(idx) >= 600 and not miss, "zone maps: %d in index, %d images missing" % (len(idx), len(miss)))
except (OSError, ValueError) as e:
    check(False, "zone maps: %s" % e)
try:
    pidx = json.load(open(os.path.join(DATA, "planet", "index.json")))
    check(all(os.path.exists(os.path.join(DATA, "planet", k + ".jpg")) for k in pidx) and len(pidx) >= 2, "planet maps: %s" % ", ".join(pidx))
except (OSError, ValueError) as e:
    check(False, "planet maps: %s" % e)

print("Lookups")
sys.path.insert(0, os.path.join(ROOT, "app"))
try:
    from tools import TOOLS
    db.row_factory = sqlite3.Row
    crashed = []
    for name, t in TOOLS.items():  # every lookup must answer an empty form without crashing
        try:
            t["run"](db, {f["name"]: None for f in t["fields"]})
        except ValueError:
            pass
        except Exception as e:  # noqa: BLE001
            crashed.append("%s: %r" % (name, e))
    check(len(TOOLS) >= 50 and not crashed, "bot lookups: %d loaded%s" % (len(TOOLS), ("; crashed: " + "; ".join(crashed)) if crashed else ""))
except Exception as e:  # noqa: BLE001
    check(False, "bot lookups failed to load: %r" % e)

print("\n%s" % ("ALL PRESENT" if not bad else "%d PROBLEM(S)" % len(bad)))
sys.exit(1 if bad else 0)
