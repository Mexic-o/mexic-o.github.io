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
    data["matches"] = SRC.upcoming_matches(errors=errors)
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


def main():
    jour = datetime.date.today().isoformat()
    dire(f"Mise à jour du site : {jour}")
    data = collecte()
    script = NS.build(data, "Mexic", fr_teams=EQUIPES_FR.split(","), weekly=True,
                      release=datetime.datetime.now())["SEMAINE"]
    arts = SITE.articles_depuis_script(script)
    h = SITE._lire(SITE.HISTORIQUE, {}) or {}
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
