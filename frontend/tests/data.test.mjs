import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./load-module.mjs";

const { validateDataset, validateField } = await loadModule("../src/data/field.ts");
const dataset = () => ({
  grid: { id: "grid", cells: [{ id: "0", west: -10, east: 10, south: -5, north: 5 }] },
  field: { gridId: "grid", name: "Test field", units: "1", colorScale: "diverging", description: "Test only", values: [-2] },
});

test("validates and copies geometry, metadata and physical values", () => {
  const raw = dataset();
  raw.field.timestamp = "2026-01-01T00:00:00Z";
  const parsed = validateDataset(raw);
  assert.deepEqual(parsed, raw);
  raw.field.values[0] = 100;
  raw.grid.cells[0].west = -20;
  assert.equal(parsed.field.values[0], -2);
  assert.equal(parsed.grid.cells[0].west, -10);
});

test("rejects malformed payloads, ambiguous IDs, invalid bounds and mismatched fields", () => {
  for (const raw of [null, [], {}, { grid: null }, { grid: { id: "g", cells: [] } }]) {
    assert.throws(() => validateDataset(raw));
  }
  for (const change of [
    (d) => d.grid.cells.push({ ...d.grid.cells[0] }),
    (d) => d.grid.cells[0].id = "",
    (d) => d.grid.cells[0].south = 91,
    (d) => d.grid.cells[0].west = Infinity,
    (d) => d.grid.cells[0].east = -20,
    (d) => { d.grid.cells[0].west = -180; d.grid.cells[0].east = 180; },
    (d) => d.field.gridId = "other",
    (d) => d.field.values = [],
    (d) => d.field.values = new Array(1),
    (d) => d.grid.cells = new Array(1),
    (d) => d.field.values = ["2"],
    (d) => d.field.name = "",
    (d) => d.field.units = "",
    (d) => d.field.colorScale = "mld",
    (d) => d.field.timestamp = "not a date",
    (d) => d.field.timestamp = "2026-02-30T00:00:00Z",
  ]) {
    const raw = dataset();
    change(raw);
    assert.throws(() => validateDataset(raw));
  }
});

test("nonfinite values become missing, zero stays physical zero; all-missing fields are valid", () => {
  for (const [value, expected] of [[null, null], [NaN, null], [Infinity, null], [-Infinity, null], [0, 0]]) {
    const raw = dataset();
    raw.field.values = [value];
    assert.deepEqual(validateDataset(raw).field.values, [expected]);
  }
});

test("new values and optional timestamps can reference the same fixed grid", () => {
  const parsed = validateDataset(dataset());
  const next = validateField({ ...parsed.field, values: [4], colorScale: "sequential" }, parsed.grid);
  assert.deepEqual(next.values, [4]);
  assert.deepEqual(parsed.field.values, [-2]);
  assert.throws(() => validateField({ ...next, gridId: "other" }, parsed.grid));
});
