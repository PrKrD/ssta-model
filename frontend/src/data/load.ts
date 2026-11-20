import { createDemoSequenceDataset } from "./demo";
import { validateSequenceDataset } from "./field";
import type { SequenceDataset } from "./field";

export interface LoadedDataset {
  dataset: SequenceDataset;
  source: "model" | "synthetic";
  notice: string;
}

/** Offline static asset only; failed or invalid pilot data are explicitly labelled. */
export async function loadDataset(demo = false, fetcher: typeof fetch = fetch): Promise<LoadedDataset> {
  if (!demo) {
    try {
      const response = await fetcher("/data/historical_surface_flux_pilot.json", { cache: "no-cache" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return { dataset: validateSequenceDataset(await response.json()), source: "model", notice: "Saved model output · 5° ocean-area aggregates" };
    } catch {
      return { dataset: validateSequenceDataset(createDemoSequenceDataset()), source: "synthetic",
        notice: "Pilot file unavailable or invalid. Showing synthetic demonstration data." };
    }
  }
  return { dataset: validateSequenceDataset(createDemoSequenceDataset()), source: "synthetic", notice: "Synthetic demonstration selected · not model output" };
}
