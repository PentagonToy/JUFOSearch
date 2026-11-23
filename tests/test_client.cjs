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
vm.runInContext(fs.readFileSync(path.join(__dirname, "../public/app.js"), "utf8"), context);

function value(expression) {
  return JSON.parse(JSON.stringify(vm.runInContext(expression, context)));
}

test("OA preferences accept worldwide institutions and reject unsupported funders or damaged identities", () => {
  context.oaTestOptions = {funders:[{id:"academyoffinlandaka"}],institution:{id:"020hwjq30",title:"Aalto University",country:"Finland"}};
  assert.equal(value('validOAProfile({institution:oaTestOptions.institution,funder:"academyoffinlandaka"},oaTestOptions)'), true);
  assert.equal(value('validOAProfile({institution:oaTestOptions.institution,funder:"wellcome"},oaTestOptions)'), false);
  assert.equal(value('validOAProfile({institution:{id:"052gg0110",title:"Oxford",country:"United Kingdom"},funder:"academyoffinlandaka"},oaTestOptions)'), true);
  assert.equal(value('validOAProfile({institution:{id:"../data",title:"Aalto",country:"Finland"},funder:"academyoffinlandaka"},oaTestOptions)'), false);
});

test("OA preferences persist only when requested and reset without touching search history", () => {
  const storage = new Map([["jufosearch.recent.v1", '["CFD"]']]);
  context.localStorage = {getItem:key=>storage.get(key)||null,setItem:(key,data)=>storage.set(key,data),removeItem:key=>storage.delete(key)};
  context.document.dispatchEvent = () => {};
  context.Event = class {constructor(type) {this.type=type;}};
  vm.runInContext('applyOAProfile({institution:oaTestOptions.institution,funder:"academyoffinlandaka"},false)',context);
  assert.equal(storage.has("jufosearch.oa-profile.v1"),false);
  vm.runInContext('applyOAProfile({institution:oaTestOptions.institution,funder:"academyoffinlandaka"},true)',context);
  assert.equal(JSON.parse(storage.get("jufosearch.oa-profile.v1")).institution.id,"020hwjq30");
  const fresh = vm.createContext({...context,localStorage:{getItem:key=>key === "jufosearch.oa-profile.v1" ? storage.get(key) : null},location:{search:""}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,"../public/app.js"),"utf8"),fresh);
  assert.equal(vm.runInContext('currentOAProfile(oaTestOptions).institution.id',fresh),"020hwjq30");
  vm.runInContext('applyOAProfile(null,false)',context);
  assert.equal(storage.has("jufosearch.oa-profile.v1"),false);
  assert.equal(storage.get("jufosearch.recent.v1"),'["CFD"]');
  context.localStorage.setItem = () => {throw new Error("Storage blocked");};
  assert.equal(value('applyOAProfile({institution:oaTestOptions.institution,funder:"academyoffinlandaka"},true)'),false);
  assert.equal(value('currentOAProfile(oaTestOptions).institution.id'),"020hwjq30");
  delete context.localStorage;
});

test("listed APCs prefer an available euro price and never infer Aalto funding", () => {
  assert.equal(value('listedAPC({apc:{prices:[{currency:"USD",amount:1910},{currency:"EUR",amount:1790}]}})'), "EUR 1,790");
  assert.equal(value('listedAPC({apc:{prices:[{currency:"USD",amount:0}]}})'), "USD 0");
  assert.equal(value('listedAPC({apc:{prices:[{currency:"EUR",amount:-1},{currency:"USD",amount:NaN}]}})'), null);
  assert.equal(value('listedAPC({})'), null);
  assert.equal(value('journalFacts({apc:{prices:[{currency:"EUR",amount:0}]}}).fee'), "Check SciFree");
});

test("main results and peer suggestions preserve every active filter", () => {
  assert.equal(value('passesFilters({level:"1",fee:"Fully covered"},[["level",["1","2"]],["fee",["Fully covered"]]])'), true);
  assert.equal(value('passesFilters({level:"1",fee:"15% discount"},[["level",["1"]],["fee",["Fully covered"]]])'), false);
  assert.equal(value('passesFilters({level:"Unclassified"},[["level",["0"]]])'), false);
});

test("large result sets load completely with at most three parallel page requests", async () => {
  let active = 0, maximum = 0;
  const offsets = [];
  context.readPage = async params => {
    const offset = Number(params.get("offset") || 0);
    offsets.push(offset);
    maximum = Math.max(maximum, ++active);
    await new Promise(resolve => setTimeout(resolve, offset === 1000 ? 8 : 1));
    active--;
    return {results: Array.from({length: Math.min(1000, 4501-offset)}, (_, i) => offset+i),
      total:4501, next_offset:offset+1000 < 4501 ? offset+1000 : null};
  };
  const pages = await vm.runInContext('loadSearchPages(new URLSearchParams({q:"ml"}),readPage)', context);
  assert.deepEqual(offsets.sort((a,b)=>a-b), [0,1000,2000,3000,4000]);
  assert.equal(maximum, 3);
  assert.deepEqual(Array.from(pages.flatMap(page=>page.results)), Array.from({length:4501},(_,i)=>i));
});

test("first results become available before remaining pages finish", async () => {
  let firstVisible = false;
  context.showFirstPage = page => { firstVisible = page.results[0] === 0; };
  context.readProgressive = async params => {
    const offset = Number(params.get("offset") || 0);
    if (offset) assert.equal(firstVisible, true);
    return {results:[offset], total:2000, next_offset:offset ? null : 1000};
  };
  const pages = await vm.runInContext('loadSearchPages(new URLSearchParams({q:"ml"}),readProgressive,undefined,showFirstPage)', context);
  assert.equal(firstVisible, true);
  assert.deepEqual(Array.from(pages.flatMap(page=>page.results)), [0,1000]);
});

test("older responses without totals retain complete sequential pagination", async () => {
  context.readLegacy = async params => {
    const offset = Number(params.get("offset") || 0);
    return {results:[offset], next_offset:offset < 2 ? offset+1 : null};
  };
  const pages = await vm.runInContext('loadSearchPages(new URLSearchParams({q:"ml"}),readLegacy)', context);
  assert.deepEqual(Array.from(pages.flatMap(page=>page.results)), [0,1,2]);
});

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
