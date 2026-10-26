// No scientific runtime or model weights are loaded in the browser.
async function jsonResponse(response){
 let data;try{data=await response.json()}catch{throw Error('The hosted service is waking or unavailable. Please retry shortly.')}
 if(!response.ok)throw Error(data.error||`Server returned HTTP ${response.status}`);return data;
}
const pause=(ms,signal)=>new Promise((resolve,reject)=>{const abort=()=>{clearTimeout(timer);reject(new DOMException('Cancelled','AbortError'))};const timer=setTimeout(()=>{signal?.removeEventListener('abort',abort);resolve()},ms);signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort()});
export async function runHosted(task,data,{signal,onProgress=()=>{}}={}){
 let id,complete=false;const deadline=Date.now()+540000;
 try{
  onProgress('Connecting to the hosted solver… The free server may take a minute to wake.');
  // Let submission finish so a cancellation can delete the actual server job.
  const created=await jsonResponse(await fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...data,task}),signal:AbortSignal.timeout(120000)}));id=created.id;
  if(!/^[A-Za-z0-9_-]{32,64}$/.test(id))throw Error('Invalid server job response');
  while(true){
   if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
   if(Date.now()>deadline)throw Error('The hosted calculation exceeded nine minutes. Reduce the request and retry.');
   const job=await jsonResponse(await fetch('/api/jobs/'+id,{cache:'no-store',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(30000)]):AbortSignal.timeout(30000)}));
   onProgress(job.message||'Calculating on the server…');
   if(job.status==='complete'){complete=true;return job.result}
   if(job.status!=='running')throw Error(job.message||'The server calculation stopped.');
   await pause(1500,signal);
  }
 }finally{
  if(id){try{await jsonResponse(await fetch('/api/jobs/'+id,{method:'DELETE',signal:AbortSignal.timeout(15000)}))}catch(e){if(!complete)throw Error('Could not confirm server cancellation. The job stops automatically at its time limit.')}}
 }
}
export async function hostedSummary(data,{signal}={}){return jsonResponse(await fetch('/api/summary',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(120000)]):AbortSignal.timeout(120000)}))}
export async function askHosted(question,context,{signal}={}){return jsonResponse(await fetch('/api/assistant',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,context}),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(90000)]):AbortSignal.timeout(90000)}))}
