import type { FieldDataset, GridCell, SequenceDataset } from "./field";

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

/** Arbitrary travelling waves: illustrative K, with no physical model implied. */
export function createDemoSequenceDataset(): SequenceDataset {
  const { grid } = createDemoDataset();
  const timestamps: string[] = [];
  const frames: (number | null)[][] = [];
  for (let month = 0; month < 120; month++) {
    timestamps.push(new Date(Date.UTC(2000, month, 1)).toISOString());
    const phase = 2 * Math.PI * month / 60;
    frames.push(grid.cells.map((cell, index) => {
      if (index % 29 === 0) return null;
      const latitude = (cell.south + cell.north) / 2 * Math.PI / 180;
      const longitude = (cell.west + cell.east) / 2 * Math.PI / 180;
      return Math.sin(latitude) * Math.cos(2 * longitude - phase)
        + 0.35 * Math.cos(latitude) * Math.sin(longitude + 2 * phase);
    }));
  }
  return {
    grid,
    sequence: {
      gridId: grid.id,
      name: "Synthetic anomaly demonstration",
      units: "K",
      colorScale: "diverging",
      description: "Arbitrary synthetic temperature anomalies — not observations or scientifically simulated SST. Gray cells are missing values, not a land mask.",
      timestamps,
      frames,
    },
  };
}
