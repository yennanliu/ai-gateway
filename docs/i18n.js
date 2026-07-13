/* AI Gateway site — language switch (English / 繁體中文), no dependencies.
 *
 * English lives inline in the HTML (default, works with JS off and for SEO).
 * The per-page dictionary (window.I18N_ZH, from i18n.<page>.js) supplies the
 * Traditional Chinese innerHTML for every element tagged with data-i18n, keyed
 * by that attribute's value. Reserved keys __title / __desc translate the
 * document <title> and <meta name="description">.
 */
(function () {
  "use strict";

  var ZH = window.I18N_ZH || {};
  var STORE_KEY = "lang";
  var root = document.documentElement;
  var descMeta = document.querySelector('meta[name="description"]');

  // Cache the original English so switching back is lossless and we never
  // depend on the dictionary carrying the English side.
  var enTitle = document.title;
  var enDesc = descMeta ? descMeta.getAttribute("content") : null;
  var nodes = Array.prototype.slice.call(document.querySelectorAll("[data-i18n]"));
  nodes.forEach(function (el) {
    el._i18nEn = el.innerHTML;
  });

  function readLang() {
    try {
      return localStorage.getItem(STORE_KEY) === "zh" ? "zh" : "en";
    } catch (e) {
      return "en";
    }
  }

  function saveLang(lang) {
    try {
      localStorage.setItem(STORE_KEY, lang);
    } catch (e) {
      /* storage unavailable — choice still applies for this session */
    }
  }

  function apply(lang) {
    var zh = lang === "zh";

    nodes.forEach(function (el) {
      var key = el.getAttribute("data-i18n");
      var translated = zh && Object.prototype.hasOwnProperty.call(ZH, key) ? ZH[key] : null;
      el.innerHTML = translated != null ? translated : el._i18nEn;
    });

    document.title = zh && ZH.__title ? ZH.__title : enTitle;
    if (descMeta && enDesc != null) {
      descMeta.setAttribute("content", zh && ZH.__desc ? ZH.__desc : enDesc);
    }

    root.setAttribute("lang", zh ? "zh-Hant" : "en");

    // Reflect the active choice on the segmented toggle.
    document.querySelectorAll("#langToggle .lang-opt").forEach(function (opt) {
      var isActive = opt.getAttribute("data-lang") === lang;
      opt.classList.toggle("active", isActive);
      opt.setAttribute("aria-pressed", String(isActive));
    });
  }

  var current = readLang();
  apply(current);

  var toggle = document.getElementById("langToggle");
  if (toggle) {
    toggle.addEventListener("click", function (e) {
      var opt = e.target.closest(".lang-opt");
      if (!opt) return;
      var lang = opt.getAttribute("data-lang") === "zh" ? "zh" : "en";
      if (lang === current) return;
      current = lang;
      saveLang(current);
      apply(current);
    });
  }
})();
