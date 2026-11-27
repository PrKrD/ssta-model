import { timestamp, validateField, validateGrid } from "./field";
import type { GridGeometry, NumericalField } from "./field";

export type ComparisonLayer = "bilinear" | "with_diffusion" | "baseline" | "era5" | "difference" | "effect" | "depth" | "depth_original";
export const isDepthLayer = (layer: ComparisonLayer): boolean => layer === "depth" || layer === "depth_original";
export const layerNames: Record<ComparisonLayer, string> = {
  bilinear: "Model SSTA — Bilinear H + diffusion",
  with_diffusion: "Model SSTA — Original H + diffusion", baseline: "Model SSTA — Original H, no diffusion",
  era5: "ERA5 SSTA", difference: "Bilinear H model − ERA5",
  effect: "H representation effect — Bilinear minus original",
  depth: "Mixed-layer depth — Bilinear H", depth_original: "Mixed-layer depth — Original H",
};
interface Manifest {
  grid: GridGeometry;
  months: string[];
  timestamps: string[];
  frameLabels: string[];
  frames: { file: string }[];
  populations: { sst: number[]; difference: number[]; effect: number[]; depth: number[] };
  staticDepth: { file: string };
  staticOriginalDepth: { file: string };
  depthDescription: string;
  originalDepthDescription: string;
  description: string;
}

export function validateComparison(input: unknown): Manifest {
  if (!input || typeof input !== "object") throw new Error("Missing comparison manifest");
  const m = input as Manifest & { format: string };
  if (m.format !== "sst-comparison-f32-v3") throw new Error("Unknown comparison format; regenerate the H sensitivity comparison assets");
  const grid = validateGrid(m.grid);
  if (grid.cells.some(c => c.east-c.west !== 0.5 || c.north-c.south !== 0.5 ||
      !(c.north <= -20 || c.south >= 20))) throw new Error("Comparison needs extratropical 0.5° cells");
  const count = m.timestamps?.length;
  if (!count || !Array.isArray(m.frames) || m.frames.length !== count ||
      !Array.isArray(m.frameLabels) || m.frameLabels.length !== count ||
      !Array.isArray(m.months) || m.months.length !== count || typeof m.description !== "string") {
    throw new Error("Comparison timeline lengths differ");
  }
  const times = m.timestamps.map(timestamp);
  for (let i = 0; i < count; i++) {
    if ((i && Date.parse(times[i]) <= Date.parse(times[i-1])) ||
        !/^\d{4}-\d{2}$/.test(m.months[i]) || !m.frameLabels[i]?.trim() ||
        !/^frames\/\d{4}\.bin$/.test(m.frames[i].file)) throw new Error("Invalid comparison month/frame");
    const [year,month] = m.months[i].split("-").map(Number);
    if (month<1 || month>12 || (i>0 && year*12+month !==
        Number(m.months[i-1].slice(0,4))*12+Number(m.months[i-1].slice(5))+1)) throw new Error("Discontinuous comparison months");
    const expected = Date.UTC(year,month,1);
    if (Date.parse(times[i]) !== expected) throw new Error("Comparison state timestamp/month mismatch");
  }
  if (m.staticDepth?.file !== "depth.bin" || typeof m.depthDescription !== "string") throw new Error("Missing fixed H field");
  if (m.staticOriginalDepth?.file !== "depth_original.bin" || typeof m.originalDepthDescription !== "string") throw new Error("Missing original fixed H field");
  for (const values of [m.populations?.sst, m.populations?.difference, m.populations?.effect, m.populations?.depth]) {
    if (!Array.isArray(values) || !values.length || values.some((v,i)=>!Number.isFinite(v) || (i>0 && v<values[i-1]))) {
      throw new Error("Invalid fixed colour population");
    }
  }
  return { ...m, grid, timestamps: times };
}

/** Native-resolution science stays in NetCDF; browser retains at most three monthly buffers. */
export class ComparisonData {
  private cache = new Map<number, Promise<ArrayBuffer>>();
  private depths = new Map<ComparisonLayer, Promise<ArrayBuffer>>();
  private fetcher: typeof fetch;
  constructor(readonly manifest: Manifest, fetcher: typeof fetch = fetch) {
    // Call the supplied function without assigning ComparisonData as native fetch's receiver.
    this.fetcher = (input, init) => fetcher(input, init);
  }

  population(layer: ComparisonLayer): readonly number[] {
    return isDepthLayer(layer) ? this.manifest.populations.depth : layer === "effect" ? this.manifest.populations.effect : layer === "difference" ? this.manifest.populations.difference : this.manifest.populations.sst;
  }

  async frame(index: number, layer: ComparisonLayer): Promise<NumericalField> {
    if (!Number.isInteger(index) || index < 0 || index >= this.manifest.frames.length) throw new Error("Frame index out of range");
    if (isDepthLayer(layer)) {
      const filename = layer === "depth" ? this.manifest.staticDepth.file : this.manifest.staticOriginalDepth.file;
      if (!this.depths.has(layer)) this.depths.set(layer, this.fetcher(`/data/era5_comparison/${filename}`).then(async response => {
        if (!response.ok) throw new Error("Unable to load fixed H");
        const buffer = await response.arrayBuffer();
        if (buffer.byteLength !== this.manifest.grid.cells.length * 4) throw new Error("H file size mismatch");
        return buffer;
      }));
      const view = new DataView(await this.depths.get(layer)!);
      const values = Array.from({length:this.manifest.grid.cells.length},(_,i)=>{
        const value=view.getFloat32(i*4,true);
        if (Number.isFinite(value) && value<=0) throw new Error("Invalid fixed H value");
        return Number.isFinite(value)?value:null;
      });
      return validateField({gridId:this.manifest.grid.id,name:layerNames[layer],units:"m",colorScale:"sequential",description:layer === "depth" ? this.manifest.depthDescription : this.manifest.originalDepthDescription,timeLabel:"Fixed throughout the simulation · de Boyer Montégut (2023)",values},this.manifest.grid);
    }
    if (!this.cache.has(index)) {
      const request = this.fetcher(`/data/era5_comparison/${this.manifest.frames[index].file}`).then(async response => {
        if (!response.ok) throw new Error(`Unable to load comparison frame: ${response.status}`);
        const buffer = await response.arrayBuffer();
        if (buffer.byteLength !== this.manifest.grid.cells.length * 6 * 4) throw new Error("Comparison frame size mismatch");
        return buffer;
      });
      this.cache.set(index, request);
      while (this.cache.size > 3) this.cache.delete(this.cache.keys().next().value!);
      request.catch(() => this.cache.delete(index));
    }
    const view = new DataView(await this.cache.get(index)!);
    const count = this.manifest.grid.cells.length;
    const layerIndex = ["bilinear", "with_diffusion", "era5", "difference", "effect", "baseline"].indexOf(layer);
    if (layerIndex < 0) throw new Error("Unknown comparison layer");
    const values = Array.from({ length: count }, (_, i) => {
      const value = view.getFloat32((layerIndex * count + i) * 4, true);
      return Number.isFinite(value) ? value : null;
    });
    return validateField({ gridId: this.manifest.grid.id, name: layerNames[layer], units: "K", colorScale: "diverging",
      description: this.manifest.description, timestamp: this.manifest.timestamps[index], timeLabel: this.manifest.frameLabels[index], values }, this.manifest.grid);
  }
}

export async function loadComparison(fetcher: typeof fetch = fetch): Promise<ComparisonData> {
  const response = await fetcher("/data/era5_comparison/manifest.json", { cache: "no-cache" });
  if (!response.ok) throw new Error("Comparison export unavailable");
  return new ComparisonData(validateComparison(await response.json()), fetcher);
}
