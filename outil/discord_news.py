"""Messages automatiques sur le Discord : seulement les infos clés sur Vitality (le reste reste sur le site).

Trois types de messages, chacun envoyé une seule fois (mémoire dans historique.json, clé « discord ») :
  - les matchs de Vitality du jour (une fois par jour) ;
  - les résultats de Vitality (match joué sur un tournoi en cours) ;
  - la qualification ou l'élimination de Vitality dans un tableau Swiss.
Le lien du webhook est lu dans la variable d'environnement NEWSCS_WEBHOOK (secret GitHub), jamais dans le code.
"""
import datetime
import json
import os
import urllib.error
import urllib.request

EQUIPE = "vitality"
MAX_PAR_PASSAGE = 5                      # garde-fou : pas plus de 5 messages à chaque passage
MEMOIRE = 300                            # nombre de messages déjà envoyés gardés en mémoire


def _suivie(nom):
    return EQUIPE in (nom or "").lower()


def _paris_date(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone(datetime.timedelta(hours=1))).date()


FUSEAU = datetime.timezone(datetime.timedelta(hours=1))


def _paire(a, b):
    return "|".join(sorted([a or "", b or ""]))


def messages(data, aujourdhui):
    """Renvoie une liste de (clé, tournoi, catégorie, ligne).

    catégorie : 0 = résultat, 1 = à venir, 2 = information (qualification, élimination).
    La clé sert à ne jamais annoncer deux fois la même chose.
    """
    items = []
    demain = aujourdhui + datetime.timedelta(days=1)
    vus = set()

    def ajouter(cle, nom, cat, ligne):
        if cle not in vus:
            vus.add(cle)
            items.append((cle, nom, cat, ligne))

    # 1. résultats (hier ou aujourd'hui) : Vitality et les autres matchs des playoffs
    for m in data.get("completed") or []:
        if m.get("s1") is None:
            continue
        jour = _paris_date(m["ts"])
        if jour != aujourdhui:                 # résultats du jour seulement
            continue
        nom = m.get("tournament", "")
        sc = f"{max(m['s1'], m['s2'])}-{min(m['s1'], m['s2'])}"
        if _suivie(m.get("t1")) or _suivie(m.get("t2")):
            gagne = (m["s1"] > m["s2"]) if _suivie(m["t1"]) else (m["s2"] > m["s1"])
            adv = m["t2"] if _suivie(m["t1"]) else m["t1"]
            ligne = (f"✅ **Vitality bat {adv} {sc}**" if gagne else f"❌ **Vitality perd contre {adv} {sc}**")
        else:
            a, b = (m["t1"], m["t2"]) if m["s1"] > m["s2"] else (m["t2"], m["t1"])
            ligne = f"{a} bat {b} {sc}"
        ajouter(f"r|{_paire(m['t1'], m['t2'])}|{m['ts']}", nom, 0, ligne)
    for page, lignes in (data.get("brackets") or {}).items():
        nom = (data.get("noms_pages") or {}).get(page, page)
        for r in lignes:
            if not r.get("ts") or r.get("s1") is None:
                continue
            if _paris_date(r["ts"]) != aujourdhui:     # résultats du jour seulement
                continue
            if _suivie(r["t1"]) or _suivie(r["t2"]):
                continue                       # déjà traité au point 1
            a, b = (r["t1"], r["t2"]) if r["s1"] > r["s2"] else (r["t2"], r["t1"])
            sc = f"{max(r['s1'], r['s2'])}-{min(r['s1'], r['s2'])}"
            ajouter(f"r|{_paire(r['t1'], r['t2'])}|{r['ts']}", nom, 0, f"🏆 {a} bat {b} {sc}")

    # 2. matchs à venir (aujourd'hui et demain) : Vitality d'abord, puis les playoffs des autres équipes
    for m in sorted(data.get("matches") or [], key=lambda x: x["ts"]):
        if m.get("s1") is not None or _paris_date(m["ts"]) not in (aujourdhui, demain):
            continue
        jour = _paris_date(m["ts"])
        marque = "⭐ " if (_suivie(m.get("t1")) or _suivie(m.get("t2"))) else ""
        ligne = f"{marque}{datetime.datetime.fromtimestamp(m['ts'], FUSEAU):%H:%M} · {m['t1']} vs {m['t2']}"
        if jour == demain:
            ligne += " (demain)"
        ajouter(f"a|{_paire(m['t1'], m['t2'])}|{jour.isoformat()}", m.get("tournament", ""), 1, ligne)
    for page, lignes in (data.get("brackets") or {}).items():
        nom = (data.get("noms_pages") or {}).get(page, page)
        for r in lignes:
            if not r.get("ts") or r.get("s1") is not None:
                continue
            jour = _paris_date(r["ts"])
            if jour not in (aujourdhui, demain):
                continue
            marque = "⭐ " if (_suivie(r["t1"]) or _suivie(r["t2"])) else ""
            ligne = f"🏆 {marque}{datetime.datetime.fromtimestamp(r['ts'], FUSEAU):%H:%M} · {r['t1']} vs {r['t2']}"
            if jour == demain:
                ligne += " (demain)"
            ajouter(f"a|{_paire(r['t1'], r['t2'])}|{jour.isoformat()}", nom, 1, ligne)

    # 3. qualification / élimination de Vitality dans un tableau Swiss
    for page, sw in (data.get("swiss") or {}).items():
        nom = (data.get("noms_pages") or {}).get(page, page)
        for quali in sw.get("qualifiees") or []:
            if _suivie(quali):
                ajouter(f"quali|{page}", nom, 2, "🟢 **Vitality est qualifiée pour les playoffs**")
        for elim in sw.get("eliminees") or []:
            if _suivie(elim):
                ajouter(f"elim|{page}", nom, 2, "🔴 **Vitality est éliminée**")

    # 4. regroupement par tournoi (les lignes gardent leur clé)
    groupes = {}
    for cle, nom, cat, ligne in items:
        groupes.setdefault(nom or "Autres", []).append((cle, cat, ligne))
    return list(groupes.items())


def _rendre(nom, lignes):
    """Un message par tournoi : résultats d'abord, puis matchs à venir, puis informations."""
    lignes = sorted(lignes, key=lambda x: x[1])
    blocs = [f"**━━ {nom} ━━**"]
    for cat, titre in ((0, "Résultats du jour"), (1, "À venir")):
        sous = [l for _, c, l in lignes if c == cat]
        if sous:
            blocs.append(f"__{titre}__\n" + "\n".join(sous))
    infos = [l for _, c, l in lignes if c == 2]
    if infos:
        blocs.append("\n".join(infos))
    return "\n\n".join(blocs)


def _poster(webhook, texte):
    corps = json.dumps({"content": texte[:1900]}).encode("utf-8")
    req = urllib.request.Request(webhook, data=corps, headers={
        "Content-Type": "application/json", "User-Agent": "MexicStudio-news/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return 200 <= r.status < 300


def envoyer(data, h, dire=print):
    """Envoie les nouveaux messages Discord. h = historique (on y garde les clés déjà envoyées)."""
    webhook = os.environ.get("NEWSCS_WEBHOOK", "").strip()
    if not webhook:
        dire("Discord : pas de webhook (secret NEWSCS_WEBHOOK absent) : rien envoyé.")
        return
    envoyes = list(h.get("discord") or [])
    aujourdhui = datetime.datetime.now(FUSEAU).date()
    nb = 0
    for nom, lignes in messages(data, aujourdhui):
        nouvelles = [l for l in lignes if l[0] not in envoyes]
        if not nouvelles:
            continue
        if nb >= MAX_PAR_PASSAGE:
            break
        try:
            if _poster(webhook, _rendre(nom, nouvelles)):
                envoyes.extend(c for c, _, _ in nouvelles)
                nb += 1
                dire(f"  Discord : message envoyé ({nom})")
        except Exception as e:
            dire(f"  [ATTENTION] Discord : message non envoyé : {e}")
            break
    h["discord"] = envoyes[-MEMOIRE:]
