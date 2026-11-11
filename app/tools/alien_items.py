# SPDX-License-Identifier: GPL-3.0-only
#
# Alien armour / bio-material / Ofab / Arul Saba tradeskill lookups, breakpoints, "what buffs", Grid Armor and
# nano browsing tools for the offline archive.
#
# Ported from Nadybot (https://github.com/Nadybot/Nadybot, branch nadybot7, GPL-3.0), modules ALIEN_MODULE
# (aiarmor, aigen, bio, bioinfo, ofabarmor, ofabweapons, leprocs), BESTQL_MODULE (bestql), ITEMS_MODULE
# (whatbuffs, whatbuffsfroob, gridarmor, gridarmorfroob), NANO_MODULE (nano, nanoloc, nanolines, bestnanos and
# their froob variants) and RECIPE_MODULE (arulsaba). Original authors: Blackruby, Mdkdoc420, Wolfbiter,
# Gatester, Marebone, Nadyita, Tyrence, Healnjoo and the other Nadybot / Budabot contributors.
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed WITHOUT ANY WARRANTY.
"""Alien armour, bio-materials, Ofab, Arul Saba, breakpoints, buff search, Grid Armor and nano lookups."""
import html
import math
import re
import urllib.parse

E = html.escape


# ------------------------------------------------------------------------------------------ helpers ----
def _rnd(x):
    """PHP round(): half away from zero"""
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def _toint(v, default=None):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _url(tool, **kw):
    q = urllib.parse.urlencode({k: v for k, v in kw.items() if v not in (None, "")})
    return "/tool/%s%s" % (tool, "?" + q if q else "")


def _tlink(tool, text, **kw):
    return "<a href='%s'>%s</a>" % (E(_url(tool, **kw)), E(str(text)))


def _ilink(iid, name, ql=None):
    return "<a class='item' href='/item/%d%s'>%s</a>" % (int(iid), "?ql=%d" % ql if ql else "", E(name))


def _table(head, rows, cls=""):
    """head: list of header strings (escaped here); rows: list of lists of ready HTML cells"""
    h = "".join("<th>%s</th>" % E(c) for c in head)
    b = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in rows)
    return "<div class='scroll'><table%s><tr>%s</tr>%s</table></div>" % (" class='%s'" % cls if cls else "", h, b)


def _kv(rows):
    return "<table class='kv'>%s</table>" % "".join("<tr><th>%s</th><td>%s</td></tr>" % (E(k), v) for k, v in rows)


def _hl(x):
    return "<strong>%s</strong>" % E(str(x))


_ITEM_SQL = ("SELECT lowid, highid, lowql, highql, name, froob_friendly, slot, flags, in_game, type, properties "
             "FROM ds_items_ql ")


def _item(r):
    return dict(lowid=_toint(r[0], 0), highid=_toint(r[1], 0), lowql=_toint(r[2], 0), highql=_toint(r[3], 0), name=r[4],
                froob=_toint(r[5], 0) == 1, slot=_toint(r[6], 0) & 0xFFFFFFFF, flags=_toint(r[7], 0) & 0xFFFFFFFF,
                in_game=_toint(r[8], 0) == 1, type=r[9], properties=_toint(r[10], 0) & 0xFFFFFFFF)


def find_item(db, name, ql=None):
    """ItemsController::findByName: highest-QL entry with that name that contains the QL"""
    rows = [_item(r) for r in db.execute(_ITEM_SQL + "WHERE name = ?", (name,))]
    if ql is not None:
        rows = [x for x in rows if x["lowql"] <= ql <= x["highql"]]
    rows.sort(key=lambda x: (-x["highql"], -x["highid"]))
    return rows[0] if rows else None


def find_id(db, iid):
    r = db.execute(_ITEM_SQL + "WHERE lowid = ? OR highid = ? LIMIT 1", (str(iid), str(iid))).fetchone()
    return _item(r) if r else None


def _ref(db, name, ql=None, note=None, show_ql=False, plus=False):
    """An item mentioned in a tradeskill step (name looked up at the QL, like ItemsController::getItemAndIcon)"""
    row = find_item(db, name, ql)
    r = dict(name=name, ql=ql, id=row["lowid"] if row else None, note=note, show_ql=show_ql, plus=plus,
             link_ql=ql if ql is not None else (row["highql"] if row else None))
    return r


def _ref_html(r):
    s = _ilink(r["id"], r["name"], r["link_ql"]) if r["id"] else E(r["name"])
    if r["show_ql"] and r["ql"] is not None:
        s += " QL%d%s" % (r["ql"], "+" if r["plus"] else "")
    if r["note"]:
        s += " <span class='dim'>(%s)</span>" % E(r["note"])
    return s


def _ref_data(r):
    return {k: r[k] for k in ("name", "id", "ql", "note")}


# ------------------------------------------------------------------------------------ professions ----
# (long name, short name as Nadybot's Profession::short())
PROFESSIONS = [("Adventurer", "Adv"), ("Agent", "Agent"), ("Bureaucrat", "Crat"), ("Doctor", "Doc"), ("Enforcer", "Enf"),
               ("Engineer", "Engi"), ("Fixer", "Fix"), ("Keeper", "Keep"), ("Martial Artist", "MA"),
               ("Meta-Physicist", "MP"), ("Nano-Technician", "NT"), ("Shade", "Shade"), ("Soldier", "Sol"),
               ("Trader", "Tra")]
_PROF_ALIAS = {"eng": "Engineer", "fixer": "Fixer", "keeper": "Keeper", "trader": "Trader", "bureau": "Bureaucrat",
               "metaphysicist": "Meta-Physicist", "metaphysician": "Meta-Physicist", "nanotechnician": "Nano-Technician",
               "nanotech": "Nano-Technician", "martialartist": "Martial Artist", "adventure": "Adventurer",
               "doctor": "Doctor", "doc": "Doctor", "sol": "Soldier", "meta": "Meta-Physicist", "nano": "Nano-Technician"}


def prof_long(text):
    """Profession::tryFromName: long name, short name or unique prefix; None if unknown"""
    t = re.sub(r"[\s\-_.]", "", str(text)).lower()
    if not t:
        return None
    for lg, sh in PROFESSIONS:
        if t in (re.sub(r"[\s\-_.]", "", lg).lower(), sh.lower()):
            return lg
    if t in _PROF_ALIAS:
        return _PROF_ALIAS[t]
    hits = [lg for lg, _ in PROFESSIONS if re.sub(r"[\s\-_.]", "", lg).lower().startswith(t)]
    return hits[0] if len(hits) == 1 else None


def prof_short(lg):
    return dict(PROFESSIONS).get(lg, lg)


# ----------------------------------------------------------------------------------------- skills ----
# Skills for which a negative amount is the good one (Nadybot Skill::negativeIsGood, reconstructed)
NEGATIVE_IS_GOOD = {318, 382, 383}
SKILL_LOCK, ADD_NANO_COST = 382, 318


class Skills:
    """ds_skills + ds_skill_alias: names, aliases, units and Skill::getMatching()"""

    def __init__(self, db):
        self.name, self.unit_, self.alias = {}, {}, {}
        for r in db.execute("SELECT id, name, unit FROM ds_skills"):
            i = _toint(r[0])
            self.name[i] = r[1]
            self.unit_[i] = r[2] or ""
        for r in db.execute("SELECT id, name FROM ds_skill_alias"):
            i = _toint(r[0])
            if r[1] not in self.alias.setdefault(i, []):
                self.alias[i].append(r[1])

    def full(self, i):
        """the descriptive name: the longest of the name and its aliases (ties: the name, then the first alias)"""
        c = [x for x in self.cands(i) if x]
        return max(c, key=len) if c else "Skill %d" % i

    def unit(self, i):
        return self.unit_.get(i, "")

    def cands(self, i):
        return [self.name.get(i, "")] + self.alias.get(i, [])

    def match(self, search):
        """ids matching a name / alias / id; an exact name or alias wins over substring matches"""
        s = str(search).strip()
        if s.isdigit() and int(s) in self.name:
            return [int(s)]
        low = s.lower()
        exact = [i for i in self.name if any(c.lower() == low for c in self.cands(i))]
        if exact:
            return sorted(exact, key=lambda i: self.full(i).lower())
        toks = low.split()
        if not toks:
            return []
        hit = [i for i in self.name if any(all(t in c.lower() for t in toks) for c in self.cands(i))]
        return sorted(hit, key=lambda i: self.full(i).lower())


# ---------------------------------------------------------------------------------------- aiarmor ----
ARMOR_TYPES = ["strong", "supple", "enduring", "observant", "arithmetic", "spiritual"]
COMBINED = {  # type: (result, source armour, source type, target armour, target type)
    "cc": ("Combined Commando's Jacket", "Strong Body Armor", "strong", "Supple Body Armor", "supple"),
    "cm": ("Combined Mercenary's Jacket", "Strong Body Armor", "strong", "Enduring Body Armor", "enduring"),
    "co": ("Combined Officer's Jacket", "Spiritual Body Armor", "spiritual", "Arithmetic Body Armor", "arithmetic"),
    "cp": ("Combined Paramedic's Jacket", "Spiritual Body Armor", "spiritual", "Enduring Body Armor", "enduring"),
    "cs": ("Combined Scout's Jacket", "Observant Body Armor", "observant", "Arithmetic Body Armor", "arithmetic"),
    "css": ("Combined Sharpshooter's Jacket", "Observant Body Armor", "observant", "Supple Body Armor", "supple"),
}
COMBINED["ss"] = COMBINED["css"]
AIARMOR_OPTIONS = [("strong", "Strong"), ("supple", "Supple"), ("enduring", "Enduring"), ("observant", "Observant"),
                   ("arithmetic", "Arithmetic"), ("spiritual", "Spiritual"), ("cc", "Combined Commando's"),
                   ("cm", "Combined Mercenary's"), ("co", "Combined Officer's"), ("cp", "Combined Paramedic's"),
                   ("cs", "Combined Scout's"), ("css", "Combined Sharpshooter's")]


def _step_html(n, step):
    def grp(alts):
        return " <em>or</em> ".join(_ref_html(a) for a in alts)
    parts = [grp(g) for g in step["inputs"]]
    out = "<h3>Step %d</h3><p>%s<br>= %s</p>" % (n, " <br>+ ".join(parts), grp(step["outputs"]))
    if step.get("skills"):
        out += "<p class='dim'>Required skills:</p><ul>%s</ul>" % "".join("<li>%s</li>" % E(s) for s in step["skills"])
    return out


def aiarmor_steps(db, atype, ql):
    miscql = int(math.floor(ql * 0.8))
    R = lambda *a, **k: _ref(db, *a, **k)
    ceil = lambda x: int(math.ceil(x))
    mutated = lambda: R("Mutated Kyr'Ozch Bio-Material", ql, show_ql=True)
    pristine = lambda: R("Pristine Kyr'Ozch Bio-Material", ql, show_ql=True)
    steps = [
        dict(inputs=[[R("Kyr'Ozch Viralbots", miscql, "Drops from Alien City Generals", True, True)],
                     [R("Kyr'Ozch Atomic Re-Structuralizing Tool", 100, "Drops from every Alien")]],
             outputs=[R("Memory-Wiped Kyr'Ozch Viralbots", miscql)],
             skills=["%d Computer Literacy" % ceil(miscql * 4.5), "%d Nano Programming" % ceil(miscql * 4.5)]),
        dict(inputs=[[R("Nano Programming Interface", 1, "Can be bought in General Shops")],
                     [R("Memory-Wiped Kyr'Ozch Viralbots", miscql)]],
             outputs=[R("Formatted Kyr'Ozch Viralbots", miscql)],
             skills=["%d Computer Literacy" % ceil(miscql * 4.5), "%d Nano Programming" % ceil(miscql * 6)]),
        dict(inputs=[[R("Kyr'Ozch Structural Analyzer", 100)],
                     [R("Solid Clump of Kyr'Ozch Bio-Material", ql, "Drops from every Alien", True)]],
             outputs=[mutated(), pristine()],
             skills=["%d Chemistry (Both require the same amount)" % ceil(ql * 4.5)]),
        dict(inputs=[[mutated(), pristine()], [R("Uncle Bazzit's Generic Nano-Solvent", 100, "Can be bought in Bazzit Shop in MMD")]],
             outputs=[R("Generic Kyr'Ozch DNA-Soup", ql)],
             skills=["%d Chemistry (for Pristine)" % ceil(ql * 4.5), "%d Chemistry (for Mutated)" % ceil(ql * 7)]),
        dict(inputs=[[R("Generic Kyr'Ozch DNA-Soup", ql)], [R("Essential Human DNA", 100, "Can be bought in Bazzit Shop in MMD")]],
             outputs=[R("DNA Cocktail", ql)], skills=["%d Pharma Tech" % ceil(ql * 6)]),
        dict(inputs=[[R("Formatted Kyr'Ozch Viralbots", miscql)], [R("DNA Cocktail", ql)]],
             outputs=[R("Kyr'Ozch Formatted Viralbot Solution", ql)], skills=["%d Pharma Tech" % ceil(ql * 6)]),
        dict(inputs=[[R("Kyr'Ozch Formatted Viralbot Solution", ql)],
                     [R("Basic Fashion Vest", 1, "Can be obtained by the Basic Armor Quest")]],
             outputs=[R("Formatted Viralbot Vest", ql)], skills=[]),
    ]
    cap = atype.capitalize()
    vbql = int(math.floor(ql * 0.8))
    steps.append(dict(inputs=[[R("%s Lead Viralbots" % cap, vbql, "Rare Drop off Alien City Generals", True)],
                              [R("Formatted Viralbot Vest", ql)]],
                      outputs=[R("%s Body Armor" % cap, ql, show_ql=True)],
                      skills=["%d Psychology" % int(math.floor(ql * 6))]))
    return steps


def run_aiarmor(db, p):
    t = (p.get("type") or "strong").strip().lower()
    ql = p.get("ql") if p.get("ql") is not None else 300
    if not 1 <= ql <= 300:
        raise ValueError("The QL has to be between 1 and 300.")
    if t in ARMOR_TYPES:
        steps = aiarmor_steps(db, t, ql)
        h = ("<p class='dim'>Note: all tradeskill processes are based on the lowest QL items usable.</p>"
             "<h2>%s armour, QL %d</h2>"
             "<p>You need: Kyr'Ozch Viralbots (QL%d+), Kyr'Ozch Atomic Re-Structuralizing Tool, Solid Clump of Kyr'Ozch "
             "Biomaterial (QL%d) and the matching Lead Viralbots (QL%d+).</p>" % (
                 E(t.capitalize()), ql, int(math.floor(ql * 0.8)), ql, int(math.floor(ql * 0.8))))
        h += "".join(_step_html(i + 1, s) for i, s in enumerate(steps))
        data = dict(type=t, ql=ql, steps=[dict(inputs=[[_ref_data(a) for a in g] for g in s["inputs"]],
                                                outputs=[_ref_data(a) for a in s["outputs"]], skills=s["skills"]) for s in steps])
        return dict(html=h, data=data)
    if t in COMBINED:
        result, src, srct, tgt, tgtt = COMBINED[t]
        sql_ = int(math.floor(ql * 0.8))
        rr, rs, rt = _ref(db, result, ql, show_ql=True), _ref(db, src, sql_, show_ql=True), _ref(db, tgt, ql, show_ql=True)
        h = ("<h2>%s, QL %d</h2><h3>Result</h3><p>%s</p><h3>Source armour</h3><p>%s (%s)</p><h3>Target armour</h3><p>%s (%s)</p>" % (
            E(result), ql, _ref_html(rr), _ref_html(rs), _tlink("aiarmor", "tradeskill process for this item", type=srct, ql=sql_),
            _ref_html(rt), _tlink("aiarmor", "tradeskill process for this item", type=tgtt, ql=ql)))
        return dict(html=h, data=dict(type=t, ql=ql, result=_ref_data(rr), source=_ref_data(rs), target=_ref_data(rt)))
    raise ValueError("Unknown armour type. Use one of: " + ", ".join(k for k, _ in AIARMOR_OPTIONS) + ".")


# ------------------------------------------------------------------------------------------ aigen ----
GENERALS = {
    "ankari": ("Ankari", "Low Evade/Dodge, Low AR, Casts Viral/Virral nukes", "Arithmetic Lead Viralbots", "Nanoskill / Tradeskill", [1, 2, 48]),
    "ilari": ("Ilari", "Low Evade/Dodge", "Spiritual Lead Viralbots", "Nanocost / Nanopool / Max Nano", [992, 880]),
    "rimah": ("Rimah", "Low Evade/Dodge", "Observant Lead Viralbots", "Init / Evades", [112, 240]),
    "jaax": ("Jaax", "High Evade, Low Dodge", "Strong Lead Viralbots", "Melee / Spec Melee / Add All Def / Add Damage", [3, 4]),
    "xoch": ("Xoch", "High Evade/Dodge, Casts Ilari Biorejuvenation heals", "Enduring Lead Viralbots", "Max Health / Body Dev", [5, 12]),
    "cha": ("Cha", "High Evade/NR, Low Dodge", "Supple Lead Viralbots", "Ranged / Spec Ranged / Add All Off", [13, 76]),
}


def run_aigen(db, p):
    g = GENERALS.get((p.get("general") or "").strip().lower())
    if not g:
        raise ValueError("Choose one of: " + ", ".join(v[0] for v in GENERALS.values()) + ".")
    name, desc, vb, vbdesc, types = g
    parts = ["<p>%s</p>" % E(desc), "<p>%s<br><span class='dim'>(%s)</span></p>" % (_ref_html(_ref(db, vb)), E(vbdesc))]
    for t in types:
        parts.append("<p>%s <span class='dim'>(%s)</span></p>" % (
            _ref_html(_ref(db, "Kyr'Ozch Bio-Material - Type %d" % t)), _tlink("bioinfo", "bio type %d" % t, type=t)))
    return dict(html="<h2>General %s</h2>%s" % (E(name), "".join(parts)),
                data=dict(general=name, description=desc, viralbots=vb, drops_for=vbdesc, bio_types=types))


# -------------------------------------------------------------------------------------------- bio ----
LE_ARMOR_TYPES = [64, 295, 468, 935]
LE_WEAPON_TYPES = [18, 34, 687, 812]
AI_ARMOR_TYPES = ["mutated", "pristine"]
AI_WEAPON_TYPES = [1, 2, 3, 4, 5, 12, 13, 48, 76, 112, 240, 880, 992]
# clump item id (low / high id) -> (bioinfo argument, name)
_BIO_IDS = {}
for _ids, _info, _name in (
        ((247707, 247708), "1", "Type 1"), ((247709, 247710), "2", "Type 2"), ((247717, 247718), "3", "Type 3"),
        ((247711, 247712), "4", "Type 4"), ((247713, 247714), "5", "Type 5"), ((247715, 247716), "12", "Type 12"),
        ((247719, 247720), "13", "Type 13"), ((288699, 288700), "48", "Type 48"), ((247697, 247698), "76", "Type 76"),
        ((247699, 247700), "112", "Type 112"), ((247701, 247702), "240", "Type 240"), ((247703, 247704), "880", "Type 880"),
        ((247705, 247706), "992", "Type 992")):
    for _i in _ids:
        _BIO_IDS[_i] = (_info, "Kyr'Ozch Bio-Material - " + _name)
for _ids, _info, _name in (((247102, 247103), "pristine", "Pristine Kyr'Ozch Bio-Material"),
                           ((247104, 247105), "mutated", "Mutated Kyr'Ozch Bio-Material"),
                           ((247764, 254804), "serum", "Kyr'Ozch Viral Serum")):
    for _i in _ids:
        _BIO_IDS[_i] = (_info, _name)


def _bio_item(db, name, ql):
    r = find_item(db, name, ql)
    if r is None:
        raise ValueError("Cannot find the expected bio material %r in the item database." % name)
    return "<p>%s <span class='dim'>QL %d</span></p>" % (_ilink(r["lowid"], r["name"], ql), ql)


def _ofab_armor_bio(db, ql, typ):
    h = _bio_item(db, "Kyr'Ozch Bio-Material - Type %d" % typ, ql)
    profs = [r[0] for r in db.execute("SELECT profession FROM ds_ofab_armor_types WHERE CAST(type AS INTEGER) = ? ORDER BY profession", (typ,))]
    h += "<p>Upgrades Ofab armour for:</p><ul>%s</ul>" % "".join(
        "<li>%s</li>" % _tlink("ofabarmor", pr, profession=prof_short(pr)) for pr in profs)
    return h, dict(type=typ, ql=ql, upgrades_armor_for=profs)


def _ofab_weapon_bio(db, ql, typ):
    h = _bio_item(db, "Kyr'Ozch Bio-Material - Type %d" % typ, ql)
    ws = [r[0] for r in db.execute("SELECT name FROM ds_ofab_weapons WHERE CAST(type AS INTEGER) = ? ORDER BY name", (typ,))]
    h += "<p>Upgrades Ofab weapons:</p><ul>%s</ul>" % "".join(
        "<li>%s</li>" % _tlink("ofabweapons", "Ofab %s Mk 1" % w, weapon=w) for w in ws)
    return h, dict(type=typ, ql=ql, upgrades_weapons=ws)


def _alien_weapon_bio(db, ql, typ):
    h = _bio_item(db, "Kyr'Ozch Bio-Material - Type %d" % typ, ql)
    maxai = int(math.floor(ql / 0.9))  # a QL 271+ bio must not combine above QL 300
    if maxai > 300 or maxai < 1:
        maxai = 300
    ee_cl = int(math.floor(ql * 4.5))
    sp = db.execute("SELECT specials FROM ds_alien_weapon_specials WHERE CAST(type AS INTEGER) = ? LIMIT 1", (typ,)).fetchone()
    specials = sp[0] if sp else ""
    h += "<p>It will take %s EE &amp; CL (<em>4.5 * QL</em>) to analyze the Bio-Material.</p>" % _hl(ee_cl)
    h += "<p>Adds %s to:</p><ul>" % _hl(specials)
    names = [r[0] for r in db.execute("SELECT name FROM ds_alien_weapons WHERE CAST(type AS INTEGER) = ?", (typ,))]
    for n in names:
        r = find_item(db, n, maxai)
        if r is None:
            raise ValueError("Cannot find the expected alien weapon %r in the item database." % n)
        h += "<li>%s</li>" % _ilink(r["lowid"], r["name"], maxai)
    h += "</ul>"
    req = int(math.floor(maxai * 6))
    h += "<p>QL %s is the highest weapon this type will combine into.</p>" % _hl(maxai)
    if maxai != 300:
        h += "<p>Note: <strong>the weapon can bump several QLs.</strong></p>"
    h += ("<p>It will take %s ME &amp; WS (<em>6 * QL</em>) to combine with a QL %s Kyr'ozch weapon.</p>"
          "<p class='dim'>Tradeskilling info added by Mdkdoc420 (RK2)</p>" % (_hl(req), _hl(maxai)))
    return h, dict(type=typ, ql=ql, specials=specials, weapons=names, max_weapon_ql=maxai, analyze_ee_cl=ee_cl, combine_me_ws=req)


def _alien_armor_bio(db, ql, typ):
    minql = max(1, int(math.floor(ql * 0.8)))
    maxql = int(math.floor(ql / 0.8)) if 1 <= ql <= 240 else 300
    req_cl = int(math.floor(minql * 4.5))
    pharma = int(math.floor(ql * 6))
    nanoprog = int(math.floor(minql * 6))
    psych = int(math.floor(ql * 6))
    max_psy = int(math.floor(maxql * 6))
    ee_cl = int(math.floor(ql * 4.5))
    if typ == "mutated":
        name, chem, chem_msg, extra = "Mutated Kyr'Ozch Bio-Material", int(math.floor(ql * 7)), "7 * QL", ""
    else:
        name, chem, chem_msg, extra = ("Pristine Kyr'Ozch Bio-Material", int(math.floor(ql * 4.5)), "4.5 * QL",
                                       " (less tradeskill requirements than mutated)")
    h = _bio_item(db, name, ql)
    h += "<p>It will take %s EE &amp; CL (<em>4.5 * QL</em>) to analyze the Bio-Material.</p>" % _hl(ee_cl)
    h += "<p>Used to build Alien Armor%s.</p>" % E(extra)
    h += ("<p>The following tradeskill amounts are required to make QL %d strong / arithmetic / enduring / spiritual / "
          "supple / observant armour:</p>" % ql)
    h += _kv([("Computer Literacy", "%s (<em>4.5 * QL</em>)" % _hl(req_cl)), ("Chemistry", "%s (<em>%s</em>)" % (_hl(chem), E(chem_msg))),
              ("Nano Programming", "%s (<em>6 * QL</em>)" % _hl(nanoprog)), ("Pharma Tech", "%s (<em>6 * QL</em>)" % _hl(pharma)),
              ("Psychology", "%s (<em>6 * QL</em>)" % _hl(psych))])
    h += "<p class='dim'>Note: tradeskill requirements are based off the lowest QL items needed throughout the entire process.</p>"
    h += ("<h3>For Supple, Arithmetic or Enduring</h3><p>When completed, the armour piece can have as low as QL %d combined into "
          "it, depending on available tradeskill options. It does not change QLs, therefore it takes %s Psychology for "
          "available combinations.</p>" % (minql, _hl(psych)))
    h += ("<h3>For Spiritual, Strong or Observant</h3><p>When completed, the armour piece can combine up to QL %d, depending on "
          "available tradeskill options. It changes QL depending on the target's QL. The maximum combination is QL %d "
          "(%d Psychology required for this combination).</p>" % (maxql, maxql, max_psy))
    h += "<p class='dim'>Tradeskilling info added by Mdkdoc420 (RK2)</p>"
    return h, dict(type=typ, ql=ql, min_ql=minql, max_ql=maxql, computer_literacy=req_cl, chemistry=chem, nano_programming=nanoprog,
                   pharma_tech=pharma, psychology=psych, analyze_ee_cl=ee_cl)


def _serum_bio(db, ql):
    pharma, chem_me, ee, cl, ee_cl = (int(math.floor(ql * 3.5)), int(math.floor(ql * 4)), int(math.floor(ql * 4.5)),
                                      int(math.floor(ql * 5)), int(math.floor(ql * 4.5)))
    h = _bio_item(db, "Kyr'Ozch Viral Serum", ql)
    h += "<p>It will take %s EE &amp; CL (<em>4.5 * QL</em>) to analyze the Bio-Material.</p>" % _hl(ee_cl)
    h += "<p>Used to build city buildings. The required skills throughout the process of making a building:</p>"
    h += _kv([("Quantum FT", "%s (<em>static</em>)" % _hl(400)),
              ("Pharma Tech", "%s (<em>3.5 * QL</em>) 400 is the minimum requirement" % _hl(max(pharma, 400))),
              ("Chemistry", "%s (<em>4 * QL</em>) 400 is the minimum requirement" % _hl(max(chem_me, 400))),
              ("Mechanical Engineering", "%s (<em>4 * QL</em>)" % _hl(chem_me)),
              ("Electrical Engineering", "%s (<em>4.5 * QL</em>)" % _hl(ee)),
              ("Comp. Literacy", "%s (<em>5 * QL</em>)" % _hl(cl))])
    h += "<p class='dim'>Tradeskilling info added by Mdkdoc420 (RK2)</p>"
    return h, dict(type="serum", ql=ql, pharma_tech=max(pharma, 400), chemistry=max(chem_me, 400), mech_eng=chem_me, elec_eng=ee,
                   comp_lit=cl, quantum_ft=400, analyze_ee_cl=ee_cl)


def _bioinfo(db, bio, ql):
    ql = min(300, max(1, ql))
    bio = str(bio).strip().lower()
    if bio.isdigit():
        n = int(bio)
        if n in LE_ARMOR_TYPES:
            return _ofab_armor_bio(db, ql, n)
        if n in LE_WEAPON_TYPES:
            return _ofab_weapon_bio(db, ql, n)
        if n in AI_WEAPON_TYPES:
            return _alien_weapon_bio(db, ql, n)
    elif bio in AI_ARMOR_TYPES:
        return _alien_armor_bio(db, ql, bio)
    elif bio == "serum":
        return _serum_bio(db, ql)
    return "<p class='verdict'>Unknown Bio-Material.</p>", dict(error="unknown bio material", type=bio)


def _bio_type_list():
    def grp(title, types, key):
        return "<h3>%s</h3><p>%s</p>" % (E(title), " &middot; ".join(_tlink("bioinfo", t, type=t) for t in types))
    h = (grp("OFAB armour types", LE_ARMOR_TYPES, 0) + grp("OFAB weapon types", LE_WEAPON_TYPES, 0)
         + grp("AI armour types", AI_ARMOR_TYPES + ["serum"], 0) + grp("AI weapon types", AI_WEAPON_TYPES, 0))
    return "<h2>Bio-material types</h2>" + h


def run_bioinfo(db, p):
    t = (p.get("type") or "list").strip().lower()
    ql = p.get("ql") if p.get("ql") is not None else 300
    if t in ("", "list"):
        return dict(html=_bio_type_list(), data=dict(ofab_armor=LE_ARMOR_TYPES, ofab_weapons=LE_WEAPON_TYPES,
                                                    ai_armor=AI_ARMOR_TYPES, ai_weapons=AI_WEAPON_TYPES))
    h, d = _bioinfo(db, t, ql)
    return dict(html="<h2>Bio-material: %s, QL %d</h2>%s" % (E(t), min(300, max(1, ql)), h), data=d)


def run_bio(db, p):
    raw = (p.get("item") or "").replace(",", " ").split()
    if not raw:
        raise ValueError("Enter the item id of the Solid Clump of Kyr'Ozch Bio-Material (or several, separated by spaces).")
    ql = p.get("ql") if p.get("ql") is not None else 300
    found, blob = [], ""
    for tok in raw:
        iid = _toint(tok)
        if iid is None:
            raise ValueError("%r is not an item id." % tok)
        if iid in _BIO_IDS:
            info, name = _BIO_IDS[iid]
        else:
            it = find_id(db, iid)
            if it is not None and it["name"] == "Solid Clump of Kyr'Ozch Bio-Material":
                info, name = "", "Unknown Bio-Material"
            else:
                raise ValueError("%s is not bio material." % (it["name"] if it else "Item %d" % iid))
        found.append((iid, info, name))
        link = _tlink("bioinfo", name, type=info, ql=ql) if info else E(name)
        blob += "<li>%s (QL %d) <span class='dim'>item %d</span></li>" % (link, ql, iid)
    if len(found) == 1 and found[0][1]:
        h, d = _bioinfo(db, found[0][1], ql)
        return dict(html="<h2>%s (QL %d)</h2>%s" % (E(found[0][2]), min(300, max(1, ql)), h), data=dict(d, identified=found[0][2]))
    return dict(html="<h2>Identified bio-materials</h2><ul>%s</ul>" % blob,
                data=dict(identified=[dict(item=i, type=t, name=n) for i, t, n in found]))


# ------------------------------------------------------------------------------- ofab, leprocs ----
def _ofab_qls(db, table):
    return sorted({_toint(r[0]) for r in db.execute("SELECT ql FROM %s" % table)})


def run_ofabarmor(db, p):
    qls = _ofab_qls(db, "ds_ofab_armor_cost")
    if not p.get("profession"):
        rows = db.execute("SELECT type, profession FROM ds_ofab_armor_types ORDER BY profession").fetchall()
        h = "<h2>Ofab armour bio-material types</h2>"
        h += _table(["Profession", "Bio type", "QL"], [[E(r[1]), _tlink("bioinfo", "Type " + r[0], type=r[0]),
                    " ".join("[%s]" % _tlink("ofabarmor", q, profession=prof_short(r[1]), ql=q) for q in qls)] for r in rows])
        return dict(html=h, data=[dict(profession=r[1], type=_toint(r[0])) for r in rows])
    prof = prof_long(p["profession"])
    if not prof:
        raise ValueError("Unknown profession %r." % p["profession"])
    ql = p.get("ql") if p.get("ql") is not None else 300
    t = db.execute("SELECT type FROM ds_ofab_armor_types WHERE profession = ?", (prof,)).fetchone()
    armors = db.execute("SELECT name, slot, lowid, highid, upgrade FROM ds_ofab_armor WHERE profession = ? "
                        "ORDER BY CAST(upgrade AS INTEGER), name", (prof,)).fetchall()
    cost = {r[0]: _toint(r[2]) for r in db.execute("SELECT slot, ql, vp FROM ds_ofab_armor_cost WHERE CAST(ql AS INTEGER) = ?", (ql,))}
    if not armors or not cost:
        raise ValueError("Could not find any OFAB armor for %s in QL %d." % (prof, ql))
    typ = _toint(t[0]) if t else None
    h = "<h2>%s Ofab armour (QL %d)</h2>" % (E(prof), ql)
    h += "<p>Upgrade with %s (minimum QL %d)</p>" % (_tlink("bioinfo", "Kyr'Ozch Bio-Material - Type %s" % typ, type=typ), _rnd(.8 * ql))
    h += "<p>%s</p>" % " ".join("[<strong>%d</strong>]" % q if q == ql else "[%s]" % _tlink("ofabarmor", q, profession=prof_short(prof), ql=q) for q in qls)
    cur, full, data = None, 0, []
    for name, slot, lowid, highid, upg in armors:
        if slot not in cost:
            continue
        upg, vp = _toint(upg, 0), cost[slot]
        if upg != cur:
            cur = upg
            h += "<h3>%s</h3>" % ("No upgrades" if upg == 0 else "1 upgrade" if upg == 1 else "%d upgrades" % upg)
        line = _ilink(_toint(lowid), name, ql)
        if upg in (0, 3):
            line += " <span class='dim'>(%d VP)</span>" % vp
            full += vp
        h += "<p>%s</p>" % line
        data.append(dict(name=name, slot=slot, id=_toint(lowid), upgrade=upg, vp=vp))
    h += "<p>Cost for full set: %s VP</p>" % _hl(full)
    return dict(html=h, data=dict(profession=prof, ql=ql, bio_type=typ, min_bio_ql=_rnd(.8 * ql), full_set_vp=full, items=data))


def run_ofabweapons(db, p):
    qls = _ofab_qls(db, "ds_ofab_weapons_cost")
    if not p.get("weapon"):
        rows = db.execute("SELECT name, type FROM ds_ofab_weapons ORDER BY name").fetchall()
        h = "<h2>Ofab weapons</h2>" + _table(["Weapon", "Bio type", "QL"], [[E(r[0]), _tlink("bioinfo", "Type " + r[1], type=r[1]),
                " ".join("[%s]" % _tlink("ofabweapons", q, weapon=r[0], ql=q) for q in qls)] for r in rows])
        return dict(html=h, data=[dict(weapon=r[0], type=_toint(r[1])) for r in rows])
    w = p["weapon"].strip()
    ql = p.get("ql") if p.get("ql") is not None else 300
    row = db.execute("SELECT name, type FROM ds_ofab_weapons WHERE lower(name) = lower(?)", (w,)).fetchone()
    vp = db.execute("SELECT vp FROM ds_ofab_weapons_cost WHERE CAST(ql AS INTEGER) = ?", (ql,)).fetchone()
    if not row or not vp:
        raise ValueError("Could not find any OFAB weapon %s in QL %d." % (w, ql))
    name, typ = row[0], _toint(row[1])
    vp = _toint(vp[0])
    h = "<h2>Ofab %s (QL %d)</h2>" % (E(name), ql)
    h += "<p>Upgrade with %s (minimum QL %d)</p>" % (_tlink("bioinfo", "Kyr'Ozch Bio-Material - Type %d" % typ, type=typ, ql=_rnd(.8 * ql)), _rnd(.8 * ql))
    h += "<p>%s</p><h3>Upgrades</h3>" % " ".join("[<strong>%d</strong>]" % q if q == ql else "[%s]" % _tlink("ofabweapons", q, weapon=name, ql=q) for q in qls)
    data = []
    for i in range(1, 7):
        it = find_item(db, "Ofab %s Mk %d" % (name, i), ql)
        if it:
            h += "<p>%s%s</p>" % (_ilink(it["lowid"], it["name"], ql), " <span class='dim'>(%d VP)</span>" % vp if i == 1 else "")
            data.append(dict(name=it["name"], id=it["lowid"], mark=i))
    return dict(html=h, data=dict(weapon=name, ql=ql, bio_type=typ, vp=vp, items=data))


def run_leprocs(db, p):
    if not p.get("profession"):
        profs = [r[0] for r in db.execute("SELECT DISTINCT profession FROM ds_le_procs ORDER BY profession")]
        return dict(html="<h2>LE procs: choose a profession</h2><ul>%s</ul>" % "".join(
            "<li>%s</li>" % _tlink("leprocs", x, profession=x) for x in profs), data=profs)
    prof = prof_long(p["profession"]) or p["profession"]
    rows = db.execute("SELECT name, research_name, research_lvl, proc_type, modifiers, duration, proc_trigger, description FROM ds_le_procs "
                      "WHERE lower(profession) = lower(?) ORDER BY CAST(proc_type AS INTEGER), CAST(research_lvl AS INTEGER) DESC", (prof,)).fetchall()
    if not rows:
        raise ValueError("No procs found for profession %s." % prof)
    h = "<h2>%s LE procs</h2>" % E(prof)
    cur = None
    for r in rows:
        if r[3] != cur:
            if cur is not None:
                h += "</table></div>"
            cur = r[3]
            h += "<h3>Type %s</h3><div class='scroll'><table><tr><th>Research</th><th>Proc</th><th>Modifiers</th><th>Duration</th><th>Trigger</th><th>Effect</th></tr>" % E(cur)
        h += "<tr><td>%s (%s)</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            E(r[2]), E(r[1]), E(r[0]), E(r[4]), E(r[5]), E(r[6]), E(r[7]))
    h += "</table></div><p class='dim'>Offensive procs have a 5% chance of firing every time you attack. Defensive procs have a 10% chance of firing every time something attacks you.</p>"
    return dict(html=h, data=[dict(name=r[0], research=r[1], research_level=_toint(r[2]), type=_toint(r[3]), modifiers=r[4], duration=r[5],
                                   trigger=r[6], description=r[7]) for r in rows])


# ---------------------------------------------------------------------------------------- arulsaba ----
GEM_GRADES = [("Arbiter Gem", "Scheol", 288, 306), ("Monarch Gem", "Adonis", 528, 563), ("Emperor Gem", "Penumbra", 937, 1035),
              ("Stellar Jewel", "Inferno", 1665, 1775), ("Galactic Jewel", "Alappaa", 2100, 2270)]
BLUEPRINTS = [[150871, 150870, 80, 150862, 150866, 150857, 150861], [150871, 150870, 80, 150862, 150866, 150857, 150861],
              [150870, 150869, 110, 150866, 150865, 150861, 150859], [150869, 150867, 150, 150865, 150863, 150859, 150858],
              [150867, 150868, 180, 150863, 150864, 150858, 150857], [150867, 150868, 200, 150863, 150864, 150858, 150857]]
UNFINISHED = {0: {"left": [150846], "right": [150843]}, 1: {"left": [150846], "right": [150843]},
              2: {"left": [150836, 150841], "right": [150833, 150847]},
              3: {"left": [150834, 150832, 150842], "right": [150820, 150818, 150844]},
              4: {"left": [150821, 150828, 150825, 150840], "right": [150831, 150829, 150826, 150837]},
              5: {"left": [150835, 150830, 150827, 150824, 150838], "right": [150817, 150819, 150823, 150822, 150845]}}
FINISHED = {0: {"left": 150855, "right": 150856}, 1: {"left": 150855, "right": 150856}, 2: {"left": 150839, "right": 150851},
            3: {"left": 150854, "right": 150848}, 4: {"left": 150852, "right": 150849}, 5: {"left": 150853, "right": 150850}}
ME, EE, AGI = "Mechanical Engineering", "Electrical Engineering", "Agility"
_NODROP, _UNIQUE = 1 << 26, 1 << 27  # Nadybot Core/Types/ItemFlag: NO_DROP, UNIQUE


class _AItem:
    """An item inside the Arul Saba recipe (like AODBItem): id, name and the QL it is shown at"""

    def __init__(self, iid, name, ql, flags=0, lowql=None, highql=None):
        self.id, self.name, self.ql, self.flags, self.lowql, self.highql = iid, name, ql, flags, lowql, highql

    def copy(self, **kw):
        c = _AItem(self.id, self.name, self.ql, self.flags, self.lowql, self.highql)
        c.__dict__.update(kw)
        return c

    def html(self):
        return _ilink(self.id, self.name, self.ql) if self.id else E(self.name)


def _aitem_by_id(db, iid, ql=None, name=None):
    r = find_id(db, iid)
    if r:
        return _AItem(iid, r["name"], ql if ql is not None else r["lowql"], r["flags"], r["lowql"], r["highql"])
    nm = db.execute("SELECT name FROM items WHERE id = ?", (iid,)).fetchone()
    return _AItem(iid, name or (nm[0] if nm else "Item %d" % iid), ql, 0, ql, ql)


def _ingredient(db, name=None, aoid=None):
    """ds_ingredients row by id, exact name, or (like the bot) all name words contained in the name"""
    rows = db.execute("SELECT name, aoid, \"where\" FROM ds_ingredients").fetchall()
    if aoid is not None:
        for r in rows:
            if _toint(r[1]) == aoid:
                return r
    else:
        for r in rows:
            if r[0] == name:
                return r
        toks = [t.lower() for t in name.split()]
        for r in rows:
            if all(t in r[0].lower() for t in toks):
                return r
    raise ValueError("Cannot find ingredient %s in the archive." % (name if aoid is None else "#%d" % aoid))


def _arul_step(source, dest, result, reqs=None):
    line = "%s + %s = %s" % (source.html(), dest.html(), result.html())
    if not (dest.flags & _NODROP) and (result.flags & _NODROP):
        line += " <span class='dim'>(becomes NODROP)</span>"
    if not reqs:
        return "<p>%s<br><span class='dim'>No skills required</span></p>" % line, dict(source=source.name, dest=dest.name, result=result.name)
    out = []
    for skill, amount in reqs:
        if isinstance(amount, str) and amount.startswith("*"):
            mult = float(amount[1:])
            out.append("%s: %d (%sx)" % (skill, int(math.ceil(mult * dest.ql)), amount[1:]))
        else:
            out.append("%s: %d" % (skill, int(amount)))
    return ("<p>%s<br><span class='dim'>%s</span></p>" % (line, E(", ".join(out))),
            dict(source=source.name, dest=dest.name, result=result.name, skills=out))


def _arul_list(db):
    rows = db.execute("SELECT name, lesser_prefix, regular_prefix, buffs FROM ds_arulsaba").fetchall()
    h = "<h2>Bracelets of Arul Saba</h2>" + _table(["Type", "Prefixes", "Buffs"], [
        [_tlink("arulsaba", r[0], type=r[0]), E("%s / %s" % (r[1], r[2])), E(r[3])] for r in rows])
    return dict(html=h, data=[dict(name=r[0], lesser=r[1], regular=r[2], buffs=r[3]) for r in rows])


def _arul_choose(db, name, skills):
    rows = db.execute("SELECT name, min_level, left_aoid, right_aoid FROM ds_arulsaba_buffs WHERE lower(name) = lower(?) "
                      "ORDER BY CAST(min_level AS INTEGER)", (name,)).fetchall()
    if not rows:
        raise ValueError("No Bracelet of Arul Saba (%s) found." % name)
    ibuffs = {}
    h = "<h2>Types of an Arul Saba %s bracelet</h2>" % E(rows[0][0])
    data = []
    for gems, r in enumerate(rows):
        left = _toint(r[2])
        it = _aitem_by_id(db, left)
        short = re.sub(r"^.*\((.+?) - Left\)$", r"\1", it.name)
        buffs = [(_toint(a), _toint(b)) for a, b in db.execute("SELECT attribute_id, amount FROM ds_item_buffs WHERE item_id = ?", (str(left),))]
        h += "<h3>%s</h3><p>Min level: %s</p>" % (E(short), _hl(r[1]))
        if buffs:
            h += "<ul>%s</ul>" % "".join("<li>%s: <strong>%+d%s</strong></li>" % (E(skills.full(a)), b, E(skills.unit(a))) for a, b in buffs)
        h += "<p>Recipe: [%s] [%s]</p>" % (_tlink("arulsaba", "Left", type=r[0], gems=gems, side="left"),
                                           _tlink("arulsaba", "Right", type=r[0], gems=gems, side="right"))
        data.append(dict(gems=gems, name=short, min_level=_toint(r[1]), left=left, right=_toint(r[3]),
                         buffs={skills.full(a): b for a, b in buffs}))
    return dict(html=h, data=data)


def run_arulsaba(db, p):
    skills = Skills(db)
    if not p.get("type"):
        return _arul_list(db)
    typ = p["type"].strip().capitalize()
    if p.get("gems") is None:
        return _arul_choose(db, typ, skills)
    num = p["gems"]
    side = (p.get("side") or "left").lower()
    if side not in ("left", "right"):
        raise ValueError("Side has to be left or right.")
    arul = db.execute("SELECT name, lesser_prefix, regular_prefix FROM ds_arulsaba WHERE lower(name) = lower(?)", (typ,)).fetchone()
    if not arul or not 0 <= num < len(BLUEPRINTS):
        raise ValueError("No Bracelet of Arul Saba (%s - %d/%d) found." % (typ, num, num))
    name, lesser, regular = arul
    req = max(1, num)
    prefix = lesser if num == 0 else regular
    bp = BLUEPRINTS[num]
    bpql = bp[2]
    ing = []  # (amount, item, ql, ql can be higher, where)

    def add(it, amount=1, ql=None, higher=False, where=None):
        ing.append((amount, it, ql, higher, where))
        return it

    gems = []
    for i in range(req):
        r = _ingredient(db, name="%s %s %s" % (GEM_GRADES[i][0], prefix, name))
        gems.append(add(_aitem_by_id(db, _toint(r[1]), name=r[0]), where=r[2]))
    bal = 3 if side == "left" else 5
    r = _ingredient(db, aoid=bp[0])
    bprow = find_id(db, bp[0])
    bprint = _aitem_by_id(db, bp[0], bpql, name=r[0])
    add(bprint, 1, bpql, where=r[2])
    bprint.lowql = bprow["lowql"] if bprow else bpql
    balanced = bprint.copy(id=bp[bal], name="Balanced Bracelet Blueprints")

    def ingredient(nm, amount=1, ql=None, higher=False):
        row = _ingredient(db, name=nm)
        it = _aitem_by_id(db, _toint(row[1]), ql, name=row[0])
        ing.append((amount, it, ql, higher, row[2]))
        return it

    adjuster = ingredient("Balance Adjuster - " + side.capitalize())
    min_ingot = int(math.ceil(0.7 * bpql))
    ingot = ingredient("Small Silver Ingot", req + 1, min_ingot, True)
    furnace = ingredient("Personal Furnace", req + 1)
    min_junk = int(math.ceil(0.53 * bpql))
    junk = ingredient("Robot Junk", req, min_junk, True)
    min_wire = int(math.ceil(0.35 * bpql))
    wire = ingredient("Nano Circuitry Wire", req * 2, min_wire, True)
    wmachine = ingredient("Wire Drawing Machine", 1, 100, True)
    screwdriver = ingredient("Screwdriver")

    h = "<h2>Bracelet of Arul Saba (%s %s - %d/%d - %s)</h2>" % (E(prefix), E(name), req, req, E(side.capitalize()))
    h += "<h3>Ingredients</h3><ul>"
    show_amount = max(a for a, _, _, _, _ in ing) > 1
    for amount, it, ql, higher, where in ing:
        qltxt = ""
        if ql is not None and (it.lowql is None or it.lowql != it.highql):
            qltxt = "QL%d%s " % (ql, "+" if higher else "")
        h += "<li>%s%s%s%s</li>" % ("%d&times; " % amount if show_amount else "", E(qltxt), it.html(),
                                    " <span class='dim'>(%s)</span>" % E(where) if where else "")
    h += "</ul>"
    steps = []

    def step(src, dst, res, reqs=None):
        s, d = _arul_step(src, dst, res, reqs)
        steps.append(d)
        return s

    h += "<h3>Balancing the blueprint</h3>" + step(adjuster, bprint, balanced, [(ME, "*3"), (EE, "*3.2")])

    def named(nm, ql):
        r = find_item(db, nm, ql)
        return _AItem(r["lowid"] if r else None, nm, ql, r["flags"] if r else 0, r["lowql"] if r else ql, r["highql"] if r else ql)

    liq = named("Liquid Silver", ingot.ql)
    filw = named("Silver Filigree Wire", liq.ql)
    nanow = named("Silver Nano Circuitry Filigree Wire", filw.ql)
    sensor = _aitem_by_id(db, 150923, min(250, junk.ql))
    isensor = _aitem_by_id(db, 150926, sensor.ql)
    circ = named("Bracelet Circuitry", nanow.ql)
    h += "<h3>Bracelet circuitry (%dx)</h3>" % req
    h += step(furnace, ingot, liq, [(ME, "*3")])
    h += step(wmachine, liq, filw, [(ME, "*4.5")])
    h += step(wire, filw, nanow, [(ME, "*4"), (AGI, "*1.7")])
    h += step(screwdriver, junk, sensor)
    h += step(wire, sensor, isensor, [(ME, "*3.5"), (EE, "*4.25")])
    h += step(isensor, nanow, circ, [(ME, "*4.25"), (EE, "*4.8"), (AGI, "*1.8")])
    h += "<h3>Add %s to the bracelet</h3>" % ("%d sockets" % req if req > 1 else "a socket")
    target = balanced
    result = target
    for i in range(req):
        uid = UNFINISHED[num][side][i]
        result = _aitem_by_id(db, uid, None, name="Unfinished Bracelet of Arul Saba")
        result.name = "Unfinished Bracelet of Arul Saba"
        result.ql = result.lowql if result.lowql is not None else bprint.lowql
        h += step(circ, target, result, [(ME, "*4"), (EE, "*4.2")])
        target = result
    coated = result.copy(id=FINISHED[num][side], name="Bracelet of Arul Saba")
    fr = find_id(db, FINISHED[num][side])
    coated.flags = fr["flags"] if fr else result.flags
    h += "<h3>Add silver coating</h3>"
    h += step(furnace, ingot, liq, [(ME, "*3")])
    h += step(liq, result, coated)
    h += "<h3>Add the gems</h3>"
    target = coated
    for i in range(req):
        rname = "Bracelet of Arul Saba (%s %s - %d/%d - %s)" % (prefix, name, i + 1, req, side.capitalize())
        ritem = None
        for x in sorted((_item(r) for r in db.execute(_ITEM_SQL + "WHERE name = ?", (rname,))), key=lambda x: -x["highql"]):
            ritem = x
            break
        if ritem is None:
            raise ValueError("Unable to find the item %s in the archive." % rname)
        res = _AItem(ritem["lowid"], ritem["name"], ritem["lowql"], ritem["flags"], ritem["lowql"], ritem["highql"])
        h += step(gems[i], target, res, [(ME, GEM_GRADES[i][2]), (EE, GEM_GRADES[i][3])])
        target = res
    h += ("<p class='dim'>The number in brackets behind a skill requirement is how many times the QL of the target item is actually "
          "required to do the tradeskill. The example numbers listed are only correct for the exact QLs shown in the equation.</p>")
    return dict(html=h, data=dict(type=name, gems=num, side=side, steps=steps,
                                  ingredients=[dict(amount=a, name=i.name, id=i.id, ql=q) for a, i, q, _, _ in ing]))


# ------------------------------------------------------------------------------------------ bestql ----
def calc_stat_from_ql(specs, ql):
    """BestQLController::calcStatFromQL; specs is a QL-sorted list of (ql, bonus); None if out of range"""
    last = None
    for itemql, bonus in specs:
        if last is None:
            last = (itemql, bonus)
        else:
            if last[0] <= ql <= itemql:
                multi = 1 / (itemql - last[0])
                return last[1] + ((bonus - last[1]) * (multi * (ql - (last[0] - 1) - 1)))
            last = (itemql, bonus)
    return None


def run_bestql(db, p):
    txt = (p.get("specs") or "").strip()
    if not re.fullmatch(r"[0-9 ]+", txt or "x"):
        raise ValueError("Enter numbers only, e.g. '1 6 400 23' (QL, bonus, QL, bonus, ...).")
    pairs = txt.split()
    if p.get("attribute") is not None:
        if len(pairs) % 2:
            raise ValueError("Enter an even number of values in the specs when you also fill in your attribute.")
        pairs.append(str(p["attribute"]))
    if len(pairs) < 4:
        raise ValueError("You have to provide at least 2 bonuses at 2 different QLs.")
    d = {}
    for i in range(1, len(pairs), 2):
        d[int(pairs[i - 1])] = int(pairs[i])
    specs = sorted(d.items())
    if len(specs) < 2:
        raise ValueError("You have to provide at least 2 bonuses at 2 different QLs.")
    item = p.get("item")
    minql, maxql = specs[0][0], specs[-1][0]
    odd = len(pairs) % 2 == 1
    maxattr = int(pairs[-1])
    rows, old, oldreq = [], None, 0
    for ql in range(minql, maxql + 1):
        v = calc_stat_from_ql(specs, ql)
        if v is None:
            raise ValueError("I was unable to find any breakpoints for the given stats.")
        v = _rnd(v)
        if odd:
            if v > maxattr:
                if ql == minql:
                    msg = "Your stats are too low to equip any QL of this item."
                    return dict(html="<p class='verdict'>%s</p>" % E(msg), data=dict(highest_ql=None))
                msg = "The highest QL is %s with a requirement of %s. QL %d already requires %d." % (_hl(ql - 1), _hl(oldreq), ql, v)
                return dict(html="<p class='verdict'>%s</p>" % msg, data=dict(highest_ql=ql - 1, requirement=oldreq, next_ql_requires=v))
            oldreq = v
        elif v != old:
            rows.append((ql, v))
            old = v
    if odd:
        msg = "The highest QL is %s with a requirement of %s." % (_hl(maxql), _hl(dict(specs)[maxql]))
        return dict(html="<p class='verdict'>%s</p>" % msg, data=dict(highest_ql=maxql, requirement=dict(specs)[maxql]))
    cells = [[str(ql), str(v)] + ([_ilink(item, "item at QL %d" % ql, ql)] if item else []) for ql, v in rows]
    h = "<p class='verdict'>Found %s breakpoints with different stats.</p>" % _hl(len(rows))
    h += _table(["QL", "Stat"] + (["Item"] if item else []), [[E(c[0]), E(c[1])] + c[2:] for c in cells])
    return dict(html=h, data=dict(breakpoints=[dict(ql=a, stat=b) for a, b in rows]))


# --------------------------------------------------------------------------------- slots & buffs ----
# Armour wear slots (bit values taken from the archive's items table: rings are 8192|32768, wrists 1024|4096, ...)
WEAR = [("Neck", 2), ("Head", 4), ("Back", 8), ("Right Shoulder", 16), ("Chest", 32), ("Left Shoulder", 64), ("Right Arm", 128),
        ("Hands", 256), ("Left Arm", 512), ("Right Wrist", 1024), ("Legs", 2048), ("Left Wrist", 4096),
        ("Right Finger", 8192), ("Feet", 16384), ("Left Finger", 32768)]
WEAR_GROUPS = [("Neck", 2), ("Head", 4), ("Back", 8), ("Shoulders", 16 | 64), ("Chest", 32), ("Arms", 128 | 512), ("Hands", 256),
               ("Wrists", 1024 | 4096), ("Legs", 2048), ("Fingers", 8192 | 32768), ("Feet", 16384)]
_SLOT_ALIAS = {"body": "Chest", "chest": "Chest", "boots": "Feet", "foot": "Feet", "feet": "Feet", "gloves": "Hands", "hand": "Hands",
               "helmet": "Head", "helm": "Head", "pants": "Legs", "leg": "Legs", "sleeves": "Arms", "arm": "Arms",
               "ring": "Fingers", "rings": "Fingers", "finger": "Fingers", "wrist": "Wrists", "shoulder": "Shoulders",
               "cloak": "Back", "ncu": "Deck", "belt": "Deck", "contracts": "Contract"}
SOCIAL_PROPERTY = 1 << 28  # Nadybot Core/Types/ItemProperty: CAN_BE_WORN_WITH_SOCIAL_ARMOR
CARRY_RIGHT, CARRY_LEFT = 64, 256
# Categories as the bot's item_types file named them. The archive's item type is only Armor/Weapon/Misc, so the category
# is derived from type and slot bits.
ITEM_CATEGORIES = ["Arms", "Back", "Chest", "Deck", "Feet", "Fingers", "Hands", "Head", "Hud", "Legs", "Neck", "Shoulders",
                   "Util", "Weapon", "Wrists"]


def item_category(it):
    s = it["slot"]
    if it["type"] == "Armor":
        hits = [g for g, m in WEAR_GROUPS if s & m]
        return hits[0] if len(hits) == 1 else None
    if it["type"] == "Weapon":
        if s & 0x38:
            return "Util"
        if s & 0x8006:
            return "Hud"
        if s & (CARRY_RIGHT | CARRY_LEFT):
            return "Weapon"
        return "Deck" if s else None
    return None


def _slot_prefix(it, category, multi):
    s = it["slot"]
    res = ""
    if multi:
        if s & CARRY_RIGHT and s & CARRY_LEFT:
            return "2x "
        res = "L-Hand " if s & CARRY_LEFT else "R-Hand "
    else:
        pairs = {"Arms": ("L-Arm ", 512, "R-Arm ", 128), "Wrists": ("L-Wrist ", 4096, "R-Wrist ", 1024),
                 "Fingers": ("L-Finger ", 32768, "R-Finger ", 8192), "Shoulders": ("L-Shoulder ", 64, "R-Shoulder ", 16)}
        if category in pairs and it["type"] == "Armor":
            ln, lb, rn, rb = pairs[category]
            if s & lb and s & rb:
                res = ""
            elif s & lb:
                res = ln
            elif s & rb:
                res = rn
    return res


def _interpolate(lowql, highql, lowv, highv, ql):
    if highql == lowql:
        return highv
    return _rnd(lowv + (highv - lowv) * (ql - lowql) / (highql - lowql))


class Perks:
    """ds_perks parsed like BuffPerksController::getPerkInfo: {perk name: {level: (expansion, profs, {skill id: amount})}}"""

    def __init__(self, db, skills):
        self.perks = {}
        cache = {}
        groups = {
            "Add. Dmg.": ["Add. Cold Dam.", "Add. Chem Dam.", "Add. Energy Dam.", "Add. Fire Dam.", "Add. Melee Dam.", "Add. Poison Dam.",
                          "Add. Rad. Dam.", "Add. Proj. Dam."],
            "AC": ["Melee/ma AC", "Disease AC", "Fire AC", "Cold AC", "Imp/Proj AC", "Energy AC", "Chemical AC", "Radiation AC"],
            "Shield": ["Shield%sAC" % x for x in ("Projectile", "Melee", "Energy", "Chemical", "Radiation", "Cold", "Nano", "Fire", "Poison")],
            "Reflect": ["Reflect%sAC" % x for x in ("Projectile", "Melee", "Energy", "Chemical", "Radiation", "Cold", "Nano", "Fire", "Poison")]}
        for name, level, exp, aoid, reqlvl, profs, buffs in db.execute(
                "SELECT name, perk_level, expansion, aoid, required_level, professions, buffs FROM ds_perks ORDER BY rowid"):
            if profs == "*":
                profs = "Adv, Agent, Crat, Doc, Enf, Engi, Fix, Keep, MA, MP, NT, Shade, Sol, Tra"
            pl = [prof_long(x) for x in profs.split(",")]
            bf = {}
            for b in (buffs or "").split(","):
                b = b.strip()
                if " " not in b:
                    continue
                sn, amt = b.rsplit(" ", 1)
                for sk in groups.get(sn.strip(), [sn.strip()]):
                    m = cache.get(sk)
                    if m is None:
                        m = cache[sk] = skills.match(sk)
                    if len(m) == 1:
                        bf[m[0]] = _toint(amt, 0)
            self.perks.setdefault(name, {})[_toint(level, 0)] = (exp, [x for x in pl if x], bf, _toint(aoid))


def _perk_matches(levels, sid, neg):
    for _, (_, _, bf, _) in levels.items():
        if sid in bf and (bf[sid] < 0 if neg else bf[sid] > 0):
            return True
    return False


def _perk_list(perks, sid, neg):
    """PerkBuffSearchResult list per generatePerkBufflist"""
    out = []
    for name, levels in perks.perks.items():
        if not _perk_matches(levels, sid, neg):
            continue
        total, pm, exp, aoid = 0, {}, None, None
        for lv in sorted(levels):
            e, profs, bf, ao = levels[lv]
            if sid not in bf:
                continue
            exp, aoid = e, aoid or ao
            total += bf[sid]
            for pr in profs:
                pm[pr] = pm.get(pr, 0) + bf[sid]
        for val in list(dict.fromkeys(pm.values())):
            out.append(dict(name=name, amount=val, profs=[pr for pr in pm if pm[pr] == val], aoid=aoid, expansion=exp))
    out.sort(key=lambda r: (-r["amount"], r["name"]))
    return out


def _nano_buffs(db, sid, froob, skills):
    neg = sid in NEGATIVE_IS_GOOD
    sql = ("SELECT b.id, b.name, b.ncu, ib.amount, b.froob_friendly, b.use_id FROM ds_nano_buffs b "
           "JOIN ds_item_buffs ib ON CAST(ib.item_id AS INTEGER) = CAST(b.id AS INTEGER) WHERE CAST(ib.attribute_id AS INTEGER) = ?")
    if froob:
        sql += " AND b.froob_friendly = '1'"
    rows = []
    for r in db.execute(sql, (sid,)):
        amount = _toint(r[3], 0)
        if not (sid in (SKILL_LOCK, ADD_NANO_COST) or amount > 0):
            continue
        if r[1] in ("Ineptitude Transfer", "Accumulated Interest", "Unforgiven Debts", "Payment Plan"):
            continue
        rows.append(dict(id=_toint(r[0]), name=r[1], ncu=_toint(r[2], 0), amount=amount, use_id=_toint(r[5])))
    rows.sort(key=lambda r: r["name"])
    rows.sort(key=lambda r: -r["amount"])
    if rows and rows[-1]["amount"] < 0:
        rows.reverse()
    return rows


def _group_wranglers(nanos):
    groups = [r"(Divest|Deprive) Skills.*Transfer", r"(Ransack|Plunder) Skills.*Transfer", r"^Umbral Wrangler", r"^Team Skill Wrangler",
              r"^Skill Wrangler"]
    best, out = {}, []
    for n in nanos:
        skip = False
        for g in groups:
            if re.search(g, n["name"]):
                if g in best:
                    best[g]["low_ncu"], best[g]["low_amount"] = n["ncu"], n["amount"]
                    skip = True
                else:
                    best[g] = n
        if not skip:
            out.append(n)
    return out


def _amount_cell(amount, unit):
    return "%+d%s" % (amount, unit)


class _Env:
    """All data one whatbuffs call needs, loaded once"""

    def __init__(self, db):
        self.db = db
        self.skills = Skills(db)
        self._perks = None

    @property
    def perks(self):
        if self._perks is None:
            self._perks = Perks(self.db, self.skills)
        return self._perks

    def items(self):
        return [_item(r) for r in self.db.execute(_ITEM_SQL)]

    def buff_map(self, sid):
        m = {}
        for iid, amt in self.db.execute("SELECT item_id, amount FROM ds_item_buffs WHERE CAST(attribute_id AS INTEGER) = ?", (sid,)):
            m[_toint(iid)] = _toint(amt, 0)
        return m


def _norm_type(text):
    t = str(text or "").strip().lower()
    if not t:
        return None
    if t in _SLOT_ALIAS:
        t = _SLOT_ALIAS[t].lower()
    if t in ("nano", "nanos", "nanoprogram", "nanoprograms"):
        return "Nanoprogram"
    if t in ("perk", "perks"):
        return "Perk"
    if t in ("weapons", "weapon"):
        return "Weapon"
    for c in ITEM_CATEGORIES:
        if c.lower() == t or c.lower().rstrip("s") == t.rstrip("s"):
            return c
    return None


def _wb_skill_choice(env, froob, extra=None, title="Choose a skill"):
    ids = {_toint(r[0]) for r in env.db.execute("SELECT DISTINCT attribute_id FROM ds_item_buffs")}
    ids = sorted((i for i in ids if i in env.skills.name), key=lambda i: env.skills.full(i).lower())
    return "<h2>WhatBuffs%s: %s</h2><ul>%s</ul>" % (" (froob)" if froob else "", E(title), "".join(
        "<li>%s</li>" % _tlink("whatbuffs", env.skills.full(i), skill=i, froob="yes" if froob else "no") for i in ids))


def _wb_types_for_skill(env, sid, froob):
    sk = env.skills
    neg = sid in NEGATIVE_IS_GOOD
    bm = env.buff_map(sid)
    counts = {}
    seen = set()
    for it in env.items():
        a = bm.get(it["highid"])
        if a is None or not (a < 0 if neg else a > 0):
            continue
        if froob and not it["froob"] or not it["in_game"]:
            continue
        c = item_category(it)
        if not c:
            continue
        key = (it["name"], c, it["lowql"], it["highql"], a)
        if key in seen:
            continue
        seen.add(key)
        counts[c] = counts.get(c, 0) + 1
    n = len(_nano_buffs(env.db, sid, froob, sk))
    if n:
        counts["Nanoprogram"] = n
    if not froob:
        k = len([1 for _, lv in env.perks.perks.items() if _perk_matches(lv, sid, neg)])
        if k:
            counts["Perk"] = k
    if not counts:
        return dict(html="<p class='verdict'>There are currently no known items or nanos buffing %s.</p>" % E(sk.full(sid)),
                    data=dict(skill=sk.full(sid), types={}))
    h = "<h2>WhatBuffs%s: %s, choose the buff type</h2><ul>%s</ul>" % (
        " (froob)" if froob else "", E(sk.full(sid)), "".join(
            "<li>%s (%d)</li>" % (_tlink("whatbuffs", c, skill=sid, type=c, froob="yes" if froob else "no"), counts[c]) for c in sorted(counts)))
    return dict(html=h, data=dict(skill=sk.full(sid), types=counts))


def _wb_skills_for_type(env, typ, froob):
    sk = env.skills
    counts = {}
    if typ == "Nanoprogram":
        for r in env.db.execute("SELECT ib.attribute_id, ib.amount, b.froob_friendly FROM ds_nano_buffs b "
                                "JOIN ds_item_buffs ib ON CAST(ib.item_id AS INTEGER) = CAST(b.id AS INTEGER)"):
            a, am = _toint(r[0]), _toint(r[1], 0)
            if froob and r[2] != "1":
                continue
            if a in (SKILL_LOCK, ADD_NANO_COST) or am > 0:
                counts[a] = counts.get(a, 0) + 1
    elif typ == "Perk":
        if froob:
            raise ValueError("Froobs don't have perks.")
        for name, levels in env.perks.perks.items():
            sids = set()
            for _, (_, _, bf, _) in levels.items():
                for s, am in bf.items():
                    if (am < 0) if s in NEGATIVE_IS_GOOD else am > 0:
                        sids.add(s)
            for s in sids:
                counts[s] = counts.get(s, 0) + 1
    else:
        by_id = {}
        for iid, a, amt in env.db.execute("SELECT item_id, attribute_id, amount FROM ds_item_buffs"):
            by_id.setdefault(_toint(iid), []).append(_toint(a))
        for it in env.items():
            if item_category(it) != typ or not it["in_game"] or (froob and not it["froob"]) or it["name"] == "Brad Test Nano":
                continue
            for a in by_id.get(it["highid"], []):
                counts[a] = counts.get(a, 0) + 1
    rows = sorted(((s, n) for s, n in counts.items() if s in sk.name), key=lambda x: sk.full(x[0]).lower())
    h = "<h2>WhatBuffs%s: %s, choose the skill to buff</h2><ul>%s</ul>" % (" (froob)" if froob else "", E(typ), "".join(
        "<li>%s (%d)</li>" % (_tlink("whatbuffs", sk.full(s), skill=s, type=typ, froob="yes" if froob else "no"), n) for s, n in rows))
    return dict(html=h, data={sk.full(s): n for s, n in rows})


def _wb_results(env, typ, sid, froob):
    sk = env.skills
    neg = sid in NEGATIVE_IS_GOOD
    unit = sk.unit(sid)
    title = "WhatBuffs%s: %s, %s" % (" (froob)" if froob else "", typ, sk.full(sid))
    if typ == "Nanoprogram":
        nanos = _nano_buffs(env.db, sid, froob, sk)
        nanos = [n for n in nanos if not re.search(r"^Composite .+ Expertise \(\d hours\)$", n["name"])]
        if not nanos:
            return dict(html="<p class='verdict'>No items found of type %s that buff %s.</p>" % (E(typ), E(sk.full(sid))), data=[])
        nanos = _group_wranglers(nanos)
        rows = []
        for n in nanos:
            ncu = 0 if n["ncu"] == 999 else n["ncu"]
            if "low_ncu" in n:
                ncus = "%d NCU (%d) - %d NCU (%d)" % (n["low_ncu"], n["low_amount"], ncu, n["amount"])
            else:
                ncus = "%d NCU" % ncu
            frm = ""
            if n["use_id"]:
                it = find_id(env.db, n["use_id"])
                if it:
                    frm = _ilink(it["lowid"], it["name"], it["lowql"])
            rows.append([E(_amount_cell(n["amount"], unit)), _ilink(n["id"], n["name"]), E(ncus), frm])
        h = "<h2>%s (%d)</h2>" % (E(title), len(rows)) + _table(["Buff", "Nanoprogram", "NCU", "From"], rows)
        return dict(html=h, data=[dict(name=n["name"], id=n["id"], amount=n["amount"], ncu=n["ncu"]) for n in nanos])
    if typ == "Perk":
        if froob:
            raise ValueError("Froobs don't have perks.")
        pl = _perk_list(env.perks, sid, neg)
        if not pl:
            return dict(html="<p class='verdict'>No items found of type Perk that buff %s.</p>" % E(sk.full(sid)), data=[])
        rows = []
        for r in pl:
            ps = "All" if len(r["profs"]) >= 14 else ", ".join(prof_short(x) for x in r["profs"])
            rows.append([E(_amount_cell(r["amount"], unit)), _ilink(r["aoid"], r["name"]) if r["aoid"] else E(r["name"]), E(ps)])
        return dict(html="<h2>%s (%d)</h2>%s" % (E(title), len(rows), _table(["Buff", "Perk", "Professions"], rows)),
                    data=[dict(name=r["name"], amount=r["amount"], professions=r["profs"]) for r in pl])
    # items
    hi = env.buff_map(sid)
    weapon_multi = set()
    if typ == "Weapon":
        for r in env.db.execute("SELECT id FROM ds_weapon_attributes WHERE (multi_m IS NOT NULL AND multi_m != '') "
                                "OR (multi_r IS NOT NULL AND multi_r != '')"):
            weapon_multi.add(_toint(r[0]))
    rows, seen = [], set()
    for it in env.items():
        if item_category(it) != typ or not it["in_game"] or (froob and not it["froob"]):
            continue
        a, lo = hi.get(it["highid"]), hi.get(it["lowid"])
        if a is None or lo is None or not (a < 0 if neg else a > 0):
            continue
        key = (it["name"], it["lowql"], it["highql"], a, lo, it["lowid"], it["highid"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(dict(it, amount=a, low_amount=lo, multi=it["highid"] in weapon_multi))
    if not rows:
        return dict(html="<p class='verdict'>No items found of type %s that buff %s.</p>" % (E(typ), E(sk.full(sid))), data=[])
    rows.sort(key=lambda r: r["name"], reverse=True)
    rows.sort(key=lambda r: -abs(r["amount"]))
    if rows[-1]["amount"] < 0:
        rows.reverse()
    maxbuff, maxql, maxamt, mapping = 0, {}, {}, {}
    for r in rows:
        if r["amount"] == r["low_amount"]:
            r["highql"] = r["lowql"]
        maxql[r["lowid"]], maxamt[r["lowid"]] = r["highql"], r["amount"]
        if r["highql"] > 250 and (" Filigree Ring set with a " in r["name"] or r["name"].startswith("Universal Advantage - ")):
            r["amount"] = _interpolate(r["lowql"], r["highql"], r["low_amount"], r["amount"], 250)
            r["highql"] = 250
        maxbuff = max(maxbuff, abs(r["amount"]))
        if r["lowid"] == r["highid"]:
            mapping[r["lowid"]] = r
    rows.sort(key=lambda r: r["amount"], reverse=not neg)
    ignore = []
    for r in rows:
        hid = r["highid"]
        if hid != r["lowid"] and hid in mapping:
            m = mapping[hid]
            r["highid"], r["highql"] = m["highid"], m["highql"]
            ignore.append(m)
    out, data = [], []
    for r in rows:
        if any(r is x for x in ignore):
            continue
        cell = [E(_amount_cell(r["amount"], unit)), E(_slot_prefix(r, typ, r["multi"])) + _ilink(r["lowid"], r["name"], r["highql"])]
        extra = ""
        if r["amount"] > r["low_amount"]:
            extra = "%d &ndash; %d " % (r["low_amount"], r["amount"])
            extra += _tlink("bestql", "Breakpoints", specs="%d %d %d %d" % (r["lowql"], r["low_amount"], maxql[r["lowid"]], maxamt[r["lowid"]]),
                            item=r["lowid"])
        flags = []
        if r["flags"] & _UNIQUE:
            flags.append("Unique")
        cell += [extra, E(" ".join(flags))]
        out.append(cell)
        data.append(dict(name=r["name"], id=r["lowid"], ql=r["highql"], amount=r["amount"], low_amount=r["low_amount"]))
    h = "<h2>%s (%d)</h2>" % (E(title), len(out)) + _table(["Buff", "Item (QL)", "Range / breakpoints", "Flags"], out)
    return dict(html=h, data=data)


def run_whatbuffs(db, p):
    env = _Env(db)
    froob = (p.get("froob") or "no") == "yes"
    skill = (p.get("skill") or "").strip()
    typ = p.get("type")
    if typ in ("", "any"):
        typ = None
    if typ:
        t = _norm_type(typ)
        if not t:
            raise ValueError("Could not find any items of type %s." % typ)
        typ = t
    if not skill:
        if typ:
            return _wb_skills_for_type(env, typ, froob)
        return dict(html=_wb_skill_choice(env, froob), data=None)
    ids = env.skills.match(skill)
    if not ids:
        raise ValueError("Could not find skill %s." % skill)
    if len(ids) > 1:
        h = "<h2>WhatBuffs%s: choose a skill</h2><ul>%s</ul>" % (" (froob)" if froob else "", "".join(
            "<li>%s</li>" % _tlink("whatbuffs", env.skills.full(i), skill=i, type=typ, froob="yes" if froob else "no") for i in ids))
        return dict(html=h, data=[env.skills.full(i) for i in ids])
    if typ:
        return _wb_results(env, typ, ids[0], froob)
    return _wb_types_for_skill(env, ids[0], froob)


# ---------------------------------------------------------------------------------------- gridarmor ----
def _slot_bits(name):
    t = str(name).strip().lower()
    if t in _SLOT_ALIAS:
        t = _SLOT_ALIAS[t].lower()
    for n, m in WEAR_GROUPS + WEAR:
        if n.lower() == t or n.lower().rstrip("s") == t.rstrip("s"):
            return n, m
    return None, 0


def _gridarmor_rows(db, bits, froob):
    rows = []
    for it in (_item(r) for r in db.execute(_ITEM_SQL + "WHERE type = 'Armor'")):
        if not it["in_game"] or not it["properties"] & SOCIAL_PROPERTY or not it["slot"] & bits:
            continue
        if froob and not it["froob"]:
            continue
        if it["name"].startswith(("Lootgiver", "Test Test", "Leet_Pet_NCU_Ring")):
            continue
        rows.append(it)
    rows.sort(key=lambda x: x["name"])
    return rows


def run_gridarmor(db, p):
    froob = (p.get("froob") or "no") == "yes"
    slot = (p.get("slot") or "list").strip()
    f = "yes" if froob else "no"
    if slot.lower() in ("", "list"):
        counts = {n: 0 for n, _ in WEAR}
        for it in _gridarmor_rows(db, sum(m for _, m in WEAR), froob):
            for n, m in WEAR:
                if it["slot"] & m:
                    counts[n] += 1
        h = ("<h2>Items wearable %swith Social Armor: choose a slot</h2><p>What is Social Armor? Grid Armor Mk I-IV, Hellfyre Magma Suit, "
             "Charred Abaddon Chassis and all Battle Suits.</p><ul>%s</ul>" % ("for froobs " if froob else "", "".join(
                 "<li>%s (%d)</li>" % (_tlink("gridarmor", n, slot=n, froob=f), counts[n]) for n, _ in WEAR if n != "Back")))
        return dict(html=h, data={n: c for n, c in counts.items() if n != "Back"})
    sname, bits = _slot_bits(slot)
    if not bits:
        raise ValueError("Unknown slot '%s'." % slot)
    rows = _gridarmor_rows(db, bits, froob)
    names = [n for n, m in WEAR if bits & m]
    title = "Items wearable %swith Social Armor in %s (%d)" % ("for froobs " if froob else "", "/".join(names), len(rows))
    out = []
    for it in rows:
        pre = ""
        for (ln, lb), (rn, rb), lab in ((("Left Arm", 512), ("Right Arm", 128), "Arm"), (("Left Wrist", 4096), ("Right Wrist", 1024), "Wrist"),
                                        (("Left Finger", 32768), ("Right Finger", 8192), "Finger"),
                                        (("Left Shoulder", 64), ("Right Shoulder", 16), "Shoulder")):
            if bits & lb and bits & rb:
                if it["slot"] & lb and it["slot"] & rb:
                    pass
                elif it["slot"] & lb:
                    pre = "L-%s " % lab
                elif it["slot"] & rb:
                    pre = "R-%s " % lab
        out.append("<li>%s%s%s</li>" % (E(pre), _ilink(it["lowid"], it["name"], it["lowql"]), " Unique" if it["flags"] & _UNIQUE else ""))
    return dict(html="<h2>%s</h2><ul>%s</ul>" % (E(title), "".join(out)), data=[dict(name=i["name"], id=i["lowid"]) for i in rows])


# ------------------------------------------------------------------------------------------- nanos ----
_NANO_SQL = ("SELECT crystal_id, nano_id, ql, crystal_name, nano_name, school, strain, strain_id, sub_strain, professions, location, "
             "nano_cost, froob_friendly, sort_order, nano_deck, spec, min_level, mm, bm, pm, si, ts, mc FROM ds_nanos ")


def _nano(r):
    n = dict(crystal_id=_toint(r[0]), nano_id=_toint(r[1]), ql=_toint(r[2], 0), crystal_name=r[3], name=r[4], school=r[5] or "",
             strain=r[6] or "", strain_id=_toint(r[7]), sub_strain=r[8] or "", professions=(r[9] or "").split(":"), location=r[10] or "",
             nano_cost=_toint(r[11], 0), froob=r[12] == "1", sort_order=_toint(r[13], 0), nano_deck=r[14] == "1",
             spec=_toint(r[15]), min_level=_toint(r[16]))
    for k, v in zip(("mm", "bm", "pm", "si", "ts", "mc"), r[17:23]):
        n[k] = _toint(v)
    return n


def _nano_link(n):
    return _ilink(n["nano_id"], n["name"])


def _crystal_link(n):
    return _ilink(n["crystal_id"], n["crystal_name"] or "Crystal", n["ql"]) if n["crystal_id"] else "Crystal"


def _tokens_where(col, text):
    where, params = [], []
    for tok in text.split():
        if tok.startswith("-") and len(tok) > 1:
            where.append("%s NOT LIKE ?" % col)
            params.append("%" + tok[1:] + "%")
        else:
            where.append("%s LIKE ?" % col)
            params.append("%" + tok + "%")
    return where, params


def _nano_head(n, froob):
    if n["strain"]:
        s = "%s &gt; %s" % (E(n["school"]), E(n["strain"]))
        if n["sub_strain"]:
            s += " &gt; %s" % E(n["sub_strain"])
        return "<h3>%s <span class='dim'>[%s]</span></h3>" % (s, _tlink("nanolines", "see all nanos", line=n["strain"], froob="yes" if froob else "no"))
    return "<h3>Unknown/General</h3>"


def run_nano(db, p):
    search = (p.get("search") or "").strip()
    if not search:
        raise ValueError("Enter (part of) a nano name.")
    where, params = _tokens_where("nano_name", search)
    limit = 100
    rows = [_nano(r) for r in db.execute(_NANO_SQL + "WHERE " + " AND ".join(where) +
                                         " ORDER BY strain, sub_strain, CAST(sort_order AS INTEGER) LIMIT %d" % limit, params)]
    if not rows:
        raise ValueError("No nanos found.")
    h, cur, tbl = "<h2>Nano search results (%d%s)</h2>" % (len(rows), "+" if len(rows) == limit else ""), None, []

    def flush():
        return _table(["QL", "ID", "Crystal", "Nano", "Location", "Professions"], tbl) if tbl else ""
    for n in rows:
        key = (n["strain"], n["sub_strain"])
        if key != cur:
            h += flush()
            tbl = []
            h += _nano_head(n, False)
            cur = key
        tbl.append([str(n["ql"]), str(n["nano_id"]), _crystal_link(n), _nano_link(n), E(n["location"]), E(", ".join(n["professions"]))])
    h += flush()
    return dict(html=h, data=[{k: n[k] for k in ("nano_id", "name", "ql", "school", "strain", "sub_strain", "professions", "location", "crystal_id")}
                              for n in rows])


def run_nanoloc(db, p):
    loc = (p.get("location") or "").strip()
    if not loc:
        counts = {}
        for r in db.execute("SELECT location, COUNT(*) FROM ds_nanos GROUP BY location"):
            for l in re.split(r"\s*/\s*", r[0] or ""):
                counts[l] = counts.get(l, 0) + r[1]
        h = "<h2>Nano locations</h2><ul>%s</ul>" % "".join(
            "<li>%s (%d)</li>" % (_tlink("nanoloc", l, location=l), counts[l]) for l in sorted(counts))
        return dict(html=h, data=counts)
    q = _NANO_SQL + "WHERE location LIKE ? OR location LIKE ? OR location LIKE ? ORDER BY nano_name"
    rows = [_nano(r) for r in db.execute(q, (loc, "%/" + loc, loc + "/%"))]
    if not rows:
        rows = [_nano(r) for r in db.execute(_NANO_SQL + "WHERE location LIKE ? ORDER BY nano_name", ("%" + loc + "%",))]
    if not rows:
        raise ValueError("No nanos found.")
    tbl = [[str(n["ql"]), _crystal_link(n), _nano_link(n), E(", ".join(n["professions"])), E(n["location"])] for n in rows]
    return dict(html="<h2>Nanos for location '%s' (%d)</h2>%s" % (E(loc), len(rows), _table(["QL", "Crystal", "Nano", "Professions", "Location"], tbl)),
                data=[dict(nano_id=n["nano_id"], name=n["name"], ql=n["ql"], location=n["location"]) for n in rows])


def run_nanolines(db, p):
    froob = (p.get("froob") or "no") == "yes"
    f = "yes" if froob else "no"
    arg = (p.get("line") or "").strip()
    fq = " AND froob_friendly = '1'" if froob else ""
    if not arg:
        profs = [r[0] for r in db.execute("SELECT DISTINCT professions FROM ds_nanos WHERE professions NOT LIKE '%:%' ORDER BY professions")]
        if froob:
            profs = [x for x in profs if x not in ("Keeper", "Shade")]
        return dict(html="<h2>Nanolines: choose a profession</h2><ul>%s</ul>" % "".join(
            "<li>%s</li>" % _tlink("nanolines", x, line=x, froob=f) for x in profs), data=profs)
    parts = arg.split(" > ")
    first = parts.pop(0).strip()
    prof = "General" if first.lower() == "general" else prof_long(first)
    if prof is None:
        return _nanolines_show(db, arg, None, froob)
    if parts:
        return _nanolines_show(db, " > ".join(parts).strip(), prof, froob)
    if froob and prof in ("Keeper", "Shade"):
        raise ValueError("%s is not playable as froob." % prof)
    rows = db.execute("SELECT DISTINCT school, strain FROM ds_nanos WHERE professions LIKE ?" + fq + " ORDER BY school, strain", ("%" + prof + "%",)).fetchall()
    short = prof if prof == "General" else prof_short(prof)
    h, cur = "<h2>%s nanolines</h2>" % E(prof), None
    for sc, st in rows:
        if sc != cur:
            h += "<h3>%s</h3>" % E(sc)
            cur = sc
        h += "<p>%s</p>" % _tlink("nanolines", st, line="%s > %s" % (short, st), froob=f)
    return dict(html=h, data=[dict(school=a, strain=b) for a, b in rows])


def _nanolines_show(db, line, prof, froob):
    q = _NANO_SQL + "WHERE lower(strain) = lower(?)"
    params = [line]
    if prof:
        q += " AND professions LIKE ?"
        params.append("%" + prof + "%")
    if froob:
        if prof in ("Keeper", "Shade"):
            raise ValueError("%s is not playable as froob." % prof)
        q += " AND froob_friendly = '1'"
    rows = [_nano(r) for r in db.execute(q + " ORDER BY sub_strain, CAST(sort_order AS INTEGER)", params)]
    if not rows:
        raise ValueError("No nanoline named %s found%s." % (line, " for %s" % prof if prof else ""))
    h = "<h2>All %s nanos%s</h2>" % (E(rows[0]["strain"]), " for %s" % E(prof) if prof else "")
    last, tbl = None, []

    def flush():
        return _table(["QL", "Crystal", "Nano", "Location"], tbl) if tbl else ""
    for n in rows:
        if n["sub_strain"] and n["sub_strain"] != last:
            h += flush()
            tbl = []
            h += "<h3>%s</h3>" % E(n["sub_strain"])
            last = n["sub_strain"]
        tbl.append([str(n["ql"]), _crystal_link(n), _nano_link(n), E(n["location"])])
    h += flush()
    return dict(html=h, data=[dict(nano_id=n["nano_id"], name=n["name"], ql=n["ql"], sub_strain=n["sub_strain"], location=n["location"]) for n in rows])


def run_bestnanos(db, p):
    froob = (p.get("froob") or "no") == "yes"
    prof = prof_long(p.get("profession") or "")
    level = p.get("level")
    if not prof:
        raise ValueError("Enter a profession, e.g. Doctor or Doc.")
    if level is None or not 1 <= level <= 220:
        raise ValueError("Level has to be between 1 and 220.")
    long = (p.get("long") or "no") == "yes"
    q = _NANO_SQL + "WHERE professions LIKE ?" + (" AND froob_friendly = '1'" if froob else "") + \
        " ORDER BY school, strain, sub_strain, CAST(sort_order AS INTEGER)"
    best = {}
    for r in db.execute(q, ("%" + prof + "%",)):
        n = _nano(r)
        if n["min_level"] is not None and n["min_level"] > level:
            continue
        best.setdefault((n["school"], n["strain"], n["sub_strain"]), n)
    nanos = list(best.values())
    need = {k: max([n[k] or 0 for n in nanos] + [0]) for k in ("mm", "bm", "pm", "si", "ts", "mc")}
    h = "<h2>Best available nanos for a level %d %s%s (%d)</h2>" % (level, "froob-" if froob else "", E(prof), len(nanos))
    h += _kv([("Required nanoskills", " &nbsp; ".join("%s: <strong>%d</strong>" % (k.upper(), need[k]) for k in ("mm", "bm", "pm", "si", "ts", "mc")))])
    h += "<p>%s</p>" % (_tlink("bestnanos", "Show compact list", profession=prof_short(prof), level=level, froob="yes" if froob else "no", long="no")
                       if long else _tlink("bestnanos", "Show verbose list", profession=prof_short(prof), level=level, froob="yes" if froob else "no", long="yes"))
    data = []
    if not long:
        tbl = []
        for n in nanos:
            line = "%s &gt; %s%s" % (E(n["school"]), E(n["strain"]), " &gt; " + E(n["sub_strain"]) if n["sub_strain"] else "") if n["strain"] else "Unknown/General"
            tbl.append([line, _nano_link(n)])
        h += _table(["Line", "Best nano"], tbl)
    else:
        for n in nanos:
            h += _nano_head(n, froob)
            h += "<p>QL%d %s <strong>%s</strong> <span class='dim'>(%s)</span></p>" % (n["ql"], _crystal_link(n), _nano_link(n), E(n["location"]))
            reqs = ["%s: %d" % (k.upper(), n[k]) for k in ("mm", "pm", "bm", "si", "ts", "mc") if n[k] is not None]
            if n["min_level"] is not None:
                reqs.append("Level: %d" % n["min_level"])
            if n["spec"] is not None:
                reqs.append("Spec: %d" % n["spec"])
            if n["nano_deck"]:
                reqs.append("Nanodeck")
            reqs.append("Nanocost: %d" % n["nano_cost"])
            h += "<p class='dim'>%s</p>" % E(", ".join(reqs))
    for n in nanos:
        data.append(dict(school=n["school"], strain=n["strain"], sub_strain=n["sub_strain"], nano=n["name"], nano_id=n["nano_id"], ql=n["ql"],
                         location=n["location"], nanocost=n["nano_cost"]))
    return dict(html=h, data=dict(profession=prof, level=level, required_nanoskills=need, nanos=data))


# -------------------------------------------------------------------------------------------- TOOLS ----
_FROOB = dict(name="froob", label="Froob-friendly only?", type="select", options=[("no", "No, everything"), ("yes", "Yes, froob-friendly only")])
_SLOT_OPTIONS = [("list", "List the slots")] + [(n, n) for n, _ in WEAR_GROUPS if n != "Back"] + [(n, n) for n, _ in WEAR if n not in ("Neck", "Head", "Back", "Chest", "Hands", "Legs", "Feet")]
_TYPE_OPTIONS = [("", "Any (show what is available)"), ("Nanoprogram", "Nanoprograms"), ("Perk", "Perks"), ("Weapon", "Weapons")] + [
    (c, c) for c in ITEM_CATEGORIES if c != "Weapon"]

TOOLS = [
    dict(name="aiarmor", title="Alien armour tradeskill", group="Alien & endgame",
         desc="The tradeskill steps, skills and QLs to build alien armour (or a combined jacket).", bot="!aiarmor",
         fields=[dict(name="type", label="Armour type", type="select", options=AIARMOR_OPTIONS),
                 dict(name="ql", label="Target QL (1-300)", type="int", default="300")], run=run_aiarmor),
    dict(name="aigen", title="Alien City Generals", group="Alien & endgame",
         desc="What an Alien City General drops: lead viralbots and bio-material types.", bot="!aigen",
         fields=[dict(name="general", label="General", type="select", options=[(k, v[0]) for k, v in GENERALS.items()])], run=run_aigen),
    dict(name="bio", title="Identify a bio-material clump", group="Alien & endgame",
         desc="Identify a Solid Clump of Kyr'Ozch Bio-Material by its item id and show what it is for.", bot="!bio",
         fields=[dict(name="item", label="Item id(s) of the clump(s), space separated", type="text"),
                 dict(name="ql", label="QL (default 300)", type="int", default="300")], run=run_bio),
    dict(name="bioinfo", title="Bio-material types", group="Alien & endgame",
         desc="What a bio-material type is used for: Ofab armour / weapons, alien weapons, armour, serum.", bot="!bioinfo",
         fields=[dict(name="type", label="Type", type="select", options=[("list", "List all types")] + [(str(t), "Type %d (Ofab armour)" % t) for t in LE_ARMOR_TYPES]
                      + [(str(t), "Type %d (Ofab weapons)" % t) for t in LE_WEAPON_TYPES] + [("mutated", "Mutated"), ("pristine", "Pristine"), ("serum", "Viral Serum")]
                      + [(str(t), "Type %d (alien weapons)" % t) for t in AI_WEAPON_TYPES]),
                 dict(name="ql", label="QL (default 300)", type="int", default="300")], run=run_bioinfo),
    dict(name="ofabarmor", title="Ofab armour", group="Alien & endgame",
         desc="Ofab armour of a profession at a QL, with its VP cost and the bio-material that upgrades it.", bot="!ofabarmor",
         fields=[dict(name="profession", label="Profession (empty: list all)", type="text"),
                 dict(name="ql", label="QL (1, 25, 50 ... 300)", type="int", default="300")], run=run_ofabarmor),
    dict(name="ofabweapons", title="Ofab weapons", group="Alien & endgame",
         desc="The six Ofab marks of a weapon at a QL, its VP cost and the bio-material that upgrades it.", bot="!ofabweapons",
         fields=[dict(name="weapon", label="Weapon (empty: list all)", type="text"),
                 dict(name="ql", label="QL (1, 25, 50 ... 300)", type="int", default="300")], run=run_ofabweapons),
    dict(name="leprocs", title="LE procs", group="Alien & endgame", desc="The Laboratory Equipment (research) procs of a profession.", bot="!leprocs",
         fields=[dict(name="profession", label="Profession (empty: list)", type="text")], run=run_leprocs),
    dict(name="arulsaba", title="Arul Saba bracelet recipe", group="Alien & endgame",
         desc="Bracelet types, their buffs, and the full tradeskill recipe for each number of gems and side.", bot="!arulsaba",
         fields=[dict(name="type", label="Bracelet type, e.g. Desert (empty: list all)", type="text"),
                 dict(name="gems", label="Gems (0-5, empty: show the types)", type="int"),
                 dict(name="side", label="Side", type="select", options=[("left", "Left"), ("right", "Right")])], run=run_arulsaba),
    dict(name="bestql", title="Best QL / breakpoints", group="Weapons & skills",
         desc="Find the breakpoints of an item's bonus, or the highest QL you can use, by interpolating between known QLs.", bot="!bestql",
         fields=[dict(name="specs", label="QL, bonus (or requirement), QL, bonus ... e.g. 1 6 400 23", type="text"),
                 dict(name="attribute", label="Your attribute (then the numbers are requirements)", type="int"),
                 dict(name="item", label="Item id (to link each QL)", type="item")], run=run_bestql),
    dict(name="whatbuffs", title="What buffs a skill", group="Items & nanos",
         desc="Items, nanos and perks that buff a skill or ability, by slot or type.", bot="!whatbuffs / !whatbuffsfroob",
         fields=[dict(name="skill", label="Skill or ability (empty: list)", type="text"),
                 dict(name="type", label="Slot / type", type="select", options=_TYPE_OPTIONS), _FROOB], run=run_whatbuffs),
    dict(name="gridarmor", title="Grid Armor / social armour", group="Items & nanos",
         desc="Items you can wear together with social armour (Grid Armor, Battle Suits, ...), by slot.", bot="!gridarmor / !gridarmorfroob",
         fields=[dict(name="slot", label="Slot", type="select", options=_SLOT_OPTIONS), _FROOB], run=run_gridarmor),
    dict(name="nano", title="Nano search", group="Items & nanos", desc="Find a nano by name and where to get it.", bot="!nano",
         fields=[dict(name="search", label="Nano name (words; -word excludes)", type="text")], run=run_nano),
    dict(name="nanoloc", title="Nanos by location", group="Items & nanos", desc="Browse nanos by where they come from.", bot="!nanoloc",
         fields=[dict(name="location", label="Location (empty: list all)", type="text")], run=run_nanoloc),
    dict(name="nanolines", title="Nanolines", group="Items & nanos", desc="Nanos of a nanoline, or the nanolines of a profession.", bot="!nanolines / !nanolinesfroob",
         fields=[dict(name="line", label="Profession, 'Prof > Nanoline' or a nanoline name (empty: list)", type="text"), _FROOB], run=run_nanolines),
    dict(name="bestnanos", title="Best nanos", group="Items & nanos",
         desc="The best nano of every line a profession can cast at a level, with the nanoskills needed.", bot="!bestnanos / !bestnanosfroob",
         fields=[dict(name="profession", label="Profession", type="text"), dict(name="level", label="Level (1-220)", type="int"),
                 dict(name="long", label="List", type="select", options=[("no", "Compact"), ("yes", "Verbose, with requirements")]), _FROOB],
         run=run_bestnanos),
]
