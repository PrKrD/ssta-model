import { ScreenSpaceEventHandler, ScreenSpaceEventType, Viewer } from "cesium";
import type { GridCell } from "../data/field";
import type { GridLayer } from "./GridLayer";

export class GridPicking {
  private handler: ScreenSpaceEventHandler;
  private leave: () => void;

  constructor(
    private viewer: Viewer,
    layer: GridLayer,
    onHover: (cell: GridCell | null, x: number, y: number) => void,
  ) {
    this.handler = new ScreenSpaceEventHandler(viewer.canvas);
    this.handler.setInputAction((movement: { endPosition: { x: number; y: number } }) => {
      const { left, top } = viewer.canvas.getBoundingClientRect();
      const { x, y } = movement.endPosition;
      onHover(layer.pickCell(movement.endPosition), x + left, y + top);
    }, ScreenSpaceEventType.MOUSE_MOVE);
    this.handler.setInputAction((movement: { position: { x: number; y: number } }) => {
      const { left, top } = viewer.canvas.getBoundingClientRect();
      const { x, y } = movement.position;
      onHover(layer.pickCell(movement.position), x + left, y + top);
    }, ScreenSpaceEventType.LEFT_CLICK);
    this.leave = () => onHover(null, 0, 0);
    viewer.canvas.addEventListener("mouseleave", this.leave);
  }

  destroy(): void {
    this.viewer.canvas.removeEventListener("mouseleave", this.leave);
    this.handler.destroy();
  }
}
