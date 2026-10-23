"""
News CS2 - écriture des scripts T1 et T2 à partir des infos collectées.

Mode gratuit : modèles de phrases en français (plusieurs tournures, tirées au hasard chaque semaine).
Option : une clé API Claude (payée à l'usage) réécrit les phrases plus naturellement, SANS ajouter d'info ;
si l'appel échoue, on garde la version gratuite.

Chaque passage = {"kind", "say" (texte lu par la voix), "sub" (sous-titre), "card" (ce qu'on affiche), "source"}.
"""
import json
import os
import random
import re
import urllib.request
from datetime import date, timedelta

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
LIQUI_SRC = "Source : Liquipedia (CC BY-SA)"

# ---------------------------------------------------------------------
#  Nombres en toutes lettres (la voix lit mal les chiffres)
# ---------------------------------------------------------------------
_U = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
      "treize", "quatorze", "quinze", "seize"]
_D = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def fr_num(n):
    n = int(n)
    if n < 0:
        return "moins " + fr_num(-n)
    if n <= 16:
        return _U[n]
    if n < 20:
        return "dix-" + _U[n - 10]
    if n < 70:
        d, u = divmod(n, 10)
        return _D[d] + ("" if u == 0 else "-et-un" if u == 1 else "-" + _U[u])
    if n < 80:
        return "soixante-" + ("et-onze" if n == 71 else fr_num(n - 60))
    if n < 100:
        r = n - 80
        return "quatre-vingts" if r == 0 else "quatre-vingt-" + fr_num(r)
    if n < 1000:
        c, r = divmod(n, 100)
        head = "cent" if c == 1 else _U[c] + "-cent" + ("s" if r == 0 else "")
        return head + ("" if r == 0 else "-" + fr_num(r))
    if n < 1_000_000:
        m, r = divmod(n, 1000)
        head = "mille" if m == 1 else fr_num(m).replace("cents", "cent").replace("vingts", "vingt") + "-mille"
        return head + ("" if r == 0 else "-" + fr_num(r))
    m, r = divmod(n, 1_000_000)
    return fr_num(m) + (" million" if m == 1 else " millions") + ("" if r == 0 else " " + fr_num(r))


def fr_ord(n):
    if n == 1:
        return "premier"
    w = fr_num(n)
    if w.endswith("cinq"):
        return w + "uième"
    if w.endswith("neuf"):
        return w[:-1] + "vième"
    if w.endswith("vingts") or w.endswith("cents"):
        w = w[:-1]
    if w.endswith("e"):
        w = w[:-1]
    return w + "ième"


# Prononciation : la voix est française, mais les noms CS sont anglais. On les réécrit « comme ça se dit ».
# Modifiable sans toucher au code : fichier news\prononciation.txt (une ligne « mot = comme ça se prononce »).
PRONONCIATION = {
    # général
    "Counter-Strike": "Kounteur-Straïk", "Counter Strike": "Kounteur-Straïk", "CS2": "cé-èss deux", "CS": "cé-èss",
    "news": "niouze", "NEWS": "niouze", "MVP": "èm-vé-pi", "tier 1": "té-un", "tier 2": "té-deux", "tier": "tire",
    "IGL": "aï-dji-èl", "AWPer": "Aoupeur", "AWP": "Aoupe", "rifler": "Raïfleur", "entry": "Èntri", "lurker": "Leurkeur",
    "upper bracket": "Eupeur braquette", "lower bracket": "Loweur braquette", "playoffs": "Pléï-offs",
    "stand-in": "stannde-ine", "headshot": "hèdchote", "headshots": "hèdchotes", "clutch": "kleutch", "ace": "aiceu", "aces": "aiceu",
    "overtime": "Ôveur-taïme", "Swiss stage": "Souiss stèïdje",
    # tournois
    "ESL": "Euh-èsse-èl", "IEM": "aï-i-èm", "ESEA": "i-èss-i-èï", "PGL": "pé-jé-elle", "CCT": "cé-cé-té", "VRS": "vé-èr-èss",
    "HLTV": "ache-èl-té-vé", "FACEIT": "Fèïsse-hit", "BLAST": "Blaste", "Premier": "Preumière", "Open": "Ôpeine",
    "Season": "Saison", "League": "Ligue", "Pro League": "Pro Ligue", "World Championship": "Ouorld Tchampionnchip",
    "Dust2": "Deusteu deux", "Dust II": "Deusteu deux", "Nuke": "Nioulk", "Ancient": "Éïnchiennte", "Overpass": "Ôveurpasse",
    "Train": "Tréïne", "Anubis": "Anoubisse", "Vertigo": "Veurtigo",
    "Series": "Siriz", "Masters": "Masteurz", "Katowice": "Katovitsé", "Bucharest": "Bucarest", "Malta": "Malte", "Cologne": "Cologne",
    # équipes
    "G2": "Jé-deux", "Natus Vincere": "Navi", "NAVI": "Navi", "HEROIC": "Héroïque", "3DMAX": "Trois-dé-max",
    "Ninjas in Pyjamas": "ène-aï-pi", "NIP": "ène-aï-pi", "paiN": "Peine", "Virtus.pro": "Virtus pro",
    "Gentle Mates": "Djènnteul Mèïtz", "The MongolZ": "Ze Monngolz", "Team Liquid": "Tim Likouid", "Liquid": "Likouid",
    "Astralis": "Astraliss", "BetBoom": "Bètt-boum", "Gaming": "Guéïmine", "Esports": "I-sporz", "fnatic": "Fnatik",
    "MOUZ": "Maouz", "ENVY": "Envy", "FURIA": "Fouria", "Falcons": "Falcone", "Spirit": "Spirite", "Legacy": "Légacy",
    "FUT": "Foute", "MIBR": "Mibeur", "9z": "Naïne-zi", "M80": "Èm-éïti", "FaZe": "Féïz", "GamerLegion": "Guéïmeur Lidjeune",
    "Gamer Legion": "Guéïmeur Lidjeune",
    # joueurs
    "ZywOo": "Zaïwou", "NiKo": "Niko", "m0NESY": "Monési", "flameZ": "Flèmz", "XANTARES": "Ksanntarèss",
    "jL": "Djé-èl", "sh1ro": "Chiro", "n1ssim": "Nissim", "PR": "Pi-ar", "Spinx": "Spinks",
}
# ces mots restent « exacts » (en minuscules ce sont des mots français : « premier », « pain »)
EXACT_CASE = {"Premier", "paiN"}
PRONONCIATION_FILE = None      # chemin du fichier perso (rempli par news_make)
# anciennes valeurs par défaut : si le fichier perso les contient encore, on met la nouvelle version
OLD_DEFAULTS = {("ESL", "i-èss-èl"), ("ESL", "Eussèl"), ("Premier", "Prèmi-eur"), ("FACEIT", "Fèïss-it"), ("Open", "Ôpeune"), ("Counter-Strike", "Kaounteur-Straïk"), ("Counter Strike", "Kaounteur-Straïk"),
                ("Major", "Méjeur"), ("Majors", "Méjeurs"), ("MVP", "M V P"), ("Falcons", "Falkonnz")} | {('Aurora', 'Aurora'), ('News', 'Niouze'), ('Fnatic', 'Fnatik'), ('Counter-Strike', 'Kounteur-Straïk'), ('ESL', 'E S L'), ('flameZ', 'Flèmz'), ('BLAST', 'Blaste'), ('Gaming', 'Guéïmine'), ('VRS', 'V R S'), ('Masters', 'Masteurz'), ('XANTARES', 'Ksanntarèss'), ('HEROIC', 'Héroïque'), ('FACEIT', 'Fèïss-it'), ('IEM', 'I E M'), ('Liquid', 'Likouid'), ('MOUZ', 'Maouz'), ('NEWS', 'niouze'), ('paiN', 'Peine'), ('Series', 'Siriz'), ('Gentle Mates', 'Djènnteul Mèïtz'), ('3DMAX', 'Trois-dé-max'), ('Pro League', 'Pro Ligue'), ('Katowice', 'Katovitsé'), ('PGL', 'pé-jé-elle'), ('BetBoom', 'Bètt-boum'), ('Esports', 'I-sporz'), ('Premier', 'Prémieur'), ('fnatic', 'Fnatik'), ('Natus Vincere', 'Navi'), ('ZywOo', 'Zaïwou'), ('FURIA', 'Fouria'), ('NiKo', 'Niko'), ('headshot', 'hèdchote'), ('Ninjas in Pyjamas', 'ène-aï-pi'), ('m0NESY', 'Monési'), ('jL', 'Djé-èl'), ('MVP', 'èm-vé-pi'), ('Team Liquid', 'Tim Likouid'), ('HLTV', 'H L T V'), ('news', 'niouze'), ('The MongolZ', 'Ze Monngolz'), ('League', 'Ligue'), ('Legacy', 'Légacy'), ('Virtus.pro', 'Virtus pro'), ('G2', 'Jé-deux'), ('headshots', 'hèdchotes'), ('CS', 'C S'), ('Falcons', 'Falcone'), ('ESEA', 'eu-èss-eu-a'), ('tier', 'tire'), ('Astralis', 'Astraliss'), ('CS2', 'C S deux'), ('CCT', 'C C T'), ('Spirit', 'Spirite'), ('stand-in', 'stannde-ine'), ('Open', 'Opeune'), ('World Championship', 'Ouorld Tchampionnchip'), ('clutch', 'kleutch'), ('Counter Strike', 'Kounteur-Straïk'), ('Season', 'Saison'), ('NIP', 'ène-aï-pi'), ('NAVI', 'Navi')}


def pronunciations():
    d = dict(PRONONCIATION)
    if PRONONCIATION_FILE:
        try:
            if not os.path.exists(PRONONCIATION_FILE):
                os.makedirs(os.path.dirname(PRONONCIATION_FILE), exist_ok=True)
                with open(PRONONCIATION_FILE, "w", encoding="utf-8") as f:
                    f.write("# Comment la voix prononce les mots anglais. Une ligne par mot : mot = comme ça se dit\n"
                            "# Les lignes qui commencent par # sont ignorées. Teste avec « Tester ma voix » (phrase perso).\n")
                    f.writelines(f"{k} = {v}\n" for k, v in PRONONCIATION.items())
            with open(PRONONCIATION_FILE, encoding="utf-8") as f:
                lines = f.readlines()
            keep, changed = [], False
            for line in lines:
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = (x.strip() for x in line.split("=", 1))
                    if (k, v) in OLD_DEFAULTS:                     # valeur par défaut d'avant : remplacée ou retirée
                        changed = True
                        if k in PRONONCIATION:
                            keep.append(f"{k} = {PRONONCIATION[k]}\n")
                        continue
                    if k:
                        d[k] = v
                keep.append(line)
            if changed:
                with open(PRONONCIATION_FILE, "w", encoding="utf-8") as f:
                    f.writelines(keep)
        except OSError:
            pass
    return d


LETTRES = {"A": "a", "B": "bé", "C": "cé", "D": "dé", "E": "euh", "F": "èf", "G": "jé", "H": "ache", "I": "i", "J": "ji",
           "K": "ka", "L": "èl", "M": "èm", "N": "ène", "O": "o", "P": "pé", "Q": "ku", "R": "èr", "S": "èss", "T": "té",
           "U": "u", "V": "vé", "W": "double-vé", "X": "ix", "Y": "i-grec", "Z": "zèd"}


def spell(t):
    """Sigles épelés lettre par lettre : « M V P » ou « M.V.P » -> « èm-vé-pé » (la voix lit mieux les lettres en toutes lettres)."""
    def rep(m):
        return "-".join(LETTRES[c] for c in re.findall(r"[A-Z]", m.group(0)))
    t = re.sub(r"(?<![\w.])[A-Z](?:[ .][A-Z])+\.?(?![\w])", rep, t)
    return t


def apply_pronunciation(t):
    d = pronunciations()
    for k in sorted(d, key=len, reverse=True):                     # « Pro League » avant « League »
        flags = 0 if k in EXACT_CASE else re.I                       # « Furia », « FURIA », « furia » : pareil
        t = re.sub(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])", lambda m, v=d[k]: v, t, flags=flags)
    return spell(pseudos(t))


LEET = {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t"}


def pseudos(t):
    """Pseudos de joueurs : chiffres au milieu des lettres (sh1ro, Br4tkO) -> lettres ; majuscules au milieu
    (flameZ, NiKo) ou noms tout en majuscules (KSCERATO) -> écrits comme un mot normal, sinon la voix les épelle."""
    def fix(m):
        w = m.group(0)
        if re.search(r"[A-Za-z][013457][A-Za-z]", w):
            w = re.sub(r"(?<=[A-Za-z])[013457](?=[A-Za-z])", lambda x: LEET[x.group(0)], w)
        letters = re.sub(r"[^A-Za-z]", "", w)
        if not letters:
            return w
        if letters.isupper() and len(letters) >= 5:                  # KSCERATO -> Kscerato (pas un sigle)
            return w[0] + w[1:].lower()
        if not letters.isupper() and re.search(r"[a-z][A-Z]", w):     # flameZ, NiKo, m0NESY -> flamez, niko
            return w[0] + w[1:].lower()
        return w
    return re.sub(r"[A-Za-zÀ-ÿ0-9]+", fix, t)


def spoken(text):
    """Texte pour la voix : chiffres en lettres, sigles lisibles, noms anglais prononcés à la française."""
    t = apply_pronunciation(text)
    t = re.sub(r"\bBO\s*(\w+)", r"bé-o \1", t)
    t = re.sub(r"\b(\d+)(?:er|re)\b", lambda m: "premier" if m.group(1) == "1" else fr_ord(int(m.group(1))), t)
    t = re.sub(r"\b(\d+)e\b", lambda m: fr_ord(int(m.group(1))), t)
    t = re.sub(r"(\d+)\s*-\s*(\d+)", lambda m: f"{fr_num(m.group(1))} à {fr_num(m.group(2))}", t)
    t = re.sub(r"(?<![A-Za-z])\d+(?![A-Za-z])", lambda m: f" {fr_num(m.group(0))} ", t)
    t = t.replace("n°", "numéro ").replace("&", " et ").replace("·", ",")
    t = t.replace("!", ".").replace(" :", ",").replace(":", ",").replace("…", ".").replace(";", ",")   # la voix bute sur « ! » et « : »
    t = re.sub(r"\bT1\b", "té-un", t)
    t = re.sub(r"\bT2\b", "té-deux", t)
    return re.sub(r"\s+", " ", t).replace(" ,", ",").replace(" .", ".").strip()


def date_fr(iso, with_day=False):
    d = date.fromisoformat(iso)
    s = ("1er" if d.day == 1 else str(d.day)) + " " + MOIS[d.month - 1]
    return (JOURS[d.weekday()] + " " + s) if with_day else s


def range_fr(a, b):
    a, b = date.fromisoformat(a), date.fromisoformat(b)
    if a == b:
        return date_fr(a.isoformat())
    if a.month == b.month:
        return f"du {'1er' if a.day == 1 else a.day} au {b.day} {MOIS[b.month - 1]}"
    return f"du {date_fr(a.isoformat())} au {date_fr(b.isoformat())}"


VILLES = {"malta": "Malte", "bucharest": "Bucarest", "copenhagen": "Copenhague", "london": "Londres", "lisbon": "Lisbonne",
          "warsaw": "Varsovie", "vienna": "Vienne", "hamburg": "Hambourg", "cologne": "Cologne", "moscow": "Moscou",
          "belgrade": "Belgrade", "budapest": "Budapest", "prague": "Prague", "athens": "Athènes", "seville": "Séville",
          "valencia": "Valence", "rome": "Rome", "milan": "Milan", "munich": "Munich", "brussels": "Bruxelles",
          "antwerp": "Anvers", "geneva": "Genève", "dubai": "Dubaï", "riyadh": "Riyad", "beijing": "Pékin",
          "singapore": "Singapour", "melbourne": "Melbourne", "sydney": "Sydney", "new york": "New York",
          "rio de janeiro": "Rio de Janeiro", "sao paulo": "São Paulo", "são paulo": "São Paulo", "mexico city": "Mexico",
          "katowice": "Katowice", "stockholm": "Stockholm", "austin": "Austin", "dallas": "Dallas", "shanghai": "Shanghai",
          "kraków": "Cracovie", "krakow": "Cracovie", "gdańsk": "Gdańsk", "tallinn": "Tallinn", "riga": "Riga",
          "kyiv": "Kiev", "astana": "Astana", "almaty": "Almaty", "baku": "Bakou", "tbilisi": "Tbilissi"}


REGIONS = {"europe", "north america", "south america", "asia", "oceania", "cis", "mena", "africa", "online", "tba",
           "america", "americas", "eastern europe", "western europe", "southeast asia", "middle east"}


def city(loc):
    if not loc or "online" in loc.lower() or loc.split(",")[0].strip().lower() in REGIONS:
        return ""
    c = loc.split(",")[0].strip()
    return VILLES.get(c.lower(), c)


def elide(t):
    """« de Envy » -> « d'Envy », « le coach de Astralis » -> « d'Astralis »."""
    return re.sub(r"\b([dD])e ([AEIOUYÉÈaeiouyéè])", r"\1'\2", t)


def week_label(d):
    y, w, _ = d.isocalendar()
    return f"{y}-S{w:02d}", w


# ---------------------------------------------------------------------
#  Transferts : qui, d'où, vers où
# ---------------------------------------------------------------------
def prize_of(t):
    try:
        return float(re.sub(r"[^\d.]", "", (t.get("prize") or "").split(".")[0]) or 0)
    except ValueError:
        return 0.0


def group_transfers(trs):
    """Même départ, même arrivée, même rôle : une seule ligne avec tous les joueurs (ex : une équipe recrute 5 joueurs)."""
    out, idx = [], {}
    for t in trs:
        k = (t.get("from"), t.get("to"), t.get("from_role"), t.get("to_role"))
        if k in idx:
            out[idx[k]]["players"] += [p for p in t["players"] if p not in out[idx[k]]["players"]]
        else:
            idx[k] = len(out)
            out.append({**t, "players": list(t["players"])})
    return out


def names(tr):
    ps = [p["name"] for p in tr["players"]]
    return ps[0] if len(ps) == 1 else ", ".join(ps[:-1]) + " et " + ps[-1]


def transfer_sentence(tr, rnd):
    n, a, b = names(tr), tr.get("from"), tr.get("to")
    plural = len(tr["players"]) > 1
    role_to, role_from = tr.get("to_role", ""), tr.get("from_role", "")
    if b and role_to == "coach":
        return f"{n} deviennent les nouveaux coachs de {b}." if plural else f"{n} devient le nouveau coach de {b}."
    if a and role_from == "coach" and not b:
        return f"{n} ne sont plus coachs de {a}." if plural else f"{n} n'est plus le coach de {a}."
    if b and role_to in ("loan", "stand-in", "standin"):
        return f"{n} {'dépannent' if plural else 'dépanne'} {b} en tant que remplaçant{'s' if plural else ''}."
    if a and role_to == "inactive" or (a and b == a and role_to == "inactive"):
        return f"{n} {'passent' if plural else 'passe'} sur le banc chez {a}."
    if a and role_to == "retired" or (not b and role_from == "retired"):
        return f"{n} {'prennent' if plural else 'prend'} {'leur' if plural else 'sa'} retraite."
    if len(tr["players"]) >= 3 and b and not role_to:
        return f"{b} recrute {fr_count(len(tr['players']))} joueurs : {n}."
    if len(tr["players"]) >= 3 and a and not b:
        return f"{a} se sépare de {fr_count(len(tr['players']))} joueurs : {n}."
    if a and b:
        return rnd.choice([f"{n} {'passent' if plural else 'passe'} de {a} à {b}.",
                           f"{b} recrute {n}, en provenance de {a}."])
    if b:
        return rnd.choice([f"{n} {'rejoignent' if plural else 'rejoint'} {b}.", f"{b} accueille {n}."])
    if a:
        return rnd.choice([f"{n} {'quittent' if plural else 'quitte'} {a}.",
                           f"{a} se sépare de {n}."])
    return ""


def transfer_row(tr):
    if tr.get("from_role") == "coach" and not tr.get("to"):
        return {"player": names(tr), "from": tr.get("from") or "", "to": "", "role": "coach parti",
                "fr": any(p.get("flag") == "France" for p in tr["players"])}
    if len(tr["players"]) >= 3:                     # sur l'écran : « Triphal, weaven +3 »
        short = ", ".join(p["name"] for p in tr["players"][:2]) + f" +{len(tr['players']) - 2}"
        return {**transfer_row({**tr, "players": tr["players"][:1]}), "player": short}
    role = {"coach": "coach", "inactive": "banc", "retired": "retraite", "loan": "prêt", "stand-in": "remplaçant"}.get(tr.get("to_role", ""), "")
    return {"player": names(tr), "from": tr.get("from") or "", "to": tr.get("to") or ("" if role else "libre"),
            "role": role, "fr": any(p.get("flag") == "France" for p in tr["players"]),
            "country": tr["players"][0].get("flag") if len(tr["players"]) == 1 else None}


# ---------------------------------------------------------------------
#  Construction des deux scripts
# ---------------------------------------------------------------------
def seg(kind, say, card, source=""):
    say = elide(say)
    return {"kind": kind, "say": spoken(say), "sub": say, "card": card, "source": source}


def build(data, prenom="Mexic", today=None, fr_teams=(), flash=False, weekly=False, release=None):
    """Les scripts T1 et T2 (et FLASH si flash=True : édition spéciale, faite à n'importe quel moment ;
    SEMAINE si weekly=True : T1 + T2 + scène FR dans une seule vidéo plus complète, datée du jour de sortie)."""
    today = date.fromisoformat(data["day"]) if data.get("day") else (today or date.today())
    from datetime import datetime as _dt
    rel_dt = release if isinstance(release, _dt) else None          # date ET heure de sortie (programme des matchs)
    if rel_dt:
        release = rel_dt.date()
    finals = data.get("finals") or {}
    season = (data.get("tournaments") or {}).get("season") or []
    updates = data.get("updates") or []
    matches = data.get("matches") or []
    female = data.get("female") or {}
    wk, wn = week_label(today)
    jour = f"{JOURS[today.weekday()]} {date_fr(today.isoformat())}"      # « lundi 20 octobre »
    rnd = random.Random(wk)
    vrs = data.get("ranking") or {}
    rows = vrs.get("rows") or []
    top_teams = {r["team"].lower() for r in rows[:25]}
    ranked = {r["team"].lower() for r in rows[:150]}                 # équipes classées : le reste est trop confidentiel
    tours = data.get("tournaments") or {"finished": [], "ongoing": [], "upcoming": []}
    if weekly and release and release > today:
        # Vidéo qui sort plus tard que le jour des infos : l'agenda est écrit pour le JOUR DE SORTIE
        # (un tournoi qui aura commencé est « en cours », un tournoi fini disparaît de l'agenda)
        tours, female = at_release(tours, release), at_release(female, release)
    trs = group_transfers(data.get("transfers") or [])
    fr_set = {t.strip().lower() for t in fr_teams if t.strip()}

    def relevant(t):
        if t.get("from_role") in ("analyst", "manager") or t.get("to_role") in ("analyst", "manager"):
            return False                                            # staff hors coach : pas une news
        return is_fr(t) or any((x or "").lower() in ranked for x in (t.get("from"), t.get("to")))

    def is_t1_transfer(t):
        return any((x or "").lower() in top_teams for x in (t.get("from"), t.get("to")))

    def is_fr(t):
        return any(p.get("flag") == "France" for p in t["players"]) or \
            any((x or "").lower() in fr_set for x in (t.get("from"), t.get("to")))

    out = {}
    for tier in ("T1", "T2"):
        tiers = ("S", "A") if tier == "T1" else ("B", "C")
        segs = []
        def known(t):                       # au moins une équipe connue (classée ou française) en finale
            return any((x or "").lower() in ranked or (x or "").lower() in fr_set for x in (t.get("winner"), t.get("runner_up")))
        fin = [t for t in tours.get("finished", []) if t["tier"] in tiers and (tier == "T1" or known(t))]
        fin.sort(key=lambda t: ("SABC".index(t["tier"]), -prize_of(t)))
        fin = fin[: 3 if weekly else 2]
        ong = sorted([t for t in tours.get("ongoing", []) if t["tier"] in tiers], key=lambda t: -prize_of(t))[:3]
        upc = sorted([t for t in tours.get("upcoming", []) if t["tier"] in tiers], key=lambda t: -prize_of(t))[:3]
        my_tr = [t for t in trs if is_t1_transfer(t) == (tier == "T1") and relevant(t)]
        if tier == "T2":
            my_tr.sort(key=lambda t: not is_fr(t))
        headline = None

        for i, t in enumerate(fin):
            c = city(t["location"])
            where = f" à {c}" if c else ""
            nm = nom_oral(t["name"])
            det = finals.get(t["name"])
            if i == 0:
                say = rnd.choice([
                    f"Gros titre : {t['winner']} remporte {nm}{where}, face à {t['runner_up']} en finale.",
                    f"On commence par le dernier résultat : {t['winner']} gagne {nm}{where}, contre {t['runner_up']} en finale.",
                    f"{cap(nm)}, c'est terminé{where} : {t['winner']} s'impose en finale contre {t['runner_up']}."])
            else:
                say = rnd.choice([f"Autre titre : {t['winner']} gagne {nm}, contre {t['runner_up']}.",
                                  f"Du côté de {nm}, c'est {t['winner']} qui l'emporte face à {t['runner_up']}."])
            rec_txt, rec_labels = record_sentence(t, season)
            if det:                                     # le score d'abord (il s'affiche avec), puis les records
                w, l = (int(x) for x in det["score"].split("-"))
                won = [m["map"] for m in det["maps"] if m["w"] > m["l"]]
                say += f" Victoire {w} à {l}" + (f", avec {liste(won)} pour {t['winner']}." if won and len(det["maps"]) > 1 else ".")
            say += rec_txt
            headline = headline or f"{t['winner']} remporte {t['name']}"
            segs.append(seg("result", say, {"title": t["name"], "winner": t["winner"], "runner_up": t["runner_up"] or "",
                                            "info": " · ".join(x for x in (c or ("En ligne" if t.get("online") else ""), t.get("prize", ""),
                                                                           range_fr(t["start"], t["end"])) if x),
                                            "score": det["score"] if det else "", "maps": det["maps"] if det else [],
                                            "roster": roster_of(t["winner"], rows), "records": rec_labels},
                            LIQUI_SRC))

        fresh = bool(rows) and (today - date.fromisoformat(vrs["date"])).days <= 9
        if tier == "T1" and rows and fresh:      # classement Valve : publié une fois par mois, on n'en parle que quand il sort
            r1, r2, r3 = rows[0], rows[1], rows[2]
            kept = r1.get("prev") == 1
            if fresh:
                say = f"Nouveau classement mondial officiel de Valve, publié le {date_fr(vrs['date'])} : {r1['team']} {'reste' if kept else 'devient'} numéro 1, devant {r2['team']} et {r3['team']}."
                climbs = [r for r in rows[:20] if r.get("prev") and r["prev"] - r["rank"] >= 3]
                if climbs:
                    b = max(climbs, key=lambda r: r["prev"] - r["rank"])
                    say += f" Grosse montée pour {b['team']}, qui passe de la {b['prev']}e à la {b['rank']}e place."
                headline = headline or f"{r1['team']} n°1 mondial"
            else:
                say = f"Au classement mondial de Valve, {r1['team']} est toujours numéro 1, devant {r2['team']} et {r3['team']}."
            note = ("Nouveau classement" if fresh else "Classement en vigueur") + f" du {date_fr(vrs['date'])}"
            segs.append(seg("ranking", say, {"rows": [{"rank": r["rank"], "team": r["team"], "points": r["points"],
                                                     "move": (r["prev"] - r["rank"]) if r.get("prev") else None} for r in rows[:8]],
                                             "note": note},
                            f"Source : classement Valve (VRS) du {date.fromisoformat(vrs['date']):%d/%m}"))

        if tier == "T2":
            frs = [t for t in my_tr if is_fr(t)][:5 if weekly else 4]
            if frs:
                lines = [transfer_sentence(t, rnd) for t in frs[:3 if weekly else 2]]
                say = "Sur la scène française : " + " ".join(lines)
                headline = headline or lines[0].rstrip(".")
                segs.append(seg("transfer" if len(frs) == 1 else "transfers", say,
                                {"title": "Scène française", "rows": [transfer_row(t) for t in frs],
                                 "player": frs[0]["players"][0]["name"]}, LIQUI_SRC))
                my_tr = [t for t in my_tr if t not in frs]
        if my_tr:
            pick = my_tr[:5]
            nsay = 3 if weekly else 2
            lines = [transfer_sentence(t, rnd) for t in pick[:nsay]]
            intro = rnd.choice(["Côté mercato : ", "Place au mercato : ", "Dans le mercato : "])
            rest = len(pick) - nsay
            extra = f" Et {fr_count(rest)} autre{'s' if rest > 1 else ''} mouvement{'s' if rest > 1 else ''} à l'écran." if rest > 0 else ""
            headline = headline or lines[0].rstrip(".")
            segs.append(seg("transfer" if len(pick) == 1 else "transfers", intro + " ".join(lines) + extra,
                            {"title": "Mercato", "rows": [transfer_row(t) for t in pick],
                             "player": pick[0]["players"][0]["name"]}, LIQUI_SRC))

        if tier == "T1" and updates:
            segs.append(update_segment(updates))
        if tier == "T1" and matches:
            pg = programme_segment(matches, rows, fr_set, rel_dt or release or today)
            if pg:
                segs.append(pg)
        if tier == "T2" and (female.get("finished") or female.get("ongoing") or female.get("upcoming")):
            segs.append(female_segment(female, rnd))
        if ong:
            t = ong[0]
            c = city(t["location"])
            say = f"En ce moment, {nom_oral(t['name'])} se joue{' à ' + c if c else ''}, jusqu'au {date_fr(t['end'])}."
            if len(ong) > 1:
                say += f" On suit aussi {nom_oral(ong[1]['name'])}."
            segs.append(seg("agenda", say, {"title": "En cours", "rows": [agenda_row(x) for x in ong]}, LIQUI_SRC))
        if upc:
            t = upc[0]
            ref = release if (weekly and release) else today        # le jour où la vidéo sera vue
            gap = (date.fromisoformat(t["start"]) - ref).days if t.get("start") else 99
            if gap == 1:
                say = f"Dès demain, rendez-vous pour {nom_oral(t['name'])}, qui démarre le {date_fr(t['start'])}."
            elif 1 < gap <= 6 and date.fromisoformat(t["start"]).weekday() > ref.weekday():
                say = f"Rendez-vous ce {JOURS[date.fromisoformat(t['start']).weekday()]} pour {nom_oral(t['name'])}, qui démarre le {date_fr(t['start'])}."
            else:
                say = rnd.choice([f"À suivre : {nom_oral(t['name'])}, à partir du {date_fr(t['start'])}.",
                                  f"La semaine prochaine, rendez-vous pour {nom_oral(t['name'])}, qui démarre le {date_fr(t['start'])}."]
                                 if gap >= 7 or date.fromisoformat(t["start"]).weekday() <= ref.weekday() else
                                 [f"À suivre : {nom_oral(t['name'])}, à partir du {date_fr(t['start'])}."])
            segs.append(seg("agenda", say, {"title": "À suivre", "rows": [agenda_row(x) for x in upc]}, LIQUI_SRC))

        chap = {"result": f"Résultats tier {1 if tier == 'T1' else 2}", "ranking": "Classement mondial",
                "agenda": "Agenda", "update": "Mise à jour CS2"}
        for x in segs:
            x["tier"] = tier
            x["chapter"] = ("Programme" if x["card"].get("title") == "Au programme" else
                            "Scène féminine" if x["card"].get("female") else None) or chap.get(x["kind"]) or \
                ("Scène française" if x["card"].get("title") == "Scène française"
                                                   else "Mercato" if tier == "T1" else "Mercato tier 2")
        content = len(segs)
        intro_say = rnd.choice([f"Salut c'est {prenom}, voilà l'actu de la scène {'pro' if tier == 'T1' else 'tier 2'} Counter-Strike, ce {jour}.",
                                f"Salut à tous c'est {prenom}, les news {'tier 1' if tier == 'T1' else 'tier 2'} de Counter-Strike de ce {jour}, c'est parti."])
        segs.insert(0, seg("intro", intro_say, {"tier": tier, "headline": headline or "L'actu Counter-Strike", "week": wn}))
        nxt = "jeudi pour l'actu du tier 2" if tier == "T1" else "mardi pour l'actu du tier 1"
        segs.append(seg("outro", rnd.choice([f"C'est tout pour aujourd'hui, abonne-toi pour ne rien rater, et on se retrouve {nxt}.",
                                             f"Voilà pour l'essentiel, si ça t'a plu abonne-toi, et rendez-vous {nxt}."]),
                        {"next": nxt}))
        short = {"intro": seg("short_intro", rnd.choice(
                     [f"Les infos Counter-Strike de ce {jour}, en moins d'une minute.",
                      f"L'actu CS2 {'tier 1' if tier == 'T1' else 'tier 2 et scène française'} de ce {jour}, en moins d'une minute."]), {}),
                 "outro": seg("short_outro", rnd.choice(["Toute l'actu est dans la vidéo complète sur la chaîne, abonne-toi.",
                                                         "La vidéo complète t'attend sur la chaîne, abonne-toi pour ne rien rater."]), {})}
        out[tier] = {"tier": tier, "week": wk, "week_num": wn, "headline": headline or "L'actu Counter-Strike",
                     "day": today.isoformat(), "day_label": date_fr(today.isoformat()),
                     "content": content, "segments": segs, "short": short}
    if flash:
        out["FLASH"] = flash_script(out, prenom, jour, rnd)
    if weekly:
        rel = release or today
        out["SEMAINE"] = weekly_script(out, prenom, f"{JOURS[rel.weekday()]} {date_fr(rel.isoformat())}", rel, rnd)
    return out


def roster_of(team, rows):
    """Les 5 joueurs de l'équipe d'après le classement Valve (VRS) ; [] si l'équipe n'y est pas (jamais inventé)."""
    n = re.sub(r"[^a-z0-9]", "", (team or "").lower())
    for r in rows or []:
        if re.sub(r"[^a-z0-9]", "", r["team"].lower()) == n:
            return list(r.get("roster") or [])[:5]
    return []


def _heure(dt):
    return f"{dt.hour} heures" + (f" {dt.minute:02d}" if dt.minute else "")


def _short_team(n):
    n = re.sub(r"\s*\([^)]*\)\s*$", "", n or "").strip()
    n = re.sub(r"\s+(Esports|eSports|Gaming|Team)$", "", n)
    return re.sub(r"^Team\s+(?=\S)", "", n) if n.lower() not in ("team liquid",) else "Liquid"


def at_release(tours, rel):
    """Tournois « en cours » / « à venir » vus depuis le jour de sortie de la vidéo (et non le jour des infos)."""
    tours = dict(tours or {})
    ong, upc = [], []
    for t in list(tours.get("ongoing") or []) + list(tours.get("upcoming") or []):
        try:
            s, e = date.fromisoformat(t["start"]), date.fromisoformat(t["end"])
        except (KeyError, ValueError, TypeError):
            (ong if t in (tours.get("ongoing") or []) else upc).append(t)
            continue
        if e < rel:
            continue                                   # fini avant la sortie de la vidéo
        (ong if s <= rel else upc).append(t)
    tours["ongoing"], tours["upcoming"] = ong, upc
    return tours


def programme_segment(matches, rows, fr_set, release):
    """Les gros matchs des 7 jours après la sortie de la vidéo (heure française), d'après Liquipedia:Matches."""
    from datetime import datetime as _dt, time as _time
    start = _dt.combine(release, _time(18, 0)) if not isinstance(release, _dt) else release
    end = start + timedelta(days=7)
    rank = {}
    for r in rows or []:
        rank[re.sub(r"[^a-z0-9]", "", r["team"].lower())] = r["rank"]
    def rk(team):
        k = re.sub(r"[^a-z0-9]", "", _short_team(team).lower())
        return rank.get(k) or rank.get(re.sub(r"[^a-z0-9]", "", team.lower())) or 999
    def is_fr(team):
        return _short_team(team).lower() in fr_set or team.lower() in fr_set
    picked = []
    for m in matches:
        when = _dt.fromtimestamp(m["ts"])
        if not (start <= when < end):
            continue
        r1, r2 = rk(m["t1"]), rk(m["t2"])
        if min(r1, r2) <= 12 or (r1 <= 30 and r2 <= 30) or is_fr(m["t1"]) or is_fr(m["t2"]):
            picked.append((min(r1, r2) + max(r1, r2) / 10, when, m))
    if not picked:
        return None
    picked.sort(key=lambda x: x[0])
    top = sorted(picked[:4], key=lambda x: x[1])
    best = picked[0]
    a, b = _short_team(best[2]["t1"]), _short_team(best[2]["t2"])
    tour = re.sub(r"\s*-\s*.*$", "", best[2]["tournament"])
    when_txt = ("dès ce soir" if best[1].hour >= 17 else "aujourd'hui") if best[1].date() == start.date() else \
        f"{JOURS[best[1].weekday()]} {date_fr(best[1].date().isoformat())}"
    say = f"Au programme : {when_txt} à {_heure(best[1])}, {a} affronte {b} au {tour}."
    others = [x for x in top if x is not best][:1]
    if others:
        o = others[0]
        oday = "aujourd'hui" if o[1].date() == start.date() else JOURS[o[1].weekday()]
        say += f" À suivre aussi : {_short_team(o[2]['t1'])} contre {_short_team(o[2]['t2'])}, {oday} à {_heure(o[1])}."
    rows_card = [{"name": f"{_short_team(x[2]['t1'])} – {_short_team(x[2]['t2'])}",
                  "when": f"{JOURS[x[1].weekday()]} {x[1].day} · {x[1]:%H:%M}",
                  "where": re.sub(r"\s*-\s*.*$", "", x[2]["tournament"])} for x in top]
    return seg("agenda", say, {"title": "Au programme", "rows": rows_card[:3]}, LIQUI_SRC)


def female_segment(female, rnd):
    fin = female.get("finished") or []
    if fin:
        t = fin[0]
        say = (f"Côté scène féminine, {t['winner']} remporte {nom_oral(t['name'])}"
               + (f", face à {t['runner_up']} en finale." if t.get("runner_up") else "."))
        return seg("result", say, {"title": t["name"], "winner": t["winner"], "runner_up": t.get("runner_up") or "",
                                   "info": " · ".join(x for x in (city(t["location"]) or ("En ligne" if t.get("online") else ""),
                                                                  t.get("prize", ""), range_fr(t["start"], t["end"])) if x),
                                   "female": True}, LIQUI_SRC)
    xs = (female.get("ongoing") or []) + (female.get("upcoming") or [])
    t = xs[0]
    say = (f"Côté scène féminine, {nom_oral(t['name'])} " +
           (f"se joue en ce moment, jusqu'au {date_fr(t['end'])}." if t in (female.get("ongoing") or [])
            else f"démarre le {date_fr(t['start'])}."))
    return seg("agenda", say, {"title": "Scène féminine", "rows": [agenda_row(x) for x in xs[:3]], "female": True}, LIQUI_SRC)


def record_sentence(t, season):
    """Le contexte : « C'est son troisième titre de l'année », « deuxième finale perdue d'affilée »."""
    if t["tier"] not in ("S", "A") or not season:
        return "", []
    same = lambda a, b: re.sub(r"[^a-z0-9]", "", (a or "").lower()) == re.sub(r"[^a-z0-9]", "", (b or "").lower())
    past = [x for x in season if x["end"] <= t["end"]]
    if not any(x["name"] == t["name"] for x in past):
        past.append({k: t[k] for k in ("name", "tier", "end", "winner", "runner_up")})
    out, labels = "", []
    n = sum(1 for x in past if same(x["winner"], t["winner"]))
    if n >= 2:
        out += f" C'est son {fr_ord(n)} titre de l'année."
        labels.append({"key": "titre", "label": f"{n}e titre de l'année"})
    if t.get("runner_up"):
        streak = 0
        for x in sorted(past, key=lambda x: x["end"], reverse=True):
            if same(x["runner_up"], t["runner_up"]):
                streak += 1
            elif same(x["winner"], t["runner_up"]):
                break
        if streak >= 2:
            out += f" Pour {t['runner_up']}, c'est une {fr_ord(streak).replace('premier', 'première')} finale perdue d'affilée."
            labels.append({"key": "finale", "label": f"{t['runner_up']} : {streak}e finale perdue d'affilée"})
    return out, labels


SECTIONS_FR = {"MAPS": "Cartes", "MAP": "Cartes", "GAMEPLAY": "Gameplay", "MISC": "Divers", "AUDIO": "Son", "SOUND": "Son",
               "UI": "Interface", "ITEMS": "Objets", "WEAPONS": "Armes", "PREMIER": "Premier", "ANIMATION": "Animations",
               "NETWORKING": "Réseau", "GENERAL": "Général", "MATCHMAKING": "Matchmaking", "STEAM WORKSHOP": "Workshop",
               "WORKSHOP": "Workshop", "CROSSHAIR": "Viseur", "RUSH": "Mode Rush", "SETTINGS": "Réglages", "ENGINE": "Moteur",
               "SCRIPTING": "Scripts", "MAP SCRIPTING": "Scripts de cartes"}


def update_segment(updates):
    """Mise à jour de CS2 de la semaine (notes officielles de Valve) : ce qui change, en français."""
    u = updates[0]
    maps = [m for x in updates for m in x["maps"]]
    maps = list(dict.fromkeys(maps))[:4]
    weapons = list(dict.fromkeys(w for x in updates for w in x["weapons"]))[:3]
    n = sum(x["count"] for x in updates)
    bits = []
    if any(x["operation"] for x in updates):
        bits.append("une nouvelle opération")
    if any(x["map_pool"] for x in updates):
        bits.append("un changement dans le pool de cartes en compétition")
    if any(x.get("mode") for x in updates):
        bits.append("un nouveau mode de jeu")
    if any(x.get("premier") for x in updates):
        bits.append("des changements en Premier")
    if any(x["case"] for x in updates):
        bits.append("une nouvelle caisse")
    if any(x.get("music") for x in updates):
        bits.append("un nouveau kit musical")
    if maps:
        bits.append(f"des retouches sur {liste(maps)}")
    if weapons:
        arts = [("l'" if w in ("AWP", "AK-47", "AUG", "M4A4", "M4A1-S") else "le ") + w for w in weapons]
        bits.append("des changements sur " + liste(arts))
    many = len(updates) > 1
    say = (f"Côté jeu, Valve a sorti {fr_count(len(updates))} mises à jour de CS2 cette semaine" if many else
           f"Côté jeu, mise à jour de CS2 le {date_fr(u['date'])}")
    say += (", avec " + liste(bits) + "." if bits else f", avec {n} changements au total.")
    rows = []
    for x in updates[:2]:
        for k, v in x["sections"].items():
            label = SECTIONS_FR.get(k, k.title())
            extra = ", ".join(x["maps"][:3]) if label == "Cartes" and x["maps"] else f"{len(v)} changement{'s' if len(v) > 1 else ''}"
            rows.append({"name": label, "info": extra})
    if weapons:
        rows.insert(1 if rows and rows[0]["name"] == "Cartes" else 0, {"name": "Armes", "info": ", ".join(weapons)})
    for flag, label in (("operation", "Nouvelle opération"), ("map_pool", "Pool de cartes"), ("case", "Nouvelle caisse"),
                        ("mode", "Nouveau mode")):
        if any(x.get(flag) for x in updates):
            rows.insert(0, {"name": label, "info": "dans cette mise à jour"})
    return seg("update", say, {"title": "Mise à jour CS2", "date": date_fr(u["date"]), "rows": rows[:5],
                               "maps": maps, "weapons": weapons, "url": u["url"]},
               "Source : notes de mise à jour officielles (Steam)")


def liste(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " et " + xs[-1]


def weekly_script(out, prenom, jour, rel, rnd):
    """La vidéo de la semaine : tier 1, puis tier 2 et scène française, puis l'agenda. Chapitrée.
    Deux Shorts : A = le tier 1, B = le tier 2 et la scène française."""
    import copy
    t1, t2 = copy.deepcopy(out["T1"]), copy.deepcopy(out["T2"])
    body = lambda sc: [x for x in sc["segments"] if x["kind"] not in ("intro", "outro", "agenda")]
    agenda = lambda sc: [x for x in sc["segments"] if x["kind"] == "agenda"]
    b1, b2 = body(t1), body(t2)
    if b2 and b2[0]["kind"] == "result":            # le « gros titre » est déjà dans le tier 1
        b2[0]["sub"] = b2[0]["sub"].replace("Gros titre : ", "Côté tier 2 : ", 1)
        b2[0]["say"] = b2[0]["say"].replace("Gros titre, ", "Côté tier 2, ", 1)
    headline = (t1["headline"] if b1 else t2["headline"]) or "L'actu Counter-Strike"
    segs = [seg("intro", rnd.choice([f"Salut c'est {prenom}, voici le point Counter-Strike de la semaine, ce {jour}.",
                                     f"Salut à tous c'est {prenom}, toute l'actu Counter-Strike de la semaine, ce {jour}, c'est parti."]),
                {"tier": "SEMAINE", "headline": headline, "week": t1["week_num"]})]
    segs[0]["chapter"] = "Intro"
    segs += b1
    if b2:
        sec = seg("section", rnd.choice(["Place au tier 2 et à la scène française.",
                                         "On passe au tier 2, avec la scène française."]),
                  {"title": "TIER 2", "sub": "et scène française"})
        sec.update(tier="T2", chapter="Résultats tier 2")
        segs += [sec] + b2
    ag = agenda(t1) + agenda(t2)
    ag.sort(key=lambda x: x["card"].get("title") != "Au programme")       # le programme des matchs d'abord
    seen_now = False
    for x in ag:                                     # deux « En ce moment » à la suite : la 2e phrase change de tournure
        if x["sub"].startswith("En ce moment, "):
            if seen_now:
                for k in ("say", "sub"):          # (say = texte prononcé, sub = sous-titre)
                    x[k] = x[k].replace("En ce moment, ", "Côté tier 2, ", 1)
            seen_now = True
    for x in ag:
        x["chapter"] = "Programme" if x["card"].get("title") == "Au programme" else "Agenda"
    segs += ag
    segs.append(seg("outro", rnd.choice(["C'est tout pour cette semaine, abonne-toi pour ne rien rater, et on se retrouve la semaine prochaine.",
                                         "Voilà pour l'actu de la semaine, si ça t'a plu abonne-toi, et à la semaine prochaine."]),
                    {"next": "la semaine prochaine"}))
    segs[-1]["chapter"] = "Agenda" if ag else (segs[-2].get("chapter") or "Fin")
    idx = {id(x): i for i, x in enumerate(segs)}
    shorts = []
    for key, part, sc, label in (("A", b1, t1, "tier 1"), ("B", b2, t2, "tier 2 et scène française")):
        if not part:
            continue
        shorts.append({"key": key, "tier": sc["tier"], "headline": sc["headline"], "segs": [idx[id(x)] for x in part],
                       "intro": seg("short_intro", f"L'actu Counter-Strike {label} de la semaine, en moins d'une minute.", {}),
                       "outro": seg("short_outro", rnd.choice(["Toute l'actu est dans la vidéo de la semaine sur la chaîne, abonne-toi.",
                                                               "La vidéo complète t'attend sur la chaîne, abonne-toi pour ne rien rater."]), {})})
    return {"tier": "SEMAINE", "week": t1["week"], "week_num": t1["week_num"], "headline": headline,
            "day": rel.isoformat(), "day_label": date_fr(rel.isoformat()), "content": t1["content"] + t2["content"],
            "segments": segs, "shorts": shorts, "short": None}


def flash_script(out, prenom, jour, rnd):
    """Édition flash : le contenu du tier 1 (ou du tier 2 s'il n'y a rien en tier 1), avec une intro « flash info » datée."""
    import copy
    base = out["T1"] if out["T1"]["content"] >= 2 or out["T1"]["content"] >= out["T2"]["content"] else out["T2"]
    sc = copy.deepcopy(base)
    sc["tier"] = "FLASH"
    sc["from_tier"] = base["tier"]
    segs = sc["segments"]
    hl = sc["headline"]
    segs[0] = seg("intro", rnd.choice([f"Salut c'est {prenom}, flash info Counter-Strike de ce {jour}.",
                                       f"Salut à tous c'est {prenom}, édition spéciale des news Counter-Strike, ce {jour}."]),
                  {"tier": "FLASH", "headline": hl, "week": sc["week_num"]})
    segs[-1] = seg("outro", rnd.choice(["C'est tout pour ce flash, abonne-toi pour ne rien rater, et on se retrouve mardi et jeudi pour les news habituelles.",
                                        "Voilà pour ce flash info, si ça t'a plu abonne-toi, et rendez-vous mardi et jeudi pour les news."]),
                   {"next": "mardi et jeudi"})
    sc["short"]["intro"] = seg("short_intro", f"Flash info Counter-Strike, ce {jour}.", {})
    return sc


def fr_count(n):
    return {1: "un", 2: "deux", 3: "trois", 4: "quatre", 5: "cinq", 6: "six"}.get(n, str(n))


ROMAINS = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
           "XIII": 13, "XIV": 14, "XV": 15, "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20}


def nom_oral(name):
    """Nom de tournoi « comme on le dit » : « Stake Pulse Beat III » -> « l'édition 3 de Stake Pulse Beat »,
    « CCT Europe 2026 Series #12 » -> « l'édition 12 de CCT Europe ». L'écran garde le nom officiel."""
    n = name.split(":")[0].strip() if ":" in name else name.strip()
    tail = name.split(":", 1)[1] if ":" in name else ""
    ed = None
    m = re.search(r"\s*#\s*(\d+)\s*$", tail or n)
    if m:
        ed = int(m.group(1))
        if not tail:
            n = n[:m.start()].strip()
    else:
        m = re.search(r"\s+([IVX]{1,5})$", n)
        if m and m.group(1) in ROMAINS:
            ed, n = ROMAINS[m.group(1)], n[:m.start()].strip()
    if ed is not None:
        n = re.sub(r"\s+(Series|Cup|Edition)$", "", n, flags=re.I)
    n = re.sub(r"\s+20\d\d$", "", re.sub(r"\s+20\d\d(?=\s)", "", n)) or n   # l'année ne se dit pas
    return f"l'édition {ed} de {n}" if ed is not None else n


def cap(t):
    return t[:1].upper() + t[1:]


def agenda_row(t):
    return {"name": t["name"], "when": range_fr(t["start"], t["end"]), "where": city(t["location"]) or ("En ligne" if t.get("online") else "")}


# ---------------------------------------------------------------------
#  Option : réécriture par Claude (clé API, payé à l'usage)
# ---------------------------------------------------------------------
def polish_with_claude(script, api_key, model, prenom):
    texts = [s["sub"] for s in script["segments"]]
    prompt = ("Tu écris pour la chaîne YouTube CS2 de " + prenom + ", qui lit ces textes à voix haute dans une vidéo news. "
              "Réécris chaque texte pour qu'il sonne naturel et dynamique à l'oral, en français, en tutoyant le spectateur. "
              "Règles strictes : n'ajoute AUCUNE information, aucun chiffre, aucun nom, aucune opinion sur des faits ; "
              "garde exactement les noms d'équipes, de joueurs et de tournois ; une ou deux phrases par texte, pas plus long que l'original + 30 %. "
              "Réponds uniquement avec un tableau JSON de chaînes, dans le même ordre.\n\n" + json.dumps(texts, ensure_ascii=False))
    body = json.dumps({"model": model, "max_tokens": 2000, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST",
                                 headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        resp = json.loads(r.read().decode("utf-8"))
    txt = "".join(b.get("text", "") for b in resp.get("content", []))
    m = re.search(r"\[.*\]", txt, re.S)
    new = json.loads(m.group(0)) if m else None
    if not isinstance(new, list) or len(new) != len(texts):
        raise RuntimeError("réponse inattendue")
    for s, t in zip(script["segments"], new):
        if not isinstance(t, str) or not t.strip():
            continue
        # garde-fou : tous les noms propres de l'original doivent rester
        keep = set(re.findall(r"\b[A-Z][\w-]{1,}\b", s["sub"])) - {"Salut", "On", "Le", "La", "Les", "Et", "En", "Du", "Au", "Côté", "Place", "Gros", "Autre", "Voilà", "Si", "Dans", "Sur", "Nouveau", "Grosse", "Abonne", "Ciao", "Counter-Strike"}
        if all(k in t for k in keep):
            s["sub"], s["say"] = t.strip(), spoken(t.strip())
    script["writer"] = "claude"
    return script
