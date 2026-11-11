"""Level lookup: !level (team / PvP ranges, XP/SK, missions, tokens, max AI/LE level, mob levels).
Ported from Nadybot (https://github.com/Nadybot/Nadybot, LEVEL_MODULE), GPL-3.0."""
import html


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _level(db, n):
    r = db.execute('SELECT * FROM "ds_levels" WHERE CAST(level AS INTEGER) = ?', (n,)).fetchone()
    if not r:
        raise ValueError("Level must be between 1 and 220.")
    return {k: r[k] for k in r.keys()}


def _num(n):
    return "{:,}".format(n)


def run_level(db, p):
    n = p["level"]
    if n is None:
        raise ValueError("Enter a level between 1 and 220.")
    L = _level(db, n)
    E = html.escape
    xp = _int(L["xpsk"])
    unit = "SK" if n >= 200 else "XP"
    summary = "L %s: Team %s-%s | PvP %s-%s | Missions %s | %s token(s)" % (
        L["level"], L["teamMin"], L["teamMax"], L["pvpMin"], L["pvpMax"], L["missions"], L["tokens"])
    rows = [("Team with", "levels %s-%s" % (L["teamMin"], L["teamMax"])),
            ("PvP with", "levels %s-%s" % (L["pvpMin"], L["pvpMax"])),
            ("%s to next level" % unit, _num(xp) if xp else "none (maximum level)"),
            ("Mission QLs", L["missions"].replace(",", ", ")),
            ("Tokens", L["tokens"]),
            ("Daily mission XP", _num(_int(L["daily_mission_xp"])) if L["daily_mission_xp"] else "-"),
            ("Max AI level", L["max_ai_level"]),
            ("Max LE level", L["max_le_level"]),
            ("Mobs that give XP", "levels %s-%s" % (L["mob_min"], L["mob_max"]))]
    h = "<p class='verdict'>%s</p><table class='kv'>%s</table>" % (
        E(summary), "".join("<tr><th>%s</th><td>%s</td></tr>" % (E(k), E(str(v))) for k, v in rows))
    return dict(html=h, data=dict(L, summary=summary))


TOOLS = [dict(name="level", title="Level", group="Levels", desc="Team and PvP ranges, XP / SK, mission QLs, tokens, max AI / LE level and mob levels of a character level.",
              bot="!level", fields=[dict(name="level", label="Level", type="int", default="100")], run=run_level)]
