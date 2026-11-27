import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModule } from "./load-module.mjs";

const { ComparisonData, loadComparison, validateComparison, layerNames, isDepthLayer } = await loadModule("../src/data/comparison.ts");
const { resolveScale, defaultRange } = await loadModule("../src/globe/ColorScale.ts");
const { PlaybackController } = await loadModule("../src/PlaybackController.ts");

function manifest() {
  return { format:"sst-comparison-f32-v4",grid:{id:"comparison",cells:[
    {id:"south",west:-180,east:-179.5,south:-20.5,north:-20,nativeCellCount:4},
    {id:"north",west:179.5,east:180,south:20,north:20.5,nativeCellCount:2},
  ]},months:Array.from({length:574},(_,i)=>new Date(Date.UTC(1979,i,1)).toISOString().slice(0,7)),
    timestamps:Array.from({length:574},(_,i)=>new Date(Date.UTC(1979,i+1,1)).toISOString()),
    frameLabels:Array.from({length:574},(_,i)=>`Calendar month ${i}`),
    frames:Array.from({length:574},(_,i)=>({file:`frames/${String(i).padStart(4,"0")}.bin`})),
    staticDepth:{file:"depth.bin"},depthDescription:"Fixed H throughout the simulation",populations:{sst:[-3,-1,0,1,3],difference:[-2,-.5,0,.5,2],depth:[50,500]},description:"0.5° common ocean aggregates"};
}

function binary() {
  const buffer=new ArrayBuffer(16),view=new DataView(buffer);
  [1,NaN,3,NaN].forEach((v,i)=>view.setFloat32(i*4,v,true));
  return buffer;
}

test("574-month comparison loads and validates half-degree geography and calendar association",async()=>{
  const data=await loadComparison(async()=>new Response(JSON.stringify(manifest())));
  assert.equal(data.manifest.months.length,574);
  assert.equal(data.manifest.months[0],"1979-01");assert.equal(data.manifest.months.at(-1),"2026-10");
  assert.equal(data.manifest.timestamps[1],"1979-03-01T00:00:00.000Z");
  const invalid=manifest();invalid.grid.cells[0].east=-175;
  assert.throws(()=>validateComparison(invalid),/0.5°/);
  const shifted=manifest();shifted.timestamps[0]="1979-01-01T00:00:00Z";
  assert.throws(()=>validateComparison(shifted),/mismatch/);
});

test("switching layers preserves selected month, shares SST limits and keeps missing values",async()=>{
  let requests=0;
  const data=new ComparisonData(validateComparison(manifest()),async()=>{requests++;return new Response(binary());});
  const playback=new PlaybackController(574,()=>{});playback.seek(16);
  const index=playback.getState().index;
  const model=await data.frame(index,"model"),era=await data.frame(index,"era5"),diff=await data.frame(index,"difference");
  assert.equal(playback.getState().index,16);
  assert.equal(model.timeLabel,era.timeLabel);assert.equal(era.timestamp,diff.timestamp);
  assert.deepEqual(model.values,[1,null]);assert.deepEqual(era.values,[3,null]);assert.deepEqual(diff.values,[-2,null]);
  assert.equal(requests,1,"all monthly layers use the same cached monthly buffer");
  assert.strictEqual(data.population("model"),data.population("era5"));
  const scale=resolveScale("diverging",data.population("model"),defaultRange());
  assert.deepEqual(resolveScale("diverging",data.population("era5"),defaultRange()),scale);
  assert.notDeepEqual(resolveScale("diverging",data.population("difference"),defaultRange()),scale);
  playback.step(1);await data.frame(playback.getState().index,"era5");
  assert.deepEqual(resolveScale("diverging",data.population("model"),defaultRange()),scale);
  playback.destroy();
});

test("monthly buffers are bounded and malformed binary files fail clearly",async()=>{
  const data=new ComparisonData(validateComparison(manifest()),async()=>new Response(binary()));
  for(let i=0;i<5;i++)await data.frame(i,"model");
  assert.equal(data.cache.size,3);
  const bad=new ComparisonData(validateComparison(manifest()),async()=>new Response(new ArrayBuffer(4)));
  await assert.rejects(()=>bad.frame(0,"model"),/size mismatch/);
});

test("injected fetch is called without a class-instance receiver",async()=>{
  const data=new ComparisonData(validateComparison(manifest()),function(){
    assert.equal(this,undefined);
    return Promise.resolve(new Response(binary()));
  });
  await data.frame(0,"model");
});

test("fixed H is sequential, in metres and independent of the selected month",async()=>{
  let requests=0;
  const data=new ComparisonData(validateComparison(manifest()),async()=>{
    requests++;const buffer=new ArrayBuffer(8),v=new DataView(buffer);v.setFloat32(0,50,true);v.setFloat32(4,500,true);return new Response(buffer);
  });
  const playback=new PlaybackController(574,()=>{});playback.seek(37);playback.pause();
  const h=await data.frame(playback.getState().index,"depth");
  assert.equal(h.units,"m");assert.equal(h.colorScale,"sequential");assert.equal(h.timestamp,undefined);
  assert.deepEqual(h.values,[50,500]);assert.match(h.timeLabel,/Fixed throughout/);
  assert.strictEqual(data.population("model"),data.population("model"));
  assert.deepEqual((await data.frame(300,"depth")).values,h.values);assert.equal(requests,1);
  await data.frame(playback.getState().index,"depth");assert.equal(playback.getState().index,37);
  playback.destroy();
});

test("only the primary model, ERA5, calculated difference and static H are selectable",async()=>{
  assert.deepEqual(Object.keys(layerNames),["model","era5","difference","depth"]);
  assert.equal(layerNames.model,"Model SSTA");assert.equal(isDepthLayer("depth"),true);
  assert.equal(isDepthLayer("model"),false);
  const old=manifest();old.format="sst-comparison-f32-v3";
  assert.throws(()=>validateComparison(old),/regenerate/);
  const data=new ComparisonData(validateComparison(manifest()),async()=>new Response(binary()));
  await assert.rejects(()=>data.frame(0,"baseline"),/Unknown comparison layer/);
});

test("difference subtracts stored floats directly and preserves asymmetric missing operands",async()=>{
  const m=manifest();m.grid.cells.push({id:"missing",west:0,east:.5,south:20,north:20.5});
  const data=new ComparisonData(validateComparison(m),async()=>{
    const buffer=new ArrayBuffer(24),view=new DataView(buffer);
    [.1,NaN,2,.3,5,Infinity].forEach((v,i)=>view.setFloat32(i*4,v,true));
    return new Response(buffer);
  });
  const model=await data.frame(1,"model"),era=await data.frame(1,"era5"),diff=await data.frame(1,"difference");
  assert.equal(diff.values[0],model.values[0]-era.values[0]);
  assert.deepEqual(diff.values.slice(1),[null,null]);
  assert.deepEqual(model.values.slice(1),[null,null]);
  assert.deepEqual(era.values.slice(1),[null,null]);
  assert.ok(diff.values[0]<0);
});
