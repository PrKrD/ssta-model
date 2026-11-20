import type { PlaybackState } from "../PlaybackController";
import { BASE_FRAMES_PER_SECOND, PLAYBACK_SPEEDS } from "../PlaybackController";

export class PlaybackControls {
  private events = new AbortController();
  private play: HTMLButtonElement;
  private previous: HTMLButtonElement;
  private next: HTMLButtonElement;
  private timeline: HTMLInputElement;
  private time: HTMLOutputElement;
  private speed: HTMLSelectElement;

  constructor(
    element: HTMLElement, private frameCount: number,
    actions: {
      toggle(): void;
      seek(index: number): void;
      step(direction: -1 | 1): void;
      speed(value: number): void;
    },
  ) {
    element.innerHTML = `
      <div class="playback-buttons">
        <button type="button" aria-label="Previous frame">←</button>
        <button type="button" class="play-toggle" aria-pressed="false">Play</button>
        <button type="button" aria-label="Next frame">→</button>
      </div>
      <label class="control timeline">Timeline <output></output>
        <input type="range" aria-label="Timeline" min="0" max="${frameCount - 1}" step="1" value="0">
      </label>
      <label class="control">Playback speed
        <select aria-label="Playback speed">
          ${PLAYBACK_SPEEDS.map((speed) => `<option value="${speed}" ${speed === 1 ? "selected" : ""}>${speed}× · ${BASE_FRAMES_PER_SECOND * speed} frames/s</option>`).join("")}
        </select>
      </label>
      <p class="help">Playback loops. Stepping or scrubbing pauses.</p>`;
    [this.previous, this.play, this.next] = Array.from(element.querySelectorAll("button"));
    this.timeline = element.querySelector("input")!;
    this.time = element.querySelector("output")!;
    this.speed = element.querySelector("select")!;
    const options = { signal: this.events.signal };
    this.play.addEventListener("click", actions.toggle, options);
    this.previous.addEventListener("click", () => actions.step(-1), options);
    this.next.addEventListener("click", () => actions.step(1), options);
    this.timeline.addEventListener("input", () => actions.seek(this.timeline.valueAsNumber), options);
    this.speed.addEventListener("change", () => actions.speed(Number(this.speed.value)), options);
  }

  show(state: PlaybackState, timestamp: string, timeLabel?: string): void {
    this.play.textContent = state.playing ? "Pause" : "Play";
    this.play.setAttribute("aria-pressed", String(state.playing));
    this.timeline.value = String(state.index);
    this.timeline.setAttribute("aria-valuetext", `${timeLabel ?? timestamp}, frame ${state.index + 1} of ${this.frameCount}`);
    this.time.textContent = `${timeLabel ?? timestamp.slice(0, 7)} · ${state.index + 1}/${this.frameCount}`;
    this.previous.disabled = state.index === 0;
    this.next.disabled = state.index === this.frameCount - 1;
    this.speed.value = String(state.speed);
  }

  destroy(): void { this.events.abort(); }
}
