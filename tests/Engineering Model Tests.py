import unittest, importlib.util, math, copy
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('engineering',Path(__file__).resolve().parents[1]/'public/Engineering Models.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
CORE=dict(swc=.2,sor=.2,krwEnd=.4,kroEnd=.9,nw=3,no=2,entry=3,lam=2,muWater=1,muOil=3,length=5,diameter=3.8,poreVolume=12,flow=2,deltaPressure=.1,coreViscosity=1)
NODAL=dict(pr=4000,pb=100,pi=1,whp=250,tvd=1500,length=1700,diameter=.076,roughness=.000045,density=820,viscosity=2,fvf=1.2,ipr='linear',vlp='liquid')
def history():return [dict(date=f'2026-{1+i//28:02d}-{1+i%28:02d}',oil_rate=float(m.decline_rate(i if i<28 else i+3,1200,.003,.55)),water_rate=100,injection_rate=50,pressure=4000) for i in range(40)]
def mlrows():
 rows=[]
 for i in range(100):
  p=3000+150*math.sin(i*.7);t=80+5*math.cos(i*.31);c=50+15*math.sin(i*.17)
  rows.append(dict(timestamp=f'2026-01-01T{(i//60):02d}:{i%60:02d}:00Z',pressure=p,temperature=t,choke=c,oil_rate=600+.2*(p-3000)+4*(t-80)+8*(c-50)))
 return rows
class EngineeringTests(unittest.TestCase):
 def test_core_cylinder_and_darcy_units(self):
  r=m.scal(CORE,[],'calculate');self.assertAlmostEqual(r['summary']['porosityFraction'],12/(math.pi*3.8**2/4*5));self.assertAlmostEqual(r['summary']['liquidPermeabilityMd'],148.904654339,places=6)
 def test_scal_endpoints_and_pc_singularity(self):
  r=m.scal(CORE,[],'calculate')['rows'];self.assertEqual(r[0]['krw'],0);self.assertAlmostEqual(r[0]['kro'],.9);self.assertIsNone(r[0]['pc']);self.assertAlmostEqual(r[-1]['krw'],.4);self.assertAlmostEqual(r[-1]['kro'],0);self.assertTrue(all(0<=a['waterFractionalFlow']<=1 for a in r))
 def test_scal_invalid_pore_volume(self):
  with self.assertRaises(ValueError):m.scal({**CORE,'poreVolume':100},[],'calculate')
 def test_scal_fitting_and_heldout_isolation(self):
  rows=[]
  for i in range(13):
   sw=.23+.045*i;se=(sw-.2)/.6;rows.append(dict(sw=sw,krw=.45*se**2.6,kro=.85*(1-se)**2.2,pc=3.4*((sw-.2)/.8)**(-1/1.8),role='validation' if i%4==3 else 'training'))
  fit=m.scal(CORE,rows,'fit');self.assertTrue(fit['fit']['eligible']);self.assertAlmostEqual(fit['parameters']['nw'],2.6,places=4)
  altered=copy.deepcopy(rows)
  for row in altered:
   if row['role']=='validation':row['pc']*=4
  other=m.scal(CORE,altered,'fit');self.assertEqual(fit['parameters'],other['parameters'])
 def test_ipr_limits_and_vogel_join(self):
  p={**NODAL,'ipr':'composite','pb':2500};self.assertEqual(m.ipr(p,4000),0);self.assertAlmostEqual(m.ipr(p,2500),1500);self.assertAlmostEqual(m.ipr(p,2499.999),1500.001,places=5);self.assertAlmostEqual(m.ipr(p,0),1500+2500/1.8)
 def test_hydrostatic_no_friction_at_zero(self):
  r=m.liquid_vlp(NODAL,0);self.assertEqual(r['frictionPsi'],0);self.assertAlmostEqual(r['pwf'],250+820*9.80665*1500/6894.757293168)
 def test_nodal_root_balance(self):
  r=m.nodal(NODAL,[]);self.assertEqual(len(r['operatingPoints']),1);self.assertLess(abs(r['operatingPoints'][0]['residualPsi']),1e-7)
 def test_nodal_shut_in_no_solution(self):self.assertEqual(m.nodal({**NODAL,'pr':500},[])['operatingPoints'],[])
 def test_liquid_rejects_liberated_gas(self):
  with self.assertRaises(ValueError):m.nodal({**NODAL,'pb':500},[])
 def test_measured_no_extrapolation(self):
  r=m.nodal({**NODAL,'vlp':'measured'},[dict(rate=0,pwf=100),dict(rate=100,pwf=200)]);self.assertEqual(r['operatingPoints'],[]);self.assertLessEqual(max(v['rate'] for v in r['rows']),100)
 def test_optimization_constraints(self):
  r=m.optimize({**NODAL,'minWhp':150,'maxWhp':500,'minDiameter':.06,'maxDiameter':.1,'maxVelocity':5,'maxRate':3000,'maxDrawdown':2500});self.assertEqual(len(r['rows']),81);self.assertTrue(r['summary']['feasibleScenarios']>0);self.assertTrue(all(v['velocity']<=5 and v['rate']<=3000 for v in r['rows'] if v['feasible']))
 def test_arps_limits(self):
  self.assertAlmostEqual(float(m.decline_rate(100,1000,.01,0)),1000/math.e);self.assertAlmostEqual(float(m.decline_rate(100,1000,.01,1)),500)
 def test_terminal_switch_continuity(self):
  switch=(.01/.001-1)/(.5*.01);a=float(m.decline_rate(switch-1e-4,1000,.01,.5,.001));b=float(m.decline_rate(switch+1e-4,1000,.01,.5,.001));self.assertLess(abs(a-b),.001)
 def test_history_recovery_and_no_validation_leak(self):
  p=dict(method='hyperbolic',horizon=30,terminal=.0001,capacity=2000,economic=0);rows=history();r=m.history(p,rows);self.assertAlmostEqual(r['summary']['b'],.55,places=4);changed=copy.deepcopy(rows)
  for v in changed[32:]:v['oil_rate']*=3
  b=m.history(p,changed);self.assertEqual(r['summary']['qiStbDay'],b['summary']['qiStbDay']);self.assertEqual(r['summary']['b'],b['summary']['b']);self.assertGreater(b['metrics'][1]['RMSE'],r['metrics'][1]['RMSE'])
 def test_forecast_capacity_and_economic_limit(self):
  r=m.history(dict(method='exponential',horizon=30,terminal=0,capacity=100,economic=101),history());self.assertTrue(all(v['forecastRate']==0 for v in r['forecast']));self.assertEqual(r['summary']['forecastVolumeStb'],0)
 def test_tank_storage_recovery(self):
  rows=history();base=m.time_rows(rows);net=0;last=None
  for row in base:
   rate=row['oil_rate']*1.2+50
   if last:net+=(rate+last[1])/2*(row['day']-last[0])
   last=(row['day'],rate);row['pressure']=4000-net/100
  r=m.history(dict(method='tank',bo=1.2,bw=1,ct=.00002),base);self.assertAlmostEqual(r['summary']['storageRbPerPsi'],100,places=4);self.assertAlmostEqual(r['summary']['poreVolumeRbGivenCt'],5000000,places=1)
 def test_duplicate_dates_rejected(self):
  with self.assertRaises(ValueError):m.history(dict(method='exponential'),[history()[0]]*10)
 def test_ridge_recovery_and_temporal_split(self):
  r=m.machine_learning(dict(pressure=3000,temperature=80,choke=50),mlrows());self.assertLess(r['metrics'][0]['RMSE'],.1);self.assertAlmostEqual(r['summary']['predictionStbDay'],600,places=1);self.assertTrue(r['summary']['beatsBaseline']);self.assertEqual(r['summary']['validationRows'],20)
 def test_ridge_holdout_cannot_change_model(self):
  rows=mlrows();a=m.machine_learning(dict(pressure=3000,temperature=80,choke=50),rows)
  for r in rows[80:]:r['oil_rate']*=10
  b=m.machine_learning(dict(pressure=3000,temperature=80,choke=50),rows);self.assertEqual(a['model'],b['model'])
 def test_ridge_extrapolation_refused(self):
  r=m.machine_learning(dict(pressure=5000,temperature=80,choke=50),mlrows());self.assertIsNone(r['summary']['predictionStbDay'])
 def test_json_serializable(self):
  import json
  json.dumps(m.nodal(NODAL,[]),allow_nan=False);json.dumps(m.scal(CORE,[],'calculate'),allow_nan=False)
if __name__=='__main__':unittest.main()
