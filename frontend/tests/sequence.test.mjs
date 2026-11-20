import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./load-module.mjs";

const { validateSequenceDataset, validateField, sequenceFrame } = await loadModule("../src/data/field.ts");
const { createDemoSequenceDataset } = await loadModule("../src/data/demo.ts");
const { sortedSequenceValues, resolveScale, colorAt, normalize, defaultRange } = await loadModule("../src/globe/ColorScale.ts");

test("synthetic sequence is deterministic: 120 monthly timestamps, 288 cells, one shared grid", () => {
  const first = validateSequenceDataset(createDemoSequenceDataset());
  assert.deepEqual(first, validateSequenceDataset(createDemoSequenceDataset()));
  const { grid, sequence } = first;
  assert.equal(grid.cells.length, 288);
  assert.equal(sequence.frames.length, 120);
  assert.equal(sequence.timestamps[0], "2000-01-01T00:00:00.000Z");
  assert.equal(sequence.timestamps.at(-1), "2009-12-01T00:00:00.000Z");
  assert.equal(sequence.units, "K");
  assert.match(sequence.description, /not observations or scientifically simulated SST/);
  sequence.timestamps.forEach((timestamp, i) => {
    assert.equal(timestamp, new Date(Date.UTC(2000, i, 1)).toISOString());
    assert.equal(sequence.frames[i].length, grid.cells.length);
    assert.ok(sequence.frames[i].some((v) => v !== null && v < 0));
    assert.ok(sequence.frames[i].some((v) => v !== null && v > 0));
    assert.equal(sequence.gridId, grid.id);
  });
});

test("wave travels spatially, is continuous across the loop and preserves explicit missing cells", () => {
  const { grid, sequence } = validateSequenceDataset(createDemoSequenceDataset());
  for (const i of [0, 1, 29, 101, 287]) {
    const cell = grid.cells[i];
    const lat = (cell.south + cell.north) / 2 * Math.PI / 180;
    const lon = (cell.west + cell.east) / 2 * Math.PI / 180;
    for (const month of [0, 1, 30, 119]) {
      const actual = sequence.frames[month][i];
      if (i % 29 === 0) assert.equal(actual, null);
      else {
        const phase = 2 * Math.PI * month / 60;
        const expected = Math.sin(lat) * Math.cos(2 * lon - phase) + 0.35 * Math.cos(lat) * Math.sin(lon + 2 * phase);
        assert.ok(Math.abs(actual - expected) < 1e-12);
      }
    }
  }
  // A travelling pattern changes sign at some locations, not just amplitude.
  assert.ok(sequence.frames[0].some((v, i) => v !== null && v * sequence.frames[30][i] < 0));
  const maxChange = (a, b) => Math.max(...a.map((v, i) => v === null ? 0 : Math.abs(v - b[i])));
  assert.ok(maxChange(sequence.frames[0], sequence.frames[1]) > 0);
  assert.ok(maxChange(sequence.frames[0], sequence.frames[1]) < 0.2);
  assert.ok(maxChange(sequence.frames[119], sequence.frames[0]) < 0.2);
});

test("sequence validation rejects mismatched dimensions, metadata, grids and timestamps", () => {
  for (const mutate of [
    (d) => d.grid.cells = [],
    (d) => d.sequence.gridId = "other",
    (d) => d.sequence.frames = [],
    (d) => d.sequence.timestamps = [],
    (d) => d.sequence.timestamps.pop(),
    (d) => d.sequence.frames[1] = [1],
    (d) => d.sequence.frames[1] = new Array(288),
    (d) => d.sequence.timestamps[1] = d.sequence.timestamps[0],
    (d) => d.sequence.timestamps.reverse(),
    (d) => d.sequence.timestamps[0] = "2000-02-30T00:00:00Z",
    (d) => d.sequence.timestamps[0] = "2000-01-01",
    (d) => d.sequence.name = "",
    (d) => d.sequence.units = "",
    (d) => d.sequence.colorScale = "adaptive",
    (d) => d.sequence.frames[1][1] = "missing",
  ]) {
    const raw = createDemoSequenceDataset();
    mutate(raw);
    assert.throws(() => validateSequenceDataset(raw));
  }
  assert.throws(() => validateSequenceDataset(null));
});

test("validated frames own immutable values; nonfinite values become missing and zero survives", () => {
  const raw = createDemoSequenceDataset();
  raw.sequence.frames[0][1] = NaN;
  raw.sequence.frames[1][1] = Infinity;
  raw.sequence.frames[2][1] = -Infinity;
  raw.sequence.frames[3][1] = 0;
  const { grid, sequence } = validateSequenceDataset(raw);
  assert.deepEqual(sequence.frames.slice(0, 4).map((frame) => frame[1]), [null, null, null, 0]);
  raw.sequence.frames[3][1] = 9;
  assert.equal(sequence.frames[3][1], 0);
  assert.throws(() => { sequence.frames[3][1] = 100; }, TypeError);
  for (const index of [0, 10, 119]) {
    const field = sequenceFrame(sequence, index);
    assert.equal(field.timestamp, sequence.timestamps[index]);
    assert.strictEqual(field.values, sequence.frames[index]);
    assert.strictEqual(validateField(field, grid).values, field.values, "renderer validation reuses immutable frame arrays");
    assert.equal(field.units, sequence.units);
    assert.equal(field.gridId, grid.id);
  }
  for (const index of [-1, 120, 0.5, NaN]) assert.throws(() => sequenceFrame(sequence, index));
});

test("sequence-wide color population excludes missing values and fixes colors across time", () => {
  const { sequence } = validateSequenceDataset(createDemoSequenceDataset());
  const before = sequence.frames[0].slice();
  const population = sortedSequenceValues(sequence.frames);
  assert.equal(population.length, 120 * (288 - 10));
  assert.deepEqual(sortedSequenceValues([[null, NaN, 3], [Infinity, -2, -Infinity, 0]]), [-2, 0, 3]);
  const fixture = sortedSequenceValues([[0, 1, null], [10, -5, null]]);
  const global = resolveScale("diverging", fixture, { lower: 0, upper: 100 });
  assert.equal(global.minimum, -10, "later-frame extrema affect sequence-wide limits");
  assert.equal(global.maximum, 10);
  assert.equal(normalize(1, global), 0.55);
  for (const type of ["diverging", "sequential"]) {
    const scale = resolveScale(type, population, defaultRange());
    const color = colorAt(0.4, scale);
    for (let index = 0; index < 120; index++) {
      sequenceFrame(sequence, index);
      assert.deepEqual(colorAt(0.4, scale), color);
    }
    if (type === "diverging") {
      assert.equal(scale.minimum, -scale.maximum);
      assert.equal(normalize(0, scale), 0.5);
    }
    const changed = resolveScale(type, population, { lower: 20, upper: 80 });
    assert.notEqual(changed.maximum, scale.maximum);
    assert.deepEqual(resolveScale(type, population, defaultRange()), scale);
  }
  assert.deepEqual(sequence.frames[0], before, "display operations cannot mutate physical values");
  assert.equal(resolveScale("diverging", sortedSequenceValues([[null], [NaN]]), defaultRange()), null);
});
