from pathlib import Path
import runpy,json,subprocess,sys
root=Path(__file__).resolve().parents[1]
x=runpy.run_path(str(root/'tests/Engine Tests.py'));req=x['request']();eng=x['e']
worker=root.parent/'Original Source/Extracted Calculation Worker.py'
checks=[]
for name,comp,temp,pres in [('Heavy reservoir',req['composition'],129.44,3450),('Heavy two-phase',req['composition'],129.44,1500),('Gas mixture',[dict(component='C1',fraction=.9),dict(component='C2',fraction=.1)],100,100),('Light two-phase',[dict(component='C1',fraction=.5),dict(component='NC4',fraction=.5)],25,300)]:
 r=dict(req,composition=comp);r['conditions']=dict(req['conditions'],temperature=temp,pressure=pres)
 f,z,names,data=eng['build'](r);modern=eng['flash'](f,z,temp,pres);surface=eng['surface'](f,z,modern,temp,pres,r['conditions'])
 oldreq=dict(task='reservoir',names=names,z=z,pseudo={d['id']:dict(Tc_K=d['Tc'],Pc_atm=d['Pc']/101325,omega=d['omega'],MW_g_mol=d['MW']) for d in data if d['pseudo']},tr=temp,pr=pres,mw=[d['MW']/1000 for d in data],surface_conditions=[25,100,15.56,14.7,15.56,14.7])
 try:
  proc=subprocess.run([sys.executable,str(worker)],input=json.dumps(oldreq),capture_output=True,text=True,timeout=35)
  lines=[s[5:] for s in proc.stdout.splitlines() if s.startswith('PM65:')]
  if not lines:raise RuntimeError((proc.stderr+proc.stdout)[-400:])
  old=json.loads(lines[-1]);pairs={'vaporFraction':(old['reservoir']['vapor'],modern['vaporFraction'])}
  for prop in ['Bo','Rs','Bg']:pairs[prop]=(old['surface'].get(prop),surface.get(prop))
  for phase,key in [('liquid','oil'),('gas','gas')]:
   if modern[phase] and old[key]:pairs[phase+'Density']=(old[key]['density'],modern[phase]['density'])
  checks.append(dict(case=name,values={k:dict(thermopack=a,thermo=b,relativeDifference=None if a is None or b is None or a==0 else abs(b-a)/abs(a),absoluteDifference=None if a is None or b is None else abs(a-b)) for k,(a,b) in pairs.items()}))
 except Exception as e:checks.append(dict(case=name,error=str(e)))
 print(json.dumps(checks[-1],indent=2),flush=True)
(root/'references/ThermoPack Comparison.json').write_text(json.dumps(checks,indent=2))

for check in checks:
 assert 'error' not in check, check
 for name, values in check['values'].items():
  a,b=values['thermopack'],values['thermo']
  assert (a is None)==(b is None), (check['case'],name,values)
  if a is not None: assert abs(a-b)<=max(1e-6,abs(a)*1e-6), (check['case'],name,values)
print('All four independent-engine comparisons passed at 1e-6 tolerance.')
