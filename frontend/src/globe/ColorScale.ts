import type { ColorScaleType } from "../data/field";

export type PercentileRange = { lower: number; upper: number };
export type ResolvedColorScale = PercentileRange & {
  type: ColorScaleType;
  minimum: number;
  maximum: number;
};
export type RGB = readonly [number, number, number];
export const defaultRange = (): PercentileRange => ({ lower: 2, upper: 98 });
const palettes: Record<ColorScaleType, readonly [RGB, RGB, RGB]> = {
  sequential: [[68, 1, 84], [33, 145, 140], [253, 231, 37]],
  diverging: [[33, 102, 172], [247, 247, 247], [178, 24, 43]],
};
const clamp = (value: number, lower: number, upper: number) => Math.max(lower, Math.min(value, upper));

export function sortedValues(values: readonly (number | null)[]): number[] {
  return values.filter((value): value is number => value !== null && Number.isFinite(value))
    .sort((a, b) => a - b);
}

/** Linear interpolation of ranks in an ascending finite population. */
export function quantile(sorted: readonly number[], percentile: number): number | undefined {
  if (!Number.isFinite(percentile) || percentile < 0 || percentile > 100) {
    throw new Error("Percentile must be between 0 and 100");
  }
  if (!sorted.length) return undefined;
  const index = (sorted.length - 1) * percentile / 100;
  const lower = Math.floor(index);
  return sorted[lower] * (1 - index + lower) + sorted[Math.ceil(index)] * (index - lower);
}

export function resolveScale(
  type: ColorScaleType, sorted: readonly number[], range: PercentileRange,
): ResolvedColorScale | null {
  if (range.lower >= range.upper) throw new Error("Lower percentile must be below upper");
  let minimum = quantile(sorted, range.lower);
  let maximum = quantile(sorted, range.upper);
  if (minimum === undefined || maximum === undefined) return null;
  if (type === "diverging") {
    const extent = Math.max(Math.abs(minimum), Math.abs(maximum));
    minimum = extent === 0 ? 0 : -extent;
    maximum = extent;
  }
  return { type, ...range, minimum, maximum };
}

/** Diverging limits are symmetric about physical zero; sequential is square-root. */
export function normalize(value: number, scale: ResolvedColorScale): number | null {
  if (!Number.isFinite(value)) return null;
  if (scale.minimum === scale.maximum) return 0.5;
  const fraction = clamp((value - scale.minimum) / (scale.maximum - scale.minimum), 0, 1);
  return scale.type === "diverging" ? fraction : Math.sqrt(fraction);
}

export function colorAt(value: number, scale: ResolvedColorScale): RGB | null {
  const t = normalize(value, scale);
  if (t === null) return null;
  const palette = palettes[scale.type];
  const [a, b, fraction] = t < 0.5
    ? [palette[0], palette[1], t * 2] as const
    : [palette[1], palette[2], (t - 0.5) * 2] as const;
  const channel = (i: number) => Math.round(a[i] + (b[i] - a[i]) * fraction);
  return [channel(0), channel(1), channel(2)];
}

export function legendStops(scale: ResolvedColorScale): string {
  // Sample the same transfer function as cells along a bar linear in values.
  return Array.from({ length: 101 }, (_, i) => {
    const color = colorAt(scale.minimum + (scale.maximum - scale.minimum) * i / 100, scale)!;
    return `rgb(${color.join(",")}) ${i}%`;
  }).join(", ");
}
