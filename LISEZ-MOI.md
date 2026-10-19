# Site Mexic Original (mexic-o.github.io)

## Mettre en ligne (depuis le PC)
1. Ouvre https://github.com/Mexic-o/mexic-o.github.io
2. « Add file » → « Upload files ».
3. Glisse TOUT le contenu du dossier dézippé (index.html, news.html, confidentialite.html, les dossiers assets et data).
   Il remplace l'ancien index.html : c'est voulu.
4. En bas : « Commit changes ».
5. Une à deux minutes plus tard : https://mexic-o.github.io

## Important : page de confidentialité de Mexic Studio
L'ancienne page d'accueil était la page de confidentialité de Mexic Studio (API YouTube).
Elle est conservée à l'adresse : https://mexic-o.github.io/confidentialite.html
→ Dans Google Cloud Console (écran de consentement OAuth / « Branding »), remplace le lien
  « Règles de confidentialité » par cette nouvelle adresse, sinon Google ne la trouvera plus.

## Mettre à jour les news
Tout est dans `data/news.json` (le site se met à jour tout seul à partir de ce fichier) :

```json
{
  "semaine": "2026-10-21",
  "video": "https://youtu.be/...",
  "articles": [
    { "titre": "Équipe X remporte le tournoi", "resume": "Victoire 3 à 1 en finale.",
      "categorie": "resultats", "tier": "Tier 1", "date": "2026-10-19",
      "cartes": ["Mirage 13-9", "Nuke 10-13"],
      "image": "assets/news/finale.jpg", "lien": "https://..." }
  ],
  "matchs": [
    { "jour": "2026-10-22", "heure": "18:00", "equipes": "A vs B", "tournoi": "Nom du tournoi" }
  ]
}
```
- `categorie` : `resultats`, `mercato`, `maj` ou `fr` (filtres de la page News).
- `image` et `lien` : facultatifs.
- Tant que `articles` est vide, le site affiche « La première édition arrive mercredi ».

## Boutique M.x.O
Quand la boutique Square sera prête, dans index.html remplace la ligne
`<span class="btn soon">Ouverture bientôt…</span>` par
`<a class="btn twitch" href="LIEN-SQUARE">Voir la boutique</a>`.
