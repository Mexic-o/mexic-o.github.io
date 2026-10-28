"""Lit le tableau Swiss (phase de classement) d'une page de tournoi Liquipedia.

Règle : 3 victoires = qualifiée pour les playoffs, 3 défaites = éliminée, sinon toujours en jeu.
La colonne « Matches » donne le bilan « 3 - 1 ».
"""
import re

_TABLE = re.compile(r'class="table2 table2--generic standings-swiss"')
_LIGNE = re.compile(r'<tr class="table2&#95;&#95;row--body"')
_CELLULE = re.compile(r'<td[^>]*>(.*?)</td>', re.S)
_NOM = re.compile(r'title="([^"]+)"')
_BILAN = re.compile(r'(\d+)\s*-\s*(\d+)')


def parse_swiss(html):
    """Renvoie {"qualifiees": [...], "eliminees": [...], "en_jeu": [...], "bilans": {nom: (v, d)}}."""
    sortie = {"qualifiees": [], "eliminees": [], "en_jeu": [], "bilans": {}}
    m = _TABLE.search(html)
    if not m:
        return sortie
    fin = html.find("</table>", m.end())
    tableau = html[m.end():fin if fin > 0 else len(html)]
    for ligne in re.split(r'(?=<tr class="table2&#95;&#95;row--body")', tableau)[1:]:
        cellules = _CELLULE.findall(ligne)
        if len(cellules) < 3:
            continue
        nom_m = _NOM.search(cellules[1])
        nom = nom_m.group(1) if nom_m else re.sub(r"<[^>]+>|\s+", " ", cellules[1]).strip()
        bilan = _BILAN.search(re.sub(r"<[^>]+>", " ", cellules[2]))
        if not nom or not bilan:
            continue
        v, d = int(bilan.group(1)), int(bilan.group(2))
        sortie["bilans"][nom] = (v, d)
        if v >= 3:
            sortie["qualifiees"].append(nom)
        elif d >= 3:
            sortie["eliminees"].append(nom)
        else:
            sortie["en_jeu"].append(nom)
    return sortie
