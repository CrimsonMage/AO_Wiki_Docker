"""General lookups: xp, axp, missions, dyna, research, oe, arbiter, whompah, citywave, whereis, spawntime,
disc, boss, bossloot and the raid loot lists.

Ported from Nadybot (https://github.com/Nadybot/Nadybot, branch nadybot7; modules LEVEL_MODULE, HELPBOT_MODULE,
WHOMPAH_MODULE, CITY_MODULE, WHEREIS_MODULE, DISC_MODULE, ITEMS_MODULE and LOOT_MODULE).
Copyright the Nadybot authors (Tyrence, Derroylo, Legendadv, Jaqueme, Nadyita, Funkman and others).

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
Public License as published by the Free Software Foundation, version 3 of the License. It is distributed in
the hope that it will be useful, but WITHOUT ANY WARRANTY; see <https://www.gnu.org/licenses/gpl-3.0.html>.
"""
import datetime
import html
import json
import math
import os
import re
import time


def _phpround(x):
    """PHP round(): halves away from zero (Python's round() goes to the even number)."""
    import math
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))

E = html.escape
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_zones = {}


# ------------------------------------------------------------------ helpers
def _num(n):
    return "{:,}".format(int(n))


def _int(v, default=0):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _text(p, name):
    return (p.get(name) or "").strip()


def _kv(rows):
    return "<table class='kv'>%s</table>" % "".join(
        "<tr><th>%s</th><td>%s</td></tr>" % (E(str(k)), v) for k, v in rows)


def _table(head, rows, raw_cols=()):
    """rows: lists of cell strings; columns listed in raw_cols (indexes) are already HTML, the rest is escaped"""
    h = "<div class='scroll'><table><thead><tr>%s</tr></thead><tbody>" % "".join("<th>%s</th>" % E(c) for c in head)
    for r in rows:
        h += "<tr>%s</tr>" % "".join("<td>%s</td>" % (c if i in raw_cols else E(str(c))) for i, c in enumerate(r))
    return h + "</tbody></table></div>"


def _zone_maps():
    if not _zones:
        # the server's media folder (Docker: /app/media), else the repository's data/
        for base in (os.environ.get("ARCHIVE_MEDIA"), "/app/media", os.path.join(_ROOT, "data")):
            path = base and os.path.join(base, "maps", "index.json")
            if path and os.path.exists(path):
                try:
                    with open(path) as f:
                        for k, v in json.load(f).items():
                            _zones[int(k)] = v
                    break
                except (OSError, ValueError):
                    pass
        if not _zones:
            _zones[-1] = {}
    return _zones


def _item_link(iid, name):
    return "<a class='item' href='/item/%d'>%s</a>" % (iid, E(name))


def _like_clause(cols_words, args):
    """Nadybot's DB::addWhereFromParams: every word must be contained in the column ('-word' = must not be);
    the columns are OR-ed together. cols_words: list of (column, words)."""
    parts = []
    for col, words in cols_words:
        conds = []
        for w in words:
            neg = w.startswith("-") and len(w) > 1
            if neg:
                w = w[1:]
            esc = w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conds.append("%s %sLIKE ? ESCAPE '\\'" % (col, "NOT " if neg else ""))
            args.append("%" + esc + "%")
        if conds:
            parts.append("(" + " AND ".join(conds) + ")")
    return " OR ".join(parts) if parts else "1"


def _words(s):
    return [w for w in s.lower().split(" ") if w]


def _playfields(db):
    return {_int(r["id"]): (r["long_name"], r["short_name"]) for r in db.execute("SELECT * FROM ds_playfields")}


def _pf_long(pfs, pid):
    return pfs.get(pid, ("Playfield %d" % pid, str(pid)))[0]


def _pf_short(pfs, pid):
    return pfs.get(pid, ("", str(pid)))[1]


def _place(pfs, pid, x, y, label=None):
    """Coordinates of a place, linked to the zone map when one exists"""
    txt = label if label is not None else "%dx%d %s" % (x, y, _pf_short(pfs, pid))
    wp = "/waypoint %d %d %d" % (x, y, pid)
    if pid in _zone_maps():
        return "<a href='/map/%d'>%s</a> <span class='dim'>(%s)</span>" % (pid, E(txt), E(wp))
    return "%s <span class='dim'>(%s)</span>" % (E(txt), E(wp))


def _item_ids_by_name(db, names):
    """name -> highest item id with that name (names the archive does not know are missing)"""
    names = sorted(set(n for n in names if n))
    out = {}
    for i in range(0, len(names), 400):
        chunk = names[i:i + 400]
        q = "SELECT name, MAX(id) FROM items WHERE name IN (%s) GROUP BY name" % ",".join("?" * len(chunk))
        for n, iid in db.execute(q, chunk):
            out[n] = iid
    return out


# ------------------------------------------------------------------ xp / axp / missions
def _levels(db):
    return {_int(r["level"]): r for r in db.execute("SELECT * FROM ds_levels")}


def run_xp(db, p):
    lv = _levels(db)
    a, b = p.get("start"), p.get("end")
    if a is None:
        raise ValueError("Enter a level.")
    if b is None:
        if a not in lv:
            raise ValueError("Level must be between 1 and 219.")
        need = _int(lv[a]["xpsk"])
        unit = "SK" if a >= 200 else "XP"
        msg = "At level %d you need %s %s to level up." % (a, _num(need), unit)
        return dict(html="<p class='verdict'>%s</p>" % E(msg), data=dict(level=a, needed=need, unit=unit))
    if not (1 <= a <= 220 and 1 <= b <= 220):
        raise ValueError("Level must be between 1 and 220.")
    if a >= b:
        raise ValueError("The start level must be lower than the end level.")
    xp = sum(_int(lv[l]["xpsk"]) for l in range(a, b) if l in lv and l < 200)
    sk = sum(_int(lv[l]["xpsk"]) for l in range(a, b) if l in lv and l >= 200)
    parts = []
    if xp > 0:
        parts.append("%s XP" % _num(xp))
    if sk > 0:
        parts.append("%s SK" % _num(sk))
    if not parts:
        raise ValueError("You somehow managed to pass illegal parameters.")
    msg = "From the beginning of level %d you need %s to reach level %d." % (a, " and ".join(parts), b)
    return dict(html="<p class='verdict'>%s</p>" % E(msg), data=dict(start=a, end=b, xp=xp, sk=sk))


_AI_RANKS = [(1500, 5, "Fledgling"), (9000, 15, "Amateur"), (22500, 25, "Beginner"), (42000, 35, "Starter"),
             (67500, 45, "Newcomer"), (99000, 55, "Student"), (136500, 65, "Common"), (180000, 75, "Intermediate"),
             (229500, 85, "Mediocre"), (285000, 95, "Fair"), (346500, 105, "Able"), (414000, 110, "Accomplished"),
             (487500, 115, "Adept"), (567000, 120, "Qualified"), (697410, 125, "Competent"), (857814, 130, "Suited"),
             (1055112, 135, "Talented"), (1297787, 140, "Trustworthy"), (1596278, 145, "Supporter"),
             (1931497, 150, "Backer"), (2298481, 155, "Defender"), (2689223, 160, "Challenger"),
             (3092606, 165, "Patron"), (3494645, 170, "Protector"), (3879056, 175, "Medalist"),
             (4228171, 180, "Champ"), (4608707, 185, "Hero"), (5023490, 190, "Guardian"),
             (5475604, 195, "Vanquisher"), (5968409, 200, "Vindicator")]


def run_axp(db, p):
    a, b = p.get("start"), p.get("end")
    if a is None and b is None:
        rows = [(i + 1, r[1], _num(r[0]), r[2]) for i, r in enumerate(_AI_RANKS)]
        return dict(html=_table(["AI level", "Level required", "AXP to reach it", "Rank"], rows),
                    data=[dict(ai_level=i + 1, level_req=r[1], axp=r[0], rank=r[2]) for i, r in enumerate(_AI_RANKS)])
    if a is None:
        a, b = b, None
    if not (0 <= a <= 30) or (b is not None and not (0 <= b <= 30)):
        raise ValueError("AI level must be between 0 and 30.")
    if b is None:
        if a >= 30:
            raise ValueError("AI level 30 is the maximum, there is nothing to level up to.")
        msg = "At AI level %d you need %s AXP to level up." % (a, _num(_AI_RANKS[a][0]))
        return dict(html="<p class='verdict'>%s</p>" % E(msg), data=dict(ai_level=a, axp=_AI_RANKS[a][0]))
    if a > b:
        raise ValueError("The start level cannot be higher than the end level.")
    tot = sum(_AI_RANKS[i][0] for i in range(a, b))
    msg = "From the beginning of AI level %d you need %s AXP to reach AI level %d." % (a, _num(tot), b)
    return dict(html="<p class='verdict'>%s</p>" % E(msg), data=dict(start=a, end=b, axp=tot))


def run_missions(db, p):
    ql = p.get("ql")
    if ql is None or ql <= 0 or ql > 250:
        raise ValueError("Missions are only available between QL1 and QL250.")
    out = [l for l, r in sorted(_levels(db).items()) if str(ql) in r["missions"].split(",")]
    if out:
        msg = "QL%d missions can be rolled from these levels: %s" % (ql, " ".join(map(str, out)))
    else:
        msg = "No level can roll QL%d missions." % ql
    return dict(html="<p class='verdict'>%s</p>" % E(msg), data=dict(ql=ql, levels=out))


# ------------------------------------------------------------------ dyna
def _dyna_results(db, rows, pfs, head):
    groups = {}
    for r in rows:
        groups.setdefault(_pf_long(pfs, _int(r["playfield_id"])), []).append(r)
    h = head
    for name in sorted(groups):
        h += "<h3>%s</h3>" % E(name)
        h += _table(["QL", "Mob", "Location"], [
            ["%s-%s" % (r["min_ql"], r["max_ql"]), r["mob"],
             _place(pfs, _int(r["playfield_id"]), _int(r["x_coord"]), _int(r["y_coord"]))] for r in groups[name]],
            raw_cols=(2,))
    return h


def run_dyna(db, p):
    q = _text(p, "search")
    if not q:
        raise ValueError("Enter a level, a mob name or a playfield.")
    pfs = _playfields(db)
    if re.fullmatch(r"\d+", q):
        ql = int(q)
        r1 = int(math.floor(ql - ql / 10))
        r2 = int(math.ceil(ql + ql / 10))
        rows = db.execute('SELECT * FROM ds_dynacamps WHERE CAST(max_ql AS INTEGER) >= ? AND CAST(min_ql AS INTEGER) <= ? '
                          'ORDER BY CAST(min_ql AS INTEGER)', (r1, r2)).fetchall()
        if not rows:
            raise ValueError("No dynacamps found between level %d and %d." % (r1, r2))
        h = _dyna_results(db, rows, pfs, "<p>Dynacamps of level <b>%d-%d</b> (%d)</p>" % (r1, r2, len(rows)))
        return dict(html=h, data=[dict(r) for r in rows])
    like = "%" + q.replace(" ", "%") + "%"
    pids = [r["id"] for r in db.execute("SELECT id FROM ds_playfields WHERE long_name LIKE ? OR short_name LIKE ?", (like, like))]
    sql = "SELECT * FROM ds_dynacamps WHERE mob LIKE ?"
    args = [like]
    if pids:
        sql += " OR playfield_id IN (%s)" % ",".join("?" * len(pids))
        args += pids
    rows = db.execute(sql, args).fetchall()
    if not rows:
        raise ValueError("No dyna names or locations matched %s." % q)
    h = _dyna_results(db, rows, pfs, "<p>Dynacamps matching <b>%s</b> (%d)</p>" % (E(q), len(rows)))
    return dict(html=h, data=[dict(r) for r in rows])


# ------------------------------------------------------------------ research
def run_research(db, p):
    rs = {_int(r["level"]): (_int(r["sk"]), _int(r["levelcap"])) for r in db.execute("SELECT * FROM ds_research")}
    a, b = p.get("level"), p.get("to")
    if a is None and b is None:
        rows = [[l, _num(rs[l][0]), _num(rs[l][0] * 1000), rs[l][1]] for l in sorted(rs) if l >= 1]
        return dict(html=_table(["Research level", "SK needed (per line)", "= XP", "Character level needed"], rows),
                    data=[dict(level=l, sk=rs[l][0], levelcap=rs[l][1]) for l in sorted(rs) if l >= 1])
    if a is None:
        a, b = b, None
    if not (1 <= a <= 10) or (b is not None and not (1 <= b <= 10)):
        raise ValueError("Valid values are 1-10.")
    if b is None:
        sk, cap = rs[a]
        xp = sk * 1000
        h = _kv([("Character level needed", "Level <b>%d</b> to reach Research Level <b>%d</b>" % (cap, a)),
                 ("SK per research line", "<b>%s SK</b> to reach Research Level %d" % (_num(sk), a)),
                 ("Equals", "<b>%s XP</b>" % _num(xp)),
                 ("Research caps at", "~<b>%s XP</b> or ~<b>%s SK</b>" % (_num(_phpround(xp * .1)), _num(_phpround(sk * .1))))])
        return dict(html=h, data=dict(level=a, sk=sk, xp=xp, levelcap=cap))
    lo, hi = min(a, b), max(a, b)
    if lo == hi:
        raise ValueError("No research is needed to stay on your current level.")
    tot = sum(rs[l][0] for l in range(lo + 1, hi + 1))
    cap = max(rs[l][1] for l in range(lo + 1, hi + 1))
    h = _kv([("Character level needed", "Level <b>%d</b> to reach Research Level <b>%d</b>" % (cap, hi)),
             ("SK per research line", "<b>%s SK</b> from Research Level %d to %d" % (_num(tot), lo, hi)),
             ("Equals", "<b>%s XP</b>" % _num(tot * 1000))])
    return dict(html=h, data=dict(start=lo, end=hi, sk=tot, xp=tot * 1000, levelcap=cap))


# ------------------------------------------------------------------ oe
def run_oe(db, p):
    req = p.get("requirement")
    if req is None or req < 0:
        raise ValueError("Enter the skill requirement of the item.")
    f = lambda x: int(math.floor(x))
    oe100, low100 = f(req / 0.8), f(req * 0.8)
    oe75, low75 = f(req / 0.6), f(req * 0.6)
    oe50, low50 = f(req / 0.4), f(req * 0.4)
    oe25, low25 = f(req / 0.2), f(req * 0.2)
    h = "<p class='verdict'>%d - <b>%d</b> - %d</p>" % (low100, req, oe100)
    skill = p.get("skill")
    if skill is not None:
        if skill >= low100:
            pct = "not over-equipped (100%)"
        elif skill >= low75:
            pct = "75% of the stats"
        elif skill > low50:
            pct = "50% of the stats"
        elif skill > low25:
            pct = "25% of the stats"
        else:
            pct = "0% of the stats"
        if pct.startswith("not"):
            h = "<p class='verdict'>With %d skill you can use an item that requires %d without being over-equipped.</p>" % (skill, req)
        else:
            h = "<p class='verdict'>With %d skill and an item requiring %d you are over-equipped: %s.</p>" % (skill, req, E(pct))
    h += "<h3>With a skill requirement of %d, you will be</h3>" % req
    h += _table(["Over-equip", "Your skill"], [
        ["Out of OE", "%d or higher" % low100], ["75%", "%d - %d" % (low75, low100 - 1)],
        ["50%", "%d - %d" % (low50 + 1, low75 - 1)], ["25%", "%d - %d" % (low25 + 1, low50)],
        ["0%", "%d or lower" % low25]])
    h += "<h3>With a personal skill of %d, you can use up to and be</h3>" % req
    h += _table(["Over-equip", "Item requirement"], [
        ["Out of OE", "%d or lower" % oe100], ["75%", "%d - %d" % (oe100 + 1, oe75)],
        ["50%", "%d - %d" % (oe75 + 1, oe50 - 1)], ["25%", "%d - %d" % (oe50, oe25 - 1)],
        ["0%", "%d or higher" % oe25]])
    h += "<p class='dim'>WARNING: May be plus/minus 1 point!</p>"
    return dict(html=h, data=dict(requirement=req, out_of_oe_from=low100, max_requirement=oe100,
                                  p75=[low75, low100 - 1], p50=[low50 + 1, low75 - 1], p25=[low25 + 1, low50], p0=low25))


# ------------------------------------------------------------------ arbiter
_ARB_CYCLE = 3628800
_ARB_NAMES = {"bs": "PvP week (Battlestation)", "ai": "Alien week", "dio": "DIO week"}
_ARB_SEED = {"ai": (1618704000, 1619395200), "bs": (1619913600, 1620604800), "dio": (1621123200, 1621814400)}


def _nice_time(secs):
    secs = int(secs) - int(secs) % 60
    d, r = divmod(secs, 86400)
    hh, r = divmod(r, 3600)
    parts = []
    if d:
        parts.append("%d day%s" % (d, "" if d == 1 else "s"))
    if hh:
        parts.append("%d hr%s" % (hh, "" if hh == 1 else "s"))
    mm = r // 60
    if mm or not parts:
        parts.append("%d min%s" % (mm, "" if mm == 1 else "s"))
    return " ".join(parts)


def _parse_date(s):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y", "%B %dst %Y", "%B %dnd %Y",
                "%B %drd %Y", "%B %dth %Y"):
        try:
            return int(datetime.datetime.strptime(s.strip().replace(",", ""), fmt).replace(tzinfo=datetime.timezone.utc).timestamp())
        except ValueError:
            pass
    raise ValueError("Unable to parse %s into a date (use YYYY-MM-DD)." % s)


def run_arbiter(db, p):
    given = _text(p, "date")
    now = _parse_date(given) if given else int(time.time())
    events = []
    for typ, (s, e) in _ARB_SEED.items():
        cycles = int((now - s) / _ARB_CYCLE)  # PHP intdiv truncates towards zero
        s += cycles * _ARB_CYCLE
        e += cycles * _ARB_CYCLE
        if e <= now:
            s += _ARB_CYCLE
            e += _ARB_CYCLE
        events.append(dict(type=typ, name=_ARB_NAMES[typ], start=s, end=e))
    events.sort(key=lambda ev: ev["start"])
    day = lambda t: time.strftime("%d-%b-%Y", time.gmtime(t))
    cur = None
    if events[0]["start"] <= now < events[0]["end"]:
        cur = events.pop(0)
        later = dict(cur, start=cur["start"] + _ARB_CYCLE, end=cur["end"] + _ARB_CYCLE)
        events.append(later)
        if given:
            msg = "On %s, it is %s." % (day(now), cur["name"])
        else:
            msg = "It's currently %s for %s." % (cur["name"], _nice_time(cur["end"] - now))
    else:
        msg = ("On %s, the arbiter is not here." % day(now)) if given else "The arbiter is currently not here."
        msg += " Next: %s in %s." % (events[0]["name"], _nice_time(events[0]["start"] - now))
    h = "<p class='verdict'>%s</p>" % E(msg)
    h += _table(["Starts", "Ends", "Event"], [[day(ev["start"]), day(ev["end"]), ev["name"]] for ev in events])
    h += "<p class='dim'>All arbiter weeks last for 8 days (Sunday 00:00 to Sunday 23:59). Dates are UTC; the three weeks repeat every 42 days.</p>"
    return dict(html=h, data=dict(now=now, current=cur, upcoming=events))


# ------------------------------------------------------------------ whompah
def _cities(db):
    return [dict(r) for r in db.execute("SELECT * FROM ds_whompah_cities ORDER BY rowid")]


def _find_city(cities, s):
    s = s.lower()
    for c in cities:
        if c["city_name"].lower() == s or c["short_name"].lower() == s:
            return c
    for c in cities:
        if s in c["city_name"].lower() or s in c["short_name"].lower():
            return c
    return None


_FACTION_COLOR = {"clan": "#d9534f", "omni": "#4a90d9", "neutral": "#3aa655"}


def _city_html(c, short=False):
    col = _FACTION_COLOR.get(c["faction"].lower(), "inherit")
    h = "<a href='/tool/whompah?from=%s' style='color:%s'>%s</a>" % (E(c["short_name"]), col, E(c["city_name"]))
    if short:
        h += " <span class='dim'>(%s, %s)</span>" % (E(c["short_name"]), E(c["zone"]))
    return h


def run_whompah(db, p):
    cities = _cities(db)
    byid = {_int(c["id"]): c for c in cities}
    a, b = _text(p, "from"), _text(p, "to")
    if not a and not b:
        rows = [[_city_html(c), c["short_name"], c["zone"], c["faction"]] for c in sorted(cities, key=lambda c: c["city_name"])]
        return dict(html="<p>All known cities with Whom-Pahs. Click a city to see its destinations.</p>" +
                    _table(["City", "Short name", "Zone", "Faction"], rows, raw_cols=(0,)), data=cities)
    if not a:
        a, b = b, ""
    start = _find_city(cities, a)
    if start is None:
        raise ValueError("Error! Could not find city %s." % a)
    links = {}
    for r in db.execute("SELECT city1_id, city2_id FROM ds_whompah_links ORDER BY CAST(city1_id AS INTEGER), rowid"):
        links.setdefault(_int(r["city1_id"]), []).append(_int(r["city2_id"]))
    if not b:
        dest = sorted((byid[i] for i in links.get(_int(start["id"]), []) if i in byid), key=lambda c: c["city_name"])
        h = "<p>From <b>%s</b> (%s) you can get to</p><ul>%s</ul>" % (
            E(start["city_name"]), E(start["short_name"]), "".join("<li>%s</li>" % _city_html(c, True) for c in dest))
        return dict(html=h, data=dict(city=start, destinations=dest))
    end = _find_city(cities, b)
    if end is None:
        raise ValueError("Error! Could not find city %s." % b)
    # same as the bot: breadth-first search that starts at the destination and stops at the start city
    sid, eid = _int(start["id"]), _int(end["id"])
    prev = {eid: None}
    queue = [eid]
    found = False
    while queue:
        cur = queue.pop(0)
        if cur == sid:
            found = True
            break
        for n in links.get(cur, []):
            if n not in prev:
                prev[n] = cur
                queue.append(n)
    if not found:
        raise ValueError("There was an error while trying to find the whompah path.")
    path = []
    cur = sid
    while cur is not None:
        path.append(byid[cur])
        cur = prev[cur]
    h = "<p class='verdict'>%s</p>" % " &rarr; ".join(_city_html(c) for c in path)
    h += "<p class='dim'>%d whom-pah%s</p>" % (len(path) - 1, "" if len(path) == 2 else "s")
    return dict(html=h, data=dict(path=[c["city_name"] for c in path]))


# ------------------------------------------------------------------ citywave
_WAVE_TIMES = [105, 150, 90, 120, 120, 120, 120, 120, 120]


def run_citywave(db, p):
    el = p.get("elapsed")
    t = 0
    rows = []
    sched = []
    for i, d in enumerate(_WAVE_TIMES):
        t += d
        nm = "General" if i == 8 else "Wave %d" % (i + 1)
        rows.append([nm, "%ds" % d, "%d:%02d" % divmod(t, 60)])
        sched.append(dict(wave=i + 1, delay=d, at=t))
    h = ""
    if el is not None:
        nxt = next((s for s in sched if s["at"] > el), None)
        if nxt is None:
            msg = "There is no raid in progress at this time (all waves and the General have been spawned)."
        elif nxt["wave"] == 9:
            msg = "Waiting for General."
        else:
            msg = "Waiting for wave %d (in %d seconds)." % (nxt["wave"], nxt["at"] - el)
        h += "<p class='verdict'>%s</p>" % E(msg)
    h += "<p>Wave alerts after the city is targeted (cloak lowered), nine alerts in all (default Nadybot timings):</p>"
    h += _table(["Alert", "After previous", "Since raid start"], rows)
    return dict(html=h, data=sched)


# ------------------------------------------------------------------ whereis / spawntime
def _whereis_rows(db, q):
    words = _words(q)
    args = []
    cond = _like_clause([("name", words), ("keywords", words)], args)
    return db.execute("SELECT * FROM ds_whereis WHERE %s ORDER BY CAST(id AS INTEGER)" % cond, args).fetchall()


def _whereis_loc(pfs, r):
    pid, x, y = _int(r["playfield_id"]), _int(r["xcoord"]), _int(r["ycoord"])
    if pid in pfs and x != 0 and y != 0:
        return _place(pfs, pid, x, y)
    return ""


def run_whereis(db, p):
    q = _text(p, "search")
    if not q:
        raise ValueError("Enter a name to search for.")
    rows = _whereis_rows(db, q)
    if not rows:
        raise ValueError("There were no matches for your search.")
    pfs = _playfields(db)
    h = "<p>Matches for <b>%s</b> (%d)</p>" % (E(q), len(rows))
    for r in rows:
        loc = _whereis_loc(pfs, r)
        h += "<h3>%s</h3><p>%s%s</p>" % (E(r["name"]), E(r["answer"]), (" " + loc) if loc else "")
    return dict(html=h, data=[dict(r) for r in rows])


def _spawn_fmt(secs):
    s = secs % 86400
    t = "%02dh%02dm%02ds" % (s // 3600, s % 3600 // 60, s % 60)
    t = re.sub(r"00[hms]", "", t)
    return t[1:] if t.startswith("0") else t


def run_spawntime(db, p):
    q = _text(p, "search")
    if q:
        words = _words(q)
        args = []
        cond = _like_clause([("mob", words), ("placeholder", words), ("alias", words)], args)
        rows = db.execute("SELECT * FROM ds_spawntimes WHERE %s" % cond, args).fetchall()
        if not rows:
            raise ValueError("No spawntime matching %s." % q)
    else:
        rows = db.execute("SELECT * FROM ds_spawntimes ORDER BY rowid").fetchall()
    pfs = _playfields(db)
    allw = db.execute("SELECT * FROM ds_whereis").fetchall()
    direct = len(rows) < 4
    out, data = [], []
    for r in rows:
        mob = r["mob"]
        sp = _int(r["spawntime"], None) if r["spawntime"] not in (None, "") else None
        t = _spawn_fmt(sp) if sp is not None else "unknown"
        flags = []
        if _int(r["can_skip_spawn"]):
            flags.append("can skip spawn")
        if r["placeholder"]:
            flags.append("placeholder: " + r["placeholder"])
        coords = [w for w in allw if w["name"].lower().startswith(mob.lower())]
        loc = ""
        if direct and coords:
            loc = "".join("<div><b>%s</b>: %s %s</div>" % (E(w["name"]), E(w["answer"]), _whereis_loc(pfs, w)) for w in coords)
        elif len(coords) > 1:
            loc = "<a href='/tool/whereis?search=%s'>locations (%d)</a>" % (E(mob.replace(" ", "+")), len(coords))
        elif len(coords) == 1:
            loc = _whereis_loc(pfs, coords[0])
        out.append([mob, "<b>%s</b>" % E(t), E(", ".join(flags)), loc])
        data.append(dict(mob=mob, spawntime=sp, formatted=t, can_skip_spawn=bool(_int(r["can_skip_spawn"])),
                         placeholder=r["placeholder"], alias=r["alias"]))
    head = "<p>%s (%d)</p>" % (("Spawntimes matching <b>%s</b>" % E(q)) if q else "All known spawntimes", len(rows))
    return dict(html=head + _table(["Mob", "Respawn", "Notes", "Location"], out, raw_cols=(1, 2, 3)), data=data)


# ------------------------------------------------------------------ disc
def _nano_details(db, crystal_id):
    return db.execute("SELECT * FROM ds_nanos WHERE crystal_id = ? LIMIT 1", (str(crystal_id),)).fetchone()


def _disc_html(db, d):
    nd = _nano_details(db, d["crystal_id"])
    h = "<p class='verdict'>%s will turn into %s</p>" % (
        _item_link(_int(d["disc_id"]), d["disc_name"]), _item_link(_int(d["crystal_id"]), d["crystal_name"]))
    rows = [("Instruction disc", "%s (QL %s)" % (_item_link(_int(d["disc_id"]), d["disc_name"]), E(d["disc_ql"]))),
            ("Nano crystal", "%s (QL %s)" % (_item_link(_int(d["crystal_id"]), d["crystal_name"]), E(d["crystal_ql"])))]
    if nd:
        rows += [("Professions", E(", ".join(nd["professions"].split(":")))), ("Nano line", E(nd["strain"])),
                 ("Location", E(nd["location"]))]
    else:
        rows.append(("Nano details", "<span class='dim'>not found for %s</span>" % E(d["crystal_name"])))
    if d["comment"]:
        rows.append(("Note", "<b>%s!</b>" % E(d["comment"])))
    return h + _kv(rows)


def run_disc(db, p):
    q = _text(p, "search")
    if not q:
        raise ValueError("Enter the name of an instruction disc.")
    if re.fullmatch(r"\d+", q):
        rows = db.execute("SELECT * FROM ds_nano_discs WHERE disc_id = ?", (q,)).fetchall()
        if not rows:
            raise ValueError("Either %s is not an instruction disc, or it cannot be turned into a nano anymore." % q)
    else:
        args = []
        cond = _like_clause([("disc_name", _words(q))], args)
        rows = db.execute("SELECT * FROM ds_nano_discs WHERE %s ORDER BY disc_name" % cond, args).fetchall()
        if not rows:
            raise ValueError("Either %s was mistyped or it cannot be turned into a nano anymore." % q)
    if len(rows) == 1:
        return dict(html=_disc_html(db, rows[0]), data=dict(rows[0]))
    shown = rows[:300]
    h = "<p>%d discs match, pick one%s:</p><ul>%s</ul>" % (len(rows), (" (first %d shown, narrow the search)" % len(shown)) if len(rows) > len(shown) else "", "".join(
        "<li><a href='/tool/disc?search=%s'>%s</a></li>" % (E(r["disc_id"]), E(r["disc_name"])) for r in shown))
    return dict(html=h, data=[dict(r) for r in rows])


# ------------------------------------------------------------------ boss / bossloot
def _boss_locations(db, pfs, name):
    out = []
    for w in db.execute("SELECT * FROM ds_whereis WHERE name = ?", (name,)):
        pid, x, y = _int(w["playfield_id"]), _int(w["xcoord"]), _int(w["ycoord"])
        if pid not in pfs or (x == 0 and y == 0):
            out.append(E(w["answer"]))
        else:
            out.append(_place(pfs, pid, x, y, w["answer"]))
    return out


def _loot_links(db, loot):
    ids = _item_ids_by_name(db, [l["itemname"] for l in loot if not l["aoid"]])
    out = []
    for l in loot:
        iid = _int(l["aoid"]) if l["aoid"] else ids.get(l["itemname"])
        out.append(_item_link(iid, l["itemname"]) if iid else "<span class='dim'>%s</span>" % E(l["itemname"]))
    return out


def _boss_summary(db, pfs, b, search=None):
    args = [b["bossid"]]
    sql = "SELECT * FROM ds_boss_loot WHERE bossid = ?"
    if search:
        c = []
        sql += " AND (%s)" % _like_clause([("itemname", _words(search))], c)
        args += c
    loot = db.execute(sql + " ORDER BY rowid", args).fetchall()
    h = "<h3><a href='/tool/boss?name=%s'>%s</a></h3>" % (E(b["bossname"].replace(" ", "+")), E(b["bossname"]))
    locs = _boss_locations(db, pfs, b["bossname"])
    if locs:
        h += "<p class='dim'>Location: %s</p>" % ", ".join(locs)
    h += "<p>Loot: %s</p>" % (", ".join(_loot_links(db, loot)) or "-")
    return h


def run_boss(db, p):
    q = _text(p, "name")
    if not q:
        raise ValueError("Enter a boss name.")
    args = []
    cond = _like_clause([("bossname", _words(q))], args)
    bosses = db.execute("SELECT * FROM ds_boss_names WHERE %s ORDER BY CAST(bossid AS INTEGER)" % cond, args).fetchall()
    if not bosses:
        raise ValueError("There were no matches for your search.")
    pfs = _playfields(db)
    if len(bosses) > 1:
        h = "<p>Boss search results for <b>%s</b> (%d)</p>" % (E(q), len(bosses))
        h += "".join(_boss_summary(db, pfs, b) for b in bosses)
        return dict(html=h, data=[dict(b) for b in bosses])
    b = bosses[0]
    loot = db.execute("SELECT * FROM ds_boss_loot WHERE bossid = ? ORDER BY rowid", (b["bossid"],)).fetchall()
    h = "<h2>%s</h2>" % E(b["bossname"])
    locs = _boss_locations(db, pfs, b["bossname"])
    if locs:
        h += "<h3>Location</h3><ul>%s</ul>" % "".join("<li>%s</li>" % l for l in locs)
    h += "<h3>Loot</h3><ul>%s</ul>" % "".join("<li>%s</li>" % l for l in _loot_links(db, loot))
    return dict(html=h, data=dict(boss=dict(b), loot=[dict(l) for l in loot]))


def run_bossloot(db, p):
    q = _text(p, "item")
    if not q:
        raise ValueError("Enter an item name.")
    args = []
    cond = _like_clause([("itemname", _words(q))], args)
    bosses = db.execute("SELECT DISTINCT bossid, bossname FROM ds_boss_loot WHERE %s ORDER BY CAST(bossid AS INTEGER)" % cond,
                        args).fetchall()
    if not bosses:
        raise ValueError("There were no matches for your search.")
    pfs = _playfields(db)
    h = "<p>Bosses that drop items matching <b>%s</b> (%d)</p>" % (E(q), len(bosses))
    h += "".join(_boss_summary(db, pfs, b, q) for b in bosses)
    return dict(html=h, data=[dict(b) for b in bosses])


# ------------------------------------------------------------------ raid loot
_RAIDS = [  # key, label, raid, categories (None = all)
    ("alb", "Albtraum", "Albtraum", None),
    ("apf", "APF (Alien Playfield)", "APF", None),
    ("sector7", "Sector 7 (APF)", "Sector 7", None),
    ("pande", "Pandemonium", "Pande", None),
    ("db1", "Dust Brigade 1", "DustBrigade", ["Armor", "DB1"]),
    ("db2", "Dust Brigade 2", "DustBrigade", ["Armor", "DB2"]),
    ("db3", "Dust Brigade 3", "DustBrigade", ["DB3"]),
    ("vortexx", "Legacy of the Xan: Vortexx", "Vortexx", None),
    ("mitaar", "Legacy of the Xan: Mitaar Hero", "Mitaar", None),
    ("12m", "Legacy of the Xan: 12-man", "12Man", None),
    ("poh", "Pyramid of Home", "Pyramid of Home", None),
    ("totw", "Temple of the Three Winds", "Temple of the Three Winds", None),
    ("subway", "Subway 201+", "Subway", None),
    ("halloween", "Halloween", "Halloween", None),
]


def run_raidloot(db, p):
    key = _text(p, "raid") or "apf"
    ent = next((r for r in _RAIDS if r[0] == key.lower()), None)
    if ent is None:
        ent = next((r for r in _RAIDS if key.lower() in r[1].lower()), None)
    if ent is None:
        raise ValueError("Unknown raid. Choose one from the list.")
    _, label, raid, cats = ent
    catfilter = _text(p, "category").lower()
    rows = db.execute("SELECT * FROM ds_raid_loot WHERE raid = ? ORDER BY CAST(id AS INTEGER)", (raid,)).fetchall()
    order = []
    groups = {}
    for r in rows:
        c = r["category"]
        if cats is not None and c not in cats:
            continue
        if catfilter and catfilter not in c.lower():
            continue
        if c not in groups:
            groups[c] = []
            order.append(c)
        groups[c].append(r)
    if not groups:
        raise ValueError("No loot found for %s%s." % (label, (" in category " + catfilter) if catfilter else ""))
    ids = _item_ids_by_name(db, [r["name"] for c in order for r in groups[c] if not r["aoid"]])
    h = "<h2>%s loot</h2>" % E(label)
    data = {}
    for c in order:
        trs = []
        for r in groups[c]:
            iid = _int(r["aoid"]) if r["aoid"] else ids.get(r["name"])
            nm = _item_link(iid, r["name"]) if iid else E(r["name"])
            if _int(r["multiloot"]) > 1:
                nm += " x%d" % _int(r["multiloot"])
            trs.append([r["ql"], nm, E(r["comment"])])
        h += "<h3>%s</h3>" % E(c) + _table(["QL", "Item", "Comment"], trs, raw_cols=(1, 2))
        data[c] = [dict(r) for r in groups[c]]
    return dict(html=h, data=data)


# ------------------------------------------------------------------ registry
TOOLS = [
    dict(name="xp", title="XP / SK needed", group="Levels", desc="XP or SK needed for one level, or between two levels.",
         bot="!xp", fields=[dict(name="start", label="Level (or start level)", type="int", default="100"),
                            dict(name="end", label="Target level (optional)", type="int")], run=run_xp),
    dict(name="axp", title="Alien experience", group="Levels", desc="AXP needed per alien level; leave both empty for the full table.",
         bot="!axp", fields=[dict(name="start", label="AI level (or start level, 0-30)", type="int"),
                             dict(name="end", label="Target AI level (optional)", type="int")], run=run_axp),
    dict(name="missions", title="Mission levels", group="Levels", desc="Which character levels can roll a mission of a given QL.",
         bot="!missions", fields=[dict(name="ql", label="Mission QL", type="int", default="100")], run=run_missions),
    dict(name="dyna", title="Dynacamps", group="World", desc="Dynacamps for a level, or by mob or playfield name.",
         bot="!dyna", fields=[dict(name="search", label="Level, mob or playfield", type="text", default="80")], run=run_dyna),
    dict(name="research", title="Research", group="Levels", desc="SK needed for research levels; leave empty for the table.",
         bot="!research", fields=[dict(name="level", label="Research level (1-10)", type="int"),
                                  dict(name="to", label="Up to level (optional)", type="int")], run=run_research),
    dict(name="oe", title="Over-equipped calculator", group="Weapons & skills",
         desc="Skill ranges for 100/75/50/25% over-equip for a requirement.",
         bot="!oe", fields=[dict(name="requirement", label="Skill requirement of the item", type="int", default="1200"),
                            dict(name="skill", label="Your skill (optional)", type="int")], run=run_oe),
    dict(name="arbiter", title="ICC arbiter weeks", group="World", desc="Which arbiter week (PvP, Alien, DIO) is on, now or on a date.",
         bot="!arbiter", fields=[dict(name="date", label="Date (YYYY-MM-DD, empty = today)", type="text")], run=run_arbiter),
    dict(name="whompah", title="Whom-Pah routes", group="World",
         desc="Shortest Whom-Pah route between two cities, or the destinations of a city.",
         bot="!whompah", fields=[dict(name="from", label="From city (name or short name)", type="text", default="tir"),
                                 dict(name="to", label="To city (optional)", type="text", default="borealis")], run=run_whompah),
    dict(name="citywave", title="City wave timer", group="World", desc="City raid wave timings; optionally which wave is next.",
         bot="!citywave", fields=[dict(name="elapsed", label="Seconds since the raid started (optional)", type="int")], run=run_citywave),
    dict(name="whereis", title="Where is...", group="World", desc="Locations of NPCs, bosses and places.",
         bot="!whereis", fields=[dict(name="search", label="Name", type="text", default="elmer ragg")], run=run_whereis),
    dict(name="spawntime", title="Spawn times", group="World", desc="Respawn timers of bosses; leave empty for all.",
         bot="!spawntime", fields=[dict(name="search", label="Mob (optional)", type="text")], run=run_spawntime),
    dict(name="disc", title="Instruction discs", group="Nanos", desc="Which nano an instruction disc turns into.",
         bot="!disc", fields=[dict(name="search", label="Disc name or item id", type="text", default="tranquility vale")], run=run_disc),
    dict(name="boss", title="Boss loot tables", group="World", desc="A boss's location and drop table.",
         bot="!boss", fields=[dict(name="name", label="Boss name", type="text", default="Afreet")], run=run_boss),
    dict(name="bossloot", title="Which boss drops...", group="World", desc="Bosses that drop an item.",
         bot="!bossloot", fields=[dict(name="item", label="Item name", type="text", default="Boots of")], run=run_bossloot),
    dict(name="raidloot", title="Raid loot lists", group="World", desc="Possible loot of the classic raids (APF, Pande, DB1-3, Xan, ...).",
         bot="!apf, !pande, !db1, !xan ...", fields=[
             dict(name="raid", label="Raid", type="select", options=[(r[0], r[1]) for r in _RAIDS]),
             dict(name="category", label="Category contains (optional)", type="text")], run=run_raidloot),
]
