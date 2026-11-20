/** Bounds and centres use degrees north/east; cells cannot cross the antimeridian. */
export interface GridCell {
  id: string;
  west: number;
  east: number;
  south: number;
  north: number;
  /** Active native model cells assigned to an aggregated display tile. */
  nativeCellCount?: number;
}

export interface GridGeometry {
  id: string;
  cells: GridCell[];
}

export type ColorScaleType = "sequential" | "diverging";

/** Values follow grid.cells order. null means unavailable, with no implied land mask. */
export interface NumericalField {
  gridId: string;
  name: string;
  units: string;
  colorScale: ColorScaleType;
  description: string;
  timestamp?: string;
  timeLabel?: string;
  values: readonly (number | null)[];
}

export interface FieldDataset {
  grid: GridGeometry;
  field: NumericalField;
}

/** One fixed cell ordering and common metadata for every timestamp. */
export interface FieldSequence extends Omit<NumericalField, "timestamp" | "values"> {
  timestamps: readonly string[];
  frames: readonly (readonly (number | null)[])[];
  frameLabels?: readonly string[];
}

export interface SequenceDataset {
  grid: GridGeometry;
  sequence: FieldSequence;
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function coordinate(value: unknown, limit: number, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || Math.abs(value) > limit) {
    throw new Error(`${label} must be finite and within ±${limit} degrees`);
  }
  return value;
}

function timestamp(value: unknown): string {
  const result = text(value, "timestamp");
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(result) ||
      !Number.isFinite(Date.parse(result)) ||
      new Date(result).toISOString().slice(0, 19) !== result.slice(0, 19)) {
    throw new Error("timestamp must be a UTC ISO timestamp");
  }
  return result;
}

/** Freeze owned values once; validated sequence frames can then be reused. */
function fieldValues(input: unknown, cellCount: number): readonly (number | null)[] {
  if (!Array.isArray(input) || input.length !== cellCount) {
    throw new Error("Field values must match grid.cells length and order");
  }
  let hasNonfinite = false;
  for (const value of input) {
    if (value === null) continue;
    if (typeof value !== "number") throw new Error("Values must be numbers or null");
    if (!Number.isFinite(value)) hasNonfinite = true;
  }
  if (Object.isFrozen(input) && !hasNonfinite) return input;
  return Object.freeze(Array.from(input, (value) => Number.isFinite(value) ? value : null));
}

/** Validate at entry, copying inputs so raw payloads cannot mutate the viewer. */
export function validateGrid(input: unknown): GridGeometry {
  const raw = object(input, "grid");
  const id = text(raw.id, "grid.id");
  if (!Array.isArray(raw.cells) || raw.cells.length === 0) {
    throw new Error("grid.cells must be a non-empty array");
  }
  const ids = new Set<string>();
  const cells = Array.from(raw.cells, (inputCell) => {
    const cell = object(inputCell, "cell");
    const id = text(cell.id, "cell.id");
    if (ids.has(id)) throw new Error(`Duplicate cell id: ${id}`);
    ids.add(id);
    const west = coordinate(cell.west, 180, "west");
    const east = coordinate(cell.east, 180, "east");
    const south = coordinate(cell.south, 90, "south");
    const north = coordinate(cell.north, 90, "north");
    if (west >= east || east - west > 180 || south >= north) {
      throw new Error("Cells need ordered bounds; split antimeridian or >180° cells");
    }
    if (cell.nativeCellCount !== undefined &&
        (typeof cell.nativeCellCount !== "number" || !Number.isInteger(cell.nativeCellCount) || cell.nativeCellCount < 1)) {
      throw new Error("nativeCellCount must be a positive integer");
    }
    return { id, west, east, south, north,
      ...(cell.nativeCellCount !== undefined ? { nativeCellCount: cell.nativeCellCount as number } : {}) };
  });
  return { id, cells };
}

export function validateField(input: unknown, grid: GridGeometry): NumericalField {
  const raw = object(input, "field");
  if (raw.gridId !== grid.id) throw new Error("field.gridId does not match grid.id");
  if (raw.colorScale !== "sequential" && raw.colorScale !== "diverging") {
    throw new Error("colorScale must be sequential or diverging");
  }
  const values = fieldValues(raw.values, grid.cells.length);
  const field: NumericalField = {
    gridId: grid.id,
    name: text(raw.name, "field.name"),
    units: text(raw.units, "field.units"),
    description: text(raw.description, "field.description"),
    colorScale: raw.colorScale,
    values,
  };
  if (raw.timestamp !== undefined) {
    field.timestamp = timestamp(raw.timestamp);
  }
  if (raw.timeLabel !== undefined) field.timeLabel = text(raw.timeLabel, "timeLabel");
  return field;
}

/** A future file loader can feed parsed JSON here, independently of its producer. */
export function validateDataset(input: unknown): FieldDataset {
  const raw = object(input, "dataset");
  const grid = validateGrid(raw.grid);
  return { grid, field: validateField(raw.field, grid) };
}

export function validateSequence(input: unknown, grid: GridGeometry): FieldSequence {
  const raw = object(input, "sequence");
  if (!Array.isArray(raw.timestamps) || !raw.timestamps.length ||
      !Array.isArray(raw.frames) || raw.frames.length !== raw.timestamps.length) {
    throw new Error("Sequence needs one frame per timestamp and at least one frame");
  }
  const timestamps = Array.from(raw.timestamps, timestamp);
  for (let i = 1; i < timestamps.length; i++) {
    if (Date.parse(timestamps[i]) <= Date.parse(timestamps[i - 1])) {
      throw new Error("Sequence timestamps must be strictly increasing");
    }
  }
  // Validate common metadata once, then validate every frame against this grid.
  const { values, timestamp: _timestamp, ...metadata } = validateField({
    gridId: raw.gridId, name: raw.name, units: raw.units,
    description: raw.description, colorScale: raw.colorScale, values: raw.frames[0],
  }, grid);
  const frames = Array.from(raw.frames, (frame, index) =>
    index === 0 ? values : fieldValues(frame, grid.cells.length));
  let frameLabels: readonly string[] | undefined;
  if (raw.frameLabels !== undefined) {
    if (!Array.isArray(raw.frameLabels) || raw.frameLabels.length !== frames.length) {
      throw new Error("Sequence needs one label per frame");
    }
    frameLabels = Object.freeze(Array.from(raw.frameLabels, (label) => text(label, "frame label")));
  }
  return Object.freeze({ ...metadata, timestamps: Object.freeze(timestamps), frames: Object.freeze(frames),
    ...(frameLabels ? { frameLabels } : {}) });
}

export function validateSequenceDataset(input: unknown): SequenceDataset {
  const raw = object(input, "dataset");
  const grid = validateGrid(raw.grid);
  return { grid, sequence: validateSequence(raw.sequence, grid) };
}

/** Small metadata wrapper; the immutable frame values are not copied. */
export function sequenceFrame(sequence: FieldSequence, index: number): NumericalField {
  if (!Number.isInteger(index) || index < 0 || index >= sequence.frames.length) {
    throw new Error("Frame index out of range");
  }
  const { timestamps, frames, frameLabels, ...metadata } = sequence;
  return { ...metadata, timestamp: timestamps[index], values: frames[index],
    ...(frameLabels ? { timeLabel: frameLabels[index] } : {}) };
}
