"""The bot datasets in the archive (data/nadybot/, Nadybot's module data, GPL-3.0).
Column names follow the nadybot7 branch's files (2026-08: the implant tables moved to snake_case);
build/verify.py fails when a column named here is missing.

Each entry:  name       table / URL name                    file    path under data/nadybot/
             title, group, desc                             what it is, for people
             item       columns holding AO item ids (linked to /item/<id>, and listed on item pages)
             pf         columns holding playfield ids (shown with the zone name)
             skill      columns holding skill / stat ids (shown with the skill name)
             label      columns that name a row in search results
             search     rows go into the global search
             cols, sep  for files without a header line (perks.csv)
             join       extra columns resolved at build time: {new_col: (key_col, other_dataset, key, value)}
"""

GROUPS = ["Items & loot", "Where things are", "Nanos", "Implants & symbiants", "Alien & endgame", "Character", "Travel", "Reference"]

DATASETS = [
    # ---------------------------------------------------------------- items & loot
    dict(name="items_ql", file="ITEMS_MODULE/aodb.csv", group="Items & loot", title="Item database (QL ranges)",
         desc="Every item with its low / high id and QL range, slot and flags.", item=["lowid", "highid"], label=["name"], search=False),
    dict(name="boss_names", file="ITEMS_MODULE/boss_namedb.csv", group="Items & loot", title="Bosses",
         desc="Named bosses of Rubi-Ka and the Shadowlands.", label=["bossname"], search=True),
    dict(name="boss_loot", file="ITEMS_MODULE/boss_lootdb.csv", group="Items & loot", title="Boss loot",
         desc="What each named boss drops.", item=["aoid"], label=["bossname", "itemname"], search=True,
         join={"bossname": ("bossid", "boss_names", "bossid", "bossname")}),
    dict(name="raid_loot", file="LOOT_MODULE/raid_loot.csv", group="Items & loot", title="Raid loot",
         desc="Loot tables of the raids (APF, Pandemonium, Xan, DB, ...).", item=["aoid"], label=["raid", "name"], search=True),
    dict(name="item_groups", file="ITEMS_MODULE/item_groups.csv", group="Items & loot", title="Item groups",
         desc="Items that belong together (armour sets, upgrade lines).", item=["item_id"], label=["groupname"], search=False,
         join={"groupname": ("group_id", "item_group_names", "group_id", "name")}),
    dict(name="item_group_names", file="ITEMS_MODULE/item_group_names.csv", group="Items & loot", title="Item group names",
         desc="Names of the item groups.", label=["name"], search=True),
    dict(name="item_types", file="ITEMS_MODULE/item_types.csv", group="Items & loot", title="Item types",
         desc="Armor, Weapon or Misc for every item id (nadybot7, 106,592 items).", item=["item_id"], label=["item_type"], search=False),
    dict(name="item_categories", file="ITEMS_MODULE/item_categories.csv", group="Items & loot", title="Item categories (by slot)",
         desc="The older, finer item classification: Head, Back, Fingers, Hud, Util, Deck, Weapon, ... (40,025 items).",
         item=["item_id"], label=["item_type"], search=False),
    dict(name="item_buffs", file="ITEMS_MODULE/item_buffs.csv", group="Items & loot", title="Item modifiers",
         desc="The skill / stat modifiers each item gives.", item=["item_id"], skill=["attribute_id"], label=["attribute_id"], search=False),
    dict(name="weapon_attributes", file="SKILLS_MODULE/weapon_attributes.csv", group="Items & loot", title="Weapon attributes",
         desc="Attack and recharge times and special attacks of every weapon.", item=["id"], label=["id"], search=False),
    dict(name="what_locks", file="WHATLOCKS_MODULE/what_locks.csv", group="Items & loot", title="What locks a skill",
         desc="Items that lock a skill when used, and for how long.", item=["item_id"], skill=["skill_id"], label=["skill_id"], search=False),
    dict(name="ingredients", file="RECIPE_MODULE/ingredient.csv", group="Items & loot", title="Tradeskill ingredients",
         desc="Common tradeskill ingredients and where to get them.", item=["aoid"], label=["name"], search=True),
    # ---------------------------------------------------------------- where things are
    dict(name="playfields", file="HELPBOT_MODULE/playfields.csv", group="Where things are", title="Playfields",
         desc="Zone ids and names.", label=["long_name"], search=True),
    dict(name="whereis", file="WHEREIS_MODULE/whereis.csv", group="Where things are", title="Where is ...",
         desc="NPCs, places and bosses with directions and coordinates.", pf=["playfield_id"], label=["name"], search=True),
    dict(name="spawntimes", file="WHEREIS_MODULE/spawntime.csv", group="Where things are", title="Spawn times",
         desc="Respawn times of bosses and named mobs.", label=["mob"], search=True),
    dict(name="dynacamps", file="HELPBOT_MODULE/dynadb.csv", group="Where things are", title="Dyna camps",
         desc="Dynamic boss camps: mob, level range and coordinates per zone.", pf=["playfield_id"], label=["mob"], search=True),
    dict(name="tower_sites", file="TOWER_MODULE/tower_site.csv", group="Where things are", title="Tower sites",
         desc="Notum Wars tower fields: zone, QL range, coordinates.", pf=["playfield_id"], label=["site_name"], search=True),
    dict(name="tower_bounds", file="TOWER_MODULE/tower_site_bounds.csv", group="Where things are", title="Tower site bounds",
         desc="The area of each tower field.", pf=["playfield_id"], label=["site_number"], search=False),
    # ---------------------------------------------------------------- nanos
    dict(name="nanos", file="NANO_MODULE/nanos.csv", group="Nanos", title="Nanos and where to get them",
         desc="Every nano: crystal, QL, school, line, professions, cost and where it is sold or dropped.",
         item=["crystal_id"], label=["nano_name", "location"], search=True),
    dict(name="nano_lines", file="NANO_MODULE/nano_lines.csv", group="Nanos", title="Nano lines",
         desc="Nano strains (lines) by id.", label=["name"], search=True),
    dict(name="nano_discs", file="DISC_MODULE/discs.csv", group="Nanos", title="Instruction discs",
         desc="Which instruction disc makes which nano crystal.", item=["disc_id", "crystal_id"], label=["disc_name", "crystal_name"], search=True),
    dict(name="nano_buffs", file="ITEMS_MODULE/buffs.csv", group="Nanos", title="Nano programs (buffs)",
         desc="Nano programs: NCU, cost, school, line, duration, ranges.", item=["nano_id", "disc_id"], label=["name"], search=True),
    # ---------------------------------------------------------------- implants & symbiants
    dict(name="symbiants", file="IMPLANT_MODULE/Symbiant.csv", group="Implants & symbiants", title="Symbiants",
         desc="Every symbiant with QL, slot and requirements.", item=["id"], label=["name"], search=True),
    dict(name="pocket_bosses", file="IMPLANT_MODULE/pocketboss.csv", group="Implants & symbiants", title="Pocket bosses",
         desc="Pocket bosses, where they and their blueprint mobs are, and the symbiants they drop.",
         item=["itemid"], label=["pb", "line", "slot"], search=True),
    dict(name="clusters", file="IMPLANT_MODULE/Cluster.csv", group="Implants & symbiants", title="Implant clusters",
         desc="Cluster names and their NP requirements.", skill=["skill_id"], label=["long_name"], search=True),
    dict(name="premade_implants", file="IMPLANT_MODULE/premade_implant.csv", group="Implants & symbiants", title="Premade implants",
         desc="The premade implants sold in stores (by slot, profession, ability and clusters).", label=["implant_type_id"], search=False),
    dict(name="implant_requirements", file="IMPLANT_MODULE/implant_requirements.csv", group="Implants & symbiants", title="Implant requirements",
         desc="Treatment and ability needed per implant QL.", label=["ql"], search=False),
    dict(name="implant_matrix", file="IMPLANT_MODULE/ImplantMatrix.csv", group="Implants & symbiants", title="Implant matrix",
         desc="Implant designer table: requirements and bonuses by QL.", label=["id"], search=False),
    dict(name="implant_types", file="IMPLANT_MODULE/ImplantType.csv", group="Implants & symbiants", title="Implant slots", desc="Implant slot ids.", label=["Name"], search=False),
    dict(name="cluster_slots", file="IMPLANT_MODULE/ClusterImplantMap.csv", group="Implants & symbiants", title="Cluster slots",
         desc="Which cluster fits which implant slot (shiny / bright / faded).", label=["cluster_id"], search=False),
    dict(name="effect_types", file="IMPLANT_MODULE/EffectTypeMatrix.csv", group="Implants & symbiants", title="Cluster effect ranges", desc="Cluster bonus ranges by effect type.", label=["name"], search=False),
    dict(name="effect_values", file="IMPLANT_MODULE/EffectValue.csv", group="Implants & symbiants", title="Cluster effect values", desc="QL 200 values of cluster effects.", label=["name"], search=False),
    dict(name="symbiant_abilities", file="IMPLANT_MODULE/SymbiantAbilityMatrix.csv", group="Implants & symbiants", title="Symbiant ability requirements",
         desc="Ability requirements per symbiant.", item=["symbiant_id"], label=["symbiant_id"], search=False),
    dict(name="symbiant_clusters", file="IMPLANT_MODULE/SymbiantClusterMatrix.csv", group="Implants & symbiants", title="Symbiant bonuses",
         desc="Skill bonuses per symbiant.", item=["symbiant_id"], label=["symbiant_id"], search=False),
    dict(name="symbiant_professions", file="IMPLANT_MODULE/SymbiantProfessionMatrix.csv", group="Implants & symbiants", title="Symbiant professions",
         desc="Which professions can use each symbiant.", item=["symbiant_id"], label=["symbiant_id"], search=False),
    dict(name="spirits", file="SPIRITS_MODULE/spiritsdb.csv", group="Implants & symbiants", title="Spirits",
         desc="Shadowlands spirits: QL, slot, level and ability requirements.", item=["id"], label=["name"], search=True),
    # ---------------------------------------------------------------- alien & endgame
    dict(name="le_procs", file="ALIEN_MODULE/leprocs.csv", group="Alien & endgame", title="LE research procs",
         desc="Legacy of the Xan research procs per profession: trigger, chance, effect.", label=["profession", "name"], search=True),
    dict(name="ofab_armor", file="ALIEN_MODULE/ofabarmor.csv", group="Alien & endgame", title="Ofab armour",
         desc="Ofab armour per profession and slot, with the upgrade it takes.", item=["lowid", "highid"], label=["profession", "name"], search=True),
    dict(name="ofab_armor_cost", file="ALIEN_MODULE/ofabarmorcost.csv", group="Alien & endgame", title="Ofab armour cost", desc="Victory points per slot and QL.", label=["slot", "ql"], search=False),
    dict(name="ofab_armor_types", file="ALIEN_MODULE/ofabarmortype.csv", group="Alien & endgame", title="Ofab armour types", desc="Which armour type each profession uses.", label=["profession"], search=False),
    dict(name="ofab_weapons", file="ALIEN_MODULE/ofabweapons.csv", group="Alien & endgame", title="Ofab weapons", desc="Ofab weapon types.", label=["name"], search=True),
    dict(name="ofab_weapons_cost", file="ALIEN_MODULE/ofabweaponscost.csv", group="Alien & endgame", title="Ofab weapon cost", desc="Victory points per QL.", label=["ql"], search=False),
    dict(name="alien_weapons", file="ALIEN_MODULE/alienweapons.csv", group="Alien & endgame", title="Kyr'Ozch weapons", desc="Alien weapon types from bio-material.", label=["name"], search=True),
    dict(name="alien_weapon_specials", file="ALIEN_MODULE/alienweaponspecials.csv", group="Alien & endgame", title="Kyr'Ozch weapon specials", desc="Special attacks per alien weapon type.", label=["specials"], search=False),
    dict(name="arulsaba", file="RECIPE_MODULE/arulsaba.csv", group="Alien & endgame", title="Arul Saba bracers", desc="The Arul Saba bracer lines and their buffs.", label=["name"], search=True),
    dict(name="arulsaba_buffs", file="RECIPE_MODULE/arulsaba_buffs.csv", group="Alien & endgame", title="Arul Saba bracer buffs",
         desc="Bracer gems by level: left and right hand items.", item=["left_aoid", "right_aoid"], label=["name"], search=True),
    # ---------------------------------------------------------------- character
    dict(name="perks", file="SKILLS_MODULE/perks.csv", group="Character", title="Perks",
         desc="Every perk level: expansion, item, required level, professions, buffs, action and description.",
         cols=["name", "perk_level", "expansion", "aoid", "required_level", "professions", "buffs", "action", "resistances", "description"],
         sep="|", item=["aoid"], label=["name", "perk_level"], search=True),
    dict(name="levels", file="LEVEL_MODULE/levels.csv", group="Character", title="Levels",
         desc="Per level: team and PvP ranges, XP / SK, tokens, mission XP and more.", label=["level"], search=False),
    dict(name="research", file="HELPBOT_MODULE/research.csv", group="Character", title="Research levels", desc="SK per research level and level cap.", label=["level"], search=False),
    dict(name="trickle", file="TRICKLE_MODULE/trickle.csv", group="Character", title="Trickle-down",
         desc="How much each ability point adds to each skill.", skill=["skill_id"], label=["skill", "groupName"], search=True,
         join={"skill": ("skill_id", "skills", "id", "name")}),
    dict(name="skills", file="ITEMS_MODULE/skills.csv", group="Reference", title="Skill ids", desc="Skill / stat ids and names.", label=["name"], search=False),
    dict(name="skill_alias", file="ITEMS_MODULE/skill_alias.csv", group="Reference", title="Skill aliases", desc="Short names players use for skills.", label=["name"], search=False),
    dict(name="abilities", file="IMPLANT_MODULE/Ability.csv", group="Reference", title="Ability ids", desc="The six abilities.", label=["Name"], search=False),
    dict(name="professions", file="IMPLANT_MODULE/Profession.csv", group="Reference", title="Profession ids", desc="Profession ids.", label=["Name"], search=False),
    dict(name="cluster_types", file="IMPLANT_MODULE/ClusterType.csv", group="Reference", title="Cluster types", desc="Shiny / bright / faded.", label=["Name"], search=False),
    # ---------------------------------------------------------------- travel
    dict(name="whompah_cities", file="WHOMPAH_MODULE/whompah_cities.csv", group="Travel", title="Whompah cities",
         desc="Cities with a whompah, by zone and faction.", label=["city_name", "zone"], search=True),
    dict(name="whompah_links", file="WHOMPAH_MODULE/whompah_cities_rel.csv", group="Travel", title="Whompah links",
         desc="Which whompah goes where.", label=["from_city", "to_city"], search=False,
         join={"from_city": ("city1_id", "whompah_cities", "id", "city_name"), "to_city": ("city2_id", "whompah_cities", "id", "city_name")}),
]

# the bot's own guide texts (GUIDE_MODULE): stored as entries next to recipes
BOT_GUIDES = "GUIDE_MODULE/guides"
