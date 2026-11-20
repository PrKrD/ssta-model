export const BASE_FRAMES_PER_SECOND = 6;
export const PLAYBACK_SPEEDS = [0.5, 1, 2] as const;

export interface PlaybackState {
  index: number;
  playing: boolean;
  speed: number;
}

/** A small injectable clock keeps timing testable without a browser or timers. */
export interface AnimationClock {
  request(callback: (now: number) => void): number;
  cancel(handle: number): void;
}

export class PlaybackController {
  private state: PlaybackState = { index: 0, playing: false, speed: 1 };
  private handle: number | null = null;
  private previousTime: number | null = null;
  private elapsed = 0;
  private hidden = false;
  private destroyed = false;

  constructor(
    private readonly frameCount: number,
    private readonly onChange: (state: PlaybackState) => void,
    private readonly clock: AnimationClock = {
      request: (callback) => requestAnimationFrame(callback),
      cancel: (handle) => cancelAnimationFrame(handle),
    },
  ) {
    if (!Number.isInteger(frameCount) || frameCount < 1) throw new Error("Playback needs at least one frame");
  }

  getState(): PlaybackState { return { ...this.state }; }

  play(): void {
    if (this.destroyed || this.state.playing) return;
    this.state.playing = true;
    this.resetClock();
    this.onChange(this.getState());
    this.schedule();
  }

  pause(): void {
    if (this.destroyed || !this.state.playing) return;
    this.state.playing = false;
    this.resetClock();
    this.onChange(this.getState());
  }

  /** Scrubbing and stepping pause; manual boundaries clamp, playback wraps. */
  seek(index: number): void {
    if (this.destroyed) return;
    if (!Number.isInteger(index)) throw new Error("Frame index must be an integer");
    this.state.index = Math.max(0, Math.min(index, this.frameCount - 1));
    this.state.playing = false;
    this.resetClock();
    this.onChange(this.getState());
  }

  step(direction: -1 | 1): void { this.seek(this.state.index + direction); }

  setSpeed(speed: number): void {
    if (this.destroyed) return;
    if (!PLAYBACK_SPEEDS.some((value) => value === speed)) throw new Error("Unsupported playback speed");
    this.state.speed = speed;
    this.resetClock();
    this.onChange(this.getState());
    this.schedule();
  }

  setHidden(hidden: boolean): void {
    if (this.destroyed || this.hidden === hidden) return;
    this.hidden = hidden;
    this.resetClock();
    this.schedule();
  }

  private resetClock(): void {
    if (this.handle !== null) this.clock.cancel(this.handle);
    this.handle = null;
    this.previousTime = null;
    this.elapsed = 0;
  }

  private schedule(): void {
    if (!this.destroyed && this.state.playing && !this.hidden && this.handle === null) {
      this.handle = this.clock.request(this.tick);
    }
  }

  private tick = (now: number): void => {
    this.handle = null;
    if (this.destroyed || !this.state.playing || this.hidden) return;
    if (this.previousTime !== null) {
      const delta = now - this.previousTime;
      // Discard long stalls rather than racing through missed frames on return.
      this.elapsed = delta >= 0 && delta <= 1000 ? this.elapsed + delta * this.state.speed : 0;
      const interval = 1000 / BASE_FRAMES_PER_SECOND;
      const steps = Math.floor((this.elapsed + 1e-9) / interval);
      if (steps > 0) {
        this.elapsed = Math.max(0, this.elapsed - steps * interval);
        this.state.index = (this.state.index + steps) % this.frameCount;
        this.onChange(this.getState());
      }
    }
    this.previousTime = now;
    this.schedule();
  };

  destroy(): void {
    this.destroyed = true;
    this.state.playing = false;
    this.resetClock();
  }
}
