"use strict";

(() => {
  const key = "jufosearch.theme";
  const system = matchMedia("(prefers-color-scheme: dark)");
  let preference;
  try { preference = localStorage.getItem(key); } catch {}
  if (preference !== "light" && preference !== "dark") preference = null;

  function apply() {
    const theme = preference || (system.matches ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
    const button = document.querySelector("#theme-toggle");
    if (button) {
      const label = theme === "dark" ? "Use light theme" : "Use dark theme";
      button.setAttribute("aria-label", label);
      button.title = label;
    }
  }

  apply();
  system.addEventListener("change", () => { if (!preference) apply(); });
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    document.querySelector("#theme-toggle").addEventListener("click", () => {
      preference = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      try { localStorage.setItem(key, preference); } catch {}
      apply();
    });
  });
})();
