import "cesium/Build/Cesium/Widgets/widgets.css";
import "./style.css";
import { loadDataset } from "./data/load";
import { loadComparison } from "./data/comparison";
import type { ComparisonLayer } from "./data/comparison";
import { sequenceFrame } from "./data/field";
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

async function bootstrap(): Promise<() => void> {
  const requested = new URLSearchParams(window.location.search).get("dataset");
  const comparison = requested !== "demo" && requested !== "pilot" ? await loadComparison().catch(() => null) : null;
  const loaded = comparison ? null : await loadDataset(requested === "demo");
  const grid = comparison?.manifest.grid ?? loaded!.dataset.grid;
  const sequence = loaded?.dataset.sequence;
  const times = comparison?.manifest.timestamps ?? sequence!.timestamps;
  const labels = comparison?.manifest.frameLabels ?? sequence!.frameLabels;
  let selected: ComparisonLayer = "model";
  const getFrame = (i: number) => comparison ? comparison.frame(i, selected) : Promise.resolve(sequenceFrame(sequence!, i));
  const legacyPopulation = sequence ? sortedSequenceValues(sequence.frames) : [];
  const population = () => comparison ? comparison.population(selected) : legacyPopulation;
  let field = await getFrame(0);
  let index = 0;
  element("description").textContent = field.description;
  element("badge").textContent = comparison ? "RETROSPECTIVE ERA5 COMPARISON · 0.5°" : loaded!.source === "model" ? "MODELLED SST · HISTORICAL PILOT" : "SYNTHETIC DEMONSTRATION";
  element("dataset-name").textContent = field.name;
  document.title = comparison ? "SSTA Model · ERA5 comparison" : loaded!.source === "model" ? "SSTA Model · Historical SST pilot" : "SSTA Model · Synthetic demonstration";
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
  const notice = comparison ? "0.5° common-ocean spatial aggregates · fixed sampled colour percentiles" : `${requested !== "pilot" && requested !== "demo" ? "Comparison export unavailable · " : ""}${loaded!.notice}`;
  const status = () => { element("status").textContent = `${notice} · ${grid.cells.length} cells · ${times.length} months`; };
  let generation = 0;
  let displayedLayer: ComparisonLayer = selected;
  const showFrame = async () => {
    const ticket = ++generation;
    if (comparison) element("status").textContent = `Loading ${labels?.[index] ?? times[index]}…`;
    try {
      const next = await getFrame(index);
      if (ticket !== generation) return;
      field = next;
      const changedLayer = displayedLayer !== selected;
      if (changedLayer) layer.setPopulation(population());
      layer.setField(field);
      element("dataset-name").textContent = field.name;
      if (changedLayer) legend.show(field, layer.getColorScale());
      else legend.updateTimestamp(field.timestamp, field.timeLabel);
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
    playbackControls.show(state, times[index], labels?.[index]);
  });
  const playbackControls = new PlaybackControls(element("playback"), times.length, {
    toggle: () => playback.getState().playing ? playback.pause() : playback.play(),
    seek: (next) => playback.seek(next),
    step: (direction) => playback.step(direction),
    speed: (speed) => playback.setSpeed(speed),
  });
  playbackControls.show(playback.getState(), field.timestamp!, field.timeLabel);
  const selector = element("comparison-layer") as HTMLSelectElement;
  element("comparison-control").hidden = !comparison;
  const changeLayer = () => { selected = selector.value as ComparisonLayer; void showFrame(); };
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
  element("status").textContent = "Unable to start the globe. Check WebGL support and the browser console.";
});
