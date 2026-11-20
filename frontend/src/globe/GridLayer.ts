import {
  Cartesian2, Color, ColorGeometryInstanceAttribute, GeometryInstance,
  PerInstanceColorAppearance, Primitive, Rectangle, RectangleGeometry, Viewer,
} from "cesium";
import { validateField, validateGrid } from "../data/field";
import type { ColorScaleType, GridCell, GridGeometry, NumericalField } from "../data/field";
import { colorAt, defaultRange, resolveScale, sortedValues } from "./ColorScale";
import type { PercentileRange, ResolvedColorScale } from "./ColorScale";

/** One geometry build; field/percentile changes update per-instance colors only. */
export class GridLayer {
  private readonly grid: GridGeometry;
  private readonly primitive: Primitive;
  private readonly cellsById: Map<string, number>;
  private field: NumericalField;
  private population: readonly number[] = [];
  private scale: ResolvedColorScale | null = null;
  private removeReadyListener: (() => void) | undefined;
  private range = defaultRange();
  private scaleType: ColorScaleType;

  constructor(
    private viewer: Viewer, grid: GridGeometry, field: NumericalField,
    private readonly sequencePopulation?: readonly number[],
  ) {
    this.grid = validateGrid(grid);
    this.field = validateField(field, this.grid);
    this.scaleType = this.field.colorScale;
    this.cellsById = new Map(this.grid.cells.map((cell, index) => [cell.id, index]));
    this.resolve();
    this.primitive = viewer.scene.primitives.add(new Primitive({
      geometryInstances: this.grid.cells.map((cell, index) => new GeometryInstance({
        id: cell.id,
        geometry: new RectangleGeometry({
          rectangle: Rectangle.fromDegrees(cell.west, cell.south, cell.east, cell.north),
          height: 5,
          vertexFormat: PerInstanceColorAppearance.FLAT_VERTEX_FORMAT,
        }),
        attributes: { color: ColorGeometryInstanceAttribute.fromColor(this.cellColor(index)) },
      })),
      appearance: new PerInstanceColorAppearance({ translucent: false, flat: true }),
      asynchronous: true,
    }));
    this.removeReadyListener = viewer.scene.postRender.addEventListener(() => {
      if (!this.primitive.ready) return;
      this.removeReadyListener?.();
      this.removeReadyListener = undefined;
      this.updateColors();
    });
    viewer.scene.requestRender();
  }

  private resolve(): void {
    this.population = this.sequencePopulation ?? sortedValues(this.field.values);
    this.scale = resolveScale(this.scaleType, this.population, this.range);
  }

  /** Sequence playback retains its resolved scale and immutable frame arrays. */
  setField(field: NumericalField): void {
    const next = validateField(field, this.grid);
    this.field = next;
    if (!this.sequencePopulation) {
      this.scaleType = next.colorScale;
      this.resolve();
    }
    this.updateColors();
  }

  setColorScale(type: ColorScaleType, range: PercentileRange): void {
    const scale = resolveScale(type, this.population, range);
    this.scaleType = type;
    this.range = { ...range };
    this.scale = scale;
    this.updateColors();
  }

  getColorScale(): ResolvedColorScale | null { return this.scale; }
  getField(): NumericalField { return { ...this.field }; }

  getValue(cell: GridCell): number | null {
    const index = this.cellsById.get(cell.id);
    return index === undefined ? null : this.field.values[index];
  }

  pickCell(position: { x: number; y: number }): GridCell | null {
    const picked = this.viewer.scene.pick(new Cartesian2(position.x, position.y));
    if (!picked || picked.primitive !== this.primitive || typeof picked.id !== "string") return null;
    const index = this.cellsById.get(picked.id);
    return index === undefined ? null : { ...this.grid.cells[index] };
  }

  private cellColor(index: number): Color {
    const value = this.field.values[index];
    const rgb = value !== null && this.scale ? colorAt(value, this.scale) : null;
    return rgb ? Color.fromBytes(...rgb) : Color.fromCssColorString("#64748b");
  }

  private updateColors(): void {
    if (this.primitive.ready) {
      this.grid.cells.forEach((cell, index) => {
        const attributes = this.primitive.getGeometryInstanceAttributes(cell.id);
        attributes.color = ColorGeometryInstanceAttribute.toValue(this.cellColor(index), attributes.color);
      });
    }
    this.viewer.scene.requestRender();
  }

  destroy(): void {
    this.removeReadyListener?.();
    this.viewer.scene.primitives.remove(this.primitive);
  }
}
