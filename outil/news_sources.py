"""
News CS2 - collecte GRATUITE des infos de la semaine (aucun abonnement, aucune clé).

Sources (toutes gratuites et autorisées) :
  - Classement mondial officiel de Valve (VRS) : github.com/ValveSoftware/counter-strike_regional_standings
  - Liquipedia (API MediaWiki, contenu sous licence CC BY-SA 3.0 : crédité dans chaque vidéo)
      règles respectées : User-Agent identifiable, gzip, 1 page "parse" toutes les 30 s, rien de plus.
  - Wikimedia Commons : photos de joueurs sous licence libre (CC BY / CC BY-SA / CC0), créditées.

Utilisé par news_make.py. Lancé seul : python news_sources.py  -> diagnostic des sources.
"""
import html as htmllib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zlib
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "news")
VERSION = "1.4"

LIQUI_API = "https://liquipedia.net/counterstrike/api.php"
LIQUI_WIKI = "https://liquipedia.net/counterstrike/"
VRS_RAW = "https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/live/{y}/{f}"
VRS_LIST = "https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/live/{y}"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
STEAM_NEWS = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"      # actu officielle de CS2 (appid 730)
MATCHES_PAGE = "Liquipedia:Matches"
FEMALE_PAGES = ["Female_Tournaments", "Portal:Female_Tournaments", "Women's_Tournaments"]

PARSE_GAP = 31          # secondes entre deux "parse" Liquipedia (leur règle : 1 toutes les 30 s)
TIER_PAGES = {"S": "S-Tier_Tournaments", "A": "A-Tier_Tournaments", "B": "B-Tier_Tournaments", "C": "C-Tier_Tournaments"}
TRANSFER_PAGE = "Portal:Transfers"
FREE_LICENSES = re.compile(r"^(cc[ -]by(-sa)?[ -]?\d|cc0|public domain|pd\b)", re.I)

CONTACT = ""            # rempli par news_make (nom de la chaîne) pour le User-Agent
DEBUG_DIR = None        # dossier où garder les pages brutes (diagnostic)
_last_parse = [0.0]


def ua():
    who = CONTACT or "streamer"
    return f"MexicStudio-News/{VERSION} (outil perso de YouTubeur CS2 : {who}; usage hebdomadaire, quelques pages)"


def fetch(url, params=None, timeout=40, raw=False):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {"User-Agent": ua(), "Accept-Encoding": "gzip"}
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]     # (sur GitHub Actions : pas de limite partagée)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = zlib.decompress(data, 16 + zlib.MAX_WBITS)    # gzip (zlib est toujours dans l'exe)
    return data if raw else data.decode("utf-8", errors="replace")


def save_debug(name, text):
    if DEBUG_DIR:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        with open(os.path.join(DEBUG_DIR, name), "w", encoding="utf-8") as f:
            f.write(text)


def strip_tags(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


# =====================================================================
#  Classement mondial Valve (VRS)
# =====================================================================
def _vrs_files(year):
    """Noms des fichiers standings_global_AAAA_MM_JJ.md publiés (API GitHub, sinon on devine les dates)."""
    try:
        items = json.loads(fetch(VRS_LIST.format(y=year), timeout=20))
        return sorted(i["name"] for i in items if i["name"].startswith("standings_global_"))
    except Exception:
        return []


def _vrs_guess(today):
    """Sans l'API GitHub : le classement sort en début de mois (1er lundi). On essaie les 10 premiers jours."""
    found = []
    for back in range(0, 3):
        m = (today.replace(day=1) - timedelta(days=1)).replace(day=1) if back else today.replace(day=1)
        if back == 2:
            m = (m - timedelta(days=1)).replace(day=1)
        for d in range(1, 11):
            day = m.replace(day=d)
            if day > today:
                break
            name = f"standings_global_{day:%Y_%m_%d}.md"
            try:
                fetch(VRS_RAW.format(y=day.year, f=name), timeout=15)
                found.append(name)
                break
            except Exception:
                continue
        if len(found) >= 2:
            break
    return sorted(found)


def parse_vrs(md):
    rows = []
    for line in md.splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|", line)
        if m:
            rows.append({"rank": int(m.group(1)), "points": int(m.group(2)), "team": m.group(3).strip(),
                         "roster": [p.strip() for p in m.group(4).split(",") if p.strip()]})
    return rows


def vrs_rankings(today=None):
    today = today or date.today()
    files = _vrs_files(today.year)
    if len(files) < 2:
        files = sorted(set(files + _vrs_files(today.year - 1)))
    if not files:
        files = _vrs_guess(today)
    if not files:
        raise RuntimeError("classement Valve introuvable")
    files = files[-2:]
    out = []
    for name in files:
        y = name.split("_")[2]
        md = fetch(VRS_RAW.format(y=y, f=name))
        save_debug("vrs_" + name, md)
        d = datetime.strptime(name[len("standings_global_"):-3], "%Y_%m_%d").date()
        out.append({"date": d.isoformat(), "rows": parse_vrs(md)})
    cur = out[-1]
    prev = out[-2] if len(out) > 1 else None
    if prev:
        before = {r["team"]: r["rank"] for r in prev["rows"]}
        for r in cur["rows"]:
            r["prev"] = before.get(r["team"])
    return {"date": cur["date"], "prev_date": prev["date"] if prev else None, "rows": cur["rows"][:150]}


# =====================================================================
#  Liquipedia
# =====================================================================
def liqui_parse(page):
    wait = PARSE_GAP - (time.time() - _last_parse[0])
    if wait > 0 and _last_parse[0]:
        time.sleep(wait)
    _last_parse[0] = time.time()
    data = json.loads(fetch(LIQUI_API, {"action": "parse", "page": page, "prop": "text", "format": "json",
                                        "formatversion": "2", "disablelimitreport": "1"}))
    if "error" in data:
        raise RuntimeError(f"Liquipedia : {data['error'].get('info', data['error'])}")
    html = data["parse"]["text"]
    save_debug("liquipedia_" + re.sub(r"\W+", "_", page) + ".html", html)
    return html


def liqui_wikitext(page):
    """Le texte source d'une page (les matchs y sont écrits avec le modèle {{Match ...}}, plus stable que le HTML)."""
    wait = PARSE_GAP - (time.time() - _last_parse[0])
    if wait > 0 and _last_parse[0]:
        time.sleep(wait)
    _last_parse[0] = time.time()
    data = json.loads(fetch(LIQUI_API, {"action": "parse", "page": page, "prop": "wikitext", "format": "json",
                                        "formatversion": "2"}))
    if "error" in data:
        raise RuntimeError(f"Liquipedia : {data['error'].get('info', data['error'])}")
    wt = data["parse"]["wikitext"]
    save_debug("wikitext_" + re.sub(r"\W+", "_", page) + ".txt", wt)
    return wt


def _norm_team(s):
    s = re.sub(r"[^a-z0-9]+", "", (s or "").lower())
    return re.sub(r"^team|esports$|gaming$", "", s) or s


def _same_team(a, b):
    """« vit » = Vitality, « navi » / « nv » = Natus Vincere... (Liquipedia écrit souvent un raccourci dans les matchs)."""
    na, nb = _norm_team(a), _norm_team(b)
    if not na or not nb:
        return False
    if na == nb or (min(len(na), len(nb)) >= 3 and (na in nb or nb in na)):
        return True
    words = [w for w in re.split(r"[^a-z0-9]+", (b or "").lower()) if w and w != "team"]
    initials = "".join(w[0] for w in words)
    return len(words) >= 2 and na == initials


def _params(txt):
    out = {}
    for part in txt.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def _map_score(p, side):
    """Score d'une carte pour l'équipe 1 ou 2 : « score1=13 », sinon les mi-temps (t1t + t1ct + prolongations o1t1t...)."""
    if p.get("score" + side, "").isdigit():
        return int(p["score" + side])
    tot, seen = 0, False
    for k, v in p.items():
        if re.fullmatch(r"(o\d+)?t%s(t|ct)" % side, k) and v.strip().isdigit():
            tot += int(v)
            seen = True
    return tot if seen else None


def _match_maps(b):
    maps = []
    for _, inner in sorted(re.findall(r"\|\s*map(\d+)\s*=\s*\{\{\s*Map\s*\|([^{}]*)\}\}", b), key=lambda x: int(x[0])):
        p = _params(inner)
        if p.get("finished") == "skip":
            continue
        s1, s2 = _map_score(p, "1"), _map_score(p, "2")
        if p.get("map") and s1 is not None and s2 is not None and (s1 or s2):
            maps.append((p["map"].replace("de_", "").replace("Dust II", "Dust2").title().replace("Dust2", "Dust2"), s1, s2))
    return maps


def parse_final(wikitext, winner, runner_up):
    """La finale winner / runner_up et ses cartes. Les équipes sont souvent en raccourci (« vit ») : si aucun match
    ne correspond aux noms, on prend le dernier match du tableau final (Grand Final) et le gagnant d'après les cartes."""
    blocks = re.split(r"\{\{\s*Match\b", wikitext)[1:]
    best, last_bracket = None, None
    for pos, b in enumerate(blocks):
        opp = dict(re.findall(r"\|\s*opponent([12])\s*=\s*\{\{\s*TeamOpponent\s*\|\s*([^|}]*)", b))
        maps = _match_maps(b)
        if len(opp) < 2 or not maps:
            continue
        bo = int((re.search(r"\|\s*bestof\s*=\s*(\d+)", b) or [0, 0])[1] or 0)
        if _same_team(opp["1"], winner) and _same_team(opp["2"], runner_up):
            side = "1"
        elif _same_team(opp["2"], winner) and _same_team(opp["1"], runner_up):
            side = "2"
        else:
            side = None
        if side:
            cand = (bo, len(maps), pos)
            if not best or cand > best[0]:
                best = (cand, maps, side)
    if not best:
        # repli : le dernier « RxM1 » (le plus grand x) avec des cartes jouées
        heads = list(re.finditer(r"\n\|\s*R(\w+?)M(\w+)\s*=", wikitext))
        for k, m in enumerate(heads):
            if m.group(2) != "1" or not m.group(1).isdigit():
                continue
            end = heads[k + 1].start() if k + 1 < len(heads) else len(wikitext)
            seg = wikitext[m.end():end]
            maps = _match_maps(seg)
            if maps and (not last_bracket or int(m.group(1)) >= last_bracket[0]):
                last_bracket = (int(m.group(1)), maps, dict(re.findall(r"\|\s*opponent([12])\s*=\s*\{\{\s*TeamOpponent\s*\|\s*([^|}]*)", seg)))
        if not last_bracket:
            return None
        maps, opp = last_bracket[1], last_bracket[2]
        w1 = sum(1 for _, a, c in maps if a > c)
        side = "1" if w1 * 2 > len(maps) else "2"
        if not _same_team(opp.get(side, ""), winner):      # le vainqueur du tableau n'est pas le bon : on ne dit rien
            return None
        best = (None, maps, side)
    _, maps, side = best
    out = [{"map": m, "w": (a if side == "1" else c), "l": (c if side == "1" else a)} for m, a, c in maps]
    won = sum(1 for m in out if m["w"] > m["l"])
    if won * 2 <= len(out):                   # le « gagnant » perd la majorité des cartes : incohérent, on ne dit rien
        return None
    return {"maps": out, "score": f"{won}-{len(out) - won}", "bestof": len(out)}


def final_detail(t):
    """Score carte par carte de la finale d'un tournoi terminé (1 ou 2 pages lues)."""
    if not t.get("page") or not t.get("winner") or not t.get("runner_up"):
        return None
    wt = liqui_wikitext(t["page"])
    found = parse_final(wt, t["winner"], t["runner_up"])
    if found:
        return found
    subs = [x.strip() for x in re.findall(r"\{\{\s*:([^}|]+)", wt) if "playoff" in x.lower()]
    sub = subs[-1] if subs else t["page"] + "/Playoffs"
    try:
        return parse_final(liqui_wikitext(sub), t["winner"], t["runner_up"])
    except Exception:
        return None


MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_date_range(txt):
    """'Sep 27 - Oct 12, 2025' / 'Oct 6 - 12, 2025' / 'Dec 30, 2025 - Jan 5, 2026' / 'Oct 12, 2025' -> (début, fin)"""
    t = re.sub(r"\s+", " ", txt.replace("–", "-").replace("—", "-")).strip()
    parts = [p.strip() for p in re.split(r"\s*-\s*", t) if p.strip()]
    years = re.findall(r"\b(20\d\d)\b", t)
    if not years:
        return None, None

    def one(p, fallback_month=None, fallback_year=None):
        m = re.match(r"([A-Za-z]{3})[a-z]*\.? ?(\d{1,2})?,? ?(20\d\d)?", p)
        if m and m.group(1).lower() in MONTHS:
            mo = MONTHS[m.group(1).lower()]
            d = int(m.group(2)) if m.group(2) else None
            y = int(m.group(3)) if m.group(3) else None
            return mo, d, y
        m = re.match(r"(\d{1,2}),? ?(20\d\d)?", p)
        if m and fallback_month:
            return fallback_month, int(m.group(1)), int(m.group(2)) if m.group(2) else None
        return None

    a = one(parts[0])
    if not a:
        return None, None
    b = one(parts[1], a[0]) if len(parts) > 1 else a
    if not b:
        b = a
    yb = b[2] or int(years[-1])
    ya = a[2] or (yb - 1 if a[0] > b[0] else yb)
    try:
        start = date(ya, a[0], a[1] or 1)
        if b[1]:
            end = date(yb, b[0], b[1])
        else:                                   # jour pas encore connu : fin du mois
            nxt = date(yb + (b[0] == 12), b[0] % 12 + 1, 1)
            end = nxt - timedelta(days=1)
    except ValueError:
        return None, None
    return start, end


def clean_team(n):
    n = re.sub(r"\s*\([^)]*\)\s*$", "", htmllib.unescape(n or "")).strip()
    n = re.sub(r"\s+(Esports|eSports|e-Sports|Gaming|Club)$", "", n)
    return re.sub(r"^Team\s+(?=\S)", "", n) if n.lower() not in ("team liquid", "team spirit", "team falcons") else n.split(" ", 1)[1]


def _team_in(chunk):
    a, b = _team_in_raw(chunk)
    return (clean_team(a), b) if a else (a, b)


def _team_in_raw(chunk):
    m = re.search(r'team-template-text[^>]*>\s*<a[^>]*title="([^"]+)"[^>]*>([^<]+)</a>', chunk)
    if m:
        return htmllib.unescape(m.group(2)).strip(), htmllib.unescape(m.group(1)).strip()
    m = re.search(r'data-highlighting-?class="([^"]+)"', chunk)
    if m:
        n = htmllib.unescape(m.group(1)).strip()
        return n, n
    m = re.search(r'<a[^>]*title="([^"]+)"[^>]*>([^<]+)</a>', chunk)
    if m:
        return htmllib.unescape(m.group(2)).strip(), htmllib.unescape(m.group(1)).strip()
    m = re.search(r'<a[^>]*title="([^"]+)"', chunk)            # lien sur le logo seulement
    if m:
        n = htmllib.unescape(m.group(1)).strip()
        return n, n
    return None, None


def _name_in(cell):
    m = re.search(r'class="name"[^>]*>\s*(?:<a[^>]*>)?\s*([^<]+)', cell)
    if m:
        n = clean_team(m.group(1).strip())
        return None if n.upper() in ("TBD", "TBA", "") else n
    t = _team_in(cell)[0]
    return t if t and t.upper() not in ("TBD", "TBA") else None


def parse_tournaments_table2(html, tier):
    """Format Liquipedia 2026 : tableau « table2 » (une ligne <tr> par tournoi)."""
    out = []
    for chunk in re.split(r'<tr class="table2__row--body', html)[1:]:
        chunk = chunk.split("</tr>")[0]
        tds = re.findall(r"<td[^>]*>(.*?)</td>", chunk, re.S)
        ti = next((i for i, td in enumerate(tds) if 'column__tournament' in chunk and re.search(r"<a[^>]*>[^<]+</a>", td)), None)
        m_t = re.search(r'class="column__tournament"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*title="([^"]+)"[^>]*>([^<]+)</a>', chunk)
        if not m_t:
            continue
        cells = re.findall(r"<td([^>]*)>(.*?)</td>", chunk, re.S)
        idx = next(i for i, (attrs, _) in enumerate(cells) if "column__tournament" in attrs)
        rest = [c for _, c in cells[idx + 1:]]
        if len(rest) < 3:
            continue
        start, end = parse_date_range(strip_tags(rest[0]))
        if not start:
            continue
        places = [c for attrs, c in cells[idx + 1:] if "column__placement" in attrs]
        loc = strip_tags(rest[2]) if len(rest) > 2 else ""
        out.append({"name": htmllib.unescape(m_t.group(3)).strip(), "tier": tier, "page": htmllib.unescape(m_t.group(2)),
                    "url": urllib.parse.urljoin(LIQUI_WIKI, m_t.group(1)),
                    "start": start.isoformat(), "end": end.isoformat(), "prize": strip_tags(rest[1]),
                    "location": loc, "online": "online" in loc.lower(),
                    "winner": _name_in(places[0]) if places else None,
                    "runner_up": _name_in(places[1]) if len(places) > 1 else None})
    return out


def parse_tournaments(html, tier):
    html = html.replace("&#95;", "_")
    if "table2__row--body" in html:
        return parse_tournaments_table2(html, tier)
    out = []
    for chunk in re.split(r'<div class="gridRow', html)[1:]:
        cell = lambda name: (re.search(r'class="gridCell[^"]*\b' + name + r'\b[^"]*"[^>]*>(.*?)(?=<div class="gridCell|\Z)', chunk, re.S) or [None, ""])[1]
        tour = cell("Tournament")
        m = re.search(r'<a[^>]*href="([^"]+)"[^>]*title="([^"]+)"[^>]*>([^<]+)</a>', tour.split("</b>")[0] if "<b>" in tour else tour)
        name = strip_tags(m.group(3)) if m else strip_tags(tour)
        if not name:
            continue
        start, end = parse_date_range(strip_tags(cell("Date")))
        if not start:
            continue
        w = _team_in(cell("FirstPlace"))
        r = _team_in(cell("SecondPlace"))
        loc = strip_tags(cell("Location"))
        out.append({"name": name, "tier": tier, "page": m.group(2) if m else "",
                    "url": urllib.parse.urljoin(LIQUI_WIKI, m.group(1)) if m else "",
                    "start": start.isoformat(), "end": end.isoformat(),
                    "prize": strip_tags(cell("Prize")), "location": loc,
                    "online": "online" in loc.lower(),
                    "winner": w[0] if w[0] and w[0].upper() != "TBD" else None,
                    "runner_up": r[0] if r[0] and r[0].upper() != "TBD" else None})
    return out


def tournaments(today=None, tiers=("S", "A", "B", "C"), errors=None):
    today = today or date.today()
    res = {"finished": [], "ongoing": [], "upcoming": [], "season": []}
    seen = set()
    for t in tiers:
        try:
            items = parse_tournaments(liqui_parse(TIER_PAGES[t]), t)
        except Exception as e:
            if errors is not None:
                errors.append(f"tournois {t}-Tier : {e}")
            continue
        for it in items:
            key = it["name"]
            if key in seen:
                continue
            seen.add(key)
            s, e = date.fromisoformat(it["start"]), date.fromisoformat(it["end"])
            if it["winner"] and e.year == today.year and e <= today and t in ("S", "A"):       # pour les records
                res["season"].append({k: it[k] for k in ("name", "tier", "end", "winner", "runner_up")})
            if today - timedelta(days=8) <= e < today + timedelta(days=1) and it["winner"]:
                res["finished"].append(it)
            elif s <= today <= e:
                res["ongoing"].append(it)
            elif today < s <= today + timedelta(days=10):
                res["upcoming"].append(it)
    for k in ("finished", "ongoing", "upcoming"):
        res[k].sort(key=lambda x: ("SABC".index(x["tier"]), x["end"] if k == "finished" else x["start"]))
    res["season"].sort(key=lambda x: x["end"])
    return res


# =====================================================================
#  Programme des matchs (page Liquipedia:Matches)
# =====================================================================
def _scores(chunk):
    """Le score d'un match terminé (ex. 2 et 1), lu de plusieurs façons selon la mise en page de Liquipedia."""
    nums = re.findall(r'scoreholder-score[^"]*"[^>]*>\s*(\d+)\s*<', chunk)
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    m = re.search(r'scoreholder-upper[^>]*>(.*?)</span>\s*</span>', chunk, re.S) or \
        re.search(r'class="[^"]*versus[^"]*"[^>]*>(.*?)</div>', chunk, re.S)
    if m:
        m2 = re.search(r"(\d+)\s*[:\-]\s*(\d+)", strip_tags(m.group(1)))
        if m2:
            return int(m2.group(1)), int(m2.group(2))
    return None


def parse_matches(html, section="upcoming"):
    """Matchs à venir (ou terminés, avec leur score) : [{ts, t1, t2, bo, tournament, page, s1, s2}]."""
    html = html.replace("&#95;", "_")
    a = html.find('data-toggle-area-content="1"') if section == "upcoming" else html.find('data-toggle-area-content="2"')
    if a < 0:
        if section != "upcoming":
            return []
        a = 0
    b = html.find('data-toggle-area-content="2"', a + 10) if section == "upcoming" else len(html)
    part = html[a:b if b > 0 else len(html)]
    out = []
    for chunk in part.split('<div class="match-info">')[1:]:
        ts = re.search(r'data-timestamp="(\d+)"', chunk)
        names = re.findall(r'<span class="name"[^>]*>(?:<a[^>]*title="([^"]+)"[^>]*>)?([^<]*)', chunk)
        tour = re.search(r'match-info-tournament-name"><a href="([^"]+)"[^>]*title="([^"]+)"[^>]*><span>([^<]+)</span>', chunk)
        bo = re.search(r"\(Bo(\d)\)", chunk)
        if not ts or len(names) < 2 or not tour:
            continue
        team = lambda n: htmllib.unescape(n[0] or n[1]).strip()          # nom complet (titre du lien)
        court = lambda n: htmllib.unescape(n[1] or n[0]).strip()         # nom affiché (souvent plus court)
        t1, t2 = team(names[0]), team(names[1])
        if not t1 or not t2 or "TBD" in (t1.upper(), t2.upper()):
            continue
        it = {"ts": int(ts.group(1)), "t1": t1, "t2": t2, "t1_court": court(names[0]), "t2_court": court(names[1]),
              "bo": int(bo.group(1)) if bo else 0,
              "tournament": htmllib.unescape(tour.group(3)).strip(), "page": htmllib.unescape(tour.group(2))}
        if section != "upcoming":
            sc = _scores(chunk)
            if not sc:
                continue
            it["s1"], it["s2"] = sc
            need = it["bo"] // 2 + 1 if it["bo"] else 0
            if sc[0] == sc[1] or (need and max(sc) != need):       # score incohérent (match pas fini) : on ignore
                continue
        out.append(it)
    return out


def matches_page(errors=None):
    """Une seule lecture de Liquipedia:Matches : (matchs à venir, matchs terminés avec score)."""
    try:
        html = liqui_parse("Liquipedia:Matches")
    except Exception as e:
        if errors is not None:
            errors.append(f"programme des matchs : {e}")
        return [], [], ""
    return parse_matches(html), parse_matches(html, "completed"), html


def upcoming_matches(errors=None):
    try:
        return parse_matches(liqui_parse("Liquipedia:Matches"))
    except Exception as e:
        if errors is not None:
            errors.append(f"programme des matchs : {e}")
        return []


# =====================================================================
#  Scène féminine (page Liquipedia Female_Tournaments) : seulement les tournois qui comptent (cashprize >= 1 000 $)
# =====================================================================
FEMALE_PAGE = "Female_Tournaments"
FEMALE_MIN_PRIZE = 1000


def female_tournaments(today=None, errors=None):
    today = today or date.today()
    res = {"finished": [], "ongoing": [], "upcoming": []}
    try:
        items = parse_tournaments(liqui_parse(FEMALE_PAGE), "F")
    except Exception as e:
        if errors is not None:
            errors.append(f"scène féminine : {e}")
        return res
    prize = lambda t: float(re.sub(r"[^\d.]", "", (t.get("prize") or "").replace(",", "")) or 0)
    for it in items:
        if prize(it) < FEMALE_MIN_PRIZE:
            continue
        s, e = date.fromisoformat(it["start"]), date.fromisoformat(it["end"])
        if today - timedelta(days=8) <= e <= today and it["winner"]:
            res["finished"].append(it)
        elif s <= today <= e:
            res["ongoing"].append(it)
        elif today < s <= today + timedelta(days=10):
            res["upcoming"].append(it)
    for k in res:
        res[k].sort(key=lambda t: -prize(t))
    return res


# =====================================================================
#  Mises à jour de CS2 (notes officielles de Valve, fil d'actu Steam)
# =====================================================================
MAPS = ["Mirage", "Inferno", "Dust2", "Dust II", "Nuke", "Ancient", "Anubis", "Overpass", "Train", "Vertigo", "Office",
        "Italy", "Agency", "Basalt", "Edin", "Thera", "Mills", "Memento", "Assembly", "Palais", "Whistle", "Jura", "Grail",
        "Golden", "Rooftop", "Pool Day", "Shoots", "Brewery", "Dogtown", "Sanctum", "Poseidon", "Cache", "Cobblestone"]
WEAPONS = ["AK-47", "M4A4", "M4A1-S", "AWP", "Desert Eagle", "Deagle", "Glock-18", "USP-S", "P2000", "P250", "Five-SeveN",
           "Tec-9", "CZ75-Auto", "R8 Revolver", "Dual Berettas", "MAC-10", "MP9", "MP7", "MP5-SD", "UMP-45", "P90", "PP-Bizon",
           "FAMAS", "Galil AR", "AUG", "SG 553", "SSG 08", "SCAR-20", "G3SG1", "Nova", "XM1014", "MAG-7", "Sawed-Off",
           "M249", "Negev", "Zeus x27", "Zeus", "Molotov", "Incendiary", "Smoke Grenade", "Flashbang", "HE Grenade", "Decoy"]


def parse_update(item):
    txt = (item.get("contents") or "").replace("\\[", "[").replace("\\]", "]")      # Valve écrit « \[ MISC ] »
    txt = re.sub(r"\[/\*\]", "\n", txt)
    txt = re.sub(r"\[/?(list|url[^\]]*|b|i|u|h\d|p|img[^\]]*|olist|previewyoutube[^\]]*)\]", "\n", txt, flags=re.I)
    secs, cur = {}, "GENERAL"
    for line in re.split(r"\[\*\]|\n|\\n", txt):
        line = strip_tags(line).strip(" -•\t")
        if not line:
            continue
        m = re.fullmatch(r"\[\s*([A-Za-z][A-Za-z &/]+?)\s*\]", line)
        if m:
            cur = m.group(1).upper()
            continue
        secs.setdefault(cur, []).append(line[:200])
    allt = " ".join(" ".join(v) for v in secs.values())
    mapt = " ".join(l for k, v in secs.items() for l in v if "MAP" in k or re.search(r"\bmaps?\b", l, re.I))
    found = lambda names, t=allt: [n for n in names if re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", t)]
    maps = []
    for n in found(MAPS, mapt):
        n = "Dust2" if n == "Dust II" else n
        if n not in maps:
            maps.append(n)
    weapons = []
    for n in found(WEAPONS):
        n = {"Deagle": "Desert Eagle", "Zeus x27": "Zeus"}.get(n, n)
        if n not in weapons:
            weapons.append(n)
    return {"date": date.fromtimestamp(item["date"]).isoformat(), "title": item.get("title", ""), "url": item.get("url", ""),
            "sections": {k: v[:6] for k, v in secs.items()}, "count": sum(len(v) for v in secs.values()),
            "maps": maps[:6], "weapons": weapons[:6],
            "operation": bool(re.search(r"\boperation\b", allt + item.get("title", ""), re.I)),
            "case": bool(re.search(r"\b(new|added)\b[^.]{0,40}\b[A-Z][\w ]{0,25} Case\b", allt)),
            "mode": bool(re.search(r"\bnew\b[^.]{0,40}\b(game )?mode\b|\bqueued [\w ]{0,12}mode\b", allt, re.I)),
            "premier": "PREMIER" in secs,
            "music": bool(re.search(r"\bMusic Kit\b", allt)),
            "map_pool": bool(re.search(r"active duty|map pool", allt, re.I))}


def cs2_updates(today=None, days=8):
    """Les notes de mise à jour officielles de CS2 publiées ces derniers jours."""
    today = today or date.today()
    raw = fetch(STEAM_NEWS, {"appid": "730", "count": "20", "maxlength": "0", "format": "json"}, timeout=25)
    save_debug("steam_news.json", raw)
    out = []
    for it in json.loads(raw).get("appnews", {}).get("newsitems", []):
        if it.get("feedname") != "steam_community_announcements":
            continue
        title = (it.get("title") or "").lower()
        if not ("update" in title or "release notes" in title or "patchnotes" in (it.get("tags") or [])):
            continue
        d = date.fromtimestamp(it.get("date", 0))
        if today - timedelta(days=days) <= d <= today:
            out.append(parse_update(it))
    return out


def parse_transfers(html):
    out = []
    for chunk in re.split(r'<div class="divRow', html)[1:]:
        dm = re.search(r'class="divCell Date"[^>]*>\s*(?:<[^>]+>\s*)*(\d{4}-\d{2}-\d{2})', chunk)
        if not dm:
            continue
        name_cell = (re.search(r'class="divCell Name"(.*?)(?=<div class="divCell Team)', chunk, re.S) or [None, ""])[1]
        players = []
        for b in re.split(r'class="block-player', name_cell)[1:]:
            pm = re.search(r'class="name"[^>]*>\s*<a[^>]*title="([^"]+)"[^>]*>([^<]+)</a>', b) \
                or re.search(r'<a[^>]*title="([^"]+)"[^>]*>([^<]+)</a>', b)
            if not pm:
                continue
            fm = re.search(r'class="flag"[^>]*>\s*(?:<a[^>]*>)?\s*<img[^>]*alt="([^"]*)"', b)
            players.append({"name": htmllib.unescape(pm.group(2)).strip(), "page": htmllib.unescape(pm.group(1)),
                            "flag": htmllib.unescape(fm.group(1)) if fm else ""})
        if not players:
            continue

        def side(cls):
            c = (re.search(r'class="divCell Team ' + cls + r'"(.*?)(?=<div class="divCell|\Z)', chunk, re.S) or [None, ""])[1]
            team = _team_in(c)[0] if "team-template" in c or "<a" in c else None
            txt = strip_tags(c)
            role = re.search(r"\((?:[^)]*?)(coach|analyst|manager|inactive|retired|substitute|loan|stand-?in)[^)]*\)", txt, re.I)
            if not team and re.search(r"retired", txt, re.I):
                role = role or re.search(r"(retired)", txt, re.I)
            return team, (role.group(1).lower() if role else "")
        old, old_role = side("OldTeam")
        new, new_role = side("NewTeam")
        if not old and not new:
            continue
        out.append({"date": dm.group(1), "players": players, "from": old, "to": new,
                    "from_role": old_role, "to_role": new_role})
    return out


def transfers(today=None, days=8, errors=None):
    today = today or date.today()
    try:
        items = parse_transfers(liqui_parse(TRANSFER_PAGE))
    except Exception as e:
        if errors is not None:
            errors.append(f"transferts : {e}")
        return []
    lim = (today - timedelta(days=days)).isoformat()
    return [t for t in items if lim <= t["date"] <= today.isoformat()]


# =====================================================================
#  Photos libres (Wikimedia Commons)
# =====================================================================
def player_photo(name, folder):
    """Cherche une photo libre du joueur. Renvoie {"file", "credit", "license", "source"} ou None.
    Cache : un fichier .json par joueur (même "rien trouvé", pour ne pas redemander chaque semaine)."""
    os.makedirs(folder, exist_ok=True)
    key = re.sub(r"[^\w-]+", "_", name.lower())
    meta_p = os.path.join(folder, key + ".json")
    if os.path.exists(meta_p):
        try:
            with open(meta_p, encoding="utf-8") as f:
                m = json.load(f)
            age = (datetime.now() - datetime.fromisoformat(m.get("checked", "2000-01-01"))).days
            if m.get("file") and os.path.exists(os.path.join(folder, m["file"])):
                return {**m, "file": os.path.join(folder, m["file"])}
            if age < 30:
                return None
        except Exception:
            pass
    found, reached = None, False
    word = re.compile(r"(?<![a-z0-9])" + re.escape(name.lower()) + r"(?![a-z0-9])")
    for q in (f'"{name}" counter-strike', f'"{name}" esports', f'"{name}" CS:GO'):
        try:
            data = json.loads(fetch(COMMONS_API, {"action": "query", "format": "json", "formatversion": "2",
                                                  "generator": "search", "gsrsearch": q, "gsrnamespace": "6",
                                                  "gsrlimit": "10", "prop": "imageinfo",
                                                  "iiprop": "url|extmetadata|size|mime", "iiurlwidth": "900"}, timeout=25))
            reached = True
        except Exception:
            continue
        for p in (data.get("query") or {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata") or {}
            lic = (em.get("LicenseShortName") or {}).get("value", "")
            if not FREE_LICENSES.match(lic.strip()) or re.search(r"\bNC\b|\bND\b", lic):
                continue
            if ii.get("mime") not in ("image/jpeg", "image/png") or (ii.get("width") or 0) < 400:
                continue
            if not word.search(p.get("title", "").lower()):
                continue
            found = {"title": p["title"], "url": ii.get("thumburl") or ii.get("url"),
                     "page": ii.get("descriptionurl", ""), "license": lic,
                     "author": strip_tags((em.get("Artist") or {}).get("value", "")) or "auteur inconnu"}
            break
        if found:
            break
    if not reached:                      # Commons injoignable : on ne retient pas « pas de photo »
        return None
    meta = {"checked": datetime.now().isoformat(timespec="seconds"), "name": name}
    if found:
        ext = ".png" if found["url"].lower().endswith(".png") else ".jpg"
        try:
            with open(os.path.join(folder, key + ext), "wb") as f:
                f.write(fetch(found["url"], raw=True, timeout=40))
            meta.update(file=key + ext, credit=f"Photo : {found['author'][:60]} · {found['license']} · Wikimedia Commons",
                        license=found["license"], source=found["page"])
        except Exception:
            pass
    with open(meta_p, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    if meta.get("file"):
        return {**meta, "file": os.path.join(folder, meta["file"])}
    return None


# =====================================================================
#  Diagnostic
# =====================================================================
def diagnostic():
    global DEBUG_DIR
    DEBUG_DIR = os.path.join(HERE, "news", "diagnostic")
    print(f"Test des sources (les pages brutes sont gardées dans {DEBUG_DIR})\n")
    try:
        v = vrs_rankings()
        print(f"[OK] Classement Valve du {v['date']} : {len(v['rows'])} équipes, n°1 {v['rows'][0]['team']}")
    except Exception as e:
        print(f"[ERREUR] Classement Valve : {e}")
    errs = []
    t = tournaments(tiers=("S", "B"), errors=errs)
    print(f"[{'OK' if not errs else 'ERREUR'}] Tournois (S et B) : {sum(len(x) for x in t.values())} trouvés "
          f"(finis {len(t['finished'])}, en cours {len(t['ongoing'])}, à venir {len(t['upcoming'])})")
    for k in ("finished", "ongoing", "upcoming"):
        for it in t[k][:3]:
            print(f"     {k:9} {it['tier']} {it['name']} ({it['start']} -> {it['end']}) {it['winner'] or ''}")
    fin = [x for x in t["finished"] if x.get("winner") and x.get("runner_up")][:1]
    if fin:
        try:
            d = final_detail(fin[0])
            print(f"[{'OK' if d else 'ATTENTION'}] Finale de {fin[0]['name']} : "
                  + (f"{fin[0]['winner']} {d['score']} ({', '.join(m['map'] + ' ' + str(m['w']) + '-' + str(m['l']) for m in d['maps'])})"
                     if d else "score des cartes introuvable"))
        except Exception as e:
            print(f"[ERREUR] Finale de {fin[0]['name']} : {e}")
    titles = {}
    for x in t.get("season", []):
        titles[x["winner"]] = titles.get(x["winner"], 0) + 1
    top = sorted(titles.items(), key=lambda kv: -kv[1])[:3]
    print(f"[{'OK' if top else 'ATTENTION'}] Titres S-Tier de l'année : " + (", ".join(f"{k} {v}" for k, v in top) or "aucun"))
    try:
        ups = cs2_updates(days=30)
        print(f"[OK] Mises à jour CS2 (30 derniers jours) : {len(ups)}"
              + (f", dernière le {ups[0]['date']} ({ups[0]['count']} changements, cartes : {', '.join(ups[0]['maps']) or '-'})" if ups else ""))
    except Exception as e:
        print(f"[ERREUR] Mises à jour CS2 (Steam) : {e}")
    # pages gardées pour les prochaines rubriques (matchs à venir, tournoi en cours, scène féminine)
    for page in [MATCHES_PAGE] + ([t["ongoing"][0]["page"]] if t["ongoing"] else []) + FEMALE_PAGES:
        try:
            liqui_parse(page)
            if page == (t["ongoing"][0]["page"] if t["ongoing"] else None):
                liqui_wikitext(page)
            print(f"[OK] Page gardée : {page}")
        except Exception as e:
            print(f"[INFO] Page {page} : {e}")
    tr = transfers(days=10, errors=errs)
    print(f"[{'OK' if tr else 'ATTENTION'}] Transferts des 10 derniers jours : {len(tr)}")
    for x in tr[:5]:
        print(f"     {x['date']} {', '.join(p['name'] for p in x['players'])} : {x['from'] or '-'} -> {x['to'] or '-'} {x['to_role']}")
    for e in errs:
        print(f"[ERREUR] {e}")
    ph = player_photo("ZywOo", os.path.join(HERE, "news", "photos"))
    print(f"[{'OK' if ph else 'ATTENTION'}] Photo libre de ZywOo : {ph['credit'] if ph else 'aucune trouvée'}")
    print("\nSi une ligne est en ERREUR ou à 0, envoie le dossier news\\diagnostic : la page a peut-être changé de forme.")


if __name__ == "__main__":
    diagnostic()
