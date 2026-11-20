import "cesium/Build/Cesium/Widgets/widgets.css";
import "./style.css";
import { createDemoSequenceDataset } from "./data/demo";
import { sequenceFrame, validateSequenceDataset } from "./data/field";
import type { GridCell } from "./data/field";
import { sortedSequenceValues } from "./globe/ColorScale";
import { GridLayer } from "./globe/GridLayer";
import { GridPicking } from "./globe/GridPicking";
import { createViewer } from "./globe/Viewer";
import { LayerControls } from "./ui/LayerControls";
import { LayerLegend } from "./ui/LayerLegend";
import { Tooltip } from "./ui/Tooltip";
import { PlaybackController } from "./PlaybackController";
import { PlaybackControls } from "./ui/PlaybackControls";

function element(id: string): HTMLElement {
  const found = document.getElementById(id);
  if (!found) throw new Error(`Missing element: ${id}`);
  return found;
}

function bootstrap(): () => void {
  const { grid, sequence } = validateSequenceDataset(createDemoSequenceDataset());
  let field = sequenceFrame(sequence, 0);
  let index = 0;
  element("description").textContent = field.description;
  const viewer = createViewer("globe");
  const layer = new GridLayer(viewer, grid, field, sortedSequenceValues(sequence.frames));
  const tooltip = new Tooltip(element("tooltip"));
  let hovered: { cell: GridCell; x: number; y: number } | null = null;
  const refreshTooltip = () => {
    if (hovered) tooltip.show(hovered.cell, layer.getValue(hovered.cell), field, hovered.x, hovered.y);
    else tooltip.hide();
  };
  const legend = new LayerLegend(element("legend"));
  const controls = new LayerControls(element("controls"), field.colorScale, (type, range) => {
    layer.setColorScale(type, range);
    legend.show(field, layer.getColorScale());
    refreshTooltip();
  });
  const picking = new GridPicking(viewer, layer, (cell, x, y) => {
    hovered = cell ? { cell, x, y } : null;
    refreshTooltip();
  });
  const playback = new PlaybackController(sequence.frames.length, (state) => {
    if (index !== state.index) {
      index = state.index;
      field = sequenceFrame(sequence, index);
      layer.setField(field);
      legend.updateTimestamp(field.timestamp);
      refreshTooltip();
    }
    playbackControls.show(state, field.timestamp!);
  });
  const playbackControls = new PlaybackControls(element("playback"), sequence.frames.length, {
    toggle: () => playback.getState().playing ? playback.pause() : playback.play(),
    seek: (next) => playback.seek(next),
    step: (direction) => playback.step(direction),
    speed: (speed) => playback.setSpeed(speed),
  });
  playbackControls.show(playback.getState(), field.timestamp!);
  const visibility = () => playback.setHidden(document.hidden);
  document.addEventListener("visibilitychange", visibility);
  visibility();
  element("status").textContent = `${grid.cells.length} cells · ${sequence.frames.length} synthetic months · Fixed color limits`;
  return () => {
    document.removeEventListener("visibilitychange", visibility);
    playback.destroy();
    playbackControls.destroy();
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
