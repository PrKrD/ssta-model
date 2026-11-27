import "cesium/Build/Cesium/Widgets/widgets.css";
import "./style.css";
import { loadComparison, isDepthLayer } from "./data/comparison";
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
import { DampingControls } from "./ui/DampingControls";
import type { InteractiveData } from "./data/interactive";

function element(id: string): HTMLElement {
  const found = document.getElementById(id);
  if (!found) throw new Error(`Missing element: ${id}`);
  return found;
}

async function bootstrap(): Promise<() => void> {
  const comparison = await loadComparison();
  const grid = comparison.manifest.grid;
  let interactive: InteractiveData | null = null;
  let selected: ComparisonLayer | "interactive" = "bilinear";
  const times = () => selected === "interactive" ? interactive!.manifest.timestamps : comparison.manifest.timestamps;
  const labels = () => selected === "interactive" ? interactive!.manifest.frameLabels : comparison.manifest.frameLabels;
  const isStatic = () => selected !== "interactive" && isDepthLayer(selected);
  const getFrame = (i: number) => selected === "interactive" ? interactive!.frame(i) : comparison.frame(i, selected);
  // Retain the historical SSTA limits so damping runs remain visually comparable.
  const population = () => comparison.population(selected === "interactive" ? "bilinear" : selected);
  let field = await getFrame(0);
  let index = 0;
  element("description").textContent = field.description;
  element("badge").textContent = "CONTROLLED H SENSITIVITY · 0.5°";
  element("dataset-name").textContent = field.name;
  document.title = "SSTA Model · H sensitivity";
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
    element("status").textContent = isStatic()
      ? `H is fixed · playback paused · selected month ${comparison.manifest.months[index]} preserved`
      : `0.5° common-ocean spatial aggregates · ${grid.cells.length} cells · ${times().length} months · fixed colour limits`;
  };
  let generation = 0;
  let displayedLayer: ComparisonLayer | "interactive" = selected;
  const showFrame = async () => {
    const ticket = ++generation;
    element("status").textContent = `Loading ${labels()[index]}…`;
    try {
      const next = await getFrame(index);
      if (ticket !== generation) return;
      field = next;
      const changedLayer = displayedLayer !== selected;
      if (changedLayer) layer.setPopulation(population());
      layer.setField(field);
      element("dataset-name").textContent = field.name;
      element("badge").textContent = selected === "interactive" ? "INTERACTIVE DAMPING · 0.5°" : "CONTROLLED H SENSITIVITY · 0.5°";
      document.title = selected === "interactive" ? "SSTA Model · Interactive damping" : "SSTA Model · H sensitivity";
      if (changedLayer) controls.setType(field.colorScale, isStatic());
      else legend.show(field, layer.getColorScale());
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
  let playback: PlaybackController;
  let playbackControls: PlaybackControls;
  const configurePlayback = (next: number) => {
    playback?.destroy();
    playbackControls?.destroy();
    index = Math.min(next, times().length - 1);
    playback = new PlaybackController(times().length, state => {
      if (index !== state.index) { index = state.index; void showFrame(); }
      playbackControls.show(state, times()[state.index], labels()[state.index]);
    });
    playbackControls = new PlaybackControls(element("playback"), times().length, {
      toggle: () => { if (!isStatic()) playback.getState().playing ? playback.pause() : playback.play(); },
      seek: next => { if (!isStatic()) playback.seek(next); },
      step: direction => { if (!isStatic()) playback.step(direction); },
      speed: speed => { if (!isStatic()) playback.setSpeed(speed); },
    });
    playback.seek(index);
    playback.setHidden(document.hidden);
    playbackControls.setDisabled(isStatic(), playback.getState());
  };
  configurePlayback(0);
  const selector = element("comparison-layer") as HTMLSelectElement;
  element("comparison-control").hidden = false;
  let historicalIndex = 0;
  let interactiveIndex = 0;
  const changeLayer = () => {
    const wasInteractive = selected === "interactive";
    if (wasInteractive) interactiveIndex = index; else historicalIndex = index;
    selected = selector.value as ComparisonLayer | "interactive";
    if (wasInteractive !== (selected === "interactive")) configurePlayback(selected === "interactive" ? interactiveIndex : historicalIndex);
    if (isStatic()) playback.pause();
    playbackControls.setDisabled(isStatic(), playback.getState());
    void showFrame();
  };
  selector.addEventListener("change", changeLayer);
  let disposed = false;
  const damping = new DampingControls(element("damping"), grid, async data => {
    await data.frame(0);
    if (disposed) return;
    if (selected !== "interactive") historicalIndex = index;
    interactive = data;
    let option = selector.querySelector<HTMLOptionElement>('option[value="interactive"]');
    if (!option) {option = document.createElement("option"); option.value = "interactive"; selector.append(option);}
    option.textContent = data.manifest.name;
    selected = "interactive";
    selector.value = selected;
    interactiveIndex = 0;
    configurePlayback(0);
    await showFrame();
  });
  const visibility = () => playback.setHidden(document.hidden);
  document.addEventListener("visibilitychange", visibility);
  visibility();
  status();
  return () => {
    disposed = true;
    generation++;
    damping.destroy();
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
  element("status").textContent = `Unable to load the historical comparison: ${String(error)}. Generate assets with python experiments/compare_bilinear_h.py --stage export.`;
});
