# AO_Wiki_Docker

**An offline wiki for Anarchy Online**, in one Docker container: the tradeskill recipes and the
data the old in-game chat bots served, searchable in your browser and linked together.

Search once and you get recipes, items and data rows. Every item has a page that gathers everything
about it: what makes it, which boss drops it, where a nano is sold, which pocket boss drops a
symbiant, what an item buffs. Anarchy Online is near its end; this is meant to keep working after
the servers and fan sites are gone, so it never connects to the game or the internet.

- 666 tradeskill recipes (the recipe-bot recipes) and 13 bot guides
- 151 recipe texts from the game's own items (construction manuals, Engineering News, ...)
- 56 bot datasets, 506,035 rows: boss and raid loot, NPC / boss locations, spawn times, nanos and
  where to get them, symbiants and pocket bosses, implants and clusters, perks, Ofab and alien gear,
  LE procs, levels, trickle-down, whompahs, ...
- 120,835 item names, with QL ranges where known, and 9,308 item icons
- Maps: 618 zone maps (every zone, also dungeons and Jobe) with markers for places, dyna camps and tower
  sites, plus the Rubi-Ka and Shadowlands planet maps
- 56 bot lookups: the calculations the chat bots answered (`!implant`, `!burst`, `!aggdef`, `!whompah`,
  `!aiarmor`, `!bio`, `!bestql`, `!whatbuffs`, `!symbiant`, `!pocketboss`, `!dyna`, `!xp`, `!arbiter`, ...)

![The datasets index: loot, locations, nanos, implants and more, by topic](docs/screenshots/datasets.webp)

![A recipe: the ICC Shuttleport starter weapon upgrades, every item a link](docs/screenshots/recipe.webp)

## Quick start

You need [Docker](https://docs.docker.com/get-docker/) (Docker Desktop on Windows / macOS).

```sh
git clone https://github.com/CrimsonMage/AO_Wiki_Docker.git
cd AO_Wiki_Docker
docker compose up -d
```

Open **<http://localhost:8080>**. Stop it with `docker compose down`. It starts again by itself
after a reboot until you stop it.

Without Compose:

```sh
docker build -t ao-wiki .
docker run -d --name ao-wiki -p 127.0.0.1:8080:8080 ao-wiki
```

The build takes a minute: it creates the database from `data/` and checks that every file and row
made it in (`build/verify.py`); it stops with an error if anything is missing.

### Troubleshooting

- **`port is already allocated`**: something else uses 8080. Use another port on the left side,
  e.g. `-p 127.0.0.1:8081:8080` (or `"127.0.0.1:8081:8080"` in `docker-compose.yml`) and open
  <http://localhost:8081>.
- **`permission denied ... docker.sock`** (Linux): run the commands with `sudo`, or add yourself to
  the `docker` group (`sudo usermod -aG docker $USER`, then log out and in).
- **Reach it from other computers on your network**: drop `127.0.0.1:` from the port mapping.

### Without Docker

Python 3.10 or newer, standard library only:

```sh
python3 build/build_db.py archive.sqlite
python3 build/verify.py archive.sqlite
python3 app/server.py --db archive.sqlite --port 8080
```

## Using it

| Page | What it shows |
|---|---|
| `/` | Search: recipes and guides, items, and rows from the datasets |
| `/item/<id>` | Everything about one item, with its icon and QL range |
| `/level` | Level lookup: team / PvP ranges, XP / SK, mission QLs; can two levels team; who can roll QL N missions |
| `/tools` | The bot lookups, by topic; `/tool/<name>` one, with its form |
| `/maps` | Planet maps and every zone map; `/map/<zone>` a zone with numbered markers and a legend |
| `/data` | All datasets by topic; `/d/<name>` one dataset, with a filter and 50 rows per page |
| `/e/<key>` | One recipe, guide or item text, every item in it a link |

There is no JavaScript and nothing is loaded from the internet. Item ids anywhere in the data link to
their item page; zone and skill ids are shown with their names.

### JSON API

| Path | Returns |
|---|---|
| `/api/search?q=carbonum&limit=50` | `entries` (recipes / guides), `items` and `data` (dataset rows) |
| `/api/entry/recipe-101` | one entry (`recipe-N`, `text-N`, `botguide-N`, `guide-N`) with its HTML and items |
| `/api/item/121571` | an item, its QL range, and the entries and dataset rows that mention it |
| `/api/datasets` | the datasets with their columns and sizes |
| `/api/d/nanos?q=composite&p=0` | rows of one dataset, filtered, 50 per page |
| `/api/d/nanos/498` | one row |
| `/api/level/100?with=130` | a level's ranges and numbers; `can_team` / `can_pvp` with another level |
| `/api/missions/150` | the levels that can roll QL 150 missions |
| `/api/maps`, `/api/map/605` | the zone and planet maps; one zone with its points of interest |
| `/api/tools`, `/api/tool/implant?ql=200` | the lookups and their fields; one lookup's result as JSON |
| `/api/stats` | how many of each are in the archive |

### Bot lookups

Every offline calculation of Nadybot's modules, ported to Python (`app/tools/`):

- **Levels:** `level`, `xp`, `axp`, `missions`, `research`
- **Weapons, skills & perks:** `aggdef`, `aimshot`, `burst`, `fullauto`, `fastattack`, `fling`, `brawl`,
  `dimach`, `mafist`, `nanoinit`, `weapon`, `oe`, `bestql`, `perks`, `trickle`
- **Implants & symbiants:** `implant`, `ladder`, `cluster`, `premade`, `implantshoppinglist`, `symbiant`,
  `bestsymbiants`, `symbcompare`, `symbbuffs`, `pocketboss`, `spirits`
- **Alien & endgame:** `aiarmor`, `aigen`, `bio`, `bioinfo`, `ofabarmor`, `ofabweapons`, `leprocs`, `arulsaba`
- **Items & nanos:** `whatbuffs`, `whatlocks`, `gridarmor`, `nano`, `nanoloc`, `nanolines`, `bestnanos`, `disc`
- **World:** `whereis`, `spawntime`, `dyna`, `whompah`, `boss`, `bossloot`, `raidloot`, `citywave`, `arbiter`

Left out: the commands that need a live game or a bot account (online lists, orgs, timers, world boss
spawns, raids, chat), the per-user `implantdesigner`, and the fun commands.

## What is inside

| Source | Size | Folder | License |
|---|---|---|---|
| The recipe-bot recipes: the recipes written for AO-Universe's recipe bot and shipped by Budabot / Nadybot / Bebot ([Nadybot RECIPE_MODULE](https://github.com/Nadybot/Nadybot)) | 666 | `data/recipes/` | GPL-3.0 |
| The bots' datasets and guides ([Nadybot](https://github.com/Nadybot/Nadybot) modules, branch `nadybot7`, Aug 2026) | 56 datasets, 13 guides | `data/nadybot/` | GPL-3.0 |
| Item names, from the game's item database | 120,830 | `data/items.tsv` | game data © Funcom |
| The game's own recipe texts (item descriptions that are tradeskill instructions) | 151 | `data/item_texts.json` | game text © Funcom |
| Item icons, from the game's icon database | 9,308 | `data/icons/` | game art © Funcom |
| Zone maps, drawn top-down by this project from the game's terrain and collision data | 618 | `data/maps/` | drawn here; the game data in them © Funcom |
| Planet maps: Funcom's own Rubi-Ka and Shadowlands maps, stitched from the game's map tiles | 2 | `data/planet/` | game art © Funcom |

`data/recipes/SOURCE.md` and `data/nadybot/SOURCE.md` name the exact commits. The datasets, by topic:

- **Items & loot:** the bots' item table with QL ranges, boss loot and boss names, raid loot (APF,
  Pandemonium, Xan, ...), item groups, item types, item and nano-program modifiers, weapon attack /
  recharge times and specials, what locks a skill, tradeskill ingredients and where to get them.
- **Where things are:** "where is" answers for NPCs, places and bosses with coordinates, spawn times,
  dyna camps, tower sites and their bounds, playfields.
- **Nanos:** every nano with QL, school, line, professions, cost and where it is sold or dropped;
  nano lines, instruction discs, nano programs.
- **Implants & symbiants:** symbiants, pocket bosses with their blueprint mobs and drops, clusters,
  premade implants, implant requirements, the implant designer matrix, spirits.
- **Alien & endgame:** LE research procs, Ofab armour and weapons with their costs, Kyr'Ozch weapons
  and specials, Arul Saba bracers.
- **Character:** perks (every level), levels (XP / SK, team and PvP ranges, mission XP), research,
  trickle-down; skill, ability and profession ids.
- **Travel:** whompah cities and links.

### Player-made planet maps (optional, not in this repository)

The game also ships two maps drawn by players: Saavick's Map of Rubi-Ka and Peace "Dovve" Forejt's map.
They came without a license, so they are not published here. With Anarchy Online installed,
`python3 build/import_planetmaps.py "/path/to/Anarchy Online"` (needs `pip install pillow`) stitches
them into `data/planet_extra/`; a server run from the repository shows them, and `Dockerfile.full`
includes them.

### AO-Universe guides (optional, not in this repository)

AO-Universe's tradeskill guides (about 190, e.g. the Arete starter weapon upgrades) fit in too, but
they are their authors' work, so they are not published here. If you have them as
`data/aou/guides.json` (built by `build/import_data.py`), `docker build -f Dockerfile.full -t
ao-wiki:full .` makes an image that includes them. Please ask AO-Universe
(<https://www.ao-universe.com>) before sharing such an image.

## Updating or extending the data

- `build/build_db.py` builds the database from `data/` in a few seconds; `build/verify.py` re-reads
  every source and checks each file, row and needed column.
- A new bot dataset: put the CSV under `data/nadybot/` and describe it in `build/datasets.py`
  (title, which columns hold item / zone / skill ids, what names a row). `verify.py` fails until
  every CSV there is described.
- `build/import_data.py` turns exported item names / item texts (plain Lua tables) into
  `data/items.tsv` and `data/item_texts.json`.

## License

- **This project's own work** (`app/` except `app/tools/`, `build/`, the Dockerfiles, `docker-compose.yml`,
  the docs, the zone map drawings) is released into the **public domain** under [The Unlicense](LICENSE):
  do whatever you want with it.
- **`app/tools/`** (the bot lookups) is ported from Nadybot's code and is therefore **GPL-3.0**.
- **`data/recipes/` and `data/nadybot/`** come from the Nadybot project and stay under the
  **GPL-3.0** (`LICENSE` in each folder). You can use and share them freely; changed versions of
  those files must stay GPL-3.0 and say where they came from.
- **Item names, texts, icons and the planet maps** are Anarchy Online game data, © Funcom. The zone map
  images are drawn by this project from game data.

Unofficial fan project, not affiliated with Funcom, Nadybot or AO-Universe. Thanks to the Nadybot,
Budabot and Bebot authors, the recipe writers, and AO-Universe.
