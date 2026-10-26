import test from 'node:test';
import assert from 'node:assert/strict';
import {ScientificJobs} from '../server/Cloudflare Jobs.mjs';
const request=(path,body,method=body===undefined?'GET':'POST')=>new Request('https://jobs'+path,{method,...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:typeof body==='string'?body:JSON.stringify(body)})});
function fixture(fetcher=async()=>new Response('{"result":{"verified":true}}',{headers:{'Content-Type':'application/json'}})){
 const tasks=[];const jobs=new ScientificJobs({waitUntil:p=>tasks.push(p)},{SCIENTIFIC:{fetch:fetcher}});
 return {jobs,tasks};
}
test('unknown tasks and nonfinite values never reach the solver',async()=>{
 let calls=0;const {jobs}=fixture(async()=>{calls++;throw Error('must not run')});
 assert.equal((await jobs.fetch(request('/jobs',{task:'execute',code:'arbitrary'}))).status,400);
 assert.equal((await jobs.fetch(request('/jobs','{"task":"calculate","pressure":1e999}'))).status,400);
 assert.equal(calls,0);
});
test('a completed private-service result is retrieved and then deleted',async()=>{
 const {jobs,tasks}=fixture();const submitted=await jobs.fetch(request('/jobs',{task:'calculate'}));assert.equal(submitted.status,202);
 const {id}=await submitted.json();assert.match(id,/^[a-f0-9]{32}$/);await Promise.all(tasks);
 const result=await(await jobs.fetch(request('/jobs/'+id))).json();assert.deepEqual(result.result,{verified:true});assert.equal(result.status,'complete');
 assert.equal((await jobs.fetch(request('/jobs/'+id,undefined,'DELETE'))).status,200);
 assert.equal((await jobs.fetch(request('/jobs/'+id))).status,404);
});
test('busy solver rejects a second job and cancellation discards any late result',async()=>{
 let finish;const gate=new Promise(resolve=>{finish=resolve});const {jobs,tasks}=fixture(async()=>{await gate;return new Response('{"result":{"late":true}}')});
 const {id}=await(await jobs.fetch(request('/jobs',{task:'tune'}))).json();
 assert.equal((await jobs.fetch(request('/jobs',{task:'calculate'}))).status,429);
 const cancelled=await(await jobs.fetch(request('/jobs/'+id,undefined,'DELETE'))).json();assert.equal(cancelled.executionMayContinueUntilLimit,true);
 finish();await Promise.all(tasks);assert.equal((await jobs.fetch(request('/jobs/'+id))).status,404);assert.equal(jobs.active,null);
});
test('runtime failure cannot be mistaken for a scientific result',async()=>{
 const {jobs,tasks}=fixture(async()=>new Response('{"error":"Memory limit reached; no result"}',{status:503}));
 const {id}=await(await jobs.fetch(request('/jobs',{task:'tune'}))).json();await Promise.all(tasks);
 const result=await(await jobs.fetch(request('/jobs/'+id))).json();assert.equal(result.status,'error');assert.match(result.message,/Memory limit/);assert.ok(!Object.hasOwn(result,'result'));
});
test('expired results and restarted objects do not retain inputs or outputs',async()=>{
 const {jobs}=fixture();jobs.jobs.set('a'.repeat(32),{status:'complete',updated:0,result:{private:'value'}});
 assert.equal((await jobs.fetch(request('/jobs/'+'a'.repeat(32)))).status,404);
 assert.equal((await fixture().jobs.fetch(request('/jobs/'+'a'.repeat(32)))).status,404);
});
test('expiry alarm removes results without needing another visitor request',async()=>{
 const alarms=[];const tasks=[];
 const jobs=new ScientificJobs({waitUntil:p=>tasks.push(p),storage:{setAlarm:async time=>alarms.push(time)}},{SCIENTIFIC:{fetch:async()=>new Response('{"result":{}}')}});
 const {id}=await(await jobs.fetch(request('/jobs',{task:'calculate'}))).json();await Promise.all(tasks);
 assert.equal(alarms.length,1);assert.equal(alarms[0],jobs.jobs.get(id).updated+600001);
 jobs.jobs.get(id).updated=Date.now()-600002;await jobs.alarm();assert.equal(jobs.jobs.size,0);
});
