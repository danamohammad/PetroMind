"""Independent native ThermoPack reference for the browser continuation solver."""
from pathlib import Path
import runpy,copy,json,numpy as np
from thermopack.cubic import cubic
root=Path(__file__).resolve().parents[1];r=runpy.run_path(str(root/'tests/Engine Tests.py'));e=r['e'];checks=[]
for title,model in [('Binary PR','PR'),('Binary SRK','SRK'),('Heavy PR','PR')]:
 q=copy.deepcopy(r['request']());q['model']=model
 if title.startswith('Binary'):q['composition']=[dict(component='C1',fraction=.5),dict(component='NC4',fraction=.5)]
 f,z,names,data=e['build'](q);tp=cubic();tp.init(','.join('PSEUDO' if c['pseudo'] else c['id'] for c in data),eos=model)
 if any(c['pseudo'] for c in data):
  tp.init_pseudo(','.join('PM'+str(i) if c['pseudo'] else '/' for i,c in enumerate(data)),np.array([c['Tc'] if c['pseudo'] else 0 for c in data]),np.array([c['Pc'] if c['pseudo'] else 0 for c in data]),np.array([c['omega'] if c['pseudo'] else 0 for c in data]),np.array([c['MW']/1000 if c['pseudo'] else 0 for c in data]))
 for i,a in enumerate(names):
  for j,b in enumerate(names):
   if j>i:tp.set_kij(i+1,j+1,q['interactions'].get(a+'|'+b,q['interactions'].get(b+'|'+a,0)))
 out=e['envelope'](q);assert out['complete'],(title,out['note'])
 tc,vc,pc=tp.critical(z);Ts,Ps=tp.get_envelope_twophase(14.7*e['PSI'],z,maximum_pressure=30000*e['PSI'],step_size_factor=.15)
 check=dict(case=title,criticalTemperatureDifferenceK=abs(tc-(out['critical']['temperature']+273.15)),criticalPressureDifferencePsia=abs(pc/e['PSI']-out['critical']['pressure']),maximumTemperatureDifferenceK=abs(max(Ts)-(out['extrema']['cricondentherm']['temperature']+273.15)),maximumPressureDifferencePsia=abs(max(Ps)/e['PSI']-out['extrema']['cricondenbar']['pressure']),browserPoints=len(out['rows']),referencePoints=len(Ts))
 print(check,flush=True);checks.append(check)
 assert check['criticalTemperatureDifferenceK']<.02 and check['criticalPressureDifferencePsia']<.1
 assert check['maximumTemperatureDifferenceK']<2 and check['maximumPressureDifferencePsia']<10
(root/'references/Envelope Comparison.json').write_text(json.dumps(checks,indent=2)+'\n')
