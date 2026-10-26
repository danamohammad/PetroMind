"""Bounded, ephemeral scientific job API behind the PetroMind edge proxy."""
import asyncio, json, os, secrets, signal, sys, time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
ROOT=Path(__file__).resolve().parents[1]
KEY=os.environ.get('PETROMIND_BACKEND_KEY','')
MAX_BODY=8_000_000
MAX_SECONDS=int(os.environ.get('PETROMIND_JOB_SECONDS','420'))
TTL=600
TASKS={'calculate','envelope','compare','tune','import','experiments','physical','engineering','data'}
jobs={}
lock=asyncio.Lock()
summary_lock=asyncio.Lock()

@asynccontextmanager
async def lifespan(app):
    async def expire_results():
        while True:
            await asyncio.sleep(30)
            cleanup()
    sweeper=asyncio.create_task(expire_results())
    try:yield
    finally:
        sweeper.cancel()
        for job in list(jobs.values()):
            if job['status']=='running':job['task'].cancel()
        await asyncio.gather(sweeper,*(j['task'] for j in list(jobs.values())),return_exceptions=True)
        jobs.clear()

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)

def reply(data,status=200):return JSONResponse(data,status_code=status,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

def cleanup():
    now=time.monotonic()
    for key in list(jobs):
        if jobs[key]['status']!='running' and now-jobs[key]['updated']>TTL:del jobs[key]

def stop_process(proc):
    if proc and proc.returncode is None:
        try:
            if os.name=='posix':os.killpg(proc.pid,signal.SIGKILL)
            else:proc.kill()
        except ProcessLookupError:pass

async def execute(job,request):
    proc=None
    try:
        env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
        proc=await asyncio.create_subprocess_exec(sys.executable,str(ROOT/'server/Calculation Process.py'),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env=env,start_new_session=os.name=='posix',limit=12_000_000)
        job['process']=proc
        proc.stdin.write(json.dumps(request).encode());await proc.stdin.drain();proc.stdin.close();request=None
        async with asyncio.timeout(MAX_SECONDS):
            while line:=await proc.stdout.readline():
                if len(line)>10_000_000:raise ValueError('Result exceeds server output limit')
                message=json.loads(line)
                if 'progress' in message:job['message']=message['progress']
                elif 'error' in message:raise ValueError(message['error'])
                elif 'result' in message:job['result']=message['result']
            await proc.wait()
        if proc.returncode!=0 or 'result' not in job:raise ValueError('Calculation process exited before producing a result')
        job['status']='complete';job['message']='Calculation completed on the server.'
    except asyncio.CancelledError:
        job.pop('result',None);job['status']='cancelled';job['message']='Calculation cancelled on the server.'
    except TimeoutError:
        job.pop('result',None);job['status']='error';job['message']='Server time limit reached. Reduce the requested calculation.'
    except Exception as exc:
        job.pop('result',None);job['status']='error';job['message']=str(exc)[:1200]
    finally:
        stop_process(proc)
        if proc:
            try:await proc.wait()
            except Exception:pass
        job.pop('process',None);job['updated']=time.monotonic()

@app.middleware('http')
async def require_key(request,call_next):
    if request.url.path!='/health':
        if not KEY:return reply({'error':'Backend is not configured.'},503)
        if not secrets.compare_digest(request.headers.get('x-petromind-key',''),KEY):return reply({'error':'Unauthorized'},401)
    return await call_next(request)

@app.get('/health')
async def health():return reply({'service':'PetroMind scientific server','version':'1.6.0','configured':bool(KEY)})

@app.post('/summary')
async def summary(request:Request):
    if 'application/json' not in request.headers.get('content-type',''):return reply({'error':'JSON is required'},415)
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>3_000_000:return reply({'error':'Summary input exceeds 3 MB'},413)
    try:
        data=json.loads(raw,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        if not isinstance(data,dict) or data.get('kind') not in {'telemetrySummary','telemetrySimulation'}:raise ValueError('Unsupported summary request')
    except (ValueError,RecursionError):return reply({'error':'Invalid summary request'},400)
    if summary_lock.locked():return reply({'error':'Summary server is busy. Retry shortly.'},429)
    async with summary_lock:
        proc=None
        try:
            proc=await asyncio.create_subprocess_exec(os.environ.get('NODE_BINARY','node'),str(ROOT/'server/Server Data.mjs'),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,start_new_session=os.name=='posix')
            out,_=await asyncio.wait_for(proc.communicate(json.dumps(data).encode()),10)
            result=json.loads(out)
            if proc.returncode or 'error' in result:return reply({'error':result.get('error','Summary failed')},400)
            return reply(result['result'])
        except TimeoutError:return reply({'error':'Summary time limit exceeded'},504)
        except (ValueError,OSError):return reply({'error':'Summary service unavailable'},503)
        finally:
            stop_process(proc)
            if proc:await proc.wait()

@app.post('/jobs')
async def create_job(request:Request):
    if 'application/json' not in request.headers.get('content-type',''):return reply({'error':'JSON is required'},415)
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>MAX_BODY:return reply({'error':'Request exceeds 8 MB'},413)
    try:
        data=json.loads(raw,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        if not isinstance(data,dict) or data.get('task') not in TASKS:raise ValueError('Unsupported calculation task')
    except (ValueError,RecursionError):return reply({'error':'Invalid calculation request'},400)
    async with lock:
        cleanup()
        if any(j['status']=='running' for j in jobs.values()):return reply({'error':'The scientific server is busy. Please retry shortly.'},429)
        while len(jobs)>=8:
            oldest=min(jobs,key=lambda k:jobs[k]['updated']);del jobs[oldest]
        token=secrets.token_urlsafe(32);job={'status':'running','message':'Starting server calculation…','updated':time.monotonic()};jobs[token]=job
        job['task']=asyncio.create_task(execute(job,data))
    return reply({'id':token,'status':'running'},202)

@app.get('/jobs/{token}')
async def job_status(token:str):
    cleanup();job=jobs.get(token)
    if not job:return reply({'error':'Job expired or unavailable. Recalculate to start a new job.'},404)
    return reply({k:job[k] for k in ['status','message','result'] if k in job})

@app.delete('/jobs/{token}')
async def cancel_job(token:str):
    job=jobs.get(token)
    if job:
        if job['status']=='running':
            job['task'].cancel()
            try:await job['task']
            except asyncio.CancelledError:pass
            stop_process(job.get('process'))
        jobs.pop(token,None)
    return reply({'status':'cancelled'})

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host=os.environ.get('HOST','0.0.0.0'),port=int(os.environ.get('PORT','10000')),access_log=False,log_level='warning')
