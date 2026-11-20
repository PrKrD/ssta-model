import "cesium/Build/Cesium/Widgets/widgets.css";
import "./style.css";
import { createDemoDataset } from "./data/demo";
import { validateDataset } from "./data/field";
import { GridLayer } from "./globe/GridLayer";
import { GridPicking } from "./globe/GridPicking";
import { createViewer } from "./globe/Viewer";
import { LayerControls } from "./ui/LayerControls";
import { LayerLegend } from "./ui/LayerLegend";
import { Tooltip } from "./ui/Tooltip";

function element(id: string): HTMLElement {
  const found = document.getElementById(id);
  if (!found) throw new Error(`Missing element: ${id}`);
  return found;
}

function bootstrap(): () => void {
  const { grid, field } = validateDataset(createDemoDataset());
  element("description").textContent = field.description;
  const viewer = createViewer("globe");
  const layer = new GridLayer(viewer, grid, field);
  const tooltip = new Tooltip(element("tooltip"));
  const legend = new LayerLegend(element("legend"));
  const controls = new LayerControls(element("controls"), field.colorScale, (type, range) => {
    layer.setColorScale(type, range);
    legend.show(layer.getField(), layer.getColorScale());
    tooltip.hide();
  });
  const picking = new GridPicking(viewer, layer, (cell, x, y) => {
    if (cell) tooltip.show(cell, layer.getValue(cell), layer.getField(), x, y);
    else tooltip.hide();
  });
  element("status").textContent = `${grid.cells.length} cells · 15° grid · Static demonstration`;
  return () => {
    controls.destroy();
    picking.destroy();
    layer.destroy();
    viewer.destroy();
  };
}

try {
  const dispose = bootstrap();
  window.addEventListener("pagehide", dispose, { once: true });
  if (import.meta.hot) import.meta.hot.dispose(() => {
    window.removeEventListener("pagehide", dispose);
    dispose();
  });
} catch (error) {
  console.error(error);
  element("status").textContent = "Unable to start the globe. Check WebGL support and the browser console.";
}
