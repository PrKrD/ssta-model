import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./load-module.mjs";

const { validateSequenceDataset, validateField, sequenceFrame } = await loadModule("../src/data/field.ts");
function fixture() {
  const cells = Array.from({length:4},(_,i)=>({id:String(i),west:i,east:i+1,south:20,north:21}));
  return {grid:{id:"sequence-grid",cells},sequence:{gridId:"sequence-grid",name:"Controlled field",units:"K",colorScale:"diverging",description:"Test fixture",timestamps:Array.from({length:4},(_,i)=>new Date(Date.UTC(2000,i,1)).toISOString()),frames:[[-1,0,1,null],[-2,.5,2,null],[-3,1,3,null],[-4,2,4,null]]}};
}
const { sortedSequenceValues, resolveScale, colorAt, normalize, defaultRange } = await loadModule("../src/globe/ColorScale.ts");

test("sequence validation rejects mismatched dimensions, metadata, grids and timestamps", () => {
  for (const mutate of [
    (d) => d.grid.cells = [],
    (d) => d.sequence.gridId = "other",
    (d) => d.sequence.frames = [],
    (d) => d.sequence.timestamps = [],
    (d) => d.sequence.timestamps.pop(),
    (d) => d.sequence.frames[1] = [1],
    (d) => d.sequence.frames[1] = new Array(4),
    (d) => d.sequence.timestamps[1] = d.sequence.timestamps[0],
    (d) => d.sequence.timestamps.reverse(),
    (d) => d.sequence.timestamps[0] = "2000-02-30T00:00:00Z",
    (d) => d.sequence.timestamps[0] = "2000-01-01",
    (d) => d.sequence.name = "",
    (d) => d.sequence.units = "",
    (d) => d.sequence.colorScale = "adaptive",
    (d) => d.sequence.frames[1][1] = "missing",
  ]) {
    const raw = fixture();
    mutate(raw);
    assert.throws(() => validateSequenceDataset(raw));
  }
  assert.throws(() => validateSequenceDataset(null));
});

test("validated frames own immutable values; nonfinite values become missing and zero survives", () => {
  const raw = fixture();
  raw.sequence.frames[0][1] = NaN;
  raw.sequence.frames[1][1] = Infinity;
  raw.sequence.frames[2][1] = -Infinity;
  raw.sequence.frames[3][1] = 0;
  const { grid, sequence } = validateSequenceDataset(raw);
  assert.deepEqual(sequence.frames.slice(0, 4).map((frame) => frame[1]), [null, null, null, 0]);
  raw.sequence.frames[3][1] = 9;
  assert.equal(sequence.frames[3][1], 0);
  assert.throws(() => { sequence.frames[3][1] = 100; }, TypeError);
  for (const index of [0, 1, 3]) {
    const field = sequenceFrame(sequence, index);
    assert.equal(field.timestamp, sequence.timestamps[index]);
    assert.strictEqual(field.values, sequence.frames[index]);
    assert.strictEqual(validateField(field, grid).values, field.values, "renderer validation reuses immutable frame arrays");
    assert.equal(field.units, sequence.units);
    assert.equal(field.gridId, grid.id);
  }
  for (const index of [-1, 4, 0.5, NaN]) assert.throws(() => sequenceFrame(sequence, index));
});

test("sequence-wide color population excludes missing values and fixes colors across time", () => {
  const { sequence } = validateSequenceDataset(fixture());
  const before = sequence.frames[0].slice();
  const population = sortedSequenceValues(sequence.frames);
  assert.equal(population.length, 12);
  assert.deepEqual(sortedSequenceValues([[null, NaN, 3], [Infinity, -2, -Infinity, 0]]), [-2, 0, 3]);
  const colorFixture = sortedSequenceValues([[0, 1, null], [10, -5, null]]);
  const global = resolveScale("diverging", colorFixture, { lower: 0, upper: 100 });
  assert.equal(global.minimum, -10, "later-frame extrema affect sequence-wide limits");
  assert.equal(global.maximum, 10);
  assert.equal(normalize(1, global), 0.55);
  for (const type of ["diverging", "sequential"]) {
    const scale = resolveScale(type, population, defaultRange());
    const color = colorAt(0.4, scale);
    for (let index = 0; index < 4; index++) {
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
