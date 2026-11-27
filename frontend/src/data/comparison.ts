import { timestamp, validateField, validateGrid } from "./field";
import type { GridGeometry, NumericalField } from "./field";

export type ComparisonLayer = "model" | "era5" | "difference" | "depth";
export const isDepthLayer = (layer: ComparisonLayer): boolean => layer === "depth";
export const layerNames: Record<ComparisonLayer, string> = {
  model: "Model SSTA", era5: "ERA5 SSTA",
  difference: "Difference — Model − ERA5", depth: "Mixed-layer depth H",
};
interface Manifest {
  grid: GridGeometry;
  months: string[];
  timestamps: string[];
  frameLabels: string[];
  frames: { file: string }[];
  populations: { sst: number[]; difference: number[]; depth: number[] };
  staticDepth: { file: string };
  depthDescription: string;
  description: string;
}

export function validateComparison(input: unknown): Manifest {
  if (!input || typeof input !== "object") throw new Error("Missing comparison manifest");
  const m = input as Manifest & { format: string };
  if (m.format !== "sst-comparison-f32-v4") throw new Error("Unknown comparison format; regenerate assets with experiments/export_historical_viewer.py");
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
  for (const values of [m.populations?.sst, m.populations?.difference, m.populations?.depth]) {
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
    return isDepthLayer(layer) ? this.manifest.populations.depth : layer === "difference" ? this.manifest.populations.difference : this.manifest.populations.sst;
  }

  async frame(index: number, layer: ComparisonLayer): Promise<NumericalField> {
    if (!Number.isInteger(index) || index < 0 || index >= this.manifest.frames.length) throw new Error("Frame index out of range");
    if (isDepthLayer(layer)) {
      const filename = this.manifest.staticDepth.file;
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
      return validateField({gridId:this.manifest.grid.id,name:layerNames[layer],units:"m",colorScale:"sequential",description:this.manifest.depthDescription,timeLabel:"Fixed throughout the simulation · de Boyer Montégut (2023)",values},this.manifest.grid);
    }
    if (!this.cache.has(index)) {
      const request = this.fetcher(`/data/era5_comparison/${this.manifest.frames[index].file}`).then(async response => {
        if (!response.ok) throw new Error(`Unable to load comparison frame: ${response.status}`);
        const buffer = await response.arrayBuffer();
        if (buffer.byteLength !== this.manifest.grid.cells.length * 2 * 4) throw new Error("Comparison frame size mismatch");
        return buffer;
      });
      this.cache.set(index, request);
      while (this.cache.size > 3) this.cache.delete(this.cache.keys().next().value!);
      request.catch(() => this.cache.delete(index));
    }
    const view = new DataView(await this.cache.get(index)!);
    const count = this.manifest.grid.cells.length;
    if (!["model", "era5", "difference"].includes(layer)) throw new Error("Unknown comparison layer");
    const values = Array.from({ length: count }, (_, i) => {
      const model = view.getFloat32(i * 4, true);
      const era5 = view.getFloat32((count + i) * 4, true);
      // Both operands must be present; never fill a missing ocean/land value.
      if (!Number.isFinite(model) || !Number.isFinite(era5)) return null;
      return layer === "difference" ? model - era5 : layer === "model" ? model : era5;
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
