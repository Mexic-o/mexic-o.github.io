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
    data["female"] = SRC.female_tournaments(errors=errors)
    dire("Mises à jour de CS2 (Steam)...")
    try:
        data["updates"] = SRC.cs2_updates()
    except Exception as e:
        data["updates"] = []
        errors.append(f"mises à jour CS2 : {e}")
    dire("Transferts...")
    data["transfers"] = SRC.transfers(errors=errors)
    for e in errors:
        dire(f"  [ATTENTION] {e}")
        if os.environ.get("GITHUB_ACTIONS"):
            dire(f"::warning title=Source en panne::{e}")      # visible sur la page du lancement (Annotations)
    return data


DEBUG = os.path.join(ICI, "debug")
MATCH_HEURES = 36                    # résultats des dernières 36 h
MATCH_MAX = 7                        # matchs affichés par tournoi et par jour
EQUIPES_SUIVIES = "Vitality"         # toujours mises en avant, en plus des équipes françaises


def _garder_page(html):
    os.makedirs(DEBUG, exist_ok=True)
    with open(os.path.join(DEBUG, "liquipedia_matches.html"), "w", encoding="utf-8") as f:
        f.write(html)
    dire("  [ATTENTION] scores des matchs non lus : page gardée dans outil/debug pour correction")


def _paris(ts):
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.fromtimestamp(ts, ZoneInfo("Europe/Paris"))
    except Exception:
        return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc) + datetime.timedelta(hours=1)


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
    groupes = {}
    for m in data.get("completed") or []:
        if m["ts"] < limite or m["ts"] > maintenant.timestamp():
            continue
        t = gros.get(m["page"]) or gros.get(m["tournament"])
        if not t and not (est_suivie(m["t1"]) or est_suivie(m["t2"])):
            continue
        jour = _paris(m["ts"]).date().isoformat()
        groupes.setdefault((t["name"] if t else m["tournament"], jour), []).append(m)
    arts = []
    for (nom, jour), ms in groupes.items():
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
        art = SITE._article(f"jour|{nom}|{jour}", f"{nom} : les résultats du {NS.date_fr(jour)}", resume,
                            "resultats", "Tier 1", pastilles)
        art["date"] = jour                                   # daté du jour des matchs, pas du jour de la collecte
        arts.append(art)
    return arts


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


def articles_programme(data, maintenant=None):
    """Le programme des gros tournois (tier S et A) : un article par tournoi et par jour, chaque affiche avec son heure
    de Paris (« 13:00 · Vitality vs FaZe »), Vitality et les équipes françaises en premier."""
    maintenant = maintenant or datetime.datetime.now(datetime.timezone.utc)
    tours = data.get("tournaments") or {}
    gros = {}
    for t in (tours.get("ongoing") or []) + (tours.get("upcoming") or []):
        if t.get("tier") in ("S", "A"):
            gros[t.get("page") or t["name"]] = t
            gros.setdefault(t["name"], t)
    suivies = [x.strip().lower() for x in (EQUIPES_FR + "," + EQUIPES_SUIVIES).split(",") if x.strip()]
    est_suivie = lambda m: any(x in (m["t1"] + " " + m["t2"]).lower() for x in suivies)
    debut, fin = maintenant.timestamp(), maintenant.timestamp() + PROG_HEURES * 3600
    groupes = {}
    for m in data.get("matches") or []:
        if not (debut <= m["ts"] <= fin):
            continue
        t = gros.get(m["page"]) or gros.get(m["tournament"])
        if not t and not est_suivie(m):
            continue
        quand = _paris(m["ts"])
        groupes.setdefault((t["name"] if t else m["tournament"], quand.date().isoformat()), []).append((quand, m))
    court = lambda m, k: m.get(k + "_court") or m[k]
    arts = []
    for (nom, jour), ms in groupes.items():
        ms.sort(key=lambda x: (not est_suivie(x[1]), x[0]))
        pastilles = [f"{q:%H:%M} · {court(m, 't1')} vs {court(m, 't2')}" for q, m in ms[:MATCH_MAX]]
        phrases = [f"{court(m, 't1')} affronte {court(m, 't2')} à {q:%H:%M}" + (f" (Bo{m['bo']})" if m.get("bo") else "") + "."
                   for q, m in ms if est_suivie(m)][:3]
        n = len(ms)
        resume = " ".join(phrases) or f"{n} match{'s' if n > 1 else ''} au programme."
        if n > len(pastilles):
            resume += f" Et {n - len(pastilles)} autre{'s' if n - len(pastilles) > 1 else ''} match{'s' if n - len(pastilles) > 1 else ''}."
        resume += " Heures de Paris."
        art = SITE._article(f"prog|{nom}|{jour}", f"{nom} : les matchs du {NS.date_fr(jour)}", resume,
                            "resultats", "Programme", pastilles)
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
            prog = articles_programme(data)
            h["articles"] = [a for a in h.get("articles", []) if not str(a.get("cle", "")).startswith("prog|")]
            SITE._ecrire(SITE.HISTORIQUE, h)              # l'ancien programme s'efface (matchs joués = résultats)
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
