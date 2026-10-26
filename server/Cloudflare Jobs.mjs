import {calculateData} from './Data Calculations.mjs';
const TASKS=new Set(['calculate','envelope','compare','tune','import','experiments','physical','engineering','data']);
const reply=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
const TTL=600000;
function finiteJSON(value,depth=0){if(depth>64)throw Error('JSON nesting exceeds 64 levels.');if(typeof value==='number'&&!Number.isFinite(value))throw Error('All numbers must be finite.');if(value&&typeof value==='object')for(const item of Object.values(value))finiteJSON(item,depth+1)}

export class ScientificJobs{
 constructor(ctx,env){this.ctx=ctx;this.env=env;this.jobs=new Map();this.active=null;}
 expire(){for(const [id,job] of this.jobs)if(job.status!=='running'&&Date.now()-job.updated>TTL)this.jobs.delete(id)}
 async scheduleCleanup(){
  const deadlines=[...this.jobs.values()].filter(job=>job.status!=='running').map(job=>job.updated+TTL+1);
  if(deadlines.length&&this.ctx.storage?.setAlarm)await this.ctx.storage.setAlarm(Math.max(Date.now()+1,Math.min(...deadlines)));
 }
 async alarm(){this.expire();await this.scheduleCleanup()}
 async fetch(request){
  this.expire();const path=new URL(request.url).pathname;
  if(request.method==='POST'){
   let input;try{input=await request.json()}catch{return reply({error:'Invalid JSON'},400)}
   if(!input||typeof input!=='object'||Array.isArray(input))return reply({error:'A JSON object is required'},400);
   try{finiteJSON(input)}catch(e){return reply({error:e.message},400)}
   if(path==='/summary'){
    if(!['pressureProfile','telemetrySummary','telemetrySimulation'].includes(input.kind))return reply({error:'Unknown summary calculation'},400);
    try{return reply(calculateData(input))}catch(e){return reply({error:String(e.message).slice(0,1200)},400)}
   }
   if(path!=='/jobs'||!TASKS.has(input.task))return reply({error:'Unknown calculation request'},400);
   if(this.active)return reply({error:'The shared scientific solver is busy. Retry when the current calculation finishes.'},429);
   if(this.jobs.size>=4)return reply({error:'Temporary result capacity reached. Retry in a few minutes.'},429);
   const id=crypto.randomUUID().replaceAll('-','');
   const job={status:'running',message:'Calculating on Cloudflare… Complex jobs are limited by the free service.',updated:Date.now(),cancelled:false};
   this.jobs.set(id,job);this.active=id;
   this.ctx.waitUntil(this.run(id,job,input));
   return reply({id},202);
  }
  const id=path.match(/^\/jobs\/([A-Za-z0-9_-]{32,64})$/)?.[1];const job=this.jobs.get(id);
  if(!id||!job)return reply({error:'This temporary job expired or the free service restarted. Submit the calculation again.'},404);
  if(request.method==='DELETE'){
   job.cancelled=true;
   if(job.status!=='running')this.jobs.delete(id);
   return reply({cancelled:true,executionMayContinueUntilLimit:job.status==='running'});
  }
  if(request.method!=='GET')return reply({error:'Method not allowed'},405);
  if(job.cancelled)return reply({status:'cancelled',message:'Results discarded. Any in-flight solver request is bounded by Cloudflare limits.'});
  const {status,message,result}=job;return reply({status,message,...(status==='complete'?{result}:{})});
 }
 async run(id,job,input){
  try{
   let result;
   if(input.task==='data')result=calculateData(input);
   else{
    const response=await this.env.SCIENTIFIC.fetch('https://science/calculate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input),signal:AbortSignal.timeout(120000)});
    let data;try{data=await response.json()}catch{throw Error('The scientific service stopped before producing a result. Reduce the calculation size and retry.')}
    if(!response.ok||data.error)throw Error(data.error||'The free scientific service could not complete this calculation.');
    if(!Object.hasOwn(data,'result'))throw Error('The scientific service returned no result.');result=data.result;
   }
   if(JSON.stringify(result).length>10000000)throw Error('Result exceeds the 10 MB service limit. Reduce the calculation size.');
   if(!job.cancelled)Object.assign(job,{status:'complete',message:'Hosted calculation complete.',result,updated:Date.now()});
  }catch(e){if(!job.cancelled)Object.assign(job,{status:'error',message:e.name==='TimeoutError'?'The free scientific request exceeded two minutes. Reduce the calculation size and retry.':String(e.message).slice(0,1200),updated:Date.now()})}
  finally{if(this.active===id)this.active=null;if(job.cancelled)this.jobs.delete(id);await this.scheduleCleanup()}
 }
}
