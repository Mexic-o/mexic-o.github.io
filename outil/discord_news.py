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


def messages(data, aujourdhui):
    """Renvoie une liste de (clé, texte). La clé sert à ne jamais envoyer deux fois le même message."""
    sortie = []
    # 1. matchs de Vitality aujourd'hui, puis demain (un message par jour, jamais deux fois)
    fuseau = datetime.timezone(datetime.timedelta(hours=1))
    for decalage, titre in ((0, "aujourd'hui"), (1, "demain")):
        jour = aujourdhui + datetime.timedelta(days=decalage)
        du_jour = sorted((m for m in data.get("matches") or []
                          if (_suivie(m.get("t1")) or _suivie(m.get("t2"))) and _paris_date(m["ts"]) == jour),
                         key=lambda x: x["ts"])
        if du_jour:
            lignes = [f"{datetime.datetime.fromtimestamp(m['ts'], fuseau):%H:%M} · {m['t1']} vs {m['t2']} "
                      f"({m.get('tournament', '')})" for m in du_jour]
            cle = ("jour" if decalage == 0 else "demain") + f"|{jour.isoformat()}"
            sortie.append((cle, f"📅 **Vitality {titre}**\n" + "\n".join(lignes) + "\nHeures de Paris."))
    # 2. résultats de Vitality (matchs terminés, hier ou aujourd'hui)
    vus = set()
    for m in data.get("completed") or []:
        if (_suivie(m.get("t1")) or _suivie(m.get("t2"))) and m.get("s1") is not None:
            jour = _paris_date(m["ts"])
            if (aujourdhui - jour).days in (0, 1):
                gagne = (m["s1"] > m["s2"]) if _suivie(m["t1"]) else (m["s2"] > m["s1"])
                adv = m["t2"] if _suivie(m["t1"]) else m["t1"]
                sc = f"{max(m['s1'], m['s2'])}-{min(m['s1'], m['s2'])}"
                cle = f"res|{m['t1']}|{m['t2']}|{m['ts']}"
                if cle not in vus:
                    vus.add(cle)
                    if gagne:
                        sortie.append((cle, f"✅ **Vitality bat {adv} {sc}** · {m.get('tournament', '')}"))
                    else:
                        sortie.append((cle, f"❌ **Vitality perd contre {adv} {sc}** · {m.get('tournament', '')}"))
    # 2 bis. playoffs du tournoi (quarts, demies, finale) : matchs à venir et résultats, sauf ceux de Vitality (déjà annoncés)
    for page, lignes in (data.get("brackets") or {}).items():
        nom = (data.get("noms_pages") or {}).get(page, page)
        for r in lignes:
            if not r.get("ts") or _suivie(r["t1"]) or _suivie(r["t2"]):
                continue
            jour = _paris_date(r["ts"])
            heure = datetime.datetime.fromtimestamp(r["ts"], datetime.timezone(datetime.timedelta(hours=1)))
            if r["s1"] is None:
                if jour in (aujourdhui, aujourdhui + datetime.timedelta(days=1)):
                    sortie.append((f"po|{page}|{r['t1']}|{r['t2']}|{jour.isoformat()}",
                                   f"🏆 **Playoffs** · {r['t1']} vs {r['t2']} à {heure:%H:%M} · {nom}"))
            elif (aujourdhui - jour).days in (0, 1):
                a, b = (r["t1"], r["t2"]) if r["s1"] > r["s2"] else (r["t2"], r["t1"])
                sc = f"{max(r['s1'], r['s2'])}-{min(r['s1'], r['s2'])}"
                sortie.append((f"poRes|{page}|{r['t1']}|{r['t2']}|{r['ts']}",
                               f"🏆 **Playoffs** · {a} bat {b} {sc} · {nom}"))
    # 3. qualification / élimination dans un tableau Swiss
    for page, sw in (data.get("swiss") or {}).items():
        nom = (data.get("noms_pages") or {}).get(page, page)
        for quali in sw.get("qualifiees") or []:
            if _suivie(quali):
                sortie.append((f"quali|{page}", f"🟢 **Vitality est qualifiée pour les playoffs** · {nom}"))
        for elim in sw.get("eliminees") or []:
            if _suivie(elim):
                sortie.append((f"elim|{page}", f"🔴 **Vitality est éliminée** · {nom}"))
    return sortie


def _poster(webhook, texte):
    corps = json.dumps({"content": texte[:1900]}).encode("utf-8")
    req = urllib.request.Request(webhook, data=corps, headers={
        "Content-Type": "application/json", "User-Agent": "MexicStudio-news/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return 200 <= r.status < 300


def envoyer(data, h, dire=print):
    """Envoie les nouveaux messages Vitality. h = historique (on y garde la liste des clés envoyées)."""
    webhook = os.environ.get("NEWSCS_WEBHOOK", "").strip()
    if not webhook:
        dire("Discord : pas de webhook (secret NEWSCS_WEBHOOK absent) : rien envoyé.")
        return
    envoyes = list(h.get("discord") or [])
    aujourdhui = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=1))).date()
    nouveaux = [(k, t) for k, t in messages(data, aujourdhui) if k not in envoyes]
    for k, t in nouveaux[:MAX_PAR_PASSAGE]:
        try:
            if _poster(webhook, t):
                envoyes.append(k)
                dire(f"  Discord : message envoyé ({k.split('|')[0]})")
        except Exception as e:
            dire(f"  [ATTENTION] Discord : message non envoyé : {e}")
            break
    h["discord"] = envoyes[-MEMOIRE:]
