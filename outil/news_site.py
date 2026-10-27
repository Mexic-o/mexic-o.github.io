# -*- coding: utf-8 -*-
"""
news_site.py - Mexic Studio : les news CS2 sur le site mexic-o.github.io

Tout est automatique une fois la cle GitHub en place :
  - CHAQUE JOUR (a l'ouverture de Mexic Studio, une fois par jour max) : collecte de l'actu
    (resultats, mercato, scene FR, mises a jour CS2, agenda), sans voix ni montage, et mise a jour
    du site. Un article reste 7 jours ; un article deja publie garde sa date.
  - VIDEO DE LA SEMAINE (mercredi 18:00) : des qu'elle est sortie et programmee sur YouTube,
    le site ajoute « Voir la video de la semaine » avec son lien.

Commandes (dans D:\\files) :
  python news_site.py tester              verifie la cle et l'acces au depot (n'envoie rien)
  python news_site.py etat                derniere mise a jour, articles en ligne, video de la semaine
  python news_site.py quotidien --force   refait la mise a jour du jour tout de suite
  python news_site.py publier [--video URL]   renvoie l'etat actuel (avec un lien video si donne)

La cle GitHub est lue dans site_github_token.txt (a cote de ce fichier), jamais ecrite dans le code.
"""
import base64
import datetime
import json
import os
import shutil
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------- reglages
SITE_NEWS = False                         # depuis le 22/10/2026 : le site est mis a jour par GITHUB tout seul
                                          # (outil/maj_news.py + .github/workflows/site.yml dans le depot du site).
                                          # Mexic Studio ne touche plus au site. True = ancien fonctionnement.
DEPOT = "Mexic-o/mexic-o.github.io"
BRANCHE = "main"
DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_CLE = os.path.join(DOSSIER, "site_github_token.txt")
DOSSIER_SITE = os.path.join(DOSSIER, "news", "site")    # news.json prepare + images + attente
JOURNAL = os.path.join(DOSSIER_SITE, "journal_site.txt")
ATTENTE = os.path.join(DOSSIER_SITE, "attente.json")
CATEGORIES = ("resultats", "mercato", "maj", "fr")
TAILLE_MAX_IMAGE = 900 * 1024             # au-dela, l'image n'est pas envoyee
ABANDON_JOURS = 6                         # video jamais sortie : on laisse tomber apres 6 jours
MAX_ARTICLES = 8
MAX_AGENDA = 6
# --------------------------------------------------------------------------

API = "https://api.github.com"


def _log(msg):
    ligne = "%s  %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(ligne)
    try:
        os.makedirs(DOSSIER_SITE, exist_ok=True)
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(ligne + "\n")
    except OSError:
        pass


def _lire(chemin, defaut=None):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defaut


def _ecrire(chemin, donnees):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    tmp = chemin + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)
    os.replace(tmp, chemin)


def _cle():
    try:
        with open(FICHIER_CLE, encoding="utf-8") as f:
            cle = f.read().strip()
    except OSError:
        raise RuntimeError("Cle GitHub introuvable : cree le fichier site_github_token.txt a cote de news_site.py")
    if not cle:
        raise RuntimeError("site_github_token.txt est vide")
    return cle


def _appel(methode, chemin, corps=None):
    req = urllib.request.Request(
        API + chemin,
        method=methode,
        data=json.dumps(corps).encode("utf-8") if corps is not None else None,
        headers={
            "Authorization": "Bearer " + _cle(),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "MexicStudio-news-site",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("message", "")
        except Exception:
            detail = ""
        return e.code, {"message": detail}


def _envoyer(chemin_depot, contenu_octets, message):
    """Cree ou remplace un fichier du depot. Renvoie True si OK."""
    code, info = _appel("GET", "/repos/%s/contents/%s?ref=%s" % (DEPOT, chemin_depot, BRANCHE))
    sha = info.get("sha") if code == 200 else None
    if code == 200 and info.get("content"):
        try:
            if base64.b64decode(info["content"]) == contenu_octets:
                _log("  %s : identique, rien a envoyer" % chemin_depot)
                return True
        except Exception:
            pass
    corps = {"message": message, "content": base64.b64encode(contenu_octets).decode("ascii"), "branch": BRANCHE}
    if sha:
        corps["sha"] = sha
    code, info = _appel("PUT", "/repos/%s/contents/%s" % (DEPOT, chemin_depot), corps)
    if code in (200, 201):
        _log("  %s : envoye" % chemin_depot)
        return True
    _log("  %s : ERREUR %s %s" % (chemin_depot, code, info.get("message", "")))
    return False


def _net(texte, maxi=400):
    t = " ".join(str(texte or "").split())
    return t if len(t) <= maxi else t[: maxi - 1].rsplit(" ", 1)[0] + "…"


def _nom_image(chemin):
    base = os.path.basename(chemin).lower()
    garde = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in base)
    return "news-" + garde


def _sans_prefixe(phrase):
    """« Côté mercato : X rejoint Y. » -> « X rejoint Y. »"""
    for p in ("Gros titre : ", "Côté tier 2 : ", "Côté mercato : ", "Place au mercato : ", "Dans le mercato : ",
              "Sur la scène française : ", "Autre titre : "):
        if phrase.startswith(p):
            return phrase[len(p):]
    return phrase


def _premiere_phrase(t):
    t = t.strip()
    for i, c in enumerate(t):
        if c == "." and (i + 1 == len(t) or t[i + 1] == " "):
            return t[: i + 1]
    return t


# ------------------------------------------------------------------ articles
HISTORIQUE = os.path.join(DOSSIER_SITE, "historique.json")   # tous les articles des 7 derniers jours
VERROU = os.path.join(DOSSIER_SITE, "quotidien.lock")
SITE_QUOTIDIEN = True        # mise a jour des news du site a l'ouverture de Mexic Studio (une fois par jour max)
GARDE_JOURS = 7              # un article reste ce nombre de jours sur le site
MAX_ARTICLES = 14


def _article(cle, titre, resume, categorie, tier="", cartes=None, lien=""):
    a = {"cle": cle, "titre": _net(titre, 140), "resume": _net(resume, 420),
         "categorie": categorie if categorie in CATEGORIES else "fr"}
    if tier:
        a["tier"] = tier
    if cartes:
        a["cartes"] = [_net(c, 40) for c in cartes][:7]
    if lien and str(lien).startswith("https://"):
        a["lien"] = lien
    return a


def _phrase_transfert(r):
    t = _phrase_brute(r)
    try:
        import news_script as NS
        return NS.elide(t)                                   # « de ENVY » -> « d'ENVY »
    except Exception:
        return t


def _phrase_brute(r):
    """Titre d'un transfert, avec l'accord au pluriel quand il y a plusieurs joueurs (« X et Y rejoignent Z »)."""
    p, de, vers, role = r.get("player", ""), r.get("from", ""), r.get("to", ""), r.get("role", "")
    pl = " et " in p or ", " in p or "+" in p                # plusieurs joueurs (ou « +3 »)
    v = lambda un, plusieurs: plusieurs if pl else un
    if role == "coach parti":
        return "%s %s de %s" % (p, v("n'est plus le coach", "ne sont plus les coachs"), de)
    if role == "coach" and vers:
        return "%s %s de %s" % (p, v("devient le coach", "deviennent les coachs"), vers)
    if role == "banc":
        return "%s %s%s" % (p, v("passe sur le banc", "passent sur le banc"), " chez " + de if de else "")
    if role == "retraite":
        return "%s %s" % (p, v("prend sa retraite", "prennent leur retraite"))
    if role in ("prêt", "remplaçant") and vers:
        return "%s %s %s" % (p, v("dépanne", "dépannent"), vers)
    if vers and vers != "libre":
        return ("%s %s de %s à %s" % (p, v("passe", "passent"), de, vers)) if de else ("%s %s %s" % (p, v("rejoint", "rejoignent"), vers))
    if de:
        return "%s %s %s" % (p, v("quitte", "quittent"), de)
    return ""


def articles_depuis_script(script):
    """Le script de la semaine (news_script.build) -> articles du site, chacun avec une cle stable."""
    out = []
    for s in script.get("segments", []):
        kind, card = s.get("kind"), s.get("card") or {}
        texte = _sans_prefixe(" ".join(str(s.get("sub") or "").split()))
        tier = {"T1": "Tier 1", "T2": "Tier 2"}.get(s.get("tier"), "")
        if kind == "result" and card.get("winner"):
            out.append(_article("res|%s|%s" % (card.get("title"), card["winner"]),
                                "%s remporte %s" % (card["winner"], card.get("title", "")), texte, "resultats", tier,
                                ["%s %s-%s" % (m.get("map", ""), m.get("w", ""), m.get("l", "")) for m in card.get("maps") or []]))
        elif kind == "ranking" and card.get("rows"):
            out.append(_article("vrs|%s" % card.get("note", ""), "Classement Valve : %s numéro 1" % card["rows"][0].get("team", ""),
                                texte, "resultats", "Classement"))
        elif kind in ("transfer", "transfers"):
            fr_bloc = card.get("title") == "Scène française"
            for r in card.get("rows") or []:
                phrase = _phrase_transfert(r)
                if not phrase:
                    continue
                fr = fr_bloc or r.get("fr")
                out.append(_article("tr|%s|%s|%s|%s" % (r.get("player"), r.get("from"), r.get("to"), r.get("role")),
                                    phrase, "", "fr" if fr else "mercato", "" if fr else tier))
        elif kind == "update":
            out.append(_article("maj|%s" % (card.get("url") or card.get("date")),
                                "Mise à jour CS2" + (" du %s" % card["date"] if card.get("date") else ""),
                                texte, "maj", lien=card.get("url") or ""))
    return out


def _fusionner(nouveaux, agenda=None, video=None, semaine=None, jour=None):
    """Ajoute les nouveaux articles a l'historique (un article deja vu garde sa date), retire les vieux,
    et ecrit news\\site\\news.json pret a envoyer."""
    jour = jour or datetime.date.today().isoformat()
    h = _lire(HISTORIQUE, {}) or {}
    connus = {a["cle"]: a for a in h.get("articles", []) if a.get("cle")}
    for a in nouveaux:
        if a["cle"] in connus:
            date = a.get("date") or connus[a["cle"]].get("date", jour)     # date propre à l'article, sinon la 1re vue
            connus[a["cle"]].update(a)
            connus[a["cle"]]["date"] = date
        else:
            connus[a["cle"]] = dict({"date": jour}, **a)          # un article peut porter sa propre date (jour du match)
    limite = (datetime.date.fromisoformat(jour) - datetime.timedelta(days=GARDE_JOURS)).isoformat()
    ordre = {"resultats": 0, "maj": 1, "mercato": 2, "fr": 3}
    def _rang(a):
        """Les plus importants d'abord, dans un même jour : Tier 1 et programme, puis Tier 2, puis le reste."""
        t = a.get("tier") or ""
        if t in ("Tier 1", "Programme"):
            return 3
        if t == "Tier 2":
            return 2
        return 1 if t else 0
    garde = sorted([a for a in connus.values() if a.get("date", jour) > limite],
                   key=lambda a: (a.get("date", jour), a.get("rang", 1), -ordre.get(a.get("categorie"), 9), _rang(a)),
                   reverse=True)
    h["articles"] = garde
    if agenda is not None:
        h["agenda"] = agenda
    if video is not None:
        h["video"] = video
    if semaine:
        h["semaine"] = semaine
    h["maj"] = jour
    try:
        from zoneinfo import ZoneInfo
        h["maj_heure"] = datetime.datetime.now(ZoneInfo("Europe/Paris")).strftime("%H:%M")
    except Exception:
        h["maj_heure"] = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).strftime("%H:%M")
    _ecrire(HISTORIQUE, h)
    donnees = {"maj": jour, "maj_heure": h.get("maj_heure", ""), "semaine": h.get("semaine", ""), "video": h.get("video", ""),
               "articles": [{k: v for k, v in a.items() if k != "cle"} for a in garde[:MAX_ARTICLES]],
               "matchs": (h.get("agenda") or [])[:MAX_AGENDA]}
    _ecrire(os.path.join(DOSSIER_SITE, "news.json"), donnees)
    return donnees


def _agenda(folder, data=None):
    """Tournois en cours et a venir (donnees du jour), pour la colonne Agenda du site."""
    data = data or _lire(os.path.join(folder, "donnees.json"), {}) or {}
    tours = data.get("tournaments") or {}
    try:
        import news_script as NS
        ville, date_fr = NS.city, NS.date_fr
    except Exception:
        ville = lambda loc: (loc or "").split(",")[0]
        date_fr = lambda iso, *a: iso
    prix = lambda t: float("".join(c for c in str(t.get("prize", "")) if c.isdigit() or c == ".") or 0)
    out = []
    for groupe, cle, n in (("En cours", "ongoing", 3), ("À venir", "upcoming", 4)):
        xs = sorted([t for t in tours.get(cle, []) if t.get("tier") in ("S", "A", "B")],
                    key=lambda t: ("SAB".index(t["tier"]), -prix(t)))[:n]
        for t in xs:
            lieu = "En ligne" if t.get("online") else ville(t.get("location"))
            quand = ("jusqu'au " + date_fr(t["end"])) if cle == "ongoing" and t.get("end") else \
                    ("dès le " + date_fr(t["start"])) if t.get("start") else ""
            out.append({"groupe": groupe, "jour": t.get("start") or "", "equipes": _net(t["name"], 90),
                        "tournoi": _net(" · ".join(x for x in (quand, lieu) if x), 90)})
    return out


# ------------------------------------------------------------------ envoi
def _envoyer_news():
    """Envoie news\\site\\news.json sur GitHub. Renvoie True si OK."""
    donnees = _lire(os.path.join(DOSSIER_SITE, "news.json"))
    if not donnees:
        _log("Pas de news.json prepare : rien envoye")
        return False
    contenu = json.dumps(donnees, ensure_ascii=False, indent=2).encode("utf-8")
    ok = _envoyer("news.json", contenu, "News du site " + donnees.get("maj", ""))
    _log("Termine : %s" % ("site a jour dans 1 a 2 minutes" if ok else "erreur d'envoi, nouvel essai plus tard"))
    return ok


# ------------------------------------------------------------------ chaque jour
def quotidien_a_faire(aujourdhui=None):
    """Verification rapide (sans reseau) : faut-il mettre le site a jour aujourd'hui ?"""
    if not (SITE_NEWS and SITE_QUOTIDIEN) or not os.path.isfile(FICHIER_CLE):
        return False
    if os.path.exists(VERROU) and datetime.datetime.now().timestamp() - os.path.getmtime(VERROU) < 3600:
        return False                                        # deja en cours
    h = _lire(HISTORIQUE, {}) or {}
    jour = (aujourdhui or datetime.date.today()).isoformat()
    return h.get("collecte") != jour or bool(h.get("envoi_en_attente"))


def quotidien(force=False):
    """Collecte l'actu du jour (comme pour la video, sans voix ni montage) et met le site a jour."""
    if not force and not quotidien_a_faire():
        _log("Site : deja a jour aujourd'hui.")
        return True
    os.makedirs(DOSSIER_SITE, exist_ok=True)
    open(VERROU, "w").close()
    try:
        h = _lire(HISTORIQUE, {}) or {}
        jour = datetime.date.today().isoformat()
        if h.get("collecte") != jour or force:
            import news_make as NM
            import news_script as NS
            _log("Site : collecte de l'actu du jour (quelques minutes, Liquipedia demande d'y aller doucement)...")
            folder = NM.week_dir()
            data = NM.collect(folder, refresh=force)       # bouton « Mettre à jour le site » : infos relues tout de suite
            script = NS.build(data, NM.on_air(), fr_teams=NM.NEWS_FR_TEAMS.split(","), weekly=True,
                              release=datetime.date.today())["SEMAINE"]
            arts = articles_depuis_script(script)
            avant = {a.get("cle") for a in h.get("articles", [])}
            nouveaux = [a for a in arts if a["cle"] not in avant]
            _fusionner(arts, agenda=_agenda(folder, data), jour=jour)
            h = _lire(HISTORIQUE, {}) or {}
            h["collecte"] = jour
            _ecrire(HISTORIQUE, h)
            _log("Site : %d info(s) trouvee(s), dont %d nouvelle(s)." % (len(arts), len(nouveaux)))
        ok = _envoyer_news()
        h = _lire(HISTORIQUE, {}) or {}
        h["envoi_en_attente"] = not ok
        _ecrire(HISTORIQUE, h)
        return ok
    finally:
        try:
            os.remove(VERROU)
        except OSError:
            pass


# ------------------------------------------------------------------ video de la semaine
def preparer_depuis_studio(folder, script, sortie=None, video_path=None):
    """Appele par news_make.py (mardi) : garde les articles de la video, publies a sa sortie avec son lien."""
    if not SITE_NEWS:
        return None
    arts = articles_depuis_script(script)
    jour = (sortie.date() if sortie else datetime.date.today()).isoformat()
    meta = (os.path.splitext(video_path)[0] + ".youtube.json") if video_path else ""
    _ecrire(ATTENTE, {"semaine": jour, "sortie": sortie.strftime("%Y-%m-%dT%H:%M") if sortie else "",
                      "video_meta": meta, "publie": False, "articles": arts, "agenda": _agenda(folder),
                      "prepare": datetime.datetime.now().isoformat(timespec="seconds")})
    _log("Video de la semaine : %d info(s) gardee(s) pour le site, envoi prevu le %s avec le lien de la video."
         % (len(arts), sortie or "?"))
    return arts


def _lien_video(att):
    meta = _lire(att.get("video_meta") or "", {}) or {}
    vid = meta.get("youtube_id")
    return ("https://youtu.be/" + vid) if vid else ""


def a_faire(maintenant=None):
    """True si la video de la semaine est sortie et que le site ne l'a pas encore (verification rapide)."""
    att = _lire(ATTENTE)
    if not SITE_NEWS or not att or att.get("publie") or not att.get("sortie"):
        return False
    try:
        sortie = datetime.datetime.fromisoformat(att["sortie"])
    except ValueError:
        return False
    return (maintenant or datetime.datetime.now()) >= sortie


def auto(maintenant=None):
    """Lance par Mexic Studio : a la sortie de la video, ajoute son lien (et ses infos) sur le site."""
    if not a_faire(maintenant) or not os.path.isfile(FICHIER_CLE):
        return False
    att = _lire(ATTENTE, {})
    sortie = datetime.datetime.fromisoformat(att["sortie"])
    maintenant = maintenant or datetime.datetime.now()
    lien = _lien_video(att)
    if not lien:
        if maintenant - sortie > datetime.timedelta(days=ABANDON_JOURS):
            att.update(publie=True, abandon="video jamais envoyee sur YouTube")
            _ecrire(ATTENTE, att)
            _log("Video du %s jamais envoyee sur YouTube : le site garde ses news sans lien." % att.get("semaine"))
        elif not att.get("note_attente"):
            att["note_attente"] = True
            _ecrire(ATTENTE, att)
            _log("C'est l'heure, mais la video n'est pas encore sur YouTube (a valider ?) : le lien attend.")
        return False
    _log("Video de la semaine sortie : ajout du lien sur le site.")
    _fusionner(att.get("articles") or [], agenda=att.get("agenda"), video=lien, semaine=att.get("semaine"),
               jour=maintenant.date().isoformat())
    ok = _envoyer_news()
    if ok:
        att.update(publie=True, publie_le=maintenant.isoformat(timespec="seconds"), video=lien)
        _ecrire(ATTENTE, att)
    return ok


def publier(video_url=""):
    """A la main : envoie tout de suite l'etat actuel (avec un lien video si donne)."""
    if not SITE_NEWS:
        _log("SITE_NEWS desactive : rien envoye")
        return False
    if video_url:
        _fusionner([], video=video_url.strip())
    elif not os.path.isfile(os.path.join(DOSSIER_SITE, "news.json")):
        _fusionner([])
    return _envoyer_news()


def tester():
    try:
        code, info = _appel("GET", "/repos/%s" % DEPOT)
    except RuntimeError as e:
        _log(str(e))
        return False
    if code != 200:
        _log("Acces refuse au depot (%s %s). Verifie la cle et qu'elle donne acces a %s." % (code, info.get("message", ""), DEPOT))
        return False
    if not info.get("permissions", {}).get("push"):
        _log("La cle lit le depot mais ne peut pas ecrire : donne-lui « Contents : Read and write ».")
        return False
    _log("OK : la cle peut ecrire sur %s (rien n'a ete envoye)." % DEPOT)
    return True


def etat():
    h = _lire(HISTORIQUE, {}) or {}
    att = _lire(ATTENTE, {}) or {}
    print("Site : derniere collecte %s | %d articles en ligne | envoi en attente : %s"
          % (h.get("collecte") or "jamais", len(h.get("articles", [])), "oui" if h.get("envoi_en_attente") else "non"))
    if att:
        print("Video de la semaine : sortie %s | YouTube : %s | lien sur le site : %s"
              % (att.get("sortie") or "?", _lien_video(att) or "pas encore envoyee",
                 att.get("publie_le") or att.get("abandon") or "pas encore"))


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "quotidien":
        sys.exit(0 if quotidien(force="--force" in args) else 1)
    elif cmd == "publier":
        url = args[args.index("--video") + 1] if "--video" in args and len(args) > args.index("--video") + 1 else ""
        sys.exit(0 if publier(url) else 1)
    elif cmd == "auto":
        auto()
    elif cmd == "tester":
        sys.exit(0 if tester() else 1)
    elif cmd == "etat":
        etat()
    else:
        print(__doc__)
