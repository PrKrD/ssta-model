import type { NumericalField } from "../data/field";
import { legendStops } from "../globe/ColorScale";
import type { ResolvedColorScale } from "../globe/ColorScale";

export class LayerLegend {
  private timestamp: HTMLElement | null = null;
  constructor(private element: HTMLElement) {}

  show(field: NumericalField, scale: ResolvedColorScale | null): void {
    this.element.replaceChildren();
    const line = (text: string, className = "") => {
      const element = document.createElement("p");
      element.textContent = text;
      element.className = className;
      this.element.append(element);
      return element;
    };
    line(`${field.name} · ${field.units}`, "legend-title");
    this.timestamp = line("", "help");
    this.updateTimestamp(field.timestamp, field.timeLabel);
    if (!scale) {
      line("No finite values available");
    } else {
      const bar = document.createElement("div");
      bar.className = "legend-bar";
      bar.style.background = `linear-gradient(90deg, ${legendStops(scale)})`;
      this.element.append(bar);
      const labels = line("", "legend-labels");
      for (const value of [scale.minimum, scale.maximum]) {
        const label = document.createElement("span");
        label.textContent = Number(value.toPrecision(4)).toString();
        labels.append(label);
      }
      line(`p${scale.lower}–p${scale.upper} · ${scale.type === "diverging"
        ? "symmetric limits; neutral = zero"
        : "square-root normalization"}`, "help");
    }
    line(`■ Gray = missing data · Bare globe = omitted region${field.units === "1" ? " · 1 = dimensionless" : ""}`, "missing");
  }

  /** Time changes do not regenerate the fixed gradient and scale labels. */
  updateTimestamp(timestamp?: string, timeLabel?: string): void {
    if (!this.timestamp) return;
    this.timestamp.hidden = timestamp === undefined && !timeLabel;
    this.timestamp.textContent = timestamp ? `${timeLabel ? `${timeLabel} · ` : ""}State timestamp: ${timestamp}` : timeLabel ?? "";
  }
}
