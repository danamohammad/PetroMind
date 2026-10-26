"""Exercise the actual HTTP API, isolated solver, authorization and cancellation."""
import asyncio, importlib.util, json, os, sys, tempfile, unittest
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]

def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class HostedServerTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.server=load(ROOT/'server/Scientific Server.py','server_test');self.server.KEY='test-only-key'
  self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.server.app),base_url='http://test',headers={'x-petromind-key':'test-only-key'})
 async def asyncTearDown(self):
  for job in list(self.server.jobs.values()):
   if job['status']=='running':job['task'].cancel()
  await asyncio.gather(*(j['task'] for j in self.server.jobs.values()),return_exceptions=True)
  await self.client.aclose()
 async def finish(self,data):
  response=await self.client.post('/jobs',json=data);self.assertEqual(response.status_code,202,response.text);token=response.json()['id']
  for _ in range(1500):
   response=await self.client.get('/jobs/'+token);job=response.json()
   if job['status']!='running':self.assertEqual(job['status'],'complete',job);return job['result']
   await asyncio.sleep(.02)
  self.fail('Test job did not finish')
 async def test_missing_or_wrong_key_is_rejected(self):
  self.assertEqual((await self.client.post('/jobs',json={},headers={'x-petromind-key':'wrong'})).status_code,401)
  self.server.KEY='';self.assertEqual((await self.client.post('/jobs',json={})).status_code,503)
  self.assertEqual((await self.client.get('/health')).status_code,200)
 async def test_unknown_task_and_nonfinite_json_rejected(self):
  self.assertEqual((await self.client.post('/jobs',json={'task':'execute','code':'print(1)'})).status_code,400)
  self.assertEqual((await self.client.post('/jobs',content='{"task":"data","x":NaN}',headers={'content-type':'application/json'})).status_code,400)
 async def test_body_limit_and_media_type(self):
  self.server.MAX_BODY=20
  self.assertEqual((await self.client.post('/jobs',json={'task':'calculate','data':'long'})).status_code,413)
  self.assertEqual((await self.client.post('/jobs',content='hello')).status_code,415)
 async def test_pressure_survey_server_result(self):
  r=await self.finish({'task':'data','kind':'pressureProfile','rows':[{'depth':0,'pressure':200,'temperature':25},{'depth':1000,'pressure':560,'temperature':55}]})
  self.assertAlmostEqual(r['summary']['pressureGradientPsiM'],.36);self.assertAlmostEqual(r['summary']['temperatureGradientCPer100M'],3)
 async def test_scientific_backend_matches_pvt_engine(self):
  base=json.loads((ROOT/'public/Fluid Catalog.json').read_text());req=dict(task='calculate',catalog=base['catalog'],interactions=base['interactions'],composition=base['sample'],model='PR',conditions=dict(temperature=129.44,pressure=3450,separatorTemperature=25,separatorPressure=100,tankTemperature=15.56,tankPressure=14.7,standardTemperature=15.56,standardPressure=14.7,minPressure=100,maxPressure=6000,points=8))
  engine=load(ROOT/'public/Fluid Engine.py','engine_test');expected=json.loads(engine.dispatch_json(json.dumps(req)));result=await self.finish(req)
  self.assertEqual(result,expected)
 async def test_invalid_calculation_reports_error_without_result(self):
  r=await self.client.post('/jobs',json={'task':'engineering','module':'not_a_module'});token=r.json()['id']
  await self.server.jobs[token]['task'];j=(await self.client.get('/jobs/'+token)).json();self.assertEqual(j['status'],'error');self.assertNotIn('result',j)
 async def test_summary_checks_use_validated_observations(self):
  r=await self.client.post('/summary',json={'kind':'telemetrySummary','well':'A','rows':[{'timestamp':'2020-01-01T00:00:00Z','well':'A','pressure':5000}],'limits':{'low':0,'high':4000,'stale':60}})
  self.assertEqual(r.status_code,200,r.text);self.assertIn('Stale data',r.json()['flags']);self.assertIn('Pressure outside configured limits',r.json()['flags'])
  self.assertEqual((await self.client.post('/summary',json={'kind':'pressureProfile','rows':[]})).status_code,400)
 async def test_cancellation_kills_process_and_busy_rejects(self):
  with tempfile.TemporaryDirectory() as directory:
   folder=Path(directory)/'server';folder.mkdir();(folder/'Calculation Process.py').write_text('import time,json\nprint(json.dumps({"progress":"waiting"}),flush=True)\ntime.sleep(30)\n')
   self.server.ROOT=Path(directory);response=await self.client.post('/jobs',json={'task':'data'});token=response.json()['id']
   while 'process' not in self.server.jobs[token]:await asyncio.sleep(.01)
   proc=self.server.jobs[token]['process'];self.assertEqual((await self.client.post('/jobs',json={'task':'data'})).status_code,429)
   self.assertEqual((await self.client.delete('/jobs/'+token)).status_code,200);self.assertIsNotNone(proc.returncode);self.assertEqual((await self.client.get('/jobs/'+token)).status_code,404)
 async def test_timeout_terminates_process(self):
  with tempfile.TemporaryDirectory() as directory:
   folder=Path(directory)/'server';folder.mkdir();(folder/'Calculation Process.py').write_text('import time\ntime.sleep(30)\n');self.server.ROOT=Path(directory);self.server.MAX_SECONDS=.05
   r=await self.client.post('/jobs',json={'task':'data'});j=self.server.jobs[r.json()['id']];await j['task'];self.assertEqual(j['status'],'error');self.assertIn('time limit',j['message']);self.assertNotIn('process',j)
 async def test_result_expiration_and_no_cache(self):
  self.server.jobs['expired']={'status':'complete','updated':0,'result':{'private':'value'}}
  r=await self.client.get('/jobs/expired');self.assertEqual(r.status_code,404);self.assertEqual(r.headers['cache-control'],'no-store')
if __name__=='__main__':unittest.main()
