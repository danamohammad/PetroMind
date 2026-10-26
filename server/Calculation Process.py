"""Isolated server calculation process; input is data, never executable code."""
import json, sys, os, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'public'

def calculate(req):
    if req.get('task')=='data':
        run=subprocess.run([os.environ.get('NODE_BINARY','node'),str(ROOT/'server/Server Data.mjs')],input=json.dumps(req),text=True,capture_output=True,timeout=30,check=False)
        if run.returncode:raise ValueError('Data calculation process failed')
        message=json.loads(run.stdout)
        if message.get('error'):raise ValueError(message['error'])
        return message['result']
    scope={'__name__':'petromind_engine'}
    for filename,key in [('Physical Models.py','physical_dispatch'),('Engineering Models.py','engineering_dispatch')]:
        module={};exec(compile((PUBLIC/filename).read_text(),filename,'exec'),module);scope[key]=module[key]
    scope['progress_callback']=lambda message: print(json.dumps({'progress':str(message)[:300]}),flush=True)
    exec(compile((PUBLIC/'Fluid Engine.py').read_text(),'Fluid Engine.py','exec'),scope)
    return json.loads(scope['dispatch_json'](json.dumps(req)))

if __name__=='__main__':
    try:
        request=json.loads(sys.stdin.read(8_000_001))
        result=calculate(request)
        print(json.dumps({'result':result},allow_nan=False),flush=True)
    except Exception as exc:
        print(json.dumps({'error':str(exc)[:1200]}),flush=True)
