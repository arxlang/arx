/* DoukiMD appearance preferences. No framework JavaScript is required. */
(() => {
  "use strict";
  const root = document.documentElement;
  const modes = ["auto", "light", "dark"];
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  const key = root.dataset.preferenceKey;
  const paletteKey = key + ":palette";
  const palettes = (root.dataset.palettes || "").split(",").filter(Boolean);
  let palette = root.dataset.palette;
  let mode = root.dataset.colorMode;
  try {
    const stored = localStorage.getItem(key);
    if (modes.includes(stored)) mode = stored;
  } catch (_) {
    // Browsers may deny storage, including when viewing local files.
  }
  try {
    const stored = localStorage.getItem(paletteKey);
    if (palettes.includes(stored)) palette = stored;
  } catch (_) { /* Storage is optional for both preferences. */ }
  const apply = () => {
    root.dataset.bsTheme = mode === "auto"
      ? (system.matches ? "dark" : "light") : mode;
    root.dataset.colorMode = mode;
    if (palettes.includes(palette)) root.dataset.palette = palette;
  };
  apply();
  system.addEventListener("change", () => {
    if (mode === "auto") apply();
  });
  document.addEventListener("DOMContentLoaded", () => {
    const paletteSelect = document.getElementById("color-palette");
    if (paletteSelect && palettes.includes(palette)) {
      paletteSelect.value = palette;
      paletteSelect.closest(".palette-picker").hidden = false;
      paletteSelect.addEventListener("change", () => {
        if (!palettes.includes(paletteSelect.value)) return;
        palette = paletteSelect.value;
        apply();
        try { localStorage.setItem(paletteKey, palette); } catch (_) { /* Optional. */ }
      });
    }
    const select = document.getElementById("color-mode");
    if (select) {
      select.value = mode;
      select.closest(".mode-picker").hidden = false;
      select.addEventListener("change", () => {
        if (!modes.includes(select.value)) return;
        mode = select.value;
        apply();
        try { localStorage.setItem(key, mode); } catch (_) { /* Optional. */ }
      });
    }
    const navigation = document.getElementById("docs-navigation");
    if (navigation) {
      const mobile = window.matchMedia("(max-width: 960px)");
      const resize = () => { navigation.open = !mobile.matches; };
      resize();
      mobile.addEventListener("change", resize);
    }
    // Also support exclusive groups in browsers without details[name].
    document.querySelectorAll(".api-navigation").forEach((menu) => {
      const modules = [...menu.querySelectorAll("details.api-module")];
      modules.forEach((module) => module.addEventListener("toggle", () => {
        if (!module.open) return;
        modules.forEach((other) => {
          if (other !== module) other.open = false;
        });
      }));
    });
  });
})();
