"""Lit les tableaux de rondes d'une page de tournoi Liquipedia (HTML rendu).

Chaque tableau : titre « Round N High/Low Matches » ou « Round N Matches »,
une date en en-tête, puis une ligne par match avec les deux équipes
(aria-label) et les deux scores (cellules brkts-matchlist-score).
"""
import re
from datetime import datetime

_BLOC = re.compile(r'<div class="general-collapsible brkts-matchlist"')
_TITRE = re.compile(r'Round (\d+)(?: (High|Low))? Matches')
_DATE = re.compile(r'brkts-matchlist-header"[^>]*>([^<]+)<')
_LIGNE = re.compile(r'<div class="brkts-matchlist-match.*?(?=<div class="brkts-matchlist-match|\Z)', re.S)
_EQUIPE = re.compile(r'brkts-matchlist-opponent[^"]*"\s*aria-label="([^"]+)"')
_SCORE = re.compile(r'brkts-matchlist-score[^"]*"[^>]*>\s*<div class="brkts-matchlist-cell-content">\s*(\d*)\s*</div>')


def _date(txt):
    try:
        return datetime.strptime(txt.strip(), "%B %d, %Y").date().isoformat()
    except ValueError:
        return ""


def parse_rondes(html):
    """Renvoie une liste de dicts : round, phase (High/Low/''), date, t1, t2, s1, s2.
    s1/s2 valent None quand le score n'est pas encore saisi."""
    sortie = []
    for bloc in _BLOC.split(html)[1:]:
        t = _TITRE.search(bloc[:600])
        if not t:
            continue
        d = _DATE.search(bloc)
        jour = _date(d.group(1)) if d else ""
        for ligne in _LIGNE.findall(bloc):
            eq = _EQUIPE.findall(ligne)
            sc = _SCORE.findall(ligne)
            if len(eq) < 2 or "TBD" in eq[:2]:
                continue
            s1 = int(sc[0]) if len(sc) > 0 and sc[0] != "" else None
            s2 = int(sc[1]) if len(sc) > 1 and sc[1] != "" else None
            sortie.append({
                "round": int(t.group(1)), "phase": t.group(2) or "",
                "date": jour, "t1": eq[0], "t2": eq[1], "s1": s1, "s2": s2,
            })
    return sortie
