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

import news_script as NS      # noqa: E402
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
    copies_pages_tournois()
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
COPIES_TOURNOIS = [
    ("PGL_Masters_Bucharest_2026", "PGL/2026/Masters"),
    ("IEM_Beijing_2026", "Intel_Extreme_Masters/2026/Beijing"),
]


def copies_pages_tournois():
    """Sauve la page complète de chaque gros tournoi dans outil/debug, une seule fois. Une page par 30 s (règle Liquipedia)."""
    import time
    for nom, chemin in COPIES_TOURNOIS:
        cible = os.path.join(DEBUG, "tournoi_%s.html" % nom)
        if os.path.exists(cible):
            continue
        try:
            # même voie que le reste de la collecte (API MediaWiki), la page HTML directe peut être refusée
            rep = json.loads(SRC.fetch(SRC.LIQUI_API, {"action": "parse", "page": chemin, "prop": "text",
                                                       "format": "json", "formatversion": "2",
                                                       "disablelimitreport": "1"}))
            if "error" in rep:
                raise RuntimeError(rep["error"].get("info", "erreur Liquipedia"))
            html = rep["parse"]["text"]
            os.makedirs(DEBUG, exist_ok=True)
            with open(cible, "w", encoding="utf-8") as f:
                f.write(html)
            dire("  page du tournoi gardée : outil/debug/tournoi_%s.html" % nom)
        except Exception as e:
            dire("  [ATTENTION] page du tournoi %s : %s" % (nom, e))
        time.sleep(30)


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
        ident = f"{m['t1']}|{m['t2']}"
        ancien = bloc["matchs"].get(ident, {})
        e = {"ts": m["ts"], "t1": m["t1"], "t2": m["t2"],
             "t1_court": m.get("t1_court") or m["t1"], "t2_court": m.get("t2_court") or m["t2"],
             "bo": m.get("bo") or "", "phase": phase_de(m)}
        if joue:
            e["s1"], e["s2"] = m["s1"], m["s2"]
        elif "s1" in ancien:                       # le score déjà connu n'est jamais effacé
            e["s1"], e["s2"] = ancien["s1"], ancien["s2"]
        bloc["matchs"][ident] = e
        bloc["etape"] = _jour_tournoi(t, jour) if t else ""

    for m in data.get("matches") or []:
        # seulement aujourd'hui et demain : pas les matchs de la semaine suivante
        if (_paris(m["ts"]).date() - aujourdhui).days > 1:
            continue
        memoriser(m, False)
    for m in data.get("completed") or []:
        memoriser(m, True)

    # on garde 7 jours de programmes
    for cle in list(memoire):
        if (datetime.date.fromisoformat(memoire[cle]["jour"]) - aujourdhui).days < -7:
            del memoire[cle]

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
        arts = jours + articles_debuts(data) + arts
        dire(f"Résultats des matchs : {len(jours)} article(s)")
    except Exception as e:
        dire(f"  [ATTENTION] résultats des matchs non faits : {e}")
    h = SITE._lire(SITE.HISTORIQUE, {}) or {}
    if not any(e.startswith("programme des matchs") for e in data["errors"]):
        try:
            memoire = h.get("programmes") or {}
            prog = articles_programme(data, memoire)
            h["programmes"] = memoire                     # le programme de chaque jour reste en mémoire 7 jours
            h["articles"] = [a for a in h.get("articles", []) if not str(a.get("cle", "")).startswith("prog|")]
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
