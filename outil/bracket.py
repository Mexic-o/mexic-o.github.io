"""Lit les matchs d'un bracket Liquipedia (phases UB/LB, playoffs) : équipes, scores, heure.

Chaque match est un bloc « brkts-match » : deux entrées « brkts-opponent-entry » (nom dans aria-label,
score dans « brkts-opponent-score-inner », parfois en gras), et une fenêtre d'infos avec data-timestamp.
"""
import re

_BLOC = re.compile(r'class="brkts-match ')
_ENTREE = re.compile(r'brkts-opponent-entry(?!-left)[^"]*"\s*aria-label="([^"]+)"')
_SCORE = re.compile(r'brkts-opponent-score-inner">\s*(?:<b>)?\s*(\d*)\s*(?:</b>)?\s*<')
_TS = re.compile(r'data-timestamp="(\d+)"')
_FIN = re.compile(r'data-finished="finished"')


def parse_bracket(html):
    """Renvoie une liste de dicts : t1, t2, s1, s2 (None si pas joué), ts (timestamp ou None)."""
    sortie = []
    for bloc in _BLOC.split(html)[1:]:
        morceaux = re.split(r'(?=brkts-opponent-entry(?!-left))', bloc)
        entrees = []
        for m in morceaux:
            nom = _ENTREE.search(m)
            if not nom:
                continue
            sc = _SCORE.search(m)
            entrees.append((nom.group(1), sc.group(1) if sc else ""))
        if len(entrees) < 2 or "TBD" in (entrees[0][0], entrees[1][0]):
            continue
        (a, sa), (b, sb) = entrees[0], entrees[1]
        joue = bool(_FIN.search(bloc))
        ts = _TS.search(bloc)
        sortie.append({
            "t1": a, "t2": b,
            "s1": int(sa) if joue and sa.isdigit() else None,
            "s2": int(sb) if joue and sb.isdigit() else None,
            "ts": int(ts.group(1)) if ts else None,
        })
    return sortie
