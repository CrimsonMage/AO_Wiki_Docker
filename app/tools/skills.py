# GPL-3.0-only. Ported from Nadybot (https://github.com/Nadybot/Nadybot, branch nadybot7):
# SKILLS_MODULE (SkillsController, SARechargeInfo, BuffPerksController), TRICKLE_MODULE, WHATLOCKS_MODULE.
# Original authors: Tyrence (RK2), Nadyita (RK5), Imoutochan (RK1), Conci, Keex-1, Keltias, TinkeringIdiot, Tradias,
# NoGoal / Healnjoo (aggdef).  Python port for the offline AO archive; formulas and constants are copied from the PHP.
"""Weapon specials, init, martial arts, perks, trickle-down and skill-lock lookups
(!aggdef !aimshot !brawl !burst !dimach !fastattack !fling !fullauto !mafist !nanoinit !weapon !perks !trickle !whatlocks)."""
import html
import math
import re
import urllib.parse

E = html.escape
GROUP = "Weapons & skills"


# ------------------------------------------------------------------ helpers ----
def phpround(x, n=0):
    """PHP round(): half away from zero."""
    m = 10 ** n
    r = math.floor(abs(x) * m + 0.5) / m
    return -r if x < 0 else r


def fnum(x):
    """float -> string the way PHP echoes it (1.0 -> 1, 1.20 -> 1.2)."""
    if isinstance(x, int):
        return str(x)
    s = "%.14g" % x
    return s


def interpolate(x1, x2, y1, y2, x):
    """Nadybot Util::interpolate: linear interpolation (no clamping), rounded to an integer."""
    if x2 == x1:
        return int(y1)
    return int(phpround((y2 - y1) / (x2 - x1) * (x - x1) + y1))


def hl(v):
    return "<b>%s</b>" % E(str(v))


def kv(rows):
    return "<table class='kv'>%s</table>" % "".join(
        "<tr><th>%s</th><td>%s</td></tr>" % (E(k), v if isinstance(v, Raw) else E(str(v))) for k, v in rows)


class Raw(str):
    """already-safe HTML"""


def raw(s):
    return Raw(s)


def readable_time(secs):
    """Util::unixtimeToReadable (approximation of its '1 hr 5 mins' layout)."""
    secs = int(secs)
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    for v, one, many in ((d, "day", "days"), (h, "hr", "hrs"), (m, "min", "mins"), (s, "sec", "secs")):
        if v:
            parts.append("%d %s" % (v, one if v == 1 else many))
    return " ".join(parts) or "0 secs"


def need(p, *names):
    for n in names:
        if p.get(n) is None:
            raise ValueError("Please fill in: %s." % n.replace("_", " "))


def item_link(db, iid, ql=None, text=None):
    r = db.execute('SELECT name FROM items WHERE id = ?', (iid,)).fetchone()
    name = text or (r["name"] if r else "Item %d" % iid)
    href = "/item/%d" % iid + ("?ql=%d" % ql if ql else "")
    return "<a class='item' href='%s'>%s</a>" % (E(href), E(name))


# ------------------------------------------------------------------ SARechargeInfo ----
def sa_burst(skill, attack, recharge, delay):
    if delay == 0:
        delay = 1000
    cap = int(math.floor(attack + 8))
    to_cap = int(math.floor(((recharge * 20) + (delay / 100) + attack - (cap + 1)) * 25 + 1))
    cur = int(math.floor((recharge * 20) + (delay / 100) - (skill / 25) + attack))
    return to_cap, max(cur, cap), cap


def sa_fullauto(skill, attack, recharge, delay):
    if delay == 0:
        delay = 1000
    cap = int(math.floor(attack + 10))
    to_cap = int(math.floor(((recharge * 40) + (delay / 100) + attack - (cap + 1)) * 25 + 1))
    cur = int(math.floor((recharge * 40) + (delay / 100) - (skill / 25) + attack))
    return to_cap, max(cur, cap), cap


def sa_fastattack(skill, attack):
    cap = int(math.floor(attack + 5))
    to_cap = int(math.floor((attack * 1600) - (cap + 1) * 100 + 1))
    cur = int(math.floor((attack * 16) - (skill / 100)))
    return to_cap, max(cur, cap), cap


def sa_fling(skill, attack):
    return sa_fastattack(skill, attack)


def sa_aimed(skill, attack, recharge):
    cap = int(math.floor(attack + 10))
    to_cap = int(math.floor(recharge * 4000 / 3 + attack * 100 / 3 - (cap + 1) * 100 / 3 + 1))
    cur = int(math.floor((recharge * 40) - (skill * 3.0 / 100) + attack))
    return to_cap, max(cur, cap), cap


# ------------------------------------------------------------------ weapon data ----
def _toint(v):
    if v is None or str(v).strip() == "":
        return None
    return int(float(v))


def weapon_attrs(db, iid):
    r = db.execute('SELECT * FROM ds_weapon_attributes WHERE CAST(id AS INTEGER) = ?', (iid,)).fetchone()
    if not r:
        return None
    d = {k: _toint(r[k]) for k in r.keys()}
    for k in ("fling_shot", "fast_attack", "aimed_shot", "brawl", "sneak_attack"):
        d[k] = bool(d[k])
    return d


def weapon_data(db, iid, ql):
    """Everything the bot's !weapon reads: item range, interpolated attack / recharge (seconds), delays, flags."""
    rows = db.execute('SELECT * FROM ds_items_ql WHERE CAST(lowid AS INTEGER) = ? OR CAST(highid AS INTEGER) = ?', (iid, iid)).fetchall()
    rows = sorted(rows, key=lambda r: 0 if int(r["highid"]) == iid else 1)
    if not rows:
        raise ValueError("Item does not exist in the items database.")
    row = None
    if ql is None:
        row = rows[0]
        ql = int(row["highql"])
    else:
        for r in rows:
            if int(r["lowql"]) <= ql <= int(r["highql"]):
                row = r
                break
        if row is None:
            raise ValueError("Item does not exist in the items database for QL %d." % ql)
    lowid, highid, lowql, highql = int(row["lowid"]), int(row["highid"]), int(row["lowql"]), int(row["highql"])
    lo, hi = weapon_attrs(db, lowid), weapon_attrs(db, highid)
    if lo is None or hi is None:
        raise ValueError("Could not find any weapon info for this item.")
    ip = lambda k: interpolate(lowql, highql, lo[k], hi[k], ql)
    out = dict(name=row["name"], lowid=lowid, highid=highid, ql=ql, lowql=lowql, highql=highql, hi=hi, lo=lo,
               attack=ip("attack_time") / 100, recharge=ip("recharge_time") / 100, full_auto=None, burst=None)
    if hi["full_auto"] is not None and lo["full_auto"] is not None:
        out["full_auto"] = ip("full_auto")
    if hi["burst"] is not None and lo["burst"] is not None:
        out["burst"] = ip("burst")
    return out


ITEM_FIELDS = [dict(name="item", label="Weapon item id (optional, fills in the numbers above)", type="item"),
               dict(name="ql", label="Weapon QL (default: its highest QL)", type="int")]


def fill_from_item(db, p, mapping):
    """If an item id was given, fill still-empty numeric params from the weapon. Returns a note (Raw) or ''."""
    if p.get("item") is None:
        return ""
    w = weapon_data(db, p["item"], p.get("ql"))
    for param, key in mapping.items():
        if p.get(param) is None and w.get(key) is not None:
            p[param] = w[key]
        elif p.get(param) is None:
            raise ValueError("%s has no %s value in the database; enter it by hand." % (w["name"], key.replace("_", " ")))
    return "<p class='dim'>Weapon values from %s at QL %d (attack %ss, recharge %ss).</p>" % (
        item_link(db, w["lowid"], w["ql"], w["name"]), w["ql"], fnum(w["attack"]), fnum(w["recharge"]))


# ------------------------------------------------------------------ init / aggdef ----
def inits_for_percent(percent, attack, recharge):
    ia = (attack - (percent - 87.5) / 50 - 1) * 600
    ir = (recharge - (percent - 87.5) / 50 - 1) * 300
    if ia > 1200:
        ia = (attack - (percent - 37.5) / 50 - 2) * 1800 + 1200
    if ir > 1200:
        ir = (recharge - (percent - 37.5) / 50 - 4) * 900 + 1200
    return int(phpround(max(max(ia, ir), 0)))


def agg_bar(percent, length=50):
    marker = int(phpround(percent / 100 * length))
    bar = "l" * length
    s = bar[:marker] + "│" + bar[marker + 1:]
    if percent < 100.0:
        s += " "
    return s


def run_aggdef(db, p):
    note = fill_from_item(db, p, dict(attack="attack", recharge="recharge"))
    need(p, "attack", "recharge", "init")
    att, rech, init = p["attack"], p["recharge"], p["init"]
    if init < 1200:
        a = phpround(((att - init / 600) - 1) / 0.02 + 87.5, 2)
        r = phpround(((rech - init / 300) - 1) / 0.02 + 87.5, 2)
    else:
        ik = init - 1200
        a = phpround(((att - 1200 / 600 - ik / 600 / 3) - 1) / 0.02 + 87.5, 2)
        r = phpround(((rech - 1200 / 300 - ik / 300 / 3) - 1) / 0.02 + 87.5, 2)
    res = r if a < r else a
    res = 0 if res < 0 else (100 if res > 100 else res)
    full_agg, neutral, full_def = (inits_for_percent(x, att, rech) for x in (100, 87.5, 0))
    pre = "%d DEF %s AGG %d\n%sYou: %d" % (full_def, agg_bar(res), full_agg, " " * 25, init)
    h = note + kv([
        ("Attack time", "%s s" % fnum(att)), ("Recharge time", "%s s" % fnum(rech)), ("Init skill", init),
        ("Set your AGG bar at", "%d%% (%d of 8)" % (phpround(res), phpround(res * 8 / 100))),
        ("Agg/def slider should read", "%d" % phpround(res * 2 - 100)),
        ("Result", "to wield your weapon at 1/1"),
        ("Inits for max speed at Full Agg (100%)", full_agg), ("Inits for max speed at Neutral (87.5%)", neutral),
        ("Inits for max speed at Full Def (0%)", full_def)])
    h += "<pre>%s</pre>" % E(pre)
    h += ("<p class='dim'>At the neutral position (87.5%) your attack and recharge time match the weapon's. "
          "Based upon a RINGBOT module by NoGoal (RK2), modified for Budabot by Healnjoo and Nadyita.</p>")
    return dict(html=h, data=dict(bar_percent=res, full_agg=full_agg, neutral=neutral, full_def=full_def))


def calc_attack_time_reduction(init):
    if init > 1200:
        return (init - 1200) / 600 + 6
    return init / 200


def calc_bar_setting(eff):
    if eff < 0:
        return 87.5 + (87.5 * eff)
    if eff > 0:
        return 87.5 + (12 * eff)
    return 87.5


def calc_inits(t):
    if t < 0:
        return 0
    if t < 6:
        return phpround(t * 200, 2)
    return phpround(1200 + (t - 6) * 600, 2)


def run_nanoinit(db, p):
    need(p, "cast", "init")
    cast, init = p["cast"], p["init"]
    eff = cast - calc_attack_time_reduction(init)
    bar = min(100, max(0, calc_bar_setting(eff)))
    fa, ne, fd = calc_inits(cast - 1), calc_inits(cast), calc_inits(cast + 1)
    mk = int(phpround(bar / 100 * 50))
    barstr = "l" * mk + "│" + ("l" * 50)[mk + 1:]
    pre = "%s DEF %s AGG %s\n%sYou: %d" % (fnum(fd), barstr, fnum(fa), " " * 25, init)
    ct = lambda x: "%.1f s" % phpround(max(0, x), 1)
    h = kv([("Casting time", "%s s" % fnum(cast)), ("Nano init skill", init), ("Def/Agg", "%d%%" % phpround(bar)),
            ("Set your AGG bar at to instacast", "%d%% (%.2f of 8)" % (phpround(bar), phpround(bar * 8 / 100, 2))),
            ("Agg/def slider should read", "%d" % phpround(bar * 2 - 100)),
            ("Inits to instacast at Full Agg (100%)", fnum(fa)), ("Inits to instacast at Neutral (87.5%)", fnum(ne)),
            ("Inits to instacast at Full Def (0%)", fnum(fd)),
            ("Current casting time at Full Agg", ct(eff - 1)), ("Current casting time at Neutral", ct(eff)),
            ("Current casting time at Full Def", ct(eff + 1))])
    return dict(html=h + "<pre>%s</pre>" % E(pre), data=dict(bar_percent=bar, effective_casting_time=eff))


# ------------------------------------------------------------------ special attack recharge tools ----
def run_aimshot(db, p):
    note = fill_from_item(db, p, dict(attack="attack", recharge="recharge"))
    need(p, "attack", "recharge", "skill")
    to_cap, cur, cap = sa_aimed(p["skill"], p["attack"], p["recharge"])
    mult = int(phpround(p["skill"] / 95))
    h = note + kv([("Attack time", "%s s" % fnum(p["attack"])), ("Recharge time", "%s s" % fnum(p["recharge"])),
                   ("Aimed Shot skill", p["skill"]), ("Aimed Shot multiplier", "1-%dx" % mult),
                   ("Your Aimed Shot recharge", "%d s" % cur), ("Recharge cap with this weapon", "%d s" % cap),
                   ("Skill needed to cap", to_cap)])
    return dict(html=h, data=dict(recharge=cur, cap=cap, skill_to_cap=to_cap, multiplier=mult))


def run_burst(db, p):
    note = fill_from_item(db, p, dict(attack="attack", recharge="recharge", burst_delay="burst"))
    need(p, "attack", "recharge", "burst_delay", "skill")
    to_cap, cur, cap = sa_burst(p["skill"], p["attack"], p["recharge"], p["burst_delay"])
    h = note + kv([("Attack time", "%s s" % fnum(p["attack"])), ("Recharge time", "%s s" % fnum(p["recharge"])),
                   ("Burst delay (Burst Cycle)", p["burst_delay"]), ("Burst skill", p["skill"]),
                   ("Your burst recharge", "%d s" % cur), ("Minimum (cap) recharge", "%d s" % cap),
                   ("Burst skill needed to cap", to_cap)])
    return dict(html=h, data=dict(recharge=cur, cap=cap, skill_to_cap=to_cap))


def run_fullauto(db, p):
    note = fill_from_item(db, p, dict(attack="attack", recharge="recharge", fa_recharge="full_auto"))
    need(p, "attack", "recharge", "fa_recharge", "skill")
    to_cap, cur, cap = sa_fullauto(p["skill"], p["attack"], p["recharge"], p["fa_recharge"])
    bullets = 5 + int(math.floor(p["skill"] / 100))
    h = note + kv([("Weapon attack", "%s s" % fnum(p["attack"])), ("Weapon recharge", "%s s" % fnum(p["recharge"])),
                   ("Full Auto recharge value (FullAuto Cycle)", p["fa_recharge"]), ("Full Auto skill", p["skill"]),
                   ("Your Full Auto recharge", "%d s" % cur), ("Maximum bullets", bullets),
                   ("Recharge cap", "%d s" % cap), ("Full Auto skill needed to cap", to_cap)])
    h += ("<p class='dim'>From 0 to 10.0K damage, the bullet damage is unchanged. From 10K to 11.5K damage, each bullet damage is "
          "halved. From 11K to 15.0K damage, each bullet damage is halved again. 15K is the damage cap.</p>")
    return dict(html=h, data=dict(recharge=cur, cap=cap, skill_to_cap=to_cap, max_bullets=bullets))


def run_fastattack(db, p):
    note = fill_from_item(db, p, dict(attack="attack"))
    need(p, "attack", "skill")
    to_cap, cur, cap = sa_fastattack(p["skill"], p["attack"])
    h = note + kv([("Attack time", "%s s" % fnum(p["attack"])), ("Fast Attack skill", p["skill"]),
                   ("Your recharge", "%d s" % cur), ("Skill needed to cap", to_cap), ("Recharge cap", "%d s" % cap)])
    h += "<p class='dim'>Every 100 points of Fast Attack skill below the cap value increases the recharge by 1 s.</p>"
    return dict(html=h, data=dict(recharge=cur, cap=cap, skill_to_cap=to_cap))


def run_fling(db, p):
    note = fill_from_item(db, p, dict(attack="attack"))
    need(p, "attack", "skill")
    to_cap, cur, cap = sa_fling(p["skill"], p["attack"])
    h = note + kv([("Attack time", "%s s" % fnum(p["attack"])), ("Fling Shot skill", p["skill"]),
                   ("Your recharge", "%d s" % cur), ("Skill needed to cap", to_cap), ("Recharge cap", "%d s" % cap)])
    return dict(html=h, data=dict(recharge=cur, cap=cap, skill_to_cap=to_cap))


# ------------------------------------------------------------------ brawl / dimach / mafist ----
SKILL_LIST = [1, 1000, 1001, 2000, 2001, 3000]


def _tier(skill):
    return 0 if skill < 1001 else (2 if skill < 2001 else 4)


def run_brawl(db, p):
    need(p, "skill")
    s = p["skill"]
    mn = [1, 100, 101, 170, 171, 235]
    mx = [2, 500, 501, 850, 851, 1145]
    cr = [3, 500, 501, 600, 601, 725]
    i = _tier(s)
    f = lambda lst: interpolate(SKILL_LIST[i], SKILL_LIST[i + 1], lst[i], lst[i + 1], s)
    lo, hi, crit = f(mn), f(mx), f(cr)
    stun = "20%" if s >= 1000 else "10% (becomes 20% above 1000 brawl skill)"
    dur = "4 s" if s >= 2001 else "3 s (becomes 4 s above 2001 brawl skill)"
    h = kv([("Brawl skill", s), ("Brawl recharge", "15 seconds (constant)"), ("Damage", "%d-%d (crit bonus %d)" % (lo, hi, crit)),
            ("Stun chance", stun), ("Stun duration", dur)]) + "<p class='dim'>by Imoutochan, RK1</p>"
    return dict(html=h, data=dict(min=lo, max=hi, crit=crit))


def run_dimach(db, p):
    need(p, "skill")
    s = p["skill"]
    gen = [1, 2000, 2001, 2500, 2501, 2850]
    ma_rech = [1800, 1800, 1188, 600, 600, 300]
    ma_dmg = [1, 2000, 2001, 2340, 2341, 2550]
    sh_rech = [300, 300, 300, 300, 240, 200]
    sh_dmg = [1, 920, 921, 1872, 1873, 2750]
    sh_drain = [70, 70, 70, 75, 75, 80]
    keeper = [1, 3000, 3001, 10500, 10501, 15000]
    i = _tier(s)
    f = lambda lst: interpolate(SKILL_LIST[i], SKILL_LIST[i + 1], lst[i], lst[i + 1], s)
    h = "<p>Dimach skill: %s</p>" % hl(s)
    h += "<h3>Martial Artist</h3>" + kv([("Damage", "%d (crit bonus 1)" % f(ma_dmg)), ("Recharge", readable_time(f(ma_rech)))])
    h += "<h3>Keeper</h3>" + kv([("Self heal", "%d HP" % f(keeper)), ("Recharge", "5 mins (constant)")])
    h += "<h3>Shade</h3>" + kv([("Damage", "%d (crit bonus 1)" % f(sh_dmg)), ("HP drain", "%d%%" % f(sh_drain)),
                                ("Recharge", readable_time(f(sh_rech)))])
    h += "<h3>All other professions</h3>" + kv([("Damage", "%d (crit bonus 1)" % f(gen)), ("Recharge", "30 mins (constant)")])
    return dict(html=h + "<p class='dim'>by Imoutochan, RK1</p>", data=dict(skill=s))


def run_mafist(db, p):
    need(p, "skill")
    orig = p["skill"]
    skl = [1, 200, 1000, 1001, 2000, 2001, 3000]
    ma_min = [4, 45, 125, 130, 220, 225, 450]
    ma_max = [8, 75, 400, 405, 830, 831, 1300]
    ma_crit = [3, 50, 500, 501, 560, 561, 800]
    ma_speed = [1.15, 1.2, 1.25, 1.30, 1.35, 1.45, 1.50]
    ma_aoid = [211352, 211353, 211354, 211357, 211358, 211363, 211364]
    sh_min = [3, 25, 55, 56, 130, 131, 280]
    sh_max = [5, 60, 258, 259, 682, 683, 890]
    sh_crit = [3, 50, 250, 251, 275, 276, 300]
    sh_aoid = [211349, 211350, 211351, 211359, 211360, 211365, 211366]
    ot_min = [3, 25, 65, 66, 140, 204, 300]
    ot_max = [5, 60, 280, 281, 715, 831, 990]
    ot_crit = [3, 50, 500, 501, 605, 605, 630]
    ot_aoid = [43712, 144745, 43713, 211355, 211356, 211361, 211362]
    s = orig
    i = 0 if s < 200 else (1 if s < 1001 else (3 if s < 2001 else 5))
    aoid_ql = int(math.fmod(math.ceil(s / 2) - 1, 500)) + 1
    fist_ql = min(1500, int(phpround(s / 2)))
    if fist_ql <= 200:
        speed = 1.25
    elif fist_ql <= 500:
        speed = 1.25 + (0.2 * ((fist_ql - 200) / 300))
    elif fist_ql <= 1000:
        speed = 1.45 + (0.2 * ((fist_ql - 500) / 500))
    else:
        speed = 1.65 + (0.2 * ((fist_ql - 1000) / 500))
    speed = phpround(speed, 2)
    s = min(3000, s)
    f = lambda lst: interpolate(skl[i], skl[i + 1], lst[i], lst[i + 1], s)
    base = ((s - skl[i]) * (ma_speed[i + 1] - ma_speed[i])) / (skl[i + 1] - skl[i]) + ma_speed[i]
    ma_fist = phpround(base, 2)

    def block(title, aoid, mn, mx, cr, spd):
        return "<h3>%s <span class='dim'>(%s, QL %d)</span></h3>" % (E(title), item_link(db, aoid[i], aoid_ql), aoid_ql) + kv([
            ("Fist speed", "%ss / %ss" % (fnum(spd), fnum(spd))),
            ("Fist damage", "%d-%d (crit bonus %d)" % (f(mn), f(mx), f(cr)))])
    h = "<p>Martial Arts skill: %s</p>" % hl(orig)
    h += block("Martial Artist", ma_aoid, ma_min, ma_max, ma_crit, ma_fist)
    h += block("Shade", sh_aoid, sh_min, sh_max, sh_crit, speed)
    h += block("All other professions", ot_aoid, ot_min, ot_max, ot_crit, speed)
    return dict(html=h, data=dict(skill=orig, ma_speed=ma_fist, speed=speed, fist_ql=aoid_ql))


# ------------------------------------------------------------------ weapon ----
def agg_table(attack, recharge):
    lines = []
    for pc in range(100, -1, -10):
        lines.append("DEF %s AGG %4d (%3d%%)" % (agg_bar(pc), inits_for_percent(pc, attack, recharge), pc))
    return "<pre>%s</pre>" % E("\n".join(lines))


def weapon_html(db, w):
    hi, atk, rec = w["hi"], w["attack"], w["recharge"]
    h = kv([("Item", raw("%s (QL %d, range %d-%d)" % (item_link(db, w["lowid"], w["ql"], w["name"]), w["ql"], w["lowql"], w["highql"]))),
            ("Attack", "%.2f s" % atk), ("Recharge", "%.2f s" % rec)])
    h += "<h3>Agg/Def</h3><p class='dim'>Initiative needed for 1/1 speed at each slider position.</p>" + agg_table(atk, rec)
    found = False
    sp = []
    if w["full_auto"] is not None:
        c, _, cap = sa_fullauto(0, atk, rec, w["full_auto"])
        sp.append(("Full Auto", "You need %d Full Auto skill to cap your recharge at %d s." % (c, cap)))
    if w["burst"] is not None:
        c, _, cap = sa_burst(0, atk, rec, w["burst"])
        sp.append(("Burst", "You need %d Burst skill to cap your recharge at %d s." % (c, cap)))
    if hi["fling_shot"]:
        c, _, cap = sa_fling(0, atk)
        sp.append(("Fling Shot", "You need %d Fling Shot skill to cap your recharge at %d s." % (c, cap)))
    if hi["fast_attack"]:
        c, _, cap = sa_fastattack(0, atk)
        sp.append(("Fast Attack", "You need %d Fast Attack skill to cap your recharge at %d s." % (c, cap)))
    if hi["aimed_shot"]:
        c, _, cap = sa_aimed(0, atk, rec)
        sp.append(("Aimed Shot", "You need %d Aimed Shot skill to cap your recharge at %d s." % (c, cap)))
    if hi["brawl"]:
        sp.append(("Brawl", "This weapon supports 1 brawl attack every 15 s (constant)."))
    if hi["sneak_attack"]:
        sp.append(("Sneak Attack", "This weapon supports sneak attacks. The recharge depends solely on your Sneak Attack skill: 40 - (Sneak Attack skill) / 150."))
    for t, s in sp:
        h += "<h3>%s</h3><p>%s</p>" % (E(t), E(s))
        found = True
    if not found:
        h += "<p>There are no specials on this weapon that could be calculated.</p>"
    h += "<p class='dim'>Rewritten by Nadyita (RK5). Specials recharge fixes by Conci, Keex-1, Keltias, TinkeringIdiot, Tradias (RK5).</p>"
    return h


def run_weapon(db, p):
    if p.get("item") is not None:
        w = weapon_data(db, p["item"], p.get("ql"))
        return dict(html=weapon_html(db, w), data=dict(name=w["name"], ql=w["ql"], attack=w["attack"], recharge=w["recharge"],
                                                       full_auto=w["full_auto"], burst=w["burst"],
                                                       flags={k: w["hi"][k] for k in ("fling_shot", "fast_attack", "aimed_shot", "brawl", "sneak_attack")}))
    if not p.get("search"):
        raise ValueError("Give a weapon item id, or a name to search for.")
    words = [x for x in re.split(r"\s+", p["search"].strip()) if x]
    cond = " AND ".join("name LIKE ? ESCAPE '\\'" for _ in words)
    args = ["%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for w in words]
    q = "SELECT * FROM ds_items_ql WHERE %s ORDER BY name LIMIT 400" % cond
    ql = p.get("ql")
    out, seen = [], set()
    for r in db.execute(q, args):
        lo, hi = int(r["lowid"]), int(r["highid"])
        if ql is not None and not (int(r["lowql"]) <= ql <= int(r["highql"])):
            continue
        if lo in seen:
            continue
        if not db.execute("SELECT 1 FROM ds_weapon_attributes WHERE CAST(id AS INTEGER) IN (?, ?)", (lo, hi)).fetchone():
            continue
        seen.add(lo)
        out.append(r)
    if not out:
        raise ValueError("No %sitems found matching %s." % ("QL %d " % ql if ql else "", p["search"]))
    if len(out) == 1:
        return run_weapon(db, dict(item=int(out[0]["lowid"]), ql=ql or int(out[0]["highql"])))
    rows = []
    for r in out[:100]:
        use = ql or int(r["highql"])
        url = "/tool/weapon?" + urllib.parse.urlencode(dict(item=int(r["lowid"]), ql=use))
        rows.append("<tr><td><a href='%s'>stats</a></td><td>%s</td><td>QL %d</td></tr>" % (E(url), item_link(db, int(r["lowid"]), use, r["name"]), use))
    return dict(html="<p>%d weapons match%s.</p><div class='scroll'><table>%s</table></div>" % (
        len(out), " (first 100 shown)" if len(out) > 100 else "", "".join(rows)),
        data=[dict(id=int(r["lowid"]), name=r["name"]) for r in out[:100]])


# ------------------------------------------------------------------ skills (Skill enum replacement) ----
_EXTRA_ALIASES = {"rangedenergy": 133, "evadeclose": 155, "evadeclosecombat": 155, "brawl": 142, "smg": 114, "rangedinit": 119,
                  "addnanodam": 315, "meleeinit": 118, "physicalinit": 120, "nanoinit": 149, "aimedshot": 151}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


class SkillIndex:
    """ds_skills + ds_skill_alias: stands in for Nadybot's Skill enum (names are loaded from the archive)."""

    def __init__(self, db):
        self.names = {}   # id -> list of names (db name first)
        self.unit = {}
        self.inline = {}
        for r in db.execute("SELECT id, name, unit FROM ds_skills"):
            i = int(r["id"])
            self.names.setdefault(i, []).append(r["name"])
            self.unit[i] = r["unit"] or ""
            self.inline[i] = r["name"]
        for r in db.execute("SELECT id, name FROM ds_skill_alias"):
            i = int(r["id"])
            if i in self.names and r["name"] not in self.names[i]:
                self.names[i].append(r["name"])
        self.full = {i: max(ns, key=lambda n: (len(n), n)) for i, ns in self.names.items()}

    def full_name(self, i):
        return self.full.get(i, "Skill %d" % i)

    def match(self, text):
        q = _norm(text)
        if not q:
            return []
        exact = sorted(i for i, ns in self.names.items() if any(_norm(n) == q for n in ns))
        if exact:
            return exact
        if q in _EXTRA_ALIASES:
            return [_EXTRA_ALIASES[q]]
        return sorted(i for i, ns in self.names.items() if any(q in _norm(n) for n in ns))


# ------------------------------------------------------------------ trickle ----
ABILITIES = [("agi", "Agility", "amountAgi"), ("int", "Intelligence", "amountInt"), ("psy", "Psychic", "amountPsy"),
             ("sta", "Stamina", "amountSta"), ("str", "Strength", "amountStr"), ("sen", "Sense", "amountSen")]


def _join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


def trickle_amounts(row):
    reqs = []
    for _, long, col in ABILITIES:
        a = float(row[col])
        if a <= 0:
            continue
        reqs.append("%s %s" % (fnum(phpround(4 / a, 2)), long))
    return _join(reqs)


def run_trickle(db, p):
    ab = {k: 0 for k, _, _ in ABILITIES}
    if p.get("all"):
        for k in ab:
            ab[k] += p["all"]
    for k in ab:
        if p.get(k):
            ab[k] += p[k]
    if any(v > 0 for v in ab.values()):
        rows = db.execute("SELECT * FROM ds_trickle ORDER BY CAST(id AS INTEGER)").fetchall()
        head = ", ".join("%s: %d" % (long, ab[k]) for k, long, _ in ABILITIES if ab[k] > 0)
        out, group, data = [], None, []
        for r in rows:
            amount = sum(float(r[col]) * ab[k] for k, _, col in ABILITIES)
            if amount <= 0:
                continue
            if r["groupName"] != group:
                if group is not None:
                    out.append("</table>")
                group = r["groupName"]
                out.append("<h3>%s</h3><table>" % E(group))
            q = amount / 4
            whole = int(math.floor(q))
            frac = ("%.2f" % (q - whole))[2:]
            out.append("<tr><td style='text-align:right'><b>%d.%s</b></td><td>%s</td></tr>" % (whole, frac, E(r["skill"])))
            data.append(dict(skill=r["skill"], group=group, amount=q))
        if group is not None:
            out.append("</table>")
        return dict(html="<p>Trickle results for %s</p>%s<p class='dim'>By Tyrence (RK2), inspired by the Bebot command of the same name.</p>" % (
            E(head), "".join(out) or "<p>No skills gain anything.</p>"), data=data)
    if p.get("skill"):
        idx = SkillIndex(db)
        ids = {str(i) for i in idx.match(p["skill"])}
        rows = [r for r in db.execute("SELECT * FROM ds_trickle ORDER BY CAST(id AS INTEGER)") if r["skill_id"] in ids]
        if not rows:
            raise ValueError("Could not find any skills for search '%s'" % p["skill"])
        h = "<p>Ability points needed to trickle 1 skill point into a skill (any one of the listed options):</p>"
        h += kv([(idx.full_name(int(r["skill_id"])), trickle_amounts(r)) for r in rows])
        return dict(html=h, data=[dict(skill=r["skill"], needs=trickle_amounts(r)) for r in rows])
    raise ValueError("Enter ability points to add (or an amount for \"all abilities\"), or a skill name to look up.")


# ------------------------------------------------------------------ whatlocks ----
def pretty_duration(sec):
    d, rem = divmod(int(sec), 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = [(d, "%dd"), (h, "%02dh"), (m, "%02dm"), (s, "%02ds")]
    out, started = [], False
    for v, f in parts:
        if v or started:
            out.append(f % v)
            started = True
    return " ".join(out) or "0s"


def run_whatlocks(db, p):
    idx = SkillIndex(db)
    sk = p.get("skill")
    if not sk:
        rows = db.execute("SELECT skill_id, COUNT(*) AS n FROM ds_what_locks WHERE skill_id <> '' GROUP BY skill_id").fetchall()
        lst = sorted(((idx.full_name(int(r["skill_id"])), int(r["n"])) for r in rows), key=lambda x: x[0])
        trs = "".join("<tr><td style='text-align:right'>%d</td><td><a href='%s'>%s</a></td></tr>" % (
            n, E("/tool/whatlocks?" + urllib.parse.urlencode(dict(skill=name))), E(name)) for name, n in lst)
        return dict(html="<p>%d skills can be locked by items. Choose one to see which items lock it.</p><div class='scroll'><table>"
                         "<tr><th>Items</th><th>Skill</th></tr>%s</table></div>" % (len(lst), trs),
                    data=[dict(skill=n, items=c) for n, c in lst])
    ids = idx.match(sk)
    if not ids:
        raise ValueError("Could not find any skills matching %s." % sk)
    if len(ids) > 1:
        lis = "".join("<li><a href='%s'>%s</a></li>" % (E("/tool/whatlocks?" + urllib.parse.urlencode(dict(skill=idx.full_name(i)))),
                                                         E(idx.full_name(i))) for i in sorted(ids, key=idx.full_name))
        return dict(html="<p>Several skills match, choose one:</p><ul>%s</ul>" % lis, data=[idx.full_name(i) for i in ids])
    sid = ids[0]
    rows = db.execute("SELECT * FROM ds_what_locks WHERE CAST(skill_id AS INTEGER) = ? ORDER BY CAST(duration AS INTEGER)", (sid,)).fetchall()
    if not rows:
        return dict(html="<p>There is currently no item in the game locking %s.</p>" % hl(idx.full_name(sid)), data=[])
    trs, data = [], []
    for r in rows:
        iid = int(r["item_id"])
        it = db.execute("SELECT name, lowql FROM ds_items_ql WHERE CAST(lowid AS INTEGER) = ?", (iid,)).fetchone()
        if not it:
            continue
        trs.append("<tr><td>%s</td><td>%s</td><td>QL %s</td></tr>" % (E(pretty_duration(int(r["duration"]))), item_link(db, iid, int(it["lowql"]), it["name"]), E(it["lowql"])))
        data.append(dict(item_id=iid, name=it["name"], duration=int(r["duration"])))
    return dict(html="<p>%d items lock %s (shortest lock first).</p><div class='scroll'><table><tr><th>Lock time</th><th>Item</th><th>QL</th></tr>%s</table></div>" % (
        len(trs), hl(idx.full_name(sid)), "".join(trs)), data=data)


# ------------------------------------------------------------------ perks ----
PROFESSIONS = ["Adventurer", "Agent", "Bureaucrat", "Doctor", "Enforcer", "Engineer", "Fixer", "Keeper", "Martial Artist",
               "Meta-Physicist", "Nano-Technician", "Shade", "Soldier", "Trader"]
_PROF_TOKENS = {"adv": "Adventurer", "agent": "Agent", "crat": "Bureaucrat", "doc": "Doctor", "enf": "Enforcer", "eng": "Engineer",
                "engi": "Engineer", "fix": "Fixer", "fixer": "Fixer", "keep": "Keeper", "keeper": "Keeper", "ma": "Martial Artist",
                "mp": "Meta-Physicist", "nt": "Nano-Technician", "shade": "Shade", "sol": "Soldier", "sold": "Soldier",
                "tra": "Trader", "trad": "Trader"}
_EXPAND = {
    "Add. Dmg.": ["Add. Cold Dam.", "Add. Chem Dam.", "Add. Energy Dam.", "Add. Fire Dam.", "Add. Melee Dam.", "Add. Poison Dam.",
                  "Add. Rad. Dam.", "Add. Proj. Dam."],
    "AC": ["Melee/ma AC", "Disease AC", "Fire AC", "Cold AC", "Imp/Proj AC", "Energy AC", "Chemical AC", "Radiation AC"],
    "Shield": ["Shield%sAC" % x for x in ("Projectile", "Melee", "Energy", "Chemical", "Radiation", "Cold", "Nano", "Fire", "Poison")],
    "Reflect": ["Reflect%sAC" % x for x in ("Projectile", "Melee", "Energy", "Chemical", "Radiation", "Cold", "Nano", "Fire", "Poison")],
}
_perk_cache = {}


def load_perks(db):
    key = id(db)
    if key in _perk_cache:
        return _perk_cache[key]
    idx = SkillIndex(db)
    nl = {int(r["strain_id"]): r["name"] for r in db.execute("SELECT strain_id, name FROM ds_nano_lines")}
    perks = {}
    for r in db.execute("SELECT * FROM ds_perks ORDER BY rowid"):
        name = r["name"]
        pk = perks.get(name)
        if pk is None:
            desc = r["description"]
            pk = perks[name] = dict(name=name, expansion=r["expansion"], description=desc.replace("\\n", "\n") if desc else None, levels={})
        profs = r["professions"]
        if profs == "*":
            profs = ",".join(["Adv", "Agent", "Crat", "Doc", "Enf", "Engi", "Fix", "Keep", "MA", "MP", "NT", "Shade", "Sol", "Tra"])
        plist = []
        for t in profs.split(","):
            v = _PROF_TOKENS.get(t.strip().lower())
            if v:
                plist.append(v)
        buffs = {}
        for b in (r["buffs"] or "").split(","):
            b = b.strip()
            pos = b.rfind(" ")
            if pos < 0:
                continue
            sname, amount = b[:pos + 1].strip(), b[pos + 1:].strip()
            for s in _EXPAND.get(sname, [sname]):
                m = idx.match(s)
                if len(m) == 1:
                    try:
                        buffs[m[0]] = int(amount)
                    except ValueError:
                        buffs[m[0]] = 0
        res = {}
        if r["resistances"]:
            for part in re.split(r"\s*,\s*", r["resistances"].strip()):
                if ":" in part:
                    a, b = re.split(r"\s*:\s*", part, 1)
                    res[int(a)] = int(b)
        action = None
        if r["action"]:
            a = r["action"].strip()
            # the PHP casts with (int); a non-numeric field becomes action 0 whose item is unknown, i.e. never shown
            m = re.match(r"^\d+", a.rstrip("*"))
            if m and db.execute("SELECT 1 FROM items WHERE id = ?", (int(m.group(0)),)).fetchone():
                action = dict(id=int(m.group(0)), scaling=a.endswith("*"))
        pk["levels"][int(r["perk_level"])] = dict(perk_level=int(r["perk_level"]), required_level=int(r["required_level"]),
                                                  aoid=int(r["aoid"]) if r["aoid"] else None, professions=plist, buffs=buffs,
                                                  resistances=res, action=action)
    _perk_cache.clear()
    _perk_cache[key] = (perks, idx, nl)
    return _perk_cache[key]


def _buff_lines(idx, buffs, signed=True):
    items = sorted(((idx.full_name(i), a, idx.unit.get(i, "")) for i, a in buffs.items() if i in idx.names), key=lambda x: x[0])
    return items


def _res_lines(nl, res):
    return sorted(((nl[i], a) for i, a in res.items() if i in nl), key=lambda x: x[0])


def render_perk(db, perk, idx, nl):
    out = []
    for lv in perk["levels"].values():
        if lv["aoid"] is None:
            continue
        out.append("<h3>%s %d <span class='dim'>[%s]</span></h3>" % (E(perk["name"]), lv["perk_level"], item_link(db, lv["aoid"])))
        pr = lv["professions"]
        rows = [("Professions" if len(pr) != 1 else "Profession", "All" if len(pr) >= 14 else ", ".join(pr)), ("Level", lv["required_level"])]
        for n, a, u in _buff_lines(idx, lv["buffs"]):
            rows.append((n, "%+d%s" % (a, u)))
        for n, a in _res_lines(nl, lv["resistances"]):
            rows.append(("Resist " + n, "+%d%%" % a))
        if lv["action"]:
            rows.append(("Add action", raw(item_link(db, lv["action"]["id"]) + (" (scaling)" if lv["action"]["scaling"] else ""))))
        out.append(kv(rows))
    return "".join(out)


def run_perks(db, p):
    perks, idx, nl = load_perks(db)
    if p.get("perk"):
        want = p["perk"].strip().lower()
        pk = next((x for x in perks.values() if x["name"].lower() == want), None)
        if not pk:
            raise ValueError("Could not find any perk '%s'." % p["perk"])
        return dict(html="<h2>%s</h2>%s" % (E(pk["name"]), render_perk(db, pk, idx, nl)), data=pk["name"])
    need(p, "level")
    if not p.get("profession"):
        raise ValueError("Please choose a profession.")
    prof, level, search = p["profession"], p["level"], p.get("search")
    skill = None
    if search:
        ids = sorted(idx.match(search), key=idx.full_name)
        if not ids:
            raise ValueError("No skill %s found." % search)
        if len(ids) > 1:
            lis = "".join("<li><a href='%s'>%s</a></li>" % (E("/tool/perks?" + urllib.parse.urlencode(dict(level=level, profession=prof, search=idx.full_name(i)))), E(idx.full_name(i))) for i in ids)
            return dict(html="<p>Matches for %s (%d), choose a skill:</p><ul>%s</ul>" % (hl(search), len(ids), lis), data=[idx.full_name(i) for i in ids])
        skill = ids[0]
    sel = []
    for pk in perks.values():
        first = pk["levels"].get(1) or pk["levels"][min(pk["levels"])]
        if prof not in first["professions"] or first["required_level"] > level:
            continue
        lv = {k: dict(v) for k, v in pk["levels"].items() if prof in v["professions"] and v["required_level"] <= level}
        if skill is not None:
            for k in list(lv):
                v = lv[k]
                v["resistances"], v["action"] = {}, None
                v["buffs"] = {skill: v["buffs"][skill]} if v["buffs"].get(skill, 0) > 0 else {}
                if not v["buffs"]:
                    del lv[k]
        if lv:
            sel.append((pk, lv))
    groups = {"Profession Perks": [], "Group Perks": [], "General Perks": []}
    for pk, lv in sel:
        mn, mx = min(lv), max(lv)
        buffs, res, actions = {}, {}, []
        for v in lv.values():
            if v["action"]:
                actions.append((v["perk_level"], v["action"]))
            for k, a in v["buffs"].items():
                buffs[k] = buffs.get(k, 0) + a
            for k, a in v["resistances"].items():
                res[k] = res.get(k, 0) + a
        agg = dict(name=pk["name"], description=pk["description"], expansion=pk["expansion"], professions=lv[mn]["professions"],
                   max_level=mx, buffs=buffs, resistances=res, actions=actions)
        n = len(agg["professions"])
        groups["Profession Perks" if n == 1 else ("General Perks" if n > 13 else "Group Perks")].append(agg)
    total = sum(len(v) for v in groups.values())
    if not total:
        raise ValueError("Could not find any perks for level %d %s." % (level, prof))
    out = []
    for gname, lst in groups.items():
        if not lst:
            continue
        out.append("<h2>%s</h2>" % E(gname))
        for a in sorted(lst, key=lambda x: x["name"]):
            link = "/tool/perks?" + urllib.parse.urlencode(dict(perk=a["name"]))
            out.append("<h3>%s %d <span class='dim'>(%s) <a href='%s'>details</a></span></h3>" % (
                E(a["name"]), a["max_level"], "Alien Invasion" if a["expansion"] == "ai" else "Shadowlands", E(link)))
            if a["description"]:
                out.append("<p class='dim'>%s</p>" % "<br>".join(E(x) for x in a["description"].split("\n")))
            rows = [(n, "%+d%s" % (am, u)) for n, am, u in _buff_lines(idx, a["buffs"])]
            rows += [("Resist " + n, "%d%%" % am) for n, am in _res_lines(nl, a["resistances"])]
            for lvl, act in a["actions"]:
                rows.append(("Add action at level %d" % lvl, raw(item_link(db, act["id"]) + (" (scaling)" if act["scaling"] else ""))))
            if rows:
                out.append(kv(rows))
    skill_txt = " buffing %s" % idx.full_name(skill) if skill is not None else ""
    return dict(html="<p>Perks for a level %d %s%s (%d)</p>%s" % (level, E(prof), E(skill_txt), total, "".join(out)),
                data=dict(count=total))


# ------------------------------------------------------------------ registry ----
def F(name, label, typ="int", **kw):
    return dict(name=name, label=label, type=typ, **kw)


_ATK = F("attack", "Weapon attack time (s)", "float")
_RCH = F("recharge", "Weapon recharge time (s)", "float")

TOOLS = [
    dict(name="aggdef", title="Agg/Def slider", group=GROUP, bot="!aggdef",
         desc="Where to set the Agg/Def bar to wield a weapon at 1/1, and the init needed at each position.",
         fields=[_ATK, _RCH, F("init", "Your Melee/Ranged init"), *ITEM_FIELDS], run=run_aggdef),
    dict(name="aimshot", title="Aimed Shot", group=GROUP, bot="!aimshot",
         desc="Aimed Shot recharge, multiplier and the skill needed to cap it.",
         fields=[_ATK, _RCH, F("skill", "Your Aimed Shot skill"), *ITEM_FIELDS], run=run_aimshot),
    dict(name="brawl", title="Brawl", group=GROUP, bot="!brawl", desc="Brawl damage, stun chance and stun duration.",
         fields=[F("skill", "Your Brawl skill")], run=run_brawl),
    dict(name="burst", title="Burst", group=GROUP, bot="!burst", desc="Burst recharge and the Burst skill needed to cap it.",
         fields=[_ATK, _RCH, F("burst_delay", "Burst delay (Burst Cycle of the weapon)"), F("skill", "Your Burst skill"), *ITEM_FIELDS], run=run_burst),
    dict(name="dimach", title="Dimach", group=GROUP, bot="!dimach", desc="Dimach damage, healing and recharge per profession.",
         fields=[F("skill", "Your Dimach skill")], run=run_dimach),
    dict(name="fastattack", title="Fast Attack", group=GROUP, bot="!fastattack", desc="Fast Attack recharge and the skill needed to cap it.",
         fields=[_ATK, F("skill", "Your Fast Attack skill"), *ITEM_FIELDS], run=run_fastattack),
    dict(name="fling", title="Fling Shot", group=GROUP, bot="!fling", desc="Fling Shot recharge and the skill needed to cap it.",
         fields=[_ATK, F("skill", "Your Fling Shot skill"), *ITEM_FIELDS], run=run_fling),
    dict(name="fullauto", title="Full Auto", group=GROUP, bot="!fullauto", desc="Full Auto recharge, bullets and the skill needed to cap it.",
         fields=[_ATK, _RCH, F("fa_recharge", "Full Auto recharge value (FullAuto Cycle of the weapon)"), F("skill", "Your Full Auto skill"), *ITEM_FIELDS],
         run=run_fullauto),
    dict(name="mafist", title="Martial Arts fists", group=GROUP, bot="!mafist", desc="Fist speed and damage for Martial Artists, Shades and others.",
         fields=[F("skill", "Your Martial Arts skill")], run=run_mafist),
    dict(name="nanoinit", title="Nano init", group=GROUP, bot="!nanoinit", desc="Agg/Def bar and effective casting time for a nano.",
         fields=[F("cast", "Nano casting time (s)", "float"), F("init", "Your Nano Init skill")], run=run_nanoinit),
    dict(name="weapon", title="Weapon specials", group=GROUP, bot="!weapon",
         desc="Attack, recharge, Agg/Def positions and the skills needed to cap every special of a weapon.",
         fields=[F("item", "Weapon item id", "item"), F("ql", "QL (default: the item's highest)"), F("search", "...or search weapons by name", "text")],
         run=run_weapon),
    dict(name="perks", title="Perks", group="Character", bot="!perks",
         desc="Buff perks available to a profession at a level (optionally only those buffing a skill), or the details of one perk.",
         fields=[F("level", "Character level"), F("profession", "Profession", "select", options=[("", "(choose)")] + [(x, x) for x in PROFESSIONS]),
                 F("search", "Only perks buffing this skill (optional)", "text"), F("perk", "...or show the details of this perk (exact name)", "text")],
         run=run_perks),
    dict(name="trickle", title="Trickle-down", group="Character", bot="!trickle",
         desc="How many skill points you gain by raising abilities, or how much of each ability one skill point needs.",
         fields=[F("all", "Add to all six abilities"), F("agi", "Agility"), F("int", "Intelligence"), F("psy", "Psychic"), F("sta", "Stamina"),
                 F("str", "Strength"), F("sen", "Sense"), F("skill", "...or look up a skill (ability points per skill point)", "text")],
         run=run_trickle),
    dict(name="whatlocks", title="Skill locks", group="Items & loot", bot="!whatlocks",
         desc="Skills that items can lock, and which items lock a given skill and for how long.",
         fields=[F("skill", "Skill (empty: list all lockable skills)", "text")], run=run_whatlocks),
]
