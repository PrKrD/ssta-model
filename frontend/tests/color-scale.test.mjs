import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./load-module.mjs";

const { quantile, sortedValues, resolveScale, normalize, colorAt, legendStops, defaultRange } =
  await loadModule("../src/globe/ColorScale.ts");
const range = { lower: 0, upper: 100 };
const scale = (type, values) => resolveScale(type, sortedValues(values), range);

test("quantiles interpolate ranks, include extrema and handle empty/single populations", () => {
  assert.ok(Math.abs(quantile([0, 10, 20, 30], 40) - 12) < 1e-12);
  assert.equal(quantile([-10, 5, 90], 0), -10);
  assert.equal(quantile([-10, 5, 90], 100), 90);
  assert.equal(quantile([4], 98), 4);
  assert.equal(quantile([], 50), undefined);
  assert.throws(() => quantile([1], NaN));
  assert.throws(() => quantile([1], 101));
});

test("populations exclude missing/nonfinite values, retaining zero and negative values", () => {
  const values = [2, null, NaN, -1, Infinity, -Infinity, 0];
  assert.deepEqual(sortedValues(values), [-1, 0, 2]);
  assert.equal(values[0], 2, "sorting does not mutate the physical values");
  assert.equal(scale("sequential", [null, NaN]), null);
  assert.equal(scale("diverging", []), null);
});

test("default ranges are independent; invalid percentile intervals fail", () => {
  const first = defaultRange();
  first.lower = 40;
  assert.deepEqual(defaultRange(), { lower: 2, upper: 98 });
  assert.throws(() => resolveScale("sequential", [1, 2], { lower: 90, upper: 10 }));
  assert.throws(() => resolveScale("sequential", [1, 2], { lower: -1, upper: 100 }));
  assert.equal(resolveScale("sequential", [0, 100], { lower: 40, upper: 60 }).minimum, 40);
});

test("sequential square-root normalization clips and supports unsigned or signed values", () => {
  const s = scale("sequential", [40, 60]);
  assert.equal(normalize(0, s), 0);
  assert.equal(normalize(45, s), 0.5);
  assert.equal(normalize(100, s), 1);
  assert.deepEqual(colorAt(-20, s), colorAt(40, s));
  assert.deepEqual(colorAt(120, s), colorAt(60, s));
  assert.equal(normalize(-1, scale("sequential", [-2, 2])), 0.5);
});

test("asymmetric signed data uses symmetric limits and physical zero at the midpoint", () => {
  const s = scale("diverging", [-2, 8]);
  assert.equal(s.minimum, -8);
  assert.equal(s.maximum, 8);
  assert.equal(normalize(-8, s), 0);
  assert.equal(normalize(-4, s), 0.25);
  assert.equal(normalize(0, s), 0.5);
  assert.equal(normalize(4, s), 0.75);
  assert.equal(normalize(8, s), 1);
  assert.deepEqual(colorAt(0, s), [247, 247, 247]);
  assert.match(legendStops(s), /rgb\(247,247,247\) 50%/);
  assert.deepEqual(colorAt(-20, s), colorAt(-8, s));
  assert.deepEqual(colorAt(20, s), colorAt(8, s));
});

test("one-sign diverging fields use the corresponding side and preserve zero", () => {
  for (const values of [[2, 8], [-8, -2]]) {
    const s = scale("diverging", values);
    assert.equal(normalize(0, s), 0.5);
    assert.equal(normalize(2, s), 0.625);
    assert.equal(normalize(-2, s), 0.375);
  }
});

test("constant, zero and nonfinite cases produce finite colors or explicit missing values", () => {
  for (const type of ["sequential", "diverging"]) {
    for (const value of [-3, 0, 3]) {
      const s = scale(type, [value, value]);
      assert.ok(Number.isFinite(normalize(value, s)));
      assert.ok(colorAt(value, s).every(Number.isFinite));
      assert.ok(!/NaN|Infinity/.test(legendStops(s)));
      assert.equal(normalize(NaN, s), null);
      assert.equal(colorAt(Infinity, s), null);
    }
  }
  assert.equal(normalize(0, scale("diverging", [0, 0])), 0.5);
});
