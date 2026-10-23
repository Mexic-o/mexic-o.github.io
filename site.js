/* Lit site.json et met à jour les textes et les liens du site.
 * Si site.json est absent ou mal écrit, le site garde simplement les textes déjà présents dans les pages. */
(function () {
  var COULEURS = { vert: "var(--green)", orange: "var(--orange)", violet: "var(--violet)", rouge: "var(--red)" };

  function txt(v) { return typeof v === "string" ? v : ""; }

  /* N'accepte que les liens web (https://…) ou une page du site (xxx.html). */
  function lien(v) {
    v = txt(v).trim();
    return /^https?:\/\//i.test(v) || /^[a-z0-9_-]+\.html(#.*)?$/i.test(v) ? v : "";
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text) n.textContent = text;
    return n;
  }

  function bouton(label, url, cls) {
    var n = el("a", "btn" + (cls ? " " + cls : ""), label);
    n.href = url;
    return n;
  }

  function liens(d) {
    var L = d.liens || {};
    document.querySelectorAll("[data-lien]").forEach(function (a) {
      var u = lien(L[a.getAttribute("data-lien")]);
      if (u) a.href = u;
    });
  }

  function planning(d) {
    var box = document.getElementById("planning");
    if (!box || !Array.isArray(d.planning) || !d.planning.length) return;
    box.textContent = "";
    d.planning.forEach(function (s) {
      if (!s) return;
      var slot = el("div", "slot");
      var k = el("span", "kicker", txt(s.quand));
      if (COULEURS[s.couleur]) k.style.color = COULEURS[s.couleur];
      slot.appendChild(k);
      slot.appendChild(el("b", null, txt(s.titre)));
      slot.appendChild(el("span", null, txt(s.detail)));
      box.appendChild(slot);
    });
  }

  /* Boutons de Mexic Lurk : accueil (home = true) ou bas de la page Chrome/Brave. */
  function lurk(d) {
    var lk = d.mexic_lurk;
    if (!lk) return;
    [["lurk-btns", true], ["lurk-autres", false]].forEach(function (cfg) {
      var box = document.getElementById(cfg[0]);
      if (!box) return;
      var home = cfg[1];
      box.textContent = "";
      var bientot = [];
      if (lien(lk.firefox)) box.appendChild(bouton(home ? "Installer sur Firefox" : "Firefox", lien(lk.firefox), "green"));
      if (home && lien(lk.chrome_brave)) box.appendChild(bouton("Chrome et Brave", lien(lk.chrome_brave)));
      if (lien(lk.edge)) box.appendChild(bouton("Edge", lien(lk.edge))); else bientot.push("Edge");
      if (lien(lk.opera)) box.appendChild(bouton("Opera / Opera GX", lien(lk.opera))); else bientot.push("Opera");
      if (bientot.length) box.appendChild(el("span", "btn soon", bientot.join(", ") + " : bientôt"));
    });
    var v = document.getElementById("lurk-version");
    if (v && txt(lk.version)) v.textContent = "Version " + lk.version + " · fichier .zip";
  }

  function maillot(d) {
    var m = d.maillot;
    if (!m) return;
    var titre = document.getElementById("maillot-titre");
    var etiquette = document.getElementById("maillot-etiquette");
    if (titre && txt(m.titre)) {
      titre.textContent = m.titre + " ";
      if (etiquette) {
        etiquette.textContent = txt(m.etiquette);
        if (txt(m.etiquette)) titre.appendChild(etiquette);
      }
    }
    var p = document.getElementById("maillot-texte");
    if (p && txt(m.texte)) p.textContent = m.texte;
    var b = document.getElementById("maillot-btn");
    if (b) {
      if (txt(m.bouton)) b.textContent = m.bouton;
      if (lien(m.lien)) b.href = lien(m.lien);
    }
    var img = document.getElementById("maillot-img");
    if (img && /^[a-z0-9_.-]+\.(jpe?g|png|webp)$/i.test(txt(m.image))) img.src = m.image;
  }

  function boutique(d) {
    var b = d.boutique;
    if (!b) return;
    var e = document.getElementById("boutique-etiquette");
    if (e && txt(b.etiquette)) e.textContent = b.etiquette;
    var t = document.getElementById("boutique-titre");
    if (t && txt(b.titre)) t.textContent = b.titre;
    var anciens = document.querySelectorAll(".boutique-txt");
    if (Array.isArray(b.textes) && b.textes.length && anciens.length) {
      var avant = anciens[0];
      b.textes.forEach(function (x) {
        if (!txt(x)) return;
        var p = el("p", "boutique-txt", x);
        avant.parentNode.insertBefore(p, avant);
      });
      anciens.forEach(function (p) { p.remove(); });
    }
    var box = document.getElementById("boutique-btns");
    var btn = document.getElementById("boutique-btn");
    if (box && txt(b.bouton)) {
      var u = lien(b.lien);
      if (u && btn) {
        btn.href = u;
        // Garde l'icône Discord seulement si le lien va vers Discord.
        var svg = btn.querySelector("svg");
        btn.textContent = "";
        if (svg && /discord/i.test(u)) btn.appendChild(svg);
        btn.appendChild(document.createTextNode(b.bouton));
        if (!/discord/i.test(u)) btn.className = "btn orange";
      } else if (!u) {
        box.textContent = "";
        box.appendChild(el("span", "btn soon", b.bouton));
      }
    }
  }

  fetch("site.json", { cache: "no-cache" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) {
      if (!d) return;
      [liens, planning, lurk, maillot, boutique].forEach(function (f) {
        try { f(d); } catch (e) { /* une partie mal remplie n'empêche pas les autres */ }
      });
    })
    .catch(function () { /* site.json absent ou mal écrit : on garde les textes des pages */ });
})();
