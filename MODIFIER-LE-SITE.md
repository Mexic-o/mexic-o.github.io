# Modifier le site sans toucher au code

Tout ce qui peut changer est dans **un seul fichier : `site.json`**. Les news, elles, restent automatiques (Mexic Studio).

Ce que `site.json` règle :
- les liens Twitch, YouTube et Discord (partout sur le site) ;
- le planning de la semaine ;
- les boutons de Mexic Lurk (Firefox, Chrome/Brave, Edge, Opera) et le numéro de version ;
- la carte du maillot ;
- l'encart boutique M.x.O.

## Comment modifier (téléphone ou PC)

1. Va sur https://github.com/Mexic-o/mexic-o.github.io et ouvre **site.json**.
2. Clique sur le **crayon** (« Edit this file »).
3. Change **seulement le texte entre guillemets**.
4. Clique sur **Commit changes…** puis encore sur **Commit changes**.
5. Attends 1 à 2 minutes, puis recharge le site (sur PC : Ctrl + F5).

## Les 3 règles pour ne rien casser

- Garde les **guillemets** autour de chaque texte : `"comme ça"`.
- Garde les **virgules** en fin de ligne, **sauf** après le dernier élément d'une liste ou d'un bloc.
- Pour mettre des guillemets dans un texte, utilise plutôt « » ou des apostrophes.

Si après ta modif le site affiche **les anciens textes**, c'est qu'il manque une virgule ou un guillemet. Le site ne casse pas : il garde simplement les textes d'avant. Pour annuler, ouvre **site.json → History**, ou envoie le fichier à Claude.

## Exemples

**Edge ou Opera validé** : colle le lien entre les guillemets vides.
```
"edge": "https://microsoftedge.microsoft.com/addons/detail/....",
"opera": "https://addons.opera.com/fr/extensions/details/mexic-lurk/",
```
Le bouton apparaît sur l'accueil et sur la page Chrome/Brave, et « bientôt » disparaît tout seul.

**Nouvelle version de l'extension** : change `"version": "1.0.3"` et renvoie le nouveau `mexic-lurk-chrome.zip` (même nom).

**Changer un horaire du planning** : modifie `quand`, `titre` ou `detail` dans le bloc concerné. Couleurs possibles : vert, orange, violet, rouge, blanc.

**Ouverture de la boutique** :
```
"etiquette": "Boutique",
"bouton": "Voir la boutique",
"lien": "https://ta-boutique...",
```
(et adapte les deux phrases de `textes`). Un lien vide `""` affiche un bouton « bientôt ».

**Nouveau lien Discord** : change `"discord"` dans `liens`, tous les boutons Discord du site suivent.
