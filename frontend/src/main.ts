import "cesium/Build/Cesium/Widgets/widgets.css";
import "./style.css";
import { loadComparison } from "./data/comparison";
import type { ComparisonLayer } from "./data/comparison";
import type { GridCell } from "./data/field";
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

async function bootstrap(): Promise<() => void> {
  const comparison = await loadComparison();
  const grid = comparison.manifest.grid;
  const times = comparison.manifest.timestamps;
  const labels = comparison.manifest.frameLabels;
  let selected: ComparisonLayer = "with_diffusion";
  const getFrame = (i: number) => comparison.frame(i, selected);
  const population = () => comparison.population(selected);
  let field = await getFrame(0);
  let index = 0;
  element("description").textContent = field.description;
  element("badge").textContent = "HISTORICAL DIFFUSION COMPARISON · 0.5°";
  element("dataset-name").textContent = field.name;
  document.title = "SSTA Model · Diffusion comparison";
  const viewer = createViewer("globe");
  const layer = new GridLayer(viewer, grid, field, population());
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
  const status = () => {
    element("status").textContent = selected === "depth"
      ? `H is fixed · playback paused · selected month ${comparison.manifest.months[index]} preserved`
      : `0.5° common-ocean spatial aggregates · ${grid.cells.length} cells · ${times.length} months · fixed colour limits`;
  };
  let generation = 0;
  let displayedLayer: ComparisonLayer = selected;
  const showFrame = async () => {
    const ticket = ++generation;
    element("status").textContent = `Loading ${labels[index]}…`;
    try {
      const next = await getFrame(index);
      if (ticket !== generation) return;
      field = next;
      const changedLayer = displayedLayer !== selected;
      if (changedLayer) layer.setPopulation(population());
      layer.setField(field);
      element("dataset-name").textContent = field.name;
      if (changedLayer) controls.setType(field.colorScale, selected === "depth");
      else legend.updateTimestamp(field.timestamp, field.timeLabel);
      element("description").textContent = field.description;
      displayedLayer = selected;
      refreshTooltip();
      status();
    } catch (error) {
      if (ticket !== generation) return;
      playback.pause();
      element("status").textContent = `Unable to load comparison month: ${String(error)}`;
    }
  };
  const playback = new PlaybackController(times.length, (state) => {
    if (index !== state.index) {
      index = state.index;
      void showFrame();
    }
    playbackControls.show(state, times[index], labels[index]);
  });
  const playbackControls = new PlaybackControls(element("playback"), times.length, {
    toggle: () => {
      if (selected !== "depth") playback.getState().playing ? playback.pause() : playback.play();
    },
    seek: (next) => { if (selected !== "depth") playback.seek(next); },
    step: (direction) => { if (selected !== "depth") playback.step(direction); },
    speed: (speed) => { if (selected !== "depth") playback.setSpeed(speed); },
  });
  playbackControls.show(playback.getState(), field.timestamp!, field.timeLabel);
  const selector = element("comparison-layer") as HTMLSelectElement;
  element("comparison-control").hidden = false;
  const changeLayer = () => {
    selected = selector.value as ComparisonLayer;
    if (selected === "depth") playback.pause();
    playbackControls.setDisabled(selected === "depth", playback.getState());
    void showFrame();
  };
  selector.addEventListener("change", changeLayer);
  const visibility = () => playback.setHidden(document.hidden);
  document.addEventListener("visibilitychange", visibility);
  visibility();
  status();
  return () => {
    generation++;
    selector.removeEventListener("change", changeLayer);
    document.removeEventListener("visibilitychange", visibility);
    playback.destroy();
    playbackControls.destroy();
    controls.destroy();
    picking.destroy();
    layer.destroy();
    viewer.destroy();
  };
}

bootstrap().then((dispose) => {
  window.addEventListener("pagehide", dispose, { once: true });
  if (import.meta.hot) import.meta.hot.dispose(() => {
    window.removeEventListener("pagehide", dispose);
    dispose();
  });
}).catch((error) => {
  console.error(error);
  element("status").textContent = `Unable to load the historical comparison: ${String(error)}. Generate assets with python experiments/compare_diffusion.py --stage export.`;
});
