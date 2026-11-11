# Implants, clusters, symbiants, pocket bosses and spirits: !implant, !cluster, !premade, !ladder,
# !implantshoppinglist, !symbiant, !bestsymbiants, !symbcompare, !symbbuffs, !pocketboss, !spirits.
#
# Ported from Nadybot (https://github.com/Nadybot/Nadybot, branch nadybot7, modules IMPLANT_MODULE and
# SPIRITS_MODULE; authors Nadyita, Tyrence, Imoutochan, Jaqueme and others).
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 of the License.
# It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GPL-3.0 for details.
"""Implant, symbiant, pocket boss and spirit lookups (GPL-3.0, ported from Nadybot)."""
import html
import math
import re
import urllib.parse

E = html.escape

# ------------------------------------------------------------------ constants ----
GRADES = ("shiny", "bright", "faded")          # ClusterGrade::cases() order
GRADE_ID = {"faded": 1, "bright": 2, "shiny": 3}

# implant slots in Nadybot's ImplantSlot order: (type id, short name, display name, pocket boss/symbiant name)
SLOTS = [(1, "eye", "Eye", "Ocular"), (2, "head", "Head", "Brain"), (3, "ear", "Ear", "Ear"),
         (11, "rarm", "Right Arm", "Right Arm"), (4, "chest", "Chest", "Chest"), (8, "larm", "Left Arm", "Left Arm"),
         (12, "rwrist", "Right Wrist", "Right Wrist"), (5, "waist", "Waist", "Waist"),
         (9, "lwrist", "Left Wrist", "Left Wrist"), (13, "rhand", "Right Hand", "Right Hand"),
         (6, "legs", "Legs", "Thigh"), (10, "lhand", "Left Hand", "Left Hand"), (7, "feet", "Feet", "Feet")]
SLOT_BY_ID = {s[0]: s for s in SLOTS}
SLOT_BY_SHORT = {s[1]: s for s in SLOTS}
SLOT_ALIASES = {"eye": 1, "eyes": 1, "ocular": 1, "head": 2, "brain": 2, "ear": 3, "ears": 3,
                "rarm": 11, "rightarm": 11, "chest": 4, "larm": 8, "leftarm": 8, "rwrist": 12, "rightwrist": 12,
                "waist": 5, "lwrist": 9, "leftwrist": 9, "rhand": 13, "righthand": 13, "leg": 6, "legs": 6,
                "thigh": 6, "lhand": 10, "lefthand": 10, "feet": 7, "foot": 7}
SLOT_OPTIONS = [("", "(any)")] + [(s[1], s[2]) for s in SLOTS]

# AO profession ids as used by the symbiant / premade tables (these differ from the alphabetical id table)
PROFESSIONS = {1: "Soldier", 2: "Martial Artist", 3: "Engineer", 4: "Fixer", 5: "Agent", 6: "Adventurer",
               7: "Trader", 8: "Bureaucrat", 9: "Enforcer", 10: "Doctor", 11: "Nano-Technician",
               12: "Meta-Physicist", 14: "Keeper", 15: "Shade"}
PROF_ALIASES = {"sol": 1, "soldier": 1, "ma": 2, "martialartist": 2, "eng": 3, "engi": 3, "engineer": 3,
                "fix": 4, "fixer": 4, "agent": 5, "adv": 6, "advy": 6, "adventurer": 6, "trader": 7,
                "crat": 8, "bureaucrat": 8, "enf": 9, "enforcer": 9, "doc": 10, "doctor": 10,
                "nt": 11, "nanotechnician": 11, "mp": 12, "metaphysicist": 12, "metap": 12,
                "keeper": 14, "keep": 14, "shade": 15}
PROF_OPTIONS = [(str(k), v) for k, v in sorted(PROFESSIONS.items(), key=lambda kv: kv[1])]

# ------------------------------------------------------------------ helpers ----


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _slot_from_name(s):
    return SLOT_ALIASES.get(_norm(s))


def _prof_from_name(s):
    n = _norm(s)
    if n in PROF_ALIASES:
        return PROF_ALIASES[n]
    hits = [k for k, v in PROFESSIONS.items() if _norm(v).startswith(n)] if len(n) >= 3 else []
    return hits[0] if len(hits) == 1 else None


def _item(iid, name):
    return "<a class='item' href='/item/%d'>%s</a>" % (iid, E(name))


def _kv(rows):
    return "<table class='kv'>%s</table>" % "".join("<tr><th>%s</th><td>%s</td></tr>" % (E(str(k)), v) for k, v in rows)


def _table(head, rows):
    return "<div class='scroll'><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>" % (
        "".join("<th>%s</th>" % E(h) for h in head),
        "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in rows))


def _tool_link(tool, label, **params):
    return "<a href='/tool/%s?%s'>%s</a>" % (tool, urllib.parse.urlencode(params), E(label))


def _skills(db):
    """{skill id: (name, unit)} and {skill id: [lowercase names + aliases]}."""
    names, words = {}, {}
    for r in db.execute("SELECT id, name, unit FROM ds_skills"):
        i = _int(r["id"], -1)
        names[i] = (r["name"], r["unit"] or "")
        words.setdefault(i, []).append(r["name"].lower())
    try:
        for r in db.execute("SELECT id, name FROM ds_skill_alias"):
            words.setdefault(_int(r["id"], -1), []).append(r["name"].lower())
    except Exception:
        pass
    return names, words


def match_skills(db, text):
    """Skill ids matching a search text (name, alias, or every word a prefix of a word in the name)."""
    names, words = _skills(db)
    q = re.sub(r"[^a-z0-9 %]", " ", text.lower()).split()
    if not q:
        return []
    flat = " ".join(q)
    exact = [i for i, ws in words.items() if any(re.sub(r"[^a-z0-9 %]", " ", w).split() == q or w == flat for w in ws)]
    if exact:
        return sorted(exact, key=lambda i: names.get(i, ("",))[0])
    out = []
    for i, ws in words.items():
        for w in ws:
            parts = re.sub(r"[^a-z0-9 %]", " ", w).split()
            if all(any(p.startswith(t) for p in parts) for t in q):
                out.append(i)
                break
    return sorted(out, key=lambda i: names.get(i, ("",))[0])


def _cluster_name_by_skill(db):
    out = {}
    for r in db.execute("SELECT skill_id, long_name, official_name FROM ds_clusters WHERE cluster_id <> '0'"):
        if r["skill_id"] not in (None, ""):
            out[_int(r["skill_id"])] = (r["long_name"], r["official_name"])
    return out

# ------------------------------------------------------------------ implant formulas ----


def interpolate(x1, x2, y1, y2, x):
    """Nadybot Util::interpolate: linear interpolation, rounded half away from zero."""
    if x1 == x2:
        return y2
    v = (y2 - y1) / (x2 - x1) * (x - x1) + y1  # the PHP expression, so .5 cases round the same way
    return int(math.floor(v + 0.5)) if v >= 0 else -int(math.floor(-v + 0.5))


def _band(ql, low, high):
    """low=(y1,y2) for QL 1-200, high=(y1,y2) for QL 201-300 (Implant::getBuff / getRequirement)."""
    if ql <= 200:
        return interpolate(1, 200, low[0], low[1], ql)
    if ql <= 300:
        return interpolate(201, 300, high[0], high[1], ql)
    raise ValueError("%d is not a valid implant QL." % ql)


_REQ = {  # (jobe, kind): (low band, high band)
    (False, "ability"): ((6, 404), (426, 1095)), (False, "treatment"): ((11, 951), (1001, 2051)),
    (False, "title"): None,
    (True, "ability"): ((16, 414), (476, 1231)), (True, "treatment"): ((11, 951), (1001, 2051)),
    (True, "title"): ((3, 4), (5, 6)),
}
_BUFF = {  # (type, grade): (low band, high band)
    ("skill", "faded"): ((2, 42), (42, 57)), ("skill", "bright"): ((3, 63), (63, 85)),
    ("skill", "shiny"): ((6, 105), (106, 141)),
    ("ability", "faded"): ((2, 22), (22, 29)), ("ability", "bright"): ((3, 33), (33, 44)),
    ("ability", "shiny"): ((5, 55), (55, 73)),
}


def get_requirement(kind, jobe, ql):
    b = _REQ[(jobe, kind)]
    return 0 if b is None else _band(ql, *b)


def get_buff(typ, grade, ql):
    return _band(ql, *_BUFF[(typ, grade)])


def required_np(jobe, grade, ql):
    if jobe:
        m = {"shiny": 6.25, "bright": 4.75, "faded": 3.25} if ql <= 200 else {"shiny": 6.75, "bright": 5.25, "faded": 3.75}
    else:
        m = {"shiny": 4, "bright": 3, "faded": 2} if ql <= 200 else {"shiny": 5.25, "bright": 4.35, "faded": 2.55}
    return int(math.floor(ql * m[grade]))


def cluster_min_ql(ql, grade):
    v = int(math.floor(ql * {"shiny": 0.86, "bright": 0.84, "faded": 0.82}[grade]))
    return max(min(v, 300), 1)


def highest_equippable(ability, treatment, jobe):
    ql = 1
    while ql <= 300:
        if get_requirement("ability", jobe, ql) > ability or get_requirement("treatment", jobe, ql) > treatment:
            break
        ql += 1
    return min(300, ql - 1)


def bonus_ql_range(typ, grade, bonus):
    """(min, max) QL giving exactly this bonus, or None."""
    found_min, found_max, stat = 0, 300, 0
    for ql in range(1, 301):
        stat = get_buff(typ, grade, ql)
        if stat > bonus:
            return (found_min, found_max)
        if stat == bonus:
            found_max = ql
            if found_min == 0:
                found_min = ql
    return (found_min, found_max) if stat == bonus else None

# ------------------------------------------------------------------ implant ----


def _implant_block(jobe, ql):
    """HTML + data for one regular or jobe implant at a QL."""
    ab, tr = get_requirement("ability", jobe, ql), get_requirement("treatment", jobe, ql)
    title = get_requirement("title", jobe, ql)
    req = [("Ability", str(ab)), ("Treatment", str(tr))]
    if title > 0:
        req.append(("Title level", str(title)))
    data = dict(ql=ql, jobe=jobe, ability_req=ab, treatment_req=tr, title_level=title, clusters={})
    rows = []
    for label, typ in (("Ability", "ability"), ("Skill", "skill")):
        for grade in GRADES:
            buff = get_buff(typ, grade, ql)
            rng = bonus_ql_range(typ, grade, buff)
            if rng is None:
                raise ValueError("Cannot calculate QL for giving +%d" % buff)
            nxt = ""
            if rng[1] < 300:
                nxt = "%d / %d" % (get_requirement("ability", jobe, rng[1] + 1), get_requirement("treatment", jobe, rng[1] + 1))
            rows.append(["%s cluster" % label, grade.capitalize(), "+%d" % buff, "QL %d&ndash;%d" % rng, nxt or "<span class='dim'>max</span>"])
            data["clusters"]["%s_%s" % (typ, grade)] = dict(bonus=buff, ql_min=rng[0], ql_max=rng[1])
    build = [(g.capitalize(), "%d NP" % required_np(jobe, g, ql)) for g in GRADES]
    if jobe:
        clean = "Jobe implants cannot be cleaned."
    elif ql > 200:
        clean = "Refined implants cannot be cleaned."
    else:
        clean = "%d Nano Programming, %d Break &amp; Entry" % (ql, int(math.floor(4.75 * ql)))
    floor_ql = 201 if ql >= 201 else 1
    mins = [(g.capitalize(), "QL %d" % max(floor_ql, cluster_min_ql(ql, g))) for g in GRADES]
    if jobe:
        name = "Implant with a shiny Jobe cluster and all other clusters filled" if ql >= 201 else "Jobe implant"
    else:
        name = "Implant"
    h = "<h3>QL %d %s</h3>" % (ql, E(name))
    h += "<h4>Requirements to wear</h4>" + _kv([(k, E(v)) for k, v in req])
    h += "<h4>Cluster bonuses</h4>" + _table(
        ["Type", "Slot", "Bonus", "QL range with this bonus", "Ability / Treatment for the next step up"], rows)
    h += "<h4>Requirements to build</h4>" + _kv([(k, E(v)) for k, v in build])
    h += "<h4>Requirements to clean</h4><p>%s</p>" % clean
    h += "<h4>Minimum cluster QL</h4>" + _kv([(k, E(v)) for k, v in mins])
    data["build_np"] = {g: required_np(jobe, g, ql) for g in GRADES}
    data["min_cluster_ql"] = {g: max(floor_ql, cluster_min_ql(ql, g)) for g in GRADES}
    return h, data


def run_implant(db, p):
    ql, ab, tr = p.get("ql"), p.get("ability"), p.get("treatment")
    out, data, intro = [], {}, ""
    if ql is not None:
        if ql < 1 or ql > 300:
            raise ValueError("Implants only exist in QLs between 1 and 300.")
        qls = [(False, ql)] + ([(True, ql)] if ql >= 100 else [])
        intro = "<p class='verdict'>QL %d implant details%s.</p>" % (ql, " and jobe implant details" if ql >= 100 else "")
    elif ab is not None and tr is not None:
        reg, jobe = highest_equippable(ab, tr, False), highest_equippable(ab, tr, True)
        if reg == 0:
            return dict(html="<p class='verdict'>Your pathetic stats aren't even enough for a QL 1 implant.</p>",
                        data=dict(regular_ql=0, jobe_ql=jobe))
        qls = [(False, reg)] + ([(True, jobe)] if jobe >= 100 else [])
        intro = "<p class='verdict'>With %d Ability and %d Treatment, the highest possible implant is QL %d%s.</p>" % (
            ab, tr, reg, " and the highest possible jobe implant is QL %d" % jobe if jobe >= 100 else "")
        data.update(regular_ql=reg, jobe_ql=jobe)
    else:
        raise ValueError("Give either a QL, or your Ability and Treatment.")
    blocks = []
    for jobe, q in qls:
        h, d = _implant_block(jobe, q)
        out.append(h)
        blocks.append(d)
    data["implants"] = blocks
    return dict(html=intro + "".join(out), data=data)

# ------------------------------------------------------------------ cluster ----


def run_cluster(db, p):
    s = p.get("skill")
    if not s:
        rows = db.execute("SELECT long_name FROM ds_clusters WHERE cluster_id <> '0' AND long_name <> '' ORDER BY long_name").fetchall()
        h = "<p>%d clusters. Search for one by skill name.</p><ul>%s</ul>" % (
            len(rows), "".join("<li>%s</li>" % _tool_link("cluster", r[0], skill=r[0]) for r in rows))
        return dict(html=h, data=[r[0] for r in rows])
    ids = match_skills(db, s)
    if not ids:
        raise ValueError("No skills found that match '%s'." % s)
    clusters = []
    for r in db.execute("SELECT cluster_id, long_name, skill_id FROM ds_clusters WHERE cluster_id <> '0'"):
        if _int(r["skill_id"], -1) in ids:
            clusters.append(r)
    if not clusters:
        raise ValueError("No clusters found that match '%s'." % s)
    out, data = [], []
    for c in sorted(clusters, key=lambda r: r["long_name"]):
        res = db.execute("SELECT implant_type_id, cluster_type_id FROM ds_cluster_slots WHERE cluster_id = ?", (c["cluster_id"],)).fetchall()
        res = sorted(res, key=lambda r: (-_int(r[1]), _int(r[0])))
        gname = {3: "Shiny", 2: "Bright", 1: "Faded"}
        rows = [[gname.get(_int(r[1]), "?"), E(SLOT_BY_ID[_int(r[0])][2]) if _int(r[0]) in SLOT_BY_ID else E(r[0])] for r in res]
        out.append("<h3>%s</h3>%s" % (E(c["long_name"]), _table(["Cluster slot", "Implant slot"], rows) if rows else "<p class='dim'>No slots.</p>"))
        data.append(dict(cluster=c["long_name"], slots=[dict(grade=r[0], slot=SLOT_BY_ID[_int(x[0])][2] if _int(x[0]) in SLOT_BY_ID else x[0])
                                                        for r, x in zip(rows, res)]))
    return dict(html="<p class='verdict'>%d clusters match '%s'.</p>%s" % (len(clusters), E(s), "".join(out)), data=data)

# ------------------------------------------------------------------ premade ----


def run_premade(db, p):
    s = (p.get("search") or "").strip()
    if not s:
        raise ValueError("Enter a profession, an implant slot or a skill (e.g. agent, rwrist, comp lit).")
    sk, names = None, _skills(db)[0]
    prof, slot = _prof_from_name(s), _slot_from_name(s)
    where, args, label = "", [], s
    if prof is not None:
        where, args, label = "WHERE CAST(profession_id AS INTEGER) = ?", [prof], PROFESSIONS[prof]
    elif slot is not None:
        where, args, label = "WHERE CAST(implant_type_id AS INTEGER) = ?", [slot], SLOT_BY_ID[slot][2]
    else:
        sk = match_skills(db, s)
        if not sk:
            raise ValueError("No results found.")
    clusters = {r["cluster_id"]: r for r in db.execute("SELECT cluster_id, long_name, skill_id FROM ds_clusters")}

    def cname(cid):
        c = clusters.get(cid)
        return "N/A" if (cid in ("0", "", None) or not c or not c["long_name"]) else c["long_name"]
    rows = db.execute("SELECT * FROM ds_premade_implants %s ORDER BY CAST(implant_type_id AS INTEGER)" % where, args).fetchall()
    res = []
    for r in rows:
        if sk is not None:
            skill_ids = [_int(clusters[r[k]]["skill_id"], -1) if r[k] in clusters else -1
                         for k in ("shiny_cluster_id", "bright_cluster_id", "faded_cluster_id")]
            if not any(i in sk for i in skill_ids):
                continue
        res.append(r)
    if not res:
        raise ValueError("No results found.")
    by_slot, data = {}, []
    for r in res:
        by_slot.setdefault(_int(r["implant_type_id"]), []).append(r)
    out = []
    for sid, rs in by_slot.items():
        rows_html = []
        for r in rs:
            pn = PROFESSIONS.get(_int(r["profession_id"]), "Profession %s" % r["profession_id"])
            ab = names.get(_int(r["ability_id"]), ("Ability %s" % r["ability_id"],))[0]
            rows_html.append([E(pn), E(ab), E(cname(r["shiny_cluster_id"])), E(cname(r["bright_cluster_id"])), E(cname(r["faded_cluster_id"]))])
            data.append(dict(slot=SLOT_BY_ID[sid][2] if sid in SLOT_BY_ID else sid, profession=pn, ability=ab,
                             shiny=cname(r["shiny_cluster_id"]), bright=cname(r["bright_cluster_id"]), faded=cname(r["faded_cluster_id"])))
        out.append("<h3>%s</h3>%s" % (E(SLOT_BY_ID[sid][2] if sid in SLOT_BY_ID else str(sid)),
                                      _table(["Profession", "Ability", "Shiny", "Bright", "Faded"], rows_html)))
    return dict(html="<p class='verdict'>Premade implants for '%s': %d.</p>%s" % (E(label), len(res), "".join(out)), data=data)

# ------------------------------------------------------------------ ladder ----


def run_ladder(db, p):
    typ = (p.get("type") or "treatment").lower()
    value = p.get("start")
    if value is None:
        raise ValueError("Enter your starting value.")
    if typ in ("treat", "treatment"):
        typ = "skill"
        if value < 11:
            raise ValueError("Base treatment must be at least 11.")
        get_max = lambda v: highest_equippable(10000, v, False)
        label = "Treatment"
    else:
        typ = "ability"
        if value < 6:
            raise ValueError("Base ability must be at least 6.")
        get_max = lambda v: highest_equippable(v, 10000, False)
        label = "Ability"
    start, current, steps, added = value, {}, [], True
    while added:
        added = False
        for grade in GRADES:
            cur = current.get(grade)
            temp = value - get_buff(typ, grade, cur) if cur is not None else value
            new = get_max(temp)
            new_buff = get_buff(typ, grade, new)
            if cur is None or new_buff > get_buff(typ, grade, cur):
                added = True
                if cur is not None:
                    value -= get_buff(typ, grade, cur)
                    steps.append(("Remove", grade, cur, None, None, None))
                cur = new
                value += new_buff
                rng = bonus_ql_range(typ, grade, new_buff) or (cur, cur)
                steps.append(("Add", grade, cur, rng[0], get_requirement("treatment", False, cur), get_requirement("ability", False, cur)))
                current[grade] = cur
    rows = []
    for act, grade, q, mn, t, a in steps:
        if act == "Remove":
            rows.append(["Remove", grade.capitalize(), "QL %d" % q, "", "", ""])
        else:
            rows.append(["<strong>Add</strong>", grade.capitalize(), "QL %d" % q, "from QL %d" % mn, str(t), str(a)])
    h = "<p class='verdict'>Laddering from %d to %d %s.</p>" % (start, value, label)
    h += _table(["Step", "Cluster", "Implant QL", "Same bonus from", "Treatment needed", "Ability needed"], rows)
    h += "<p class='dim'>The base value is what you have with all buffs, perks and equipment but without implants. Inspired by a command written by Lucier of the same name.</p>"
    return dict(html=h, data=dict(type=label, start=start, end=value, steps=[dict(action=s[0], grade=s[1], ql=s[2], min_ql=s[3]) for s in steps]))

# ------------------------------------------------------------------ shopping list ----


def run_shopping(db, p):
    default_ql = p.get("ql") or 300
    if not 1 <= default_ql <= 300:
        raise ValueError("Implants only exist in QLs between 1 and 300.")
    by_skill = _cluster_name_by_skill(db)
    slots_ok = {}
    for r in db.execute("SELECT c.skill_id, s.implant_type_id, s.cluster_type_id FROM ds_cluster_slots s JOIN ds_clusters c ON c.cluster_id = s.cluster_id"):
        slots_ok.setdefault((_int(r[1]), _int(r[2])), set()).add(_int(r[0], -1))
    implants, lists, warn = [], {g: [] for g in GRADES}, []
    for sid, short, long_, _pb in SLOTS:
        txt = p.get(short)
        if not txt:
            continue
        m = re.match(r"^\s*(?:ql\s*(\d+)\s*[:;]\s*)?(.*)$", txt, re.I)
        ql = int(m.group(1)) if m.group(1) else default_ql
        if not 1 <= ql <= 300:
            raise ValueError("%s: implants only exist in QLs between 1 and 300." % long_)
        parts = [x.strip() for x in m.group(2).replace(";", ",").split(",")]
        parts += [""] * (3 - len(parts))
        add, refined = False, "Refined " if ql > 200 else ""
        for grade, part in zip(GRADES, parts[:3]):
            if not part:
                continue
            ids = [i for i in match_skills(db, part) if i in by_skill]
            if not ids:
                raise ValueError("%s %s: no cluster found for '%s'." % (long_, grade, part))
            sid_ = ids[0]
            if sid_ not in slots_ok.get((sid, GRADE_ID[grade]), set()):
                warn.append("%s cannot take %s as a %s cluster." % (long_, by_skill[sid_][0], grade))
            name = by_skill[sid_][1]
            if name.endswith("Jobe"):
                name = name.replace(" Jobe", " %sJobe Cluster" % refined)
            else:
                name += " %sCluster" % refined
            cql = cluster_min_ql(ql, grade)
            if ql > 200 and cql < 201:
                cql = 201
            lists[grade].append("%s (QL %d+)" % (name, cql))
            add = True
        if add:
            implants.append("%s Implant Refined Empty (QL %d)" % (long_, ql) if ql > 200 else "Basic %s Implant (QL %d)" % (long_, ql))
    if not implants:
        return dict(html="<p class='verdict'>Nothing to buy.</p>", data=dict())
    out = ""
    if warn:
        out += "<p class='verdict'>%s</p>" % E(" ".join(warn))
    for title, items in (("Empty implants", implants), ("Shiny clusters", lists["shiny"]),
                         ("Bright clusters", lists["bright"]), ("Faded clusters", lists["faded"])):
        if items:
            out += "<h3>%s</h3><ul>%s</ul>" % (title, "".join("<li>%s</li>" % E(x) for x in sorted(items)))
    return dict(html=out, data=dict(implants=sorted(implants), shiny=sorted(lists["shiny"]), bright=sorted(lists["bright"]),
                                    faded=sorted(lists["faded"])))

# ------------------------------------------------------------------ symbiants ----


def _pb_name(r):
    t, line, slot, iid = r["type"], r["line"], r["slot"], _int(r["itemid"])
    return t, line, slot, iid


def _symb_title(db, r):
    t, line, slot, iid = _pb_name(r)
    if t == "Special":
        row = db.execute("SELECT name FROM items WHERE id = ?", (iid,)).fetchone()
        return row[0] if row else "Unknown"
    if line in ("Alpha", "Beta"):
        return "Xan %s Symbiant, %s Unit %s" % (slot, t, line)
    return "%s %s Symbiant, %s Unit Aban" % (line, slot, t)


def _pb_search(db, search):
    s = search.strip()
    if s.lower() == "tnh":
        s = "The Night Heart"
    row = db.execute("SELECT pb FROM ds_pocket_bosses WHERE pb = ? COLLATE NOCASE ORDER BY pb LIMIT 1", (s,)).fetchone()
    if row:
        return [row[0]]
    words = [w for w in s.split() if w]
    if not words:
        return []
    like = " AND ".join("pb LIKE ? ESCAPE '\\'" for _ in words)
    args = ["%%%s%%" % w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") for w in words]
    return [r[0] for r in db.execute("SELECT DISTINCT pb FROM ds_pocket_bosses WHERE %s ORDER BY pb" % like, args)]


def _pb_detail(db, name):
    rows = db.execute("SELECT * FROM ds_pocket_bosses WHERE pb = ? ORDER BY CAST(ql AS INTEGER), CAST(id AS INTEGER)", (name,)).fetchall()
    last = rows[-1]
    info = [("Location", E(last["pb_location"]) + ("" if last["bp_location"] == last["pb_location"] else ", " + E(last["bp_location"]))),
            ("Found on", "%s, level %s" % (E(last["bp_mob"]), E(last["bp_lvl"])))]
    lis = []
    for r in rows:
        li = _item(_int(r["itemid"]), _symb_title(db, r))
        if _int(r["ql"]) != 1:
            li += " (QL %s)" % E(r["ql"])
        lis.append("<li>%s</li>" % li)
    h = "<h3>Remains of %s</h3>%s<h4>Symbiants</h4><ul>%s</ul>" % (E(name), _kv(info), "".join(lis))
    return h, dict(pb=name, location=last["pb_location"], blueprint_location=last["bp_location"], mob=last["bp_mob"],
                   level=last["bp_lvl"], symbiants=[dict(itemid=_int(r["itemid"]), ql=_int(r["ql"]), type=r["type"], slot=r["slot"], line=r["line"]) for r in rows])


def run_pocketboss(db, p):
    s = p.get("name")
    if not s:
        raise ValueError("Enter (part of) a pocket boss name.")
    names = _pb_search(db, s)
    if not names:
        raise ValueError("Could not find any pocket bosses that matched your search criteria.")
    if len(names) == 1:
        h, d = _pb_detail(db, names[0])
        return dict(html=h, data=d)
    h = "<p class='verdict'>Search results for '%s' (%d).</p><ul>%s</ul>" % (
        E(s), len(names), "".join("<li>%s</li>" % _tool_link("pocketboss", n, name=n) for n in names))
    return dict(html=h, data=names)


def run_symbiant(db, p):
    args = [a for a in (p.get("arg1"), p.get("arg2"), p.get("arg3")) if a]
    if not args:
        raise ValueError("Give 1-3 of: a slot (rhand), a type (artillery) or a line (living, alpha, beta).")
    lines = [r[0] for r in db.execute("SELECT DISTINCT line FROM ds_pocket_bosses")]
    slot = typ = line = None
    for a in args:
        sid = _slot_from_name(a)
        if sid is not None:
            slot = SLOT_BY_ID[sid][3]
            continue
        hit = [l for l in lines if l.lower() == a.lower()]
        if hit:
            line = hit[0]
            continue
        t = a[:3].lower()
        tmap = {"art": "Artillery", "sup": "Support", "inf": "Infantry", "ext": "Extermination", "con": "Control"}
        if t in tmap:
            typ = tmap[t]
            continue
        hit = [l for l in lines if l.lower().startswith(a.lower())]
        if len(hit) == 1:
            line = hit[0]
            continue
        raise ValueError("I cannot find any symbiant line, location or type '%s'." % a)
    cond, ar = [], []
    for col, v in (("slot", slot), ("type", typ), ("line", line)):
        if v:
            cond.append("%s = ? COLLATE NOCASE" % col)
            ar.append(v)
    rows = db.execute("SELECT * FROM ds_pocket_bosses %s ORDER BY CAST(ql AS INTEGER) DESC, line = 'Alpha' DESC, line = 'Beta' DESC, type" %
                      ("WHERE " + " AND ".join(cond) if cond else ""), ar).fetchall()
    if not rows:
        raise ValueError("Could not find any symbiants that matched your search criteria.")
    groups = {}
    for r in rows:
        groups.setdefault(_int(r["itemid"]), []).append(r)
    out, data = [], []
    for iid, rs in groups.items():
        r = rs[0]
        head = _item(iid, _symb_title(db, r)) + (" (QL %s)" % E(r["ql"]) if _int(r["ql"]) != 1 else "")
        bosses = ", ".join(_tool_link("pocketboss", x["pb"], name=x["pb"]) for x in rs)
        out.append("<li>%s<br><span class='dim'>Found on</span> %s</li>" % (head, bosses))
        data.append(dict(itemid=iid, name=_symb_title(db, r), ql=_int(r["ql"]), bosses=[x["pb"] for x in rs]))
    return dict(html="<p class='verdict'>Symbiant search results: %d symbiants.</p><ul class='results'>%s</ul>" % (len(groups), "".join(out)), data=data)


def run_bestsymbiants(db, p):
    level, prof = p.get("level"), _int(p.get("profession"), 0)
    if level is None or prof not in PROFESSIONS:
        raise ValueError("Enter a level and a profession.")
    rows = db.execute(
        "SELECT s.* FROM ds_symbiants s JOIN ds_symbiant_professions spm ON spm.symbiant_id = s.id "
        "WHERE CAST(spm.profession_id AS INTEGER) = ? AND CAST(s.level_req AS INTEGER) <= ? AND s.name NOT LIKE 'Prototype%' "
        "ORDER BY s.name LIKE '%Alpha' DESC, s.name LIKE '%Beta' DESC, CAST(s.ql AS INTEGER) DESC", (prof, level)).fetchall()
    configs = {}  # unit -> slot id -> [rows]
    for r in rows:
        unit = r["unit"] or "Special"
        configs.setdefault(unit, {}).setdefault(_int(r["slot_id"]), []).append(r)
    if not configs:
        return dict(html="<p class='verdict'>No symbiants for a level %d %s.</p>" % (level, E(PROFESSIONS[prof])), data=[])
    out, data = [], []
    for sid, short, long_, pb in SLOTS:
        lines, ids = [], []
        for unit, cfg in configs.items():
            ss = cfg.get(sid, [])[:3]
            if not ss:
                continue
            ids.append(_int(ss[0]["id"]))
            links = []
            for s in ss:
                text = "QL%s" % s["ql"]
                m = re.search(r"\b(Alpha|Beta)$", s["name"])
                if unit == "Special":
                    text = s["name"]
                elif m:
                    text = m.group(1)
                links.append(_item(_int(s["id"]), text))
            lines.append(["<strong>%s</strong>" % E(unit), " &gt; ".join(links)])
            data.append(dict(slot=long_, unit=unit, symbiants=[dict(id=_int(s["id"]), name=s["name"], ql=_int(s["ql"])) for s in ss]))
        if lines:
            cmp_ = " " + _tool_link("symbcompare", "compare", ids=" ".join(map(str, ids))) if len(ids) > 1 else ""
            out.append("<h3>%s%s</h3>%s" % (E(long_), cmp_, _table(["Unit", "Best first"], lines)))
    return dict(html="<p class='verdict'>Best 3 symbiants in each slot for a level %d %s.</p>%s" % (level, E(PROFESSIONS[prof]), "".join(out)), data=data)


def run_symbbuffs(db, p):
    s = p.get("skill")
    if not s:
        raise ValueError("Enter a skill.")
    ids = match_skills(db, s)
    if not ids:
        raise ValueError("No skill matching '%s' found." % s)
    names = _skills(db)[0]
    blocks, data = [], {}
    for sk in ids:
        rows = db.execute(
            "SELECT DISTINCT sym.* FROM ds_symbiants sym JOIN ds_symbiant_clusters scm ON scm.symbiant_id = sym.id "
            "JOIN ds_clusters c ON c.cluster_id = scm.cluster_id WHERE CAST(c.skill_id AS INTEGER) = ? "
            "ORDER BY CAST(sym.slot_id AS INTEGER), sym.name", (sk,)).fetchall()
        if not rows:
            continue
        by_slot = {}
        for r in rows:
            by_slot.setdefault(_int(r["slot_id"]), []).append(r)
        part = []
        for sid, rs in by_slot.items():
            lines = []
            by_unit = {}
            for r in rs:
                if not r["unit"]:
                    lines.append("<li>%s</li>" % _item(_int(r["id"]), r["name"]))
                else:
                    by_unit.setdefault(r["unit"], []).append(r)
            for unit, us in by_unit.items():
                where = []
                if any(_int(x["ql"]) < 300 or ("Beta" not in x["name"] and "Alpha" not in x["name"]) for x in us):
                    where.append("regular")
                if any(_int(x["ql"]) == 300 and "Beta" in x["name"] for x in us):
                    where.append("beta")
                if any(_int(x["ql"]) == 300 and "Alpha" in x["name"] for x in us):
                    where.append("alpha")
                lines.append("<li>%s <span class='dim'>(%s)</span></li>" % (E(unit), E(", ".join(where))))
            part.append("<h4>%s</h4><ul>%s</ul>" % (E(SLOT_BY_ID[sid][2] if sid in SLOT_BY_ID else str(sid)), "".join(lines)))
        nm = names.get(sk, ("Skill %d" % sk,))[0]
        blocks.append("<h3>%s</h3>%s" % (E(nm), "".join(part)))
        data[nm] = [dict(id=_int(r["id"]), name=r["name"], ql=_int(r["ql"]), unit=r["unit"]) for r in rows]
    if not blocks:
        raise ValueError("No symbiants buff '%s'." % s)
    return dict(html="<p class='verdict'>Symbiants buffing '%s'.</p>%s" % (E(s), "".join(blocks)), data=data)


def run_symbcompare(db, p):
    ids = [int(x) for x in re.findall(r"\d+", p.get("ids") or "")][:12]
    names = _skills(db)[0]
    items = []
    for i in ids:
        row = db.execute("SELECT name FROM items WHERE id = ?", (i,)).fetchone()
        if not row:
            continue
        buffs = {}
        for b in db.execute("SELECT attribute_id, amount FROM ds_item_buffs WHERE item_id = ?", (str(i),)):
            buffs[_int(b[0], -1)] = _int(b[1])
        items.append((i, row[0], buffs))
    if len(items) < 2:
        raise ValueError("You have to give at least 2 symbiants (item ids) for a comparison.")
    count = {}
    for _i, _n, bs in items:
        for k in bs:
            count[k] = count.get(k, 0) + 1
    order = sorted(count, key=lambda k: (count[k], names.get(k, ("Skill %d" % k,))[0]))
    rows = []
    for k in order:
        nm, unit = names.get(k, ("Skill %d" % k, ""))
        cells = ["<strong>%s</strong>" % E(nm) if count[k] < len(items) else E(nm)]
        for _i, _n, bs in items:
            cells.append("%+d%s" % (bs[k], E(unit)) if k in bs else "<span class='dim'>&ndash;</span>")
        rows.append(cells)
    h = "<p class='verdict'>Bold skills are not buffed by every item.</p>"
    h += _table(["Skill"] + [i[1] for i in items], rows)
    return dict(html=h, data=[dict(id=i, name=n, buffs={names.get(k, (str(k),))[0]: v for k, v in bs.items()}) for i, n, bs in items])

# ------------------------------------------------------------------ spirits ----


def run_spirits(db, p):
    name, slot, lo, hi = p.get("name"), p.get("slot"), p.get("ql_min"), p.get("ql_max")
    cond, args = [], []
    if name:
        sid = _slot_from_name(name)
        short = SLOT_BY_ID[sid][1].capitalize() if sid else name
        if sid and not slot:
            cond.append("(spot = ? COLLATE NOCASE)")
            args.append(short)
        else:
            cond.append("name LIKE ?")
            args.append("%%%s%%" % name)
    if slot:
        cond.append("spot = ? COLLATE NOCASE")
        args.append(slot)
    if lo is not None:
        if hi is None:
            hi = lo
        if lo < 1 or hi > 300 or lo > hi:
            raise ValueError("Invalid QL range specified.")
        cond.append("CAST(ql AS INTEGER) BETWEEN ? AND ?")
        args += [lo, hi]
    elif hi is not None:
        cond.append("CAST(ql AS INTEGER) <= ?")
        args.append(hi)
    if not cond:
        raise ValueError("Give a name, a slot or a QL (range).")
    order = "CAST(ql AS INTEGER), CAST(level AS INTEGER)" if lo is not None else "CAST(level AS INTEGER), CAST(ql AS INTEGER)"
    rows = db.execute("SELECT * FROM ds_spirits WHERE %s ORDER BY %s" % (" AND ".join(cond), order), args).fetchall()
    if not rows:
        raise ValueError("No spirits found. Valid slots: Head, Eye, Ear, Chest, Larm, Rarm, Waist, Lwrist, Rwrist, Legs, Lhand, Rhand, Feet.")
    out, data = [], []
    for r in rows[:400]:
        sid = _slot_from_name(r["spot"])
        sl = SLOT_BY_ID[sid][2] if sid else r["spot"]
        it = db.execute("SELECT name FROM items WHERE id = ?", (_int(r["id"]),)).fetchone()
        nm = it[0] if it else r["name"]
        out.append([_item(_int(r["id"]), nm), E(r["ql"]), E(sl), E(r["level"]), E(r["agility"])])
        data.append(dict(id=_int(r["id"]), name=nm, ql=_int(r["ql"]), slot=sl, min_level=_int(r["level"]), agility_sense=_int(r["agility"])))
    more = " Showing the first 400." if len(rows) > 400 else ""
    return dict(html="<p class='verdict'>%d spirits.%s</p>%s" % (len(rows), more, _table(["Spirit", "QL", "Slot", "Minimum level", "Agility/Sense needed"], out)), data=data)

# ------------------------------------------------------------------ registry ----


_SG = "Implants & symbiants"
TOOLS = [
    dict(name="implant", title="Implant requirements", group=_SG, bot="!implant",
         desc="Requirements, cluster bonuses and build needs of an implant QL, or the highest QL for your Ability and Treatment.",
         fields=[dict(name="ql", label="Implant QL (1-300)", type="int"),
                 dict(name="ability", label="Your Ability (instead of QL)", type="int"),
                 dict(name="treatment", label="Your Treatment (instead of QL)", type="int")], run=run_implant),
    dict(name="cluster", title="Cluster finder", group=_SG, bot="!cluster",
         desc="Which clusters buff a skill, and in which implant slots they fit. Leave empty to list all clusters.",
         fields=[dict(name="skill", label="Skill or ability", type="text")], run=run_cluster),
    dict(name="premade", title="Premade implants", group=_SG, bot="!premade",
         desc="Premade implants from the booths, by profession, slot or modifier.",
         fields=[dict(name="search", label="Profession, slot or skill", type="text")], run=run_premade),
    dict(name="ladder", title="Implant ladder", group=_SG, bot="!ladder",
         desc="The sequence of implants to ladder up to the most Treatment or Ability.",
         fields=[dict(name="type", label="Ladder", type="select", options=[("treatment", "Treatment"), ("ability", "Ability")]),
                 dict(name="start", label="Base value (without implants)", type="int")], run=run_ladder),
    dict(name="implantshoppinglist", title="Implant shopping list", group=_SG, bot="!implantshoppinglist",
         desc="What to buy for an implant build. Per slot, enter the clusters as 'shiny, bright, faded' (optionally 'ql 250: ...').",
         fields=[dict(name="ql", label="Default QL", type="int", default="300")] +
                [dict(name=s[1], label="%s: shiny, bright, faded" % s[2], type="text") for s in SLOTS], run=run_shopping),
    dict(name="symbiant", title="Symbiant sources", group=_SG, bot="!symbiant",
         desc="Which pocket bosses drop a symbiant: any of slot, type and line (e.g. brain alpha arti).",
         fields=[dict(name="arg1", label="Slot, type or line", type="text"),
                 dict(name="arg2", label="Another (optional)", type="text"),
                 dict(name="arg3", label="Another (optional)", type="text")], run=run_symbiant),
    dict(name="bestsymbiants", title="Best symbiants", group=_SG, bot="!bestsymbiants",
         desc="The three best symbiants per slot and unit for a profession and level.",
         fields=[dict(name="level", label="Level", type="int"),
                 dict(name="profession", label="Profession", type="select", options=PROF_OPTIONS)], run=run_bestsymbiants),
    dict(name="symbcompare", title="Symbiant comparison", group=_SG, bot="!symbcompare",
         desc="Compare the bonuses of symbiants (item ids).",
         fields=[dict(name="ids", label="Symbiant item ids, separated by spaces", type="text")], run=run_symbcompare),
    dict(name="symbbuffs", title="Symbiants buffing a skill", group=_SG, bot="!symbbuffs",
         desc="All symbiants that buff a skill, by slot and unit.",
         fields=[dict(name="skill", label="Skill", type="text")], run=run_symbbuffs),
    dict(name="pocketboss", title="Pocket bosses", group=_SG, bot="!pocketboss",
         desc="Where a pocket boss is found and which symbiants it drops.",
         fields=[dict(name="name", label="Pocket boss name (or part of it)", type="text")], run=run_pocketboss),
    dict(name="spirits", title="Spirits", group=_SG, bot="!spirits",
         desc="Search spirits by name, slot and QL (range).",
         fields=[dict(name="name", label="Name or type (e.g. grave)", type="text"),
                 dict(name="slot", label="Slot", type="select", options=[("", "(any)")] + [(x[1].capitalize(), x[2]) for x in SLOTS]),
                dict(name="ql_min", label="QL (from)", type="int"),
                 dict(name="ql_max", label="QL to (optional)", type="int")], run=run_spirits),
]
