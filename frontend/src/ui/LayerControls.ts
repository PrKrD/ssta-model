import type { ColorScaleType } from "../data/field";
import { defaultRange } from "../globe/ColorScale";
import type { PercentileRange } from "../globe/ColorScale";

/** Native controls retain keyboard and touch support without a UI framework. */
export class LayerControls {
  private events = new AbortController();

  constructor(
    element: HTMLElement,
    initialType: ColorScaleType,
    onChange: (type: ColorScaleType, range: PercentileRange) => void,
  ) {
    element.innerHTML = `
      <label class="control">Color scale
        <select aria-label="Color scale">
          <option value="diverging">Diverging · zero centred</option>
          <option value="sequential">Sequential · square root</option>
        </select>
      </label>
      <label class="control">Lower percentile <output></output>
        <input type="range" aria-label="Lower percentile" min="0" max="99" step="1" value="2">
      </label>
      <label class="control">Upper percentile <output></output>
        <input type="range" aria-label="Upper percentile" min="1" max="100" step="1" value="98">
      </label>
      <button type="button">Reset color limits</button>`;
    const select = element.querySelector("select")!;
    const [lower, upper] = Array.from(element.querySelectorAll("input"));
    const outputs = element.querySelectorAll("output");
    select.value = initialType;
    const sync = () => {
      const range = { lower: lower.valueAsNumber, upper: upper.valueAsNumber };
      lower.max = String(range.upper - 1);
      upper.min = String(range.lower + 1);
      outputs[0].textContent = `p${range.lower}`;
      outputs[1].textContent = `p${range.upper}`;
      onChange(select.value as ColorScaleType, range);
    };
    const options = { signal: this.events.signal };
    select.addEventListener("change", sync, options);
    lower.addEventListener("input", sync, options);
    upper.addEventListener("input", sync, options);
    element.querySelector("button")!.addEventListener("click", () => {
      lower.max = "99";
      upper.min = "1";
      const range = defaultRange();
      lower.value = String(range.lower);
      upper.value = String(range.upper);
      sync();
    }, options);
    sync();
  }

  destroy(): void { this.events.abort(); }
}
