// Affiche les news et le calendrier à partir de data/news.json.
// Format attendu (voir LISEZ-MOI.md) :
// { "semaine": "2026-10-21", "video": "https://youtu.be/...",
//   "articles": [{ "titre": "...", "resume": "...", "categorie": "resultats|mercato|maj|fr",
//                  "tier": "Tier 1", "date": "2026-10-20", "image": "assets/news/finale.jpg",
//                  "cartes": ["Mirage 13-9"], "lien": "https://..." }],
//   "matchs": [{ "jour": "2026-10-22", "heure": "18:00", "equipes": "A vs B", "tournoi": "..." }] }
(function () {
  var NOMS = { resultats: 'Résultats', mercato: 'Mercato', maj: 'Mise à jour', fr: 'Scène FR' };

  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }
  function dateFr(iso, opts) {
    if (!iso) return '';
    var d = new Date(iso + 'T12:00:00');
    if (isNaN(d)) return iso;
    return d.toLocaleDateString('fr-FR', opts || { day: 'numeric', month: 'long' });
  }
  function sur(url) { return /^(https:\/\/|assets\/|[a-z0-9_-]+\.(jpg|jpeg|png|webp)$)/.test(url || '') ? url : ''; }

  function carte(a) {
    var c = el('article', 'card');
    var img = sur(a.image);
    if (img) { var i = el('img', 'img'); i.src = img; i.alt = ''; i.loading = 'lazy'; c.appendChild(i); }
    var b = el('div', 'body');
    var t = el('div', 'tags');
    t.appendChild(el('span', 'tag ' + (NOMS[a.categorie] ? a.categorie : 'fr'), NOMS[a.categorie] || 'Info'));
    if (a.tier) t.appendChild(el('span', 'tag t', a.tier));
    if (a.date) t.appendChild(el('span', 'date', dateFr(a.date)));
    b.appendChild(t);
    b.appendChild(el('h3', null, a.titre || ''));
    if (a.cartes && a.cartes.length) {
      var m = el('div', 'maps');
      a.cartes.forEach(function (x) { m.appendChild(el('span', null, x)); });
      b.appendChild(m);
    }
    if (a.resume) b.appendChild(el('p', null, a.resume));
    var lien = sur(a.lien);
    if (lien) { var l = el('a', 'more', 'En savoir plus →'); l.href = lien; b.appendChild(l); }
    c.appendChild(b);
    c.dataset.cat = a.categorie || '';
    return c;
  }

  function vide(cible, txt) { cible.innerHTML = ''; cible.appendChild(el('div', 'empty', txt)); }

  function calendrier(cible, matchs) {
    cible.innerHTML = '';
    if (!matchs.length) { cible.appendChild(el('p', 'date', 'Le programme des matchs arrive avec la prochaine édition.')); return; }
    var jour = null;
    matchs.forEach(function (m) {
      if (m.jour !== jour) { jour = m.jour; cible.appendChild(el('span', 'day', dateFr(m.jour, { weekday: 'long', day: 'numeric', month: 'long' }))); }
      var r = el('div', 'row');
      var g = el('div');
      g.appendChild(el('b', null, m.equipes || ''));
      if (m.tournoi) { g.appendChild(document.createElement('br')); g.appendChild(el('span', null, m.tournoi)); }
      r.appendChild(g);
      r.appendChild(el('span', null, m.heure || ''));
      cible.appendChild(r);
    });
  }

  fetch('news.json', { cache: 'no-cache' })
    .then(function (r) { return r.json(); })
    .catch(function () { return { articles: [], matchs: [] }; })
    .then(function (d) {
      var arts = d.articles || [];
      var accueil = document.getElementById('news-accueil');
      if (accueil) {
        if (!arts.length) vide(accueil, 'La première édition des news CS2 arrive mercredi à 18 h, avec la vidéo.');
        else { accueil.innerHTML = ''; arts.slice(0, 3).forEach(function (a) { accueil.appendChild(carte(a)); }); }
      }
      var liste = document.getElementById('news-liste');
      if (liste) {
        var titre = document.getElementById('semaine');
        if (titre && d.semaine) titre.textContent = 'News CS2 · semaine du ' + dateFr(d.semaine);
        var v = document.getElementById('video');
        if (v && sur(d.video)) { v.href = d.video; v.hidden = false; }
        if (!arts.length) vide(liste, 'La première édition des news CS2 arrive mercredi à 18 h, avec la vidéo.');
        else { liste.innerHTML = ''; arts.forEach(function (a) { liste.appendChild(carte(a)); }); }
        var btns = document.querySelectorAll('.filters button');
        btns.forEach(function (bt) {
          bt.addEventListener('click', function () {
            btns.forEach(function (x) { x.setAttribute('aria-pressed', x === bt ? 'true' : 'false'); });
            var f = bt.dataset.f;
            liste.querySelectorAll('.card').forEach(function (c) { c.hidden = f !== 'tout' && c.dataset.cat !== f; });
          });
        });
      }
      var cal = document.getElementById('calendrier');
      if (cal) calendrier(cal, d.matchs || []);
    });
})();
