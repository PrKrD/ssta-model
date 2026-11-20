/** Bounds and centres use degrees north/east; cells cannot cross the antimeridian. */
export interface GridCell {
  id: string;
  west: number;
  east: number;
  south: number;
  north: number;
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
  values: (number | null)[];
}

export interface FieldDataset {
  grid: GridGeometry;
  field: NumericalField;
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
    return { id, west, east, south, north };
  });
  return { id, cells };
}

export function validateField(input: unknown, grid: GridGeometry): NumericalField {
  const raw = object(input, "field");
  if (raw.gridId !== grid.id) throw new Error("field.gridId does not match grid.id");
  if (!Array.isArray(raw.values) || raw.values.length !== grid.cells.length) {
    throw new Error("Field values must match grid.cells length and order");
  }
  if (raw.colorScale !== "sequential" && raw.colorScale !== "diverging") {
    throw new Error("colorScale must be sequential or diverging");
  }
  const values = Array.from(raw.values, (value) => {
    if (value === null) return null;
    if (typeof value !== "number") throw new Error("Values must be numbers or null");
    // Non-finite in-memory values are treated as unavailable, never as zero.
    return Number.isFinite(value) ? value : null;
  });
  const field: NumericalField = {
    gridId: grid.id,
    name: text(raw.name, "field.name"),
    units: text(raw.units, "field.units"),
    description: text(raw.description, "field.description"),
    colorScale: raw.colorScale,
    values,
  };
  if (raw.timestamp !== undefined) {
    const timestamp = text(raw.timestamp, "field.timestamp");
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(timestamp) ||
        !Number.isFinite(Date.parse(timestamp)) ||
        new Date(timestamp).toISOString().slice(0, 19) !== timestamp.slice(0, 19)) {
      throw new Error("timestamp must be a UTC ISO timestamp");
    }
    field.timestamp = timestamp;
  }
  return field;
}

/** A future file loader can feed parsed JSON here, independently of its producer. */
export function validateDataset(input: unknown): FieldDataset {
  const raw = object(input, "dataset");
  const grid = validateGrid(raw.grid);
  return { grid, field: validateField(raw.field, grid) };
}
