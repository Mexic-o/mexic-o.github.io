# -*- coding: utf-8 -*-
"""
maj_news.py - les news CS2 du site mexic-o.github.io, mises à jour par GITHUB tout seul (GitHub Actions).

Tourne chaque jour sur les serveurs de GitHub (PC éteint, rien à faire) :
  1. collecte l'actu (Liquipedia, classement Valve, mises à jour CS2 de Steam), comme Mexic Studio ;
  2. en fait les petits articles du site (même code que Mexic Studio : news_script + news_site) ;
  3. cherche la dernière vidéo « News CS2 » publique de la chaîne (flux public YouTube, sans compte) ;
  4. écrit news.json à la racine du site et garde l'historique dans outil/historique.json.

Lancé par .github/workflows/site.yml. À la main (sur un PC) : python outil/maj_news.py
"""
import datetime
import json
import os
import re
import sys
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
RACINE = os.environ.get("GITHUB_WORKSPACE") or (os.path.dirname(ICI) if os.path.basename(ICI) == "outil" else ICI)

import news_script as NS
import rondes as RONDES      # noqa: E402
import bracket as BRACKET    # noqa: E402
import swiss as SWISS        # noqa: E402
import discord_news as DISCORD  # noqa: E402
import news_site as SITE      # noqa: E402
import news_sources as SRC    # noqa: E402

# ---------------------------------------------------------------- réglages
CHAINE = "@Mexic_Original"                 # la chaîne YouTube (pour le bouton « Voir la vidéo de la semaine »)
CHAINE_ID = ""                             # rempli tout seul (UC...) ; à mettre à la main si la recherche échoue
CONTACT = "Mexic Original / twitch.tv/mexic_original"     # pour le User-Agent poli demandé par Liquipedia
EQUIPES_FR = "Gentle Mates, Mandatory, Wildcard, Solary, BLUEJAYS, Joblife, Vitality Academy, GameWard, Team Bliss"
VIDEO_JOURS = 7                            # le bouton vidéo reste affiché 7 jours après la sortie
MOTS_VIDEO = ("point cs2 de la semaine", "news cs2", "flash info cs2")
# --------------------------------------------------------------------------

SITE.DOSSIER_SITE = RACINE                                   # news.json à la racine du site
SITE.HISTORIQUE = os.path.join(RACINE, "outil", "historique.json")
SITE.JOURNAL = os.path.join(os.environ.get("RUNNER_TEMP") or ICI, "journal_site.txt")
SRC.CONTACT = CONTACT


def dire(msg):
    print(msg, flush=True)


def collecte():
    """La même collecte que Mexic Studio (news_make.collect), sans rien d'autre."""
    errors = []
    data = {"day": datetime.date.today().isoformat(), "collected": datetime.datetime.now().isoformat(timespec="seconds"),
            "errors": errors}
    dire("Classement mondial Valve...")
    try:
        data["ranking"] = SRC.vrs_rankings()
    except Exception as e:
        errors.append(f"classement : {e}")
        data["ranking"] = None
    dire("Tournois (Liquipedia, une page toutes les 30 s : c'est leur règle)...")
    data["tournaments"] = SRC.tournaments(tiers=("S", "A", "B", "C"), errors=errors)
    data["finals"] = {}
    fins = sorted(data["tournaments"].get("finished", []), key=lambda t: ("SABC".index(t["tier"]), -NS.prize_of(t)))[:6]
    for t in fins:
        try:
            d = SRC.final_detail(t)
        except Exception as e:
            d = None
            errors.append(f"finale {t['name']} : {e}")
        if d:
            data["finals"][t["name"]] = d
    dire("Programme des matchs, scène féminine...")
    data["matches"], data["completed"], html_matchs = SRC.matches_page(errors=errors)
    dire(f"  {len(data['matches'])} match(s) à venir, {len(data['completed'])} match(s) terminé(s) avec score")
    if html_matchs and data["matches"] and not data["completed"]:
        _garder_page(html_matchs)                       # scores illisibles : page gardée pour la corriger
    elif html_matchs and not os.path.exists(os.path.join(DEBUG, "liquipedia_matches.html")):
        _garder_page(html_matchs, "copie unique de la page des matchs (pour lire les phases du tournoi)")
    data["female"] = SRC.female_tournaments(errors=errors)
    dire("Mises à jour de CS2 (Steam)...")
    try:
        data["updates"] = SRC.cs2_updates()
    except Exception as e:
        data["updates"] = []
        errors.append(f"mises à jour CS2 : {e}")
    dire("Transferts...")
    data["transfers"] = SRC.transfers(errors=errors)
    copies_pages_tournois(data)
    for e in errors:
        dire(f"  [ATTENTION] {e}")
        if os.environ.get("GITHUB_ACTIONS"):
            dire(f"::warning title=Source en panne::{e}")      # visible sur la page du lancement (Annotations)
    return data


DEBUG = os.path.join(ICI, "debug")
MATCH_HEURES = 36                    # résultats des dernières 36 h
MATCH_MAX = 7                        # matchs affichés par tournoi et par jour
EQUIPES_SUIVIES = "Vitality"         # toujours mises en avant, en plus des équipes françaises


def _garder_page(html, pourquoi="[ATTENTION] scores des matchs non lus"):
    os.makedirs(DEBUG, exist_ok=True)
    with open(os.path.join(DEBUG, "liquipedia_matches.html"), "w", encoding="utf-8") as f:
        f.write(html)
    dire(f"  {pourquoi} : page gardée dans outil/debug")


def _paris(ts):
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.fromtimestamp(ts, ZoneInfo("Europe/Paris"))
    except Exception:
        return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc) + datetime.timedelta(hours=1)


def _jour_tournoi(t, jour):
    """« jour 2 » : le numéro du jour dans le tournoi (à partir de sa date de début sur Liquipedia)."""
    try:
        n = (datetime.date.fromisoformat(jour) - datetime.date.fromisoformat(t["start"])).days + 1
        fin = (datetime.date.fromisoformat(t["end"]) - datetime.date.fromisoformat(t["start"])).days + 1
    except (KeyError, TypeError, ValueError):
        return ""
    if not (1 <= n <= fin):
        return ""
    return "dernier jour" if n == fin and fin > 1 else f"jour {n}"


def articles_matchs(data, maintenant=None):
    """Les résultats des matchs des gros tournois en cours (tier S et A) : un article par tournoi et par jour,
    chaque match dans une pastille (« Vitality 2-1 MOUZ »). Rien d'inventé : seulement les scores lus sur Liquipedia."""
    maintenant = maintenant or datetime.datetime.now(datetime.timezone.utc)
    tours = data.get("tournaments") or {}
    gros = {}
    for t in (tours.get("ongoing") or []) + (tours.get("finished") or []):
        if t.get("tier") in ("S", "A"):
            gros[t.get("page") or t["name"]] = t
            gros.setdefault(t["name"], t)
    suivies = [x.strip().lower() for x in (EQUIPES_FR + "," + EQUIPES_SUIVIES).split(",") if x.strip()]
    est_suivie = lambda n: any(x in n.lower() for x in suivies)
    limite = maintenant.timestamp() - MATCH_HEURES * 3600
    groupes, infos = {}, {}
    for m in data.get("completed") or []:
        if m["ts"] < limite or m["ts"] > maintenant.timestamp():
            continue
        t = gros.get(m["page"]) or gros.get(m["tournament"])
        if not t and not (est_suivie(m["t1"]) or est_suivie(m["t2"])):
            continue
        jour = _paris(m["ts"]).date().isoformat()
        groupes.setdefault((t["name"] if t else m["tournament"], jour), []).append(m)
        if t:
            infos[t["name"]] = t
    arts = []
    for (nom, jour), ms in groupes.items():
        etape = _jour_tournoi(infos[nom], jour) if nom in infos else ""
        ms.sort(key=lambda m: (not (est_suivie(m["t1"]) or est_suivie(m["t2"])), m["ts"]))
        court = lambda m, k: m.get(k + "_court") or m[k]
        pastilles = [f"{court(m, 't1')} {m['s1']}-{m['s2']} {court(m, 't2')}" for m in ms[:MATCH_MAX]]
        phrases = []
        for m in ms:
            if est_suivie(m["t1"]) or est_suivie(m["t2"]):
                g, p = (court(m, "t1"), court(m, "t2")) if m["s1"] > m["s2"] else (court(m, "t2"), court(m, "t1"))
                sc = f"{max(m['s1'], m['s2'])}-{min(m['s1'], m['s2'])}"
                phrases.append(f"{g} bat {p} {sc}.")
        reste = len(ms) - len(pastilles)
        resume = " ".join(phrases[:3]) or f"{len(ms)} match{'s' if len(ms) > 1 else ''} joué{'s' if len(ms) > 1 else ''}."
        if reste > 0:
            resume += f" Et {reste} autre{'s' if reste > 1 else ''} match{'s' if reste > 1 else ''}."
        ph = _phase_principale(ms)
        titre = " · ".join(x for x in (nom, etape, ph) if x) + f" : les résultats du {NS.date_fr(jour)}"
        art = SITE._article(f"jour|{nom}|{jour}", titre, resume,
                            "resultats", "Tier 1", pastilles)
        art["date"] = jour                                   # daté du jour des matchs, pas du jour de la collecte
        arts.append(art)
    return arts


def phase_de(m):
    """La phase lue dans l'adresse de la page du match : Round 3, groupe B, playoffs. Rien si on ne sait pas."""
    mt = re.search(r"#(Round|Group|Playoffs)_?([0-9A-Za-z]*)", m.get("page") or "")
    if not mt:
        return ""
    if mt.group(1) == "Round":
        return f"round {mt.group(2)}"
    if mt.group(1) == "Group":
        return f"groupe {mt.group(2)}"
    return "playoffs"


def _phase_principale(ms):
    from collections import Counter
    c = Counter(phase_de(m) for m in ms if phase_de(m))
    return c.most_common(1)[0][0] if c else ""


def _prix(txt):
    """« $1,250,000 » -> « 1 250 000 $ » (écriture française)."""
    m = re.fullmatch(r"\s*([$€£])\s*([\d,.\s]+)\s*", txt or "")
    if not m:
        return txt
    n = re.sub(r"\D", "", m.group(2).split(".")[0])
    return (f"{int(n):,}".replace(",", "\u202f") + " " + m.group(1)) if n else txt


def articles_debuts(data, aujourdhui=None):
    """Un gros tournoi (tier S) qui vient de commencer : un article, même avant les premiers scores."""
    aujourdhui = aujourdhui or datetime.date.today()
    out = []
    for t in (data.get("tournaments") or {}).get("ongoing") or []:
        if t.get("tier") != "S":
            continue
        debut = datetime.date.fromisoformat(t["start"])
        if not (0 <= (aujourdhui - debut).days <= 2):
            continue
        ville = NS.city(t.get("location"))
        bits = [f"à {ville}" if ville else ("en ligne" if t.get("online") else ""),
                f"jusqu'au {NS.date_fr(t['end'])}", (_prix(t["prize"]) + " en jeu") if t.get("prize") else ""]
        art = SITE._article(f"debut|{t['name']}", f"{t['name']} a commencé",
                            "Le tournoi se joue " + ", ".join(b for b in bits if b) + ".", "resultats", "Tier 1")
        art["date"] = t["start"]                           # daté du 1er jour : les résultats passent devant
        out.append(art)
    return out


# Pages de tournois dont on garde une copie (une seule fois), pour lire bracket, notes d'effectif et casters.


MAX_PAGES_TOURNOIS = 4                # pages de tournois lues à chaque passage (une toutes les 30 s)


def pages_tournois(data):
    """Les gros tournois (tier S et A) en cours ou qui commencent : leur page Liquipedia est lue. Liste donnée par Liquipedia."""
    tours = data.get("tournaments") or {}
    voulus = []
    for statut, liste in (("ongoing", tours.get("ongoing") or []), ("upcoming", tours.get("upcoming") or [])):
        for t in liste:
            if t.get("tier") in ("S", "A") and t.get("page") and t["page"] not in [v["page"] for v in voulus]:
                voulus.append(dict(t, _statut=statut))
    # Tier 1 d'abord (le plus suivi), puis les tournois en cours avant ceux qui commencent, puis par nom
    voulus.sort(key=lambda t: (t.get("tier") != "S", t.get("_statut") != "ongoing", t.get("name", "")))
    return voulus[:MAX_PAGES_TOURNOIS]


def copies_pages_tournois(data):
    """Relit à chaque passage la page des gros tournois (liste donnée par Liquipedia, une page toutes les 30 s).
    Garde une copie dans outil/debug ; si la lecture échoue, on reprend la dernière copie gardée.
    Range les résultats (rondes, brackets, classement Swiss) par page de tournoi."""
    import time
    data["rondes"], data["brackets"], data["swiss"] = {}, {}, {}
    for t in pages_tournois(data):
        chemin, nom = t["page"], t["name"]
        cible = os.path.join(DEBUG, "tournoi_%s.html" % re.sub(r"\W+", "_", chemin).strip("_"))
        html = None
        try:
            rep = json.loads(SRC.fetch(SRC.LIQUI_API, {"action": "parse", "page": chemin, "prop": "text",
                                                       "format": "json", "formatversion": "2",
                                                       "disablelimitreport": "1"}))
            if "error" in rep:
                raise RuntimeError(rep["error"].get("info", "erreur Liquipedia"))
            html = rep["parse"]["text"]
            os.makedirs(DEBUG, exist_ok=True)
            with open(cible, "w", encoding="utf-8") as f:
                f.write(html)
            dire("  page du tournoi relue : %s" % nom)
        except Exception as e:
            dire("  [ATTENTION] page du tournoi %s : %s" % (nom, e))
            if os.path.exists(cible):
                with open(cible, encoding="utf-8") as f:
                    html = f.read()
                dire("  on reprend la dernière copie gardée")
        if html:
            data["rondes"][chemin] = RONDES.parse_rondes(html)
            data["brackets"][chemin] = BRACKET.parse_bracket(html)
            data["swiss"][chemin] = SWISS.parse_swiss(html)
        time.sleep(30)


def _cle_equipe(nom):
    """Nom d'équipe normalisé : « Team Vitality », « Vitality », « The MongolZ » et « MongolZ » donnent la même clé."""
    mots = re.findall(r"[a-z0-9]+", (nom or "").lower())
    return "".join(m for m in mots if m not in ("team", "the", "esports", "esport", "gaming"))


def _meme_paire(a, b, c, d):
    return sorted([_cle_equipe(a), _cle_equipe(b)]) == sorted([_cle_equipe(c), _cle_equipe(d)])


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (site Mexic Original)",
                                               "Accept-Language": "fr-FR,fr;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def chaine_id(h):
    if CHAINE_ID:
        return CHAINE_ID
    if (h.get("chaine") or {}).get("handle") == CHAINE and h["chaine"].get("id"):
        return h["chaine"]["id"]
    page = _get("https://www.youtube.com/" + CHAINE)
    m = re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"', page) or \
        re.search(r'youtube\.com/channel/(UC[\w-]{22})', page)
    if not m:
        raise RuntimeError("identifiant de la chaîne introuvable (remplis CHAINE_ID dans outil/maj_news.py)")
    h["chaine"] = {"handle": CHAINE, "id": m.group(1)}
    return m.group(1)


def video_de_la_semaine(h, maintenant=None):
    """Lien de la dernière vidéo news PUBLIQUE de la chaîne (flux public YouTube), si elle a moins de VIDEO_JOURS jours.
    Une vidéo programmée n'apparaît dans le flux qu'à sa sortie : le bouton arrive tout seul au bon moment."""
    maintenant = maintenant or datetime.datetime.now(datetime.timezone.utc)
    flux = _get("https://www.youtube.com/feeds/videos.xml?channel_id=" + chaine_id(h))
    for entree in re.findall(r"<entry>(.*?)</entry>", flux, re.S):
        titre = re.search(r"<title>(.*?)</title>", entree, re.S)
        vid = re.search(r"<yt:videoId>(.*?)</yt:videoId>", entree)
        pub = re.search(r"<published>(.*?)</published>", entree)
        if not (titre and vid and pub):
            continue
        t = titre.group(1).replace("&amp;", "&").lower()
        if not any(m in t for m in MOTS_VIDEO):
            continue
        quand = datetime.datetime.fromisoformat(pub.group(1).replace("Z", "+00:00"))
        if maintenant - quand <= datetime.timedelta(days=VIDEO_JOURS):
            return "https://youtu.be/" + vid.group(1), quand.date().isoformat()
        return "", ""                       # la dernière vidéo news est trop vieille : plus de bouton
    return "", ""


PROG_HEURES = 24                     # programme : les matchs des prochaines 24 h


def articles_programme(data, memoire=None, maintenant=None):
    """Le programme des gros tournois (tier S et A), jour par jour. Chaque jour garde tous ses matchs :
    joués (avec le score) et à venir. Le programme est mémorisé (memoire, dans historique.json) pour ne rien perdre
    quand un match est joué et sort de la liste des matchs à venir."""
    maintenant = maintenant or datetime.datetime.now(datetime.timezone.utc)
    memoire = memoire if memoire is not None else {}
    aujourdhui = _paris(maintenant.timestamp()).date()
    tours = data.get("tournaments") or {}
    gros = {}
    for t in (tours.get("ongoing") or []) + (tours.get("upcoming") or []) + (tours.get("finished") or []):
        if t.get("tier") in ("S", "A"):
            gros[t.get("page") or t["name"]] = t
            gros.setdefault(t["name"], t)
    suivies = [x.strip().lower() for x in (EQUIPES_FR + "," + EQUIPES_SUIVIES).split(",") if x.strip()]
    est_suivie = lambda m: any(x in (m["t1"] + " " + m["t2"]).lower() for x in suivies)

    def memoriser(m, joue):
        t = gros.get((m.get("page") or "").split("#")[0]) or gros.get(m.get("page") or "") or gros.get(m["tournament"])
        if not t and not est_suivie(m):
            return
        jour = _paris(m["ts"]).date().isoformat()
        nom = t["name"] if t else m["tournament"]
        bloc = memoire.setdefault(f"{nom}|{jour}", {"nom": nom, "jour": jour, "matchs": {}})
        # même match quel que soit l'ordre des équipes (à venir ou joué)
        ident = "|".join(sorted([m["t1"], m["t2"]]))
        for k in list(bloc["matchs"]):
            if k != ident and _meme_paire(*k.split("|"), m["t1"], m["t2"]):
                ancien_doublon = bloc["matchs"].pop(k)
                bloc["matchs"].setdefault(ident, ancien_doublon)
        ancien = bloc["matchs"].get(ident, {})
        e = {"ts": m["ts"], "t1": m["t1"], "t2": m["t2"],
             "t1_court": m.get("t1_court") or m["t1"], "t2_court": m.get("t2_court") or m["t2"],
             "bo": m.get("bo") or "", "phase": phase_de(m)}
        if joue:
            e["s1"], e["s2"] = m["s1"], m["s2"]
        elif "s1" in ancien:                       # le score déjà connu n'est jamais effacé
            if ancien.get("t1") == m["t1"]:
                e["s1"], e["s2"] = ancien["s1"], ancien["s2"]
            else:                                  # équipes dans l'autre ordre : on remet le score du bon côté
                e["s1"], e["s2"] = ancien["s2"], ancien["s1"]
        bloc["matchs"][ident] = e
        bloc["etape"] = _jour_tournoi(t, jour) if t else ""
        bloc["tier"] = t.get("tier") if t else ""

    for m in data.get("matches") or []:
        # seulement aujourd'hui et demain : pas les matchs de la semaine suivante
        if (_paris(m["ts"]).date() - aujourdhui).days > 1:
            continue
        memoriser(m, False)
    for m in data.get("completed") or []:
        memoriser(m, True)

    # matchs des brackets (playoffs, UB/LB) : scores et heures lus sur la page du tournoi
    for chemin, lignes in (data.get("brackets") or {}).items():
        t = gros.get(chemin)
        if not t:
            continue
        for r in lignes:
            if not r.get("ts"):
                continue
            jour_r = _paris(r["ts"]).date()
            if not (-2 <= (jour_r - aujourdhui).days <= 1):
                continue
            bloc = memoire.setdefault(f"{t['name']}|{jour_r.isoformat()}", {"nom": t["name"], "jour": jour_r.isoformat(), "matchs": {}})
            trouve = next((k for k, e in bloc["matchs"].items()
                           if _meme_paire(e["t1"], e["t2"], r["t1"], r["t2"])), None)
            if trouve is None:
                bloc["matchs"]["|".join(sorted([r["t1"], r["t2"]]))] = {
                    "ts": r["ts"], "t1": r["t1"], "t2": r["t2"], "t1_court": r["t1"], "t2_court": r["t2"],
                    "bo": "", "phase": "playoffs"}
                trouve = "|".join(sorted([r["t1"], r["t2"]]))
            e = bloc["matchs"][trouve]
            e.setdefault("phase", "playoffs")
            if r["s1"] is not None:
                if _cle_equipe(e["t1"]) == _cle_equipe(r["t1"]):
                    e["s1"], e["s2"] = r["s1"], r["s2"]
                else:
                    e["s1"], e["s2"] = r["s2"], r["s1"]

    # scores lus dans les tableaux de rondes de la page du tournoi : ils arrivent dès que Liquipedia les saisit
    for chemin, lignes in (data.get("rondes") or {}).items():
        t = gros.get(chemin)
        if not t:
            continue
        for r in lignes:
            if not r["date"]:
                continue
            if r["s1"] is None:
                # match pas encore joué : seulement s'il est aujourd'hui ou demain, et sans heure (Liquipedia ne la donne pas ici)
                jour_r = datetime.date.fromisoformat(r["date"])
                if not (0 <= (jour_r - aujourdhui).days <= 1):
                    continue
                if any(_meme_paire(e["t1"], e["t2"], r["t1"], r["t2"]) for e in memoire.get(f"{t['name']}|{r['date']}", {}).get("matchs", {}).values()):
                    continue
                ts = datetime.datetime.fromisoformat(r["date"] + "T12:00:00+01:00").timestamp()
                bloc = memoire.setdefault(f"{t['name']}|{r['date']}", {"nom": t["name"], "jour": r["date"], "matchs": {}})
                bloc["matchs"]["|".join(sorted([r["t1"], r["t2"]]))] = {
                    "ts": ts, "t1": r["t1"], "t2": r["t2"], "t1_court": r["t1"], "t2_court": r["t2"],
                    "bo": "", "phase": "round %d" % r["round"], "sans_heure": True}
                continue
            bloc = memoire.setdefault(f"{t['name']}|{r['date']}", {"nom": t["name"], "jour": r["date"], "matchs": {}})
            trouve = next((k for k, e in bloc["matchs"].items()
                           if _meme_paire(e["t1"], e["t2"], r["t1"], r["t2"])), None)
            if trouve is None:
                ts = datetime.datetime.fromisoformat(r["date"] + "T12:00:00+01:00").timestamp()
                bloc["matchs"]["|".join(sorted([r["t1"], r["t2"]]))] = {
                    "ts": ts, "t1": r["t1"], "t2": r["t2"], "t1_court": r["t1"], "t2_court": r["t2"],
                    "bo": "", "phase": "round %d" % r["round"], "s1": r["s1"], "s2": r["s2"]}
                continue
            e = bloc["matchs"][trouve]
            if _cle_equipe(e["t1"]) == _cle_equipe(r["t1"]):
                e["s1"], e["s2"] = r["s1"], r["s2"]
            else:
                e["s1"], e["s2"] = r["s2"], r["s1"]
            e.setdefault("phase", "round %d" % r["round"])

    # on garde 7 jours de programmes, et seulement jusqu'à demain
    for cle in list(memoire):
        ecart = (datetime.date.fromisoformat(memoire[cle]["jour"]) - aujourdhui).days
        if ecart < -7 or ecart > 1:
            del memoire[cle]

    tier_de = {t["name"]: t.get("tier") for t in gros.values()}
    # qualifiées (3 victoires) et éliminées (3 défaites) du tableau Swiss, ajoutées au dernier programme du tournoi
    quali_de, dernier_jour = {}, {}
    for chemin, sw in (data.get("swiss") or {}).items():
        t = gros.get(chemin)
        if not t or not (sw.get("qualifiees") or sw.get("eliminees")):
            continue
        quali_de[t["name"]] = ([{"nom": n, "k": "ok"} for n in sw["qualifiees"]]
                               + [{"nom": n, "k": "ko"} for n in sw["eliminees"]]
                               + [{"nom": n, "k": "enjeu"} for n in sw.get("en_jeu", [])])
    for bloc in memoire.values():
        dernier_jour[bloc["nom"]] = max(dernier_jour.get(bloc["nom"], ""), bloc["jour"])
    arts = []
    for cle, bloc in sorted(memoire.items(), key=lambda kv: kv[1]["jour"]):
        ms = sorted(bloc["matchs"].values(), key=lambda e: e["ts"])
        if not ms:
            continue
        court = lambda e, k: e.get(k + "_court") or e[k]
        pastilles = []
        for e in ms[:MATCH_MAX * 2]:
            if "s1" in e:
                pastilles.append(f"{court(e, 't1')} {e['s1']}-{e['s2']} {court(e, 't2')}")
            elif e.get("sans_heure"):
                pastilles.append(f"à venir · {court(e, 't1')} vs {court(e, 't2')}")
            else:
                pastilles.append(f"{_paris(e['ts']):%H:%M} · {court(e, 't1')} vs {court(e, 't2')}")
        joues = [e for e in ms if "s1" in e]
        restants = len(ms) - len(joues)
        phrases = [f"{court(e, 't1') if e['s1'] > e['s2'] else court(e, 't2')} bat "
                   f"{court(e, 't2') if e['s1'] > e['s2'] else court(e, 't1')} {max(e['s1'], e['s2'])}-{min(e['s1'], e['s2'])}."
                   for e in joues if est_suivie(e)]
        resume = " ".join(phrases[:2])
        resume += (" " if resume else "") + f"{len(joues)} match{'s' if len(joues) > 1 else ''} joué{'s' if len(joues) > 1 else ''}, "
        resume += f"{restants} à venir. Heures de Paris."
        from collections import Counter
        c = Counter(e["phase"] for e in ms if e.get("phase"))
        ph = c.most_common(1)[0][0] if c else ""
        nom, jour = bloc["nom"], bloc["jour"]
        titre = " · ".join(x for x in (nom, bloc.get("etape"), ph) if x) + f" : les matchs du {NS.date_fr(jour)}"
        art = SITE._article(f"prog|{nom}|{jour}", titre, resume, "resultats", "Programme", pastilles)
        art["date"] = jour
        if nom in quali_de and jour == dernier_jour.get(nom):
            art["qualifs"] = quali_de[nom]                  # qualifiées en vert, éliminées en rouge, sur le dernier programme
        # programme d'aujourd'hui ou de demain : en tête. Tier S d'abord, puis le plus récent (voir _fusionner)
        if jour >= aujourdhui.isoformat():
            art["rang"] = 3 if tier_de.get(nom) == "S" else 2
        else:
            art["rang"] = 0
        arts.append(art)
    return arts

def main():
    jour = datetime.date.today().isoformat()
    dire(f"Mise à jour du site : {jour}")
    data = collecte()
    script = NS.build(data, "Mexic", fr_teams=EQUIPES_FR.split(","), weekly=True,
                      release=datetime.datetime.now())["SEMAINE"]
    arts = SITE.articles_depuis_script(script)
    try:
        jours = articles_matchs(data)
        arts = articles_debuts(data) + arts       # les scores des gros tournois sont dans l'article programme du jour
        dire(f"Résultats des matchs : {len(jours)} article(s)")
    except Exception as e:
        dire(f"  [ATTENTION] résultats des matchs non faits : {e}")
    h = SITE._lire(SITE.HISTORIQUE, {}) or {}
    if not any(e.startswith("programme des matchs") for e in data["errors"]):
        try:
            memoire = h.get("programmes") or {}
            prog = articles_programme(data, memoire)
            h["programmes"] = memoire                     # le programme de chaque jour reste en mémoire 7 jours
            h["articles"] = [a for a in h.get("articles", []) if not str(a.get("cle", "")).startswith(("prog|", "jour|"))]
            SITE._ecrire(SITE.HISTORIQUE, h)
            arts = prog + arts
            dire(f"Programme des matchs : {len(prog)} article(s)")
        except Exception as e:
            dire(f"  [ATTENTION] programme des matchs non fait : {e}")
    avant = {a.get("cle") for a in h.get("articles", [])}
    video, semaine = None, None
    try:
        video, semaine = video_de_la_semaine(h)
        dire("Vidéo de la semaine : " + (video or "aucune récente"))
        SITE._ecrire(SITE.HISTORIQUE, h)                      # (garde l'identifiant de la chaîne)
    except Exception as e:
        dire(f"  [ATTENTION] vidéo de la semaine non vérifiée : {e} (le bouton ne change pas)")
    agenda = SITE._agenda("", data)
    if not agenda and data["errors"]:
        agenda = None                                         # Liquipedia en panne : on garde l'agenda d'avant
        dire("  agenda vide à cause d'une source en panne : l'ancien agenda est gardé")
    try:
        data["noms_pages"] = {t["page"]: t["name"] for t in pages_tournois(data)}
        DISCORD.envoyer(data, h, dire)                        # infos clés sur Vitality (secret NEWSCS_WEBHOOK)
        SITE._ecrire(SITE.HISTORIQUE, h)
    except Exception as e:
        dire(f"  [ATTENTION] Discord non fait : {e}")
    SITE._fusionner(arts, agenda=agenda, video=video, semaine=semaine or None, jour=jour)
    h = SITE._lire(SITE.HISTORIQUE, {}) or {}
    h["collecte"] = jour
    h["erreurs"] = data["errors"]
    SITE._ecrire(SITE.HISTORIQUE, h)
    nouveaux = [a for a in arts if a["cle"] not in avant]
    dire(f"Terminé : {len(arts)} info(s) trouvée(s), dont {len(nouveaux)} nouvelle(s) ; "
         f"{len(h.get('articles', []))} article(s) gardé(s) (7 jours).")
    if not arts and data["errors"]:
        sys.exit(1)                                           # rien trouvé ET des sources en panne : on le signale


if __name__ == "__main__":
    main()
