import type { FieldDataset, GridCell } from "./field";

/** Arbitrary dimensionless wave, solely for demonstrating rendering and gaps. */
export function createDemoDataset(): FieldDataset {
  const cells: GridCell[] = [];
  const values: (number | null)[] = [];
  for (let south = -90; south < 90; south += 15) {
    for (let west = -180; west < 180; west += 15) {
      const index = cells.length;
      cells.push({ id: `cell-${index}`, west, east: west + 15, south, north: south + 15 });
      const latitude = (south + 7.5) * Math.PI / 180;
      const longitude = (west + 7.5) * Math.PI / 180;
      values.push(index % 29 === 0 ? null : Math.sin(latitude) * Math.cos(2 * longitude));
    }
  }
  return {
    grid: { id: "synthetic-15-degree-grid", cells },
    field: {
      gridId: "synthetic-15-degree-grid",
      name: "Synthetic demonstration wave",
      units: "1",
      colorScale: "diverging",
      description: "Synthetic dimensionless data — not observational SST or model output. Gray cells are missing values, not a land mask.",
      values,
    },
  };
}
