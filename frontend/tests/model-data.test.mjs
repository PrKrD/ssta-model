import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./load-module.mjs";

const { loadDataset } = await loadModule("../src/data/load.ts");
const { sequenceFrame, validateSequenceDataset } = await loadModule("../src/data/field.ts");
const { sortedSequenceValues, resolveScale, defaultRange, normalize, colorAt } = await loadModule("../src/globe/ColorScale.ts");
const { PlaybackController } = await loadModule("../src/PlaybackController.ts");

function pilot() {
  return { grid: { id: "sst-pilot-5deg", cells: [
    {id:"south", west:-180,east:-175,south:-25,north:-20,nativeCellCount:17},
    {id:"north", west:175,east:180,south:20,north:25,nativeCellCount:40},
  ] }, sequence: { gridId:"sst-pilot-5deg",name:"Modelled SST anomaly",units:"K",colorScale:"diverging",description:"5° ocean-area aggregates",
    timestamps:Array.from({length:24},(_,i)=>new Date(Date.UTC(1979,i+1,1)).toISOString()),
    frameLabels:Array.from({length:24},(_,i)=>`${new Intl.DateTimeFormat("en",{month:"long",year:"numeric",timeZone:"UTC"}).format(new Date(Date.UTC(1979,i,1)))} — end-of-month model state`),
    frames:Array.from({length:24},(_,i)=>[i===5?null:-i/10,i/20]),
  }};
}

test("static model payload loads through validated sequence boundary with correct forcing labels", async () => {
  let requested;
  const loaded=await loadDataset(false,async (url)=>{requested=url;return new Response(JSON.stringify(pilot()));});
  assert.equal(requested,"/data/historical_surface_flux_pilot.json");
  assert.equal(loaded.source,"model");
  assert.equal(loaded.dataset.grid.cells[0].nativeCellCount,17);
  const field=sequenceFrame(loaded.dataset.sequence,0);
  assert.equal(field.timeLabel,"January 1979 — end-of-month model state");
  assert.equal(field.timestamp,"1979-02-01T00:00:00.000Z");
  assert.equal(sequenceFrame(loaded.dataset.sequence,23).timeLabel,"December 1980 — end-of-month model state");
  assert.equal(loaded.dataset.sequence.frames[5][0],null);
});

test("missing, invalid and network-failed model assets visibly fall back to synthetic demo", async () => {
  for (const fetcher of [async()=>new Response("missing",{status:404}),async()=>new Response("<html>Vite fallback</html>"),async()=>new Response('{}'),async()=>{throw new Error("offline");}]) {
    const loaded=await loadDataset(false,fetcher);
    assert.equal(loaded.source,"synthetic");
    assert.match(loaded.notice,/Pilot file unavailable or invalid/);
    assert.match(loaded.dataset.sequence.description,/synthetic/);
    assert.equal(loaded.dataset.sequence.frames.length,120);
  }
  const demo=await loadDataset(true,async()=>{throw new Error("Demo must not fetch");});
  assert.equal(demo.source,"synthetic");
  assert.match(demo.notice,/selected/);
});

test("model-shaped sequence keeps a fixed zero-centred scale and existing playback behaviour", () => {
  const {sequence}=validateSequenceDataset(pilot());
  const scale=resolveScale("diverging",sortedSequenceValues(sequence.frames),defaultRange());
  assert.equal(normalize(0,scale),0.5);
  const color=colorAt(.2,scale);
  const seen=[];
  const playback=new PlaybackController(24,(state)=>seen.push(state.index));
  playback.seek(16);
  assert.equal(sequenceFrame(sequence,playback.getState().index).timeLabel,"May 1980 — end-of-month model state");
  playback.step(1);
  assert.equal(playback.getState().index,17);
  for(let i=0;i<24;i++){sequenceFrame(sequence,i);assert.deepEqual(colorAt(.2,scale),color);}
  playback.destroy();
  assert.deepEqual(seen,[16,17]);
});

test("optional display metadata is validated", () => {
  const bad=pilot();bad.sequence.frameLabels.pop();
  assert.throws(()=>validateSequenceDataset(bad),/one label/);
  const cell=pilot();cell.grid.cells[0].nativeCellCount=-1;
  assert.throws(()=>validateSequenceDataset(cell),/positive integer/);
});
