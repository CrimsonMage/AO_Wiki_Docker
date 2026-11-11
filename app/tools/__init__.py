"""Bot lookups ("tools"): the calculations the Anarchy Online chat bots answered (!implant, !burst,
!whompah, ...), ported from Nadybot (GPL-3.0). Every file in this package is GPL-3.0, see the README.

Each module defines TOOLS, a list of dicts:

    dict(name="burst",                      # URL name: /tool/burst, /api/tool/burst
         title="Burst calculator",          # shown on /tools and the form
         group="Weapons & skills",          # section on /tools
         desc="Burst recharge and the Burst skill needed to cap it.",
         bot="!burst",                      # the bot command it replaces
         fields=[dict(name="attack", label="Attack time (s)", type="float", default="1.0"),
                 dict(name="recharge", label="Recharge time (s)", type="float"),
                 dict(name="burst_delay", label="Burst delay (from the weapon)", type="int"),
                 dict(name="skill", label="Your Burst skill", type="int")],
         run=fn)                            # fn(db, p) -> dict(html=<safe HTML snippet>, data=<JSON-able>)

field types: "int", "float", "text", "select" (with options=[(value, label), ...]), "item" (an item id).
`p` holds the submitted values already converted (missing optional values are None). `db` is a
read-only sqlite3 connection to the archive (row_factory = sqlite3.Row): the ds_<name> tables of
build/datasets.py, items(id, name), item_icons(item_id, icon), nano_programs(id, name).
run() raises ValueError("message") for bad input; the page shows the message.
HTML: escape every value (html.escape); use the site's classes: <table class='kv'> for key/value,
<div class='scroll'><table>...</table></div> for tables, <p class='verdict'>, <span class='dim'>,
item links <a class='item' href='/item/ID'>Name</a>. No JavaScript, no outside URLs.
"""
import importlib
import pkgutil

# one set of sections on /tools, whatever group name a module used
GROUP = {"Character": "Weapons, skills & perks", "Weapons & skills": "Weapons, skills & perks",
         "Items & loot": "Items & nanos", "Nanos": "Items & nanos"}
TOOLS = {}
for _m in pkgutil.iter_modules(__path__):
    if _m.name.startswith("_"):
        continue
    _mod = importlib.import_module(__name__ + "." + _m.name)
    for _t in getattr(_mod, "TOOLS", []):
        TOOLS[_t["name"]] = dict(_t, module=_m.name, group=GROUP.get(_t["group"], _t["group"]))
