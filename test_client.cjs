const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const context = vm.createContext({
  document: {
    querySelector: () => ({querySelectorAll: () => [], addEventListener() {}, replaceChildren() {}}),
    querySelectorAll: () => [],
    addEventListener() {},
  },
  location: {search: ""},
  URLSearchParams,
});
vm.runInContext(fs.readFileSync(path.join(__dirname, "public/app.js"), "utf8"), context);

function value(expression) {
  return JSON.parse(JSON.stringify(vm.runInContext(expression, context)));
}

test("SciFree journal links preserve plain titles and URL punctuation", () => {
  for (const title of ["Constructions and frames", "Computers & Fluids", "Şükrü's Journal"] ) {
    const url = new URL(value(`sciFree(${JSON.stringify(title)})`));
    assert.equal(url.origin, "https://search.scifree.se");
    assert.equal(url.pathname, "/aalto");
    assert.equal(url.searchParams.get("term"), title);
  }
});

test("JUFO levels and quartiles share four visual tiers without changing missing labels", () => {
  assert.deepEqual(value('[0,1,2,3].map(level => rankTier(level))'), [0, 1, 2, 3]);
  assert.deepEqual(value('[4,3,2,1].map(q => rankTier(q,true))'), [0, 1, 2, 3]);
  assert.equal(value('rankTier(null)'), 0);
  assert.equal(value('rankTier(undefined)'), 0);
  assert.equal(value('rankTier("None")'), 0);
  assert.equal(value('rankTier(0,true)'), 0);
  assert.equal(value('journalFacts({level:null}).level'), "Unclassified");
});

test("recent searches validate local data, deduplicate and keep only five", () => {
  assert.deepEqual(value('recentQueries([" ML ", "ml", null, 3, "a", "x".repeat(161), "CFD", "SGS", "TCI", "Physics", "Energy"])'),
    ["ML", "CFD", "SGS", "TCI", "Physics"]);
  assert.deepEqual(value('recentQueries({query: "CFD"})'), []);
  assert.deepEqual(value('readRecentSearches()'), []);
});

test("recent search history comes only from this browser's storage", () => {
  let stored = '["CFD","ML"]';
  context.localStorage = {getItem: key => key === "jufosearch.recent.v1" ? stored : null};
  assert.deepEqual(value('readRecentSearches()'), ["CFD", "ML"]);
  stored = null;
  assert.deepEqual(value('readRecentSearches()'), []);
  stored = '{broken';
  assert.deepEqual(value('readRecentSearches()'), []);
  delete context.localStorage;
});

test("history begins at publication and missing evaluations stay missing", () => {
  assert.deepEqual(value('annualLevels({2020: "0", 2021: "0", 2022: "0", 2023: "0", 2024: "", 2025: "1", 2026: "1"}, 2024)'),
    [[2024, null], [2025, 1], [2026, 1]]);
});

test("absent years are gaps and an explicit zero remains zero", () => {
  assert.deepEqual(value('annualLevels({2024: "1", 2026: "0"}, 2024)'),
    [[2024, 1], [2025, null], [2026, 0]]);
  assert.deepEqual(value('annualLevels({2023: null, 2024: "None", 2025: "", 2026: 0}, 2023)'),
    [[2023, null], [2024, null], [2025, null], [2026, 0]]);
});

test("unknown publication dates preserve recorded history", () => {
  assert.deepEqual(value('annualLevels({2024: "2", 2025: "1"}, null)'), [[2024, 2], [2025, 1]]);
  assert.deepEqual(value('annualLevels({}, 2024)'), []);
});

test("missing years use dashed baseline links and real zero levels stay recorded", () => {
  assert.deepEqual(value('historySegments([[2024, null], [2025, null], [2026, 1], [2027, 0]])'), [
    {from: [2024, 0], to: [2025, 0], missing: true},
    {from: [2025, 0], to: [2026, 1], missing: true},
    {from: [2026, 1], to: [2027, 0], missing: false},
  ]);
  assert.deepEqual(value('historySegments([[2024, 1]])'), []);
});

test("ticks include endpoints and readable two- or five-year intervals", () => {
  assert.deepEqual(value('historyTicks(annualLevels({2020: 1, 2026: 1}, 2020))'), [2020, 2022, 2024, 2026]);
  assert.deepEqual(value('historyTicks(annualLevels({2012: 1, 2026: 1}, 2012))'), [2012, 2015, 2020, 2026]);
  assert.deepEqual(value('historyTicks([[2024, 1]])'), [2024]);
});

test("publisher labels preserve Unicode and identify damaged source names", () => {
  assert.equal(value('publisherName({publisher_name: "Şükrü Dursun"})'), "Şükrü Dursun");
  assert.equal(value('publisherName({publisher_name: "?smail ?ahin"})'), "Publisher name incomplete");
  assert.equal(value('publisherName({publisher_name: "Bad\\uFFFDname"})'), "Publisher name incomplete");
});

test("missing metadata has neutral values and unclassified is distinct from zero", () => {
  assert.deepEqual(value('journalFacts({})'), {
    level: "Unclassified", publisher: "Unknown publisher", fee: "Check SciFree",
    licence: "Not listed", model: "Not listed",
  });
  assert.equal(value('journalFacts({level: 0}).level'), "0");
});

test("positive model evidence fills gaps without treating non-OA as hybrid or free", () => {
  assert.equal(value('publishingInfo({external:{oa_info:{is_oa:false,is_hybrid:false,open_access_type:"unknown"}}}).model'), "Not listed");
  assert.equal(value('publishingInfo({external:{oa_info:{is_oa:true}}}).model'), "Gold OA");
  assert.equal(value('publishingInfo({publishing_model:{model:"Hybrid OA",provider:"Publisher"}}).model'), "Hybrid OA");
  assert.equal(value('publishingInfo({external:{oa_info:{is_diamondOA:true}},agreement:{model:"Pure OA"}}).model'), "Diamond OA");
  assert.equal(value('publishingInfo({external:{oa_info:{open_access_type:"Hybrid"}},publishing_model:{model:"Gold OA"}}).model'), "Hybrid OA");
  assert.equal(value('journalFacts({publishing_model:{model:"Hybrid OA"}}).fee'), "Check SciFree");
});
