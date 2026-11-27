import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./load-module.mjs";

const { DEFAULT_GAMMA, validateGamma, validateInteractive, runSimulation, InteractiveData } = await loadModule("../src/data/interactive.ts");
const grid={id:"same-historical-grid",cells:[{id:"comparison-1",west:0,east:.5,south:20,north:20.5},{id:"comparison-2",west:0,east:.5,south:-20.5,north:-20}]};
const id="a".repeat(32);
function manifest(){return {format:"sst-interactive-f32-v1",grid:structuredClone(grid),gamma_w_m2_k:10,name:"Interactive model SSTA — γ = 10 W m⁻² K⁻¹",description:"Controlled local run",months:Array.from({length:24},(_,i)=>new Date(Date.UTC(1979,i,1)).toISOString().slice(0,7)),timestamps:Array.from({length:24},(_,i)=>new Date(Date.UTC(1979,i+1,1)).toISOString()),frameLabels:Array.from({length:24},(_,i)=>`month ${i}`),frames:Array.from({length:24},(_,i)=>({file:`frames/${String(i).padStart(4,"0")}.bin`}))};}
const response = body => new Response(JSON.stringify(body));

test("damping bounds preserve exact default and reject nonfinite or unsupported values",()=>{
  assert.equal(validateGamma(DEFAULT_GAMMA),16.072239642825945);
  for(const v of [0,40,10.25])assert.equal(validateGamma(v),v);
  for(const v of [NaN,Infinity,-1,41,"10",null])assert.throws(()=>validateGamma(v),/0 to 40/);
});

test("interactive manifest must match historical geometry, requested damping and 24-month calendar",()=>{
  assert.strictEqual(validateInteractive(manifest(),grid,10).grid,grid);
  for(const mutate of [m=>m.grid.cells[0].east=1,m=>m.gamma_w_m2_k=20,m=>m.months[0]="1980-01",m=>m.timestamps[0]="1979-01-01T00:00:00Z",m=>m.frames.pop()]){
    const m=manifest();mutate(m);assert.throws(()=>validateInteractive(m,grid,10));
  }
});

test("completed API run automatically loads a 24-state sequence on the existing grid",async()=>{
  let polls=0, waits=0;const statuses=[], requests=[];
  const fetcher=async(url,options)=>{
    requests.push(String(url));
    if(url==="/api/run"){assert.deepEqual(JSON.parse(options.body),{gamma_w_m2_k:10});return response({run_id:id,status:"queued"});}
    if(url===`/api/status/${id}`)return response({gamma_w_m2_k:10,status:["queued","running","completed"][polls++]});
    if(url===`/api/results/${id}`)return response({dataset_url:`/api/results/${id}/manifest.json`});
    if(url===`/api/results/${id}/manifest.json`)return response(manifest());
    const buffer=new ArrayBuffer(8),view=new DataView(buffer);view.setFloat32(0,String(url).endsWith("0023.bin")?-2:1,true);view.setFloat32(4,NaN,true);return new Response(buffer);
  };
  const data=await runSimulation(10,grid,s=>statuses.push(s),new AbortController().signal,fetcher,async()=>{waits++;});
  assert.equal(waits,2);assert.match(statuses[1],/Running/);
  assert.strictEqual(data.manifest.grid,grid);
  const first=await data.frame(0),last=await data.frame(23);
  assert.deepEqual(first.values,[1,null]);assert.deepEqual(last.values,[-2,null]);
  assert.equal(first.timestamp,"1979-02-01T00:00:00.000Z");assert.equal(last.timestamp,"1981-01-01T00:00:00.000Z");
  assert.equal(last.units,"K");assert.equal(last.colorScale,"diverging");assert.match(last.name,/γ = 10/);
  for(let i=1;i<5;i++)await data.frame(i);
  assert.equal(data.cache.size,3);
  assert.equal(requests.filter(u=>u==="/api/run").length,1);
});

test("failed, busy and mismatched API runs surface errors rather than completed data",async()=>{
  await assert.rejects(()=>runSimulation(10,grid,()=>{},new AbortController().signal,async()=>new Response(JSON.stringify({detail:"A simulation is already running"}),{status:409})),/already running/);
  const failed=async url=>response(url==="/api/run"?{run_id:id}:{gamma_w_m2_k:10,status:"failed",error:"Missing required local inputs"});
  await assert.rejects(()=>runSimulation(10,grid,()=>{},new AbortController().signal,failed),/Missing required/);
  const wrong=async url=>response(url==="/api/run"?{run_id:id}:{gamma_w_m2_k:20,status:"completed"});
  await assert.rejects(()=>runSimulation(10,grid,()=>{},new AbortController().signal,wrong),/does not match/);
  await assert.rejects(()=>runSimulation(10,grid,()=>{},new AbortController().signal,async()=>new Response("",{status:500})),/Start the Python service/);
});

test("interactive frame fetches do not bind the class as native fetch's receiver",async()=>{
  const data=new InteractiveData(validateInteractive(manifest(),grid,10),"/api/results/test/",function(){
    assert.equal(this,undefined);return Promise.resolve(new Response(new ArrayBuffer(8)));
  });
  assert.deepEqual((await data.frame(0)).values,[0,0]);
});
