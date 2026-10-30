/* Local document search. No service, framework JS, or network CDN required. */
(() => {
  "use strict";
  document.addEventListener("DOMContentLoaded", () => {
    const trigger = document.getElementById("search-open");
    const dialog = document.getElementById("search-dialog");
    const input = document.getElementById("search-input");
    const results = document.getElementById("search-results");
    const status = document.getElementById("search-status");
    if (!trigger || !dialog || !input || !results || !status ||
        typeof dialog.showModal !== "function") return;
    const limit = Number(dialog.dataset.limit) || 8;
    const minimum = Number(dialog.dataset.minLength) || 2;
    const indexURL = new URL(dialog.dataset.indexUrl, document.baseURI);
    const baseURL = new URL("./", indexURL);
    let pending;
    let generation = 0;
    let timer;
    let previousFocus;
    const normalize = (text) => text.normalize("NFKC").toLowerCase();
    const terms = (text) => [...new Set(normalize(text).match(/[\p{L}\p{N}_]+/gu) || [])];
    const clear = () => results.replaceChildren();
    const message = (text, busy = false) => {
      status.textContent = text;
      results.setAttribute("aria-busy", String(busy));
    };
    const load = () => {
      if (!pending) {
        pending = fetch(indexURL.href, { credentials: "same-origin" }).then((response) => {
          if (!response.ok) throw new Error("Search index unavailable");
          return response.json();
        }).then((data) => {
          if (!Array.isArray(data)) throw new Error("Invalid search index");
          return data.map((item) => {
            if (!item || ![item.title, item.url, item.text].every((value) => typeof value === "string") ||
                item.url.startsWith("/") || /^[a-z][a-z\d+.-]*:/i.test(item.url)) {
              throw new Error("Invalid search record");
            }
            const url = new URL(item.url, baseURL);
            if (url.origin !== baseURL.origin || !url.pathname.startsWith(baseURL.pathname)) {
              throw new Error("Search record escapes site");
            }
            return { ...item, href: url.href, name: normalize(item.title), body: normalize(item.text) };
          });
        }).catch((error) => { pending = undefined; throw error; });
      }
      return pending;
    };
    const excerpt = (text, words) => {
      const body = normalize(text);
      const positions = words.map((word) => body.indexOf(word)).filter((value) => value >= 0);
      const start = Math.max(0, (positions.length ? Math.min(...positions) : 0) - 55);
      return (start ? "…" : "") + text.slice(start, start + 180) +
        (text.length > start + 180 ? "…" : "");
    };
    const render = (items, words) => {
      const ranked = items.map((item) => {
        let score = 0;
        for (const word of words) {
          if (item.name.includes(word)) score += 12;
          else if (item.body.includes(word)) score += 1;
          else return null;
        }
        if (item.name === words.join(" ")) score += 20;
        return { item, score };
      }).filter(Boolean).sort((left, right) => right.score - left.score ||
        (left.item.url < right.item.url ? -1 : left.item.url > right.item.url ? 1 : 0));
      // Keep the most relevant section for each page, avoiding repeated hits.
      const pages = new Set();
      const matches = ranked.filter(({ item }) => {
        const page = item.href.split("#")[0];
        if (pages.has(page)) return false;
        pages.add(page);
        return true;
      });
      clear();
      for (const { item } of matches.slice(0, limit)) {
        const row = document.createElement("li");
        const link = document.createElement("a");
        link.href = item.href;
        link.textContent = item.title;
        const detail = document.createElement("p");
        detail.className = "search-excerpt";
        detail.textContent = excerpt(item.text, words);
        row.append(link, detail);
        results.append(row);
      }
      message(matches.length ? `Showing ${Math.min(matches.length, limit)} of ${matches.length} matching pages.` : "No matches found.");
    };
    const search = async () => {
      const current = ++generation;
      const words = terms(input.value);
      if (!words.length || [...input.value.trim()].length < minimum) {
        clear();
        message(`Type at least ${minimum} characters to search.`);
        return;
      }
      clear();
      message("Searching…", true);
      try {
        const items = await load();
        if (current === generation && dialog.open) render(items, words);
      } catch (_) {
        if (current !== generation || !dialog.open) return;
        clear();
        message(indexURL.protocol === "file:" ?
          "Search needs HTTP. Serve the generated site locally." :
          "Search is unavailable. Close and reopen search to retry.");
      }
    };
    const open = () => {
      if (!dialog.open) {
        previousFocus = document.activeElement;
        dialog.showModal();
      }
      input.focus();
      input.select();
      search();
    };
    trigger.hidden = false;
    trigger.addEventListener("click", open);
    dialog.addEventListener("close", () => {
      ++generation;
      clearTimeout(timer);
      if (previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
    });
    input.addEventListener("input", () => {
      ++generation;
      clearTimeout(timer);
      timer = setTimeout(search, 120);
    });
    dialog.addEventListener("keydown", (event) => {
      if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
      const links = [...results.querySelectorAll("a")];
      if (!links.length) return;
      const current = links.indexOf(document.activeElement);
      const next = event.key === "ArrowDown" ? (current + 1) % links.length :
        (current <= 0 ? links.length - 1 : current - 1);
      links[next].focus();
      event.preventDefault();
    });
    document.addEventListener("keydown", (event) => {
      const target = event.target;
      if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
      if (event.altKey || (event.key !== "/" && !((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k"))) return;
      if (event.key === "/" && (event.ctrlKey || event.metaKey)) return;
      event.preventDefault();
      open();
    });
  });
})();
