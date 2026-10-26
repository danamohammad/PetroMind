import {numeric} from './Data Tools.mjs';
export const channels=['pressure','temperature','oil_rate','water_rate','choke'];
export function ingestTelemetry(input){
 if(!Array.isArray(input)||input.length>10000)throw Error('Telemetry must contain at most 10,000 rows.');
 const map=new Map();let duplicates=0;
 for(const [i,r] of input.entries()){
  if(!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(String(r.timestamp))||!Number.isFinite(Date.parse(r.timestamp)))throw Error(`Row ${i+1}: use an ISO timestamp with Z or UTC offset.`);
  const well=String(r.well||'Well 1').trim().slice(0,100);if(!well)throw Error('Well name is required.');
  const out={timestamp:new Date(r.timestamp).toISOString(),well};
  for(const k of channels){out[k]=numeric(r[k],`Row ${i+1} ${k}`,{optional:true});if(out[k]!==null&&((k!=='temperature'&&out[k]<0)||(k==='choke'&&out[k]>100)||(k==='temperature'&&out[k]<-273.15)))throw Error(`Row ${i+1}: invalid ${k}.`)}
  if(channels.every(k=>out[k]===null))throw Error(`Row ${i+1}: enter at least one measured channel.`);
  const key=well+'|'+out.timestamp;if(map.has(key))duplicates++;map.set(key,out);
 }
 return {rows:[...map.values()].sort((a,b)=>a.timestamp.localeCompare(b.timestamp)),duplicates};
}
export function mergeTelemetry(existing,incoming){
 const current=ingestTelemetry(existing),next=ingestTelemetry(incoming);
 const map=new Map(current.rows.map(r=>[r.well+'|'+r.timestamp,r]));let duplicates=next.duplicates;
 for(const r of next.rows){const key=r.well+'|'+r.timestamp;if(map.has(key))duplicates++;map.set(key,r)}
 return {rows:[...map.values()].sort((a,b)=>a.timestamp.localeCompare(b.timestamp)).slice(-10000),duplicates};
}
export function telemetrySummary(rows,well,now=Date.now(),limits={low:0,high:10000,stale:300}){
 const selected=rows.filter(r=>r.well===well);if(!selected.length)throw Error('No rows for this well.');
 const latest=selected.at(-1),age=(now-Date.parse(latest.timestamp))/1000;
 const low=numeric(limits.low,'Low pressure'),high=numeric(limits.high,'High pressure'),stale=numeric(limits.stale,'Stale seconds');if(low>high||stale<=0)throw Error('Enter ordered pressure thresholds and a positive stale time.');
 const flags=[];if(age>stale)flags.push('Stale data');if(age< -60)flags.push('Future timestamp');if(latest.pressure!==null&&(latest.pressure<low||latest.pressure>high))flags.push('Pressure outside configured limits');
 const gaps=selected.slice(1).map((r,i)=>(Date.parse(r.timestamp)-Date.parse(selected[i].timestamp))/1000);
 return {latest,ageSeconds:age,flags,largestGapSeconds:gaps.length?Math.max(...gaps):null,rows:selected};
}
export function pressureProfile(rows){
 if(rows.length<2||rows.length>2000)throw Error('Enter 2 to 2,000 depth observations.');
 const data=rows.map(r=>({depth:numeric(r.depth,'TVD · m'),pressure:numeric(r.pressure,'Pressure · psia'),temperature:numeric(r.temperature,'Temperature · °C')})).sort((a,b)=>a.depth-b.depth);
 if(data.some(r=>r.depth<0||r.pressure<=0||r.temperature< -273.15)||new Set(data.map(r=>r.depth)).size!==data.length)throw Error('Use unique nonnegative depths, positive absolute pressure and physical temperatures.');
 const mean=k=>data.reduce((s,r)=>s+r[k],0)/data.length,md=mean('depth'),den=data.reduce((s,r)=>s+(r.depth-md)**2,0),fit=k=>{const m=mean(k),slope=data.reduce((s,r)=>s+(r.depth-md)*(r[k]-m),0)/den;return {slope,intercept:m-slope*md}};
 const p=fit('pressure'),t=fit('temperature');return {rows:data.map(r=>({...r,fittedPressure:p.intercept+p.slope*r.depth,fittedTemperature:t.intercept+t.slope*r.depth})),summary:{pressureGradientPsiM:p.slope,temperatureGradientCPer100M:t.slope*100,equivalentStaticDensityKgM3:p.slope*6894.757293168/9.80665},note:'Least-squares gradients through measured points. Equivalent density is a hydrostatic interpretation only; flowing friction, gas holdup and sensor drift can change the gradient. No well-test permeability or heat-transfer model is inferred.'};
}
