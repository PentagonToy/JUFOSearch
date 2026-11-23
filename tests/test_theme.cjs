const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../public/theme.js"), "utf8");

function browserTheme(saved, dark = false, blocked = false) {
  const root = {dataset: {}};
  const handlers = {};
  const button = {setAttribute(name, value) { this[name] = value; }, addEventListener(name, fn) { handlers[name] = fn; }};
  const media = {matches: dark, addEventListener(name, fn) { handlers.system = fn; }};
  const storage = {getItem() { if (blocked) throw Error("Blocked"); return saved; },
    setItem(key, value) { if (blocked) throw Error("Blocked"); saved = value; }};
  vm.runInNewContext(source, {matchMedia: () => media, localStorage: storage,
    document: {documentElement: root, querySelector: () => button,
      addEventListener(name, fn) { handlers.ready = fn; }}});
  return {root, button, media, handlers, saved: () => saved};
}

test("theme follows the system before first paint and updates accessible action labels", () => {
  const page = browserTheme(null, true);
  assert.equal(page.root.dataset.theme, "dark");
  page.handlers.ready();
  assert.equal(page.button["aria-label"], "Use light theme");
  page.media.matches = false;
  page.handlers.system();
  assert.equal(page.root.dataset.theme, "light");
  assert.equal(page.button["aria-label"], "Use dark theme");
});

test("manual choice persists and overrides later system changes", () => {
  const page = browserTheme("light", true);
  page.handlers.ready();
  assert.equal(page.root.dataset.theme, "light");
  page.handlers.click();
  assert.equal(page.saved(), "dark");
  assert.equal(page.root.dataset.theme, "dark");
  page.media.matches = false;
  page.handlers.system();
  assert.equal(page.root.dataset.theme, "dark");
  assert.equal(browserTheme(page.saved(), false).root.dataset.theme, "dark");
});

test("invalid or blocked browser storage still permits theme switching", () => {
  assert.equal(browserTheme("unexpected", true).root.dataset.theme, "dark");
  const page = browserTheme(null, false, true);
  page.handlers.ready();
  page.handlers.click();
  assert.equal(page.root.dataset.theme, "dark");
});
