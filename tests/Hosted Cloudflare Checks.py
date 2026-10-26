"""Verify a deployed HTTPS gateway using public/synthetic data; models run remotely."""
import base64
import copy
import json
import http.client
import io
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = sys.argv[1].rstrip('/')
if not URL.startswith('https://'): raise SystemExit('Supply a deployed HTTPS origin.')

def api(path, value=None, method=None):
    req = urllib.request.Request(URL + path, data=None if value is None else json.dumps(value).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': 'PetroMind deployment verification'}, method=method)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=145) as response: return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'{path}: HTTP {exc.code}: {exc.read().decode()[:800]}') from exc
        except (urllib.error.URLError, http.client.RemoteDisconnected, TimeoutError):
            if req.get_method() not in ('GET','DELETE') or attempt == 2: raise
            time.sleep(2*(attempt+1))

def solve(name, task, **data):
    token = api('/api/jobs', dict(data, task=task))['id']
    try:
        end = time.time() + 160
        while time.time() < end:
            value = api('/api/jobs/' + token)
            if value['status'] == 'complete':
                print(name + ': hosted result returned', flush=True)
                return value['result']
            if value['status'] != 'running': raise AssertionError((name, value))
            time.sleep(3)
        raise AssertionError(name + ': request did not finish')
    finally:
        api('/api/jobs/' + token, method='DELETE')

status = api('/api/status')
assert status['scientificConfigured'] and status['assistantConfigured'] and status['execution'] == 'hosted'
print('Hosted gateway configured:', status['version'], flush=True)

base = json.loads((ROOT/'public/Fluid Catalog.json').read_text())
q = dict(catalog=base['catalog'], interactions=base['interactions'], composition=base['sample'], model='PR',
    conditions=dict(temperature=129.44, pressure=3450, separatorTemperature=25, separatorPressure=100,
    tankTemperature=15.56, tankPressure=14.7, standardTemperature=15.56, standardPressure=14.7,
    minPressure=100, maxPressure=6000, points=12))
nodal = dict(pr=4000,pb=100,pi=1,whp=250,tvd=1500,length=1700,diameter=.076,roughness=.000045,
    density=820,viscosity=2,fvf=1.2,ipr='linear',vlp='liquid')
if '--remaining' not in sys.argv[2:]:
    result = solve('PVT', 'calculate', **q)
    expected = json.loads((ROOT/'references/Sample Results.json').read_text())
    assert result['state']['balance'] < 1e-8 and result['surface']['balance'] < 1e-8
    for key in ['Bo', 'Rs']:
        assert abs(result['surface'][key]-expected['surface'][key]) < 1e-6*max(abs(expected['surface'][key]),1)

    binary = dict(q, composition=[dict(component='C1', fraction=.5), dict(component='NC4', fraction=.5)])
    result = solve('Binary envelope', 'envelope', **binary)
    assert result['complete'] and abs(result['critical']['temperature']-100.7426342364) < .001
    assert all(row['fugacityResidual'] < 1e-6 for row in result['rows'])
    result = solve('Heavy-fluid envelope', 'envelope', **q)
    assert result['complete'] and abs(result['critical']['temperature']-392.4221) < .01

    demo = json.loads((ROOT/'public/Tuning Example.json').read_text())
    result = solve('EOS tuning', 'tune', **dict(demo['input'], lab=demo['lab'],
        tuningParameters=[dict(kind='kij', name='C1|NC4', lower=-.1, upper=.15)]))
    assert result['eligible'] and abs(result['parameters'][0]['after']-.06) < 1e-5

    studies = json.loads((ROOT/'public/Physical Model Studies.json').read_text())
    result = solve('Brine', 'physical', study=studies[0])
    assert all(abs(c['error']) < (.000051 if c['property']=='viscosity' else .25) for c in result['checks'])
    for name, study, tolerance in [('Wax', studies[1], .20), ('Asphaltene', studies[3], .024)]:
        result = solve(name+' fit', 'physical', study=study, action='fit')
        assert result['fit']['eligible']
        assert next(x for x in result['metrics'] if x['role']=='validation')['rmse'] < tolerance

    core = dict(swc=.2,sor=.2,krwEnd=.4,kroEnd=.9,nw=3,no=2,entry=3,lam=2,muWater=1,muOil=3,
        length=5,diameter=3.8,poreVolume=12,flow=2,deltaPressure=.1,coreViscosity=1)
    result = solve('Core', 'engineering', kind='core', parameters=core)
    assert abs(result['summary']['liquidPermeabilityMd']-148.904654339) < 1e-6
    result = solve('Nodal', 'engineering', kind='nodal', parameters=nodal)
    assert len(result['operatingPoints']) == 1 and abs(result['operatingPoints'][0]['residualPsi']) < 1e-7
result = solve('Optimization', 'engineering', kind='optimize', parameters=dict(nodal,
    minWhp=150,maxWhp=500,minDiameter=.06,maxDiameter=.1,maxVelocity=5,maxRate=3000,maxDrawdown=2500))
assert result['summary']['feasibleScenarios'] > 0

rows = [dict(date=str(date(2026,1,1)+timedelta(days=i)),oil_rate=1200/(1+.55*.003*i)**(1/.55),
    water_rate=100,injection_rate=50,pressure=4000) for i in range(40)]
for kind in ['history','forecast']:
    result = solve(kind, 'engineering', kind=kind, rows=rows,
        parameters=dict(method='hyperbolic',horizon=30,terminal=.0001,capacity=2000,economic=0))
    assert abs(result['summary']['b']-.55) < 1e-4
ml = []
for i in range(100):
    p=3000+150*math.sin(i*.7);t=80+5*math.cos(i*.31);c=50+15*math.sin(i*.17)
    ml.append(dict(timestamp=f'2026-01-01T{i//60:02d}:{i%60:02d}:00Z',pressure=p,temperature=t,
        choke=c,oil_rate=600+.2*(p-3000)+4*(t-80)+8*(c-50)))
result = solve('Predictor training', 'engineering', kind='learning', rows=ml,
    parameters=dict(pressure=3000,temperature=80,choke=50))
assert result['metrics'][0]['RMSE'] < .1 and abs(result['summary']['predictionStbDay']-600) < .1

result = api('/api/summary', dict(kind='pressureProfile', rows=[dict(depth=0,pressure=200,temperature=25),
    dict(depth=1000,pressure=560,temperature=55)]))
assert abs(result['summary']['pressureGradientPsiM']-.36) < 1e-12
result = api('/api/summary', dict(kind='telemetrySimulation', index=0))
assert result['well'].startswith('SIMULATED')
result = solve('CSV import', 'import', filename='Public Check.csv',
    data=base64.b64encode(b'Component,Mole Fraction\nC1,0.8\nC2,0.2').decode())
assert len(result['rows']) == 2

# This creates a file fixture only; all parsing is performed by the hosted service.
from openpyxl import Workbook
book=Workbook();sheet=book.active
sheet.append(['date','oil_rate']);sheet.append([date(2026,1,1),1200]);sheet.append([date(2026,1,2),1100])
buffer=io.BytesIO();book.save(buffer);book.close()
result = solve('Excel import', 'import', filename='Public Check.xlsx', data=base64.b64encode(buffer.getvalue()).decode())
assert result['rows']==[{'date':'2026-01-01','oil_rate':1200},{'date':'2026-01-02','oil_rate':1100}]

answer = api('/api/assistant', dict(question='What is held-out validation?', context=''))
assert answer['execution'] == 'hosted' and len(answer['answer']) > 10
print('Hosted AI:', answer['model'], 'on', answer['provider'], flush=True)
print('All hosted checks passed.', flush=True)
