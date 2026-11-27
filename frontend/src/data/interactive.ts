import { timestamp, validateField, validateGrid } from "./field";
import type { GridGeometry, NumericalField } from "./field";

export const DEFAULT_GAMMA = 16.072239642825945;
export function validateGamma(value: number): number {
  if (!Number.isFinite(value) || value < 0 || value > 40) throw new Error("Surface damping must be a number from 0 to 40 W m⁻² K⁻¹.");
  return value;
}

interface InteractiveManifest {
  format: string;
  grid: GridGeometry;
  gamma_w_m2_k: number;
  name: string;
  description: string;
  months: string[];
  timestamps: string[];
  frameLabels: string[];
  frames: {file: string}[];
}

export function validateInteractive(input: unknown, grid: GridGeometry, gamma: number): InteractiveManifest {
  const m = input as InteractiveManifest;
  if (!m || m.format !== "sst-interactive-f32-v1" || m.gamma_w_m2_k !== validateGamma(gamma)) throw new Error("Interactive result does not match the requested damping.");
  const returned = validateGrid(m.grid);
  if (returned.id !== grid.id || returned.cells.length !== grid.cells.length || returned.cells.some((c,i) => {
    const expected = grid.cells[i];
    return c.id !== expected.id || c.west !== expected.west || c.east !== expected.east || c.south !== expected.south || c.north !== expected.north;
  })) throw new Error("Interactive display grid differs from the historical grid. Reload the viewer after regenerating historical assets.");
  if (typeof m.name !== "string" || !m.name.trim() || typeof m.description !== "string" || !m.description.trim() ||
      !Array.isArray(m.months) || !Array.isArray(m.timestamps) || !Array.isArray(m.frames) || !Array.isArray(m.frameLabels) ||
      [m.months.length,m.timestamps.length,m.frames.length,m.frameLabels.length].some(n => n !== 24)) throw new Error("Interactive result must have 24 monthly states.");
  const times = m.timestamps.map(timestamp);
  for (let i=0;i<24;i++) {
    if (m.months[i] !== new Date(Date.UTC(1979,i,1)).toISOString().slice(0,7) ||
        Date.parse(times[i]) !== Date.UTC(1979,i+1,1) ||
        m.frames[i]?.file !== `frames/${String(i).padStart(4,"0")}.bin` || typeof m.frameLabels[i] !== "string" || !m.frameLabels[i].trim()) throw new Error("Invalid interactive calendar/frame labels.");
  }
  return {...m, grid, timestamps: times};
}

export class InteractiveData {
  private cache = new Map<number, Promise<ArrayBuffer>>();
  private fetcher: typeof fetch;
  constructor(readonly manifest: InteractiveManifest, private base: string, fetcher: typeof fetch = fetch) {
    this.fetcher = (input, init) => fetcher(input, init);
  }
  async frame(index: number): Promise<NumericalField> {
    if (!Number.isInteger(index) || index < 0 || index >= 24) throw new Error("Interactive frame index out of range.");
    if (!this.cache.has(index)) {
      const request = this.fetcher(`${this.base}${this.manifest.frames[index].file}`).then(async response => {
        if (!response.ok) throw new Error("Unable to load interactive SST frame.");
        const buffer = await response.arrayBuffer();
        if (buffer.byteLength !== this.manifest.grid.cells.length*4) throw new Error("Interactive frame size mismatch.");
        return buffer;
      });
      this.cache.set(index,request);
      while(this.cache.size>3) this.cache.delete(this.cache.keys().next().value!);
      request.catch(()=>this.cache.delete(index));
    }
    const view = new DataView(await this.cache.get(index)!);
    const values = Array.from({length:this.manifest.grid.cells.length},(_,i)=>{const v=view.getFloat32(i*4,true);return Number.isFinite(v)?v:null;});
    return validateField({gridId:this.manifest.grid.id,name:this.manifest.name,description:this.manifest.description,units:"K",colorScale:"diverging",timestamp:this.manifest.timestamps[index],timeLabel:this.manifest.frameLabels[index],values},this.manifest.grid);
  }
}

async function responseJSON(response: Response): Promise<Record<string, unknown>> {
  let body;
  try { body = await response.json(); }
  catch { throw new Error("Local API returned no readable response. Start the Python service on 127.0.0.1:8000 and retry."); }
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `API request failed (${response.status}).`);
  return body;
}

function pause(signal: AbortSignal): Promise<void> {
  return new Promise((resolve,reject)=>{
    if (signal.aborted) {reject(new Error("Request cancelled."));return;}
    const abort=()=>{clearTimeout(timer);reject(new Error("Request cancelled."));};
    const timer=setTimeout(()=>{signal.removeEventListener("abort",abort);resolve();},1000);
    signal.addEventListener("abort",abort,{once:true});
  });
}

export async function runSimulation(gamma: number, grid: GridGeometry, onStatus: (message: string)=>void, signal: AbortSignal,
  fetcher: typeof fetch = fetch, wait: (signal: AbortSignal)=>Promise<void> = pause): Promise<InteractiveData> {
  validateGamma(gamma);
  const started = await responseJSON(await fetcher("/api/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({gamma_w_m2_k:gamma}),signal}));
  const id = started.run_id;
  if (typeof id !== "string" || !/^[a-f0-9]{32}$/.test(id)) throw new Error("API returned an invalid run ID.");
  for (;;) {
    const state = await responseJSON(await fetcher(`/api/status/${id}`,{signal}));
    if (state.gamma_w_m2_k !== gamma) throw new Error("API damping does not match request.");
    if (state.status === "failed") throw new Error(typeof state.error === "string" ? state.error : "Simulation failed.");
    if (state.status === "completed") break;
    if (state.status !== "queued" && state.status !== "running") throw new Error("API returned an invalid simulation status.");
    onStatus(state.status === "queued" ? "Simulation queued…" : "Running simulation… This may take about a minute.");
    await wait(signal);
  }
  onStatus("Loading completed SST sequence…");
  const result = await responseJSON(await fetcher(`/api/results/${id}`,{signal}));
  const url = `/api/results/${id}/manifest.json`;
  if (result.dataset_url !== url) throw new Error("API returned an invalid dataset URL.");
  const manifest = validateInteractive(await responseJSON(await fetcher(url,{signal})),grid,gamma);
  return new InteractiveData(manifest,url.slice(0,-"manifest.json".length),(input,init)=>fetcher(input,init));
}
