import { DEFAULT_GAMMA, runSimulation, validateGamma } from "../data/interactive";
import type { InteractiveData } from "../data/interactive";
import type { GridGeometry } from "../data/field";

export class DampingControls {
  private events = new AbortController();
  private request = new AbortController();
  private destroyed = false;
  constructor(element: HTMLElement, grid: GridGeometry, onComplete: (data: InteractiveData)=>Promise<void>) {
    element.innerHTML = `<form>
      <label class="control" for="damping-slider">Surface damping γ <span class="help">(W m⁻² K⁻¹)</span></label>
      <div class="damping-values">
        <input id="damping-slider" aria-label="Surface damping slider" type="range" min="0" max="40" step="1" value="16">
        <input aria-label="Surface damping value" type="number" min="0" max="40" step="any" value="${DEFAULT_GAMMA}" required>
      </div>
      <button type="submit">Run Simulation</button>
      <p role="status" class="help" aria-live="polite">Fixed January 1979–December 1980 experiment.</p>
    </form>`;
    const form=element.querySelector("form")!,slider=element.querySelector<HTMLInputElement>('input[type="range"]')!,number=element.querySelector<HTMLInputElement>('input[type="number"]')!,button=element.querySelector("button")!,status=element.querySelector("p")!;
    const options={signal:this.events.signal};
    slider.addEventListener("input",()=>{number.value=slider.value;},options);
    number.addEventListener("input",()=>{if(Number.isFinite(number.valueAsNumber))slider.value=String(Math.round(number.valueAsNumber));},options);
    form.addEventListener("submit",event=>{
      event.preventDefault();
      if(button.disabled)return;
      let gamma: number;
      try {gamma=validateGamma(number.valueAsNumber);} catch(error) {status.textContent=String(error);return;}
      button.disabled=slider.disabled=number.disabled=true;
      status.textContent="Starting simulation…";
      this.request=new AbortController();
      void runSimulation(gamma,grid,message=>{if(!this.destroyed)status.textContent=message;},this.request.signal)
        .then(async data=>{if(!this.destroyed){await onComplete(data);status.textContent=`Loaded 24 monthly states · γ = ${gamma} W m⁻² K⁻¹.`;}})
        .catch(error=>{if(!this.destroyed)status.textContent=`Unable to run simulation: ${String(error)}`;})
        .finally(()=>{if(!this.destroyed)button.disabled=slider.disabled=number.disabled=false;});
    },options);
  }
  destroy(): void {this.destroyed=true;this.events.abort();this.request.abort();}
}
