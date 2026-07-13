/* AI Gateway site — progressive enhancement (no dependencies) */
(function () {
  "use strict";

  /* ---- theme toggle (light / dark) ---- */
  // The initial theme is set by an inline <head> script to avoid a flash.
  var themeToggle = document.getElementById("themeToggle");
  if (themeToggle) {
    var root = document.documentElement;
    var setLabel = function () {
      var t = root.getAttribute("data-theme") === "light" ? "light" : "dark";
      themeToggle.setAttribute(
        "aria-label",
        t === "light" ? "Switch to dark theme" : "Switch to light theme"
      );
    };
    setLabel();
    themeToggle.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("theme", next);
      } catch (e) {
        /* storage unavailable — theme still applies for this session */
      }
      setLabel();
    });
  }

  /* ---- mobile nav toggle ---- */
  var topbar = document.querySelector(".topbar");
  var toggle = document.getElementById("navToggle");
  if (toggle && topbar) {
    toggle.addEventListener("click", function () {
      var open = topbar.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    // close the menu after tapping a link
    topbar.querySelectorAll(".nav a").forEach(function (a) {
      a.addEventListener("click", function () {
        topbar.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  /* ---- copy-to-clipboard on code blocks ---- */
  document.querySelectorAll(".code[data-copy]").forEach(function (block) {
    var btn = block.querySelector(".copy-btn");
    var code = block.querySelector("code");
    if (!btn || !code) return;
    btn.addEventListener("click", function () {
      var text = code.innerText.replace(/ /g, " ");
      navigator.clipboard.writeText(text).then(function () {
        var prev = btn.textContent;
        btn.textContent = "Copied";
        btn.classList.add("copied");
        setTimeout(function () {
          btn.textContent = prev;
          btn.classList.remove("copied");
        }, 1400);
      });
    });
  });

  /* ---- active nav link on scroll ---- */
  var links = Array.prototype.slice.call(document.querySelectorAll(".nav a"));
  var sections = links
    .map(function (a) {
      var id = a.getAttribute("href");
      return id && id.charAt(0) === "#" ? document.querySelector(id) : null;
    })
    .filter(Boolean);

  if ("IntersectionObserver" in window && sections.length) {
    var byId = {};
    links.forEach(function (a) {
      byId[a.getAttribute("href")] = a;
    });
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            links.forEach(function (l) {
              l.classList.remove("active");
            });
            var active = byId["#" + entry.target.id];
            if (active) active.classList.add("active");
          }
        });
      },
      { rootMargin: "-45% 0px -50% 0px", threshold: 0 }
    );
    sections.forEach(function (s) {
      observer.observe(s);
    });
  }
})();
