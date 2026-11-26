import type { GridCell, NumericalField } from "../data/field";

export class Tooltip {
  constructor(private element: HTMLElement) {}

  show(cell: GridCell, value: number | null, field: NumericalField, x: number, y: number): void {
    const latitude = (cell.south + cell.north) / 2;
    const longitude = (cell.west + cell.east) / 2;
    this.element.textContent = [
      `Cell: ${cell.id}`,
      `Centre: ${latitude.toFixed(2)}° N, ${longitude.toFixed(2)}° E`,
      `Latitude bounds: ${cell.south}° to ${cell.north}°`,
      `Longitude bounds: ${cell.west}° to ${cell.east}°`,
      `${field.name}: ${value === null ? "Missing data" : `${value.toPrecision(5)} ${field.units}`}`,
      ...(cell.nativeCellCount !== undefined ? [`Spatial aggregate · ${cell.nativeCellCount} native H-grid cells in tile; only finite supported values contribute`] : []),
      ...(field.timeLabel ? [field.timeLabel] : []),
      ...(field.timestamp ? [`State timestamp: ${field.timestamp}`] : []),
    ].join("\n");
    this.element.hidden = false;
    const margin = 10;
    this.element.style.left = `${Math.max(margin, Math.min(x + 14, window.innerWidth - this.element.offsetWidth - margin))}px`;
    this.element.style.top = `${Math.max(margin, Math.min(y + 14, window.innerHeight - this.element.offsetHeight - margin))}px`;
  }

  hide(): void { this.element.hidden = true; }
}
