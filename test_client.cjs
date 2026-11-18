const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const context = vm.createContext({
  document: {
    querySelector: () => ({querySelectorAll: () => [], addEventListener() {}}),
    querySelectorAll: () => [],
  },
  location: {search: ""},
  URLSearchParams,
});
vm.runInContext(fs.readFileSync(path.join(__dirname, "public/app.js"), "utf8"), context);

function value(expression) {
  return JSON.parse(JSON.stringify(vm.runInContext(expression, context)));
}

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
