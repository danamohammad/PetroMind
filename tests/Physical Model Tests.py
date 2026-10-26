import unittest,runpy,json,copy,math
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[1];e=runpy.run_path(str(root/'public/Physical Models.py'));studies=json.loads((root/'public/Physical Model Studies.json').read_text());run=e['physical_dispatch']
class PhysicalTests(unittest.TestCase):
 def test_brine_published_table_rounding(self):
  r=run(dict(study=studies[0]))
  for c in r['checks']:
   self.assertLess(abs(c['error']),.000051 if c['property']=='viscosity' else .25)
 def test_brine_derivative_and_reference(self):
  f=e['brine'];r=f(80,20,2);dp=.001
  derivative=(1/f(80,20+dp,2)['density']-1/f(80,20-dp,2)['density'])/(2*dp)
  self.assertAlmostEqual(-derivative*r['density'],r['compressibility'],places=10)
  self.assertEqual(f(20,.1,2)['Bw'],1)
  self.assertGreater(r['density'],f(80,20,0)['density'])
 def test_brine_domain_rejected(self):
  for args in [(19,1,1),(25,36,1),(25,1,6.1),(150,.1,1),('',1,1),(True,1,1)]:
   with self.assertRaises(ValueError):e['brine'](*args)
 def test_brine_fit_recovers_synthetic_scales(self):
  s=copy.deepcopy(studies[0]);s['observations']=[]
  for i,t in enumerate([30,50,80,110,140]):
   r=e['brine'](t,20,2,1.015,.975)
   for prop in ['density','viscosity']:s['observations'].append(dict(temperature=t,pressure=20,molality=2,property=prop,measured=r[prop],role='validation' if i==2 else 'training'))
  out=run(dict(study=s,action='fit'));self.assertTrue(out['fit']['eligible']);self.assertAlmostEqual(out['fit']['parameters']['densityScale'],1.015,places=7);self.assertAlmostEqual(out['fit']['parameters']['viscosityScale'],.975,places=7)
  self.assertTrue(all(m['rmse']<1e-6 for m in out['metrics']))
 def test_reference_rows_cannot_train(self):
  with self.assertRaisesRegex(ValueError,'training'):run(dict(study=studies[0],action='fit'))
 def test_wax_binary_analytic_lever_rule(self):
  s=studies[1];c=s['components'];r=e['wax_state'](c,30);z=(.1/c[1]['MW'])/(.1/c[1]['MW']+.9/c[0]['MW']);k=math.exp(c[1]['H']/e['R']*(1/c[1]['Tm']-1/303.15));L=(1-z)/(1-k)
  self.assertAlmostEqual(r['liquidMoleFraction'],L,places=11)
 def test_wax_multisolid_conservation(self):
  c=copy.deepcopy(studies[1]['components']);c[0]['massFraction']=.8;c.append(dict(studies[2]['components'][1],massFraction=.1))
  r=e['wax_state'](c,30);self.assertLess(r['balance'],1e-12);self.assertTrue(all(x['solidMoles']>0 for x in r['components'][1:]));self.assertAlmostEqual(sum(x['liquidComposition'] for x in r['components']),1,places=10)
  for x in r['components']:self.assertAlmostEqual(x['feedMoles'],x['liquidMoles']+x['solidMoles'],places=13)
 def test_wax_onset_and_pressure_sign(self):
  c=copy.deepcopy(studies[1]['components']);wat=e['wax_onset'](c)
  self.assertLess(e['wax_state'](c,wat+.01)['waxMassPercent'],1e-10);self.assertGreater(e['wax_state'](c,wat-.01)['waxMassPercent'],0)
  c[1]['deltaV']=-1e-5;self.assertGreater(e['wax_onset'](c,20),e['wax_onset'](c,.1))
 def test_wax_held_out_calibration(self):
  for s,limit in zip(studies[1:3],[.20,.41]):
   out=run(dict(study=s,action='fit'));self.assertTrue(out['fit']['eligible']);v=next(m for m in out['metrics'] if m['role']=='validation');self.assertLess(v['rmse'],limit)
 def test_validation_does_not_enter_fit(self):
  s=copy.deepcopy(studies[1]);a=run(dict(study=s,action='fit'))
  for o in s['observations']:
   if o['role']=='validation':o['measured']+=30
  b=run(dict(study=s,action='fit'));self.assertEqual(a['fit']['parameters'],b['fit']['parameters'])
 def test_fh_stability_and_symmetry(self):
  self.assertIsNone(e['fh_binodal'](10,.1))
  for N,chi in [(2,2),(20,.8),(100,2),(18.4137749278,.7606018178)]:
   b=e['fh_binodal'](N,chi);self.assertLess(b['residual'],1e-7);self.assertLess(b['lean'],b['rich'])
   def gp(x):return (math.log(x)+1)/N-math.log1p(-x)-1+chi*(1-2*x)
   self.assertAlmostEqual(gp(b['lean']),gp(b['rich']),places=6)
 def test_asphaltene_material_and_gibbs(self):
  s=studies[3];r=run(dict(study=s));self.assertTrue(any(x['richPhaseVolumeFraction']>0 for x in r['rows']))
  for x in r['rows']:
   self.assertLess(x['balance'],1e-10);self.assertGreaterEqual(x['gibbsReduction'],-1e-10);self.assertTrue(0<=x['asphalteneSeparatedPercent']<=100+1e-8)
   if x['richPhaseVolumeFraction']>0:self.assertLess(x['richVolumeFraction'],1)
 def test_asphaltene_fit_and_heldout(self):
  r=run(dict(study=studies[3],action='fit'));self.assertTrue(r['fit']['eligible']);self.assertEqual(r['fit']['rank'],2);self.assertLess(next(x for x in r['metrics'] if x['role']=='validation')['rmse'],.024)
 def test_asphaltene_onset_preserves_stock(self):
  p=studies[3]['parameters'];r=e['asph_onset'](.02,'heptane',**p);w=r['precipitantMassFraction'];state=e['asph_state'](w,.02*(1-w),'heptane',**p);self.assertAlmostEqual(state['onsetResidual'],0,places=6)
 def test_bad_composition_and_roles_rejected(self):
  s=copy.deepcopy(studies[1]);s['components'][0]['massFraction']=.8
  with self.assertRaises(ValueError):run(dict(study=s))
  s=copy.deepcopy(studies[3]);s['conditions']['pressure']=20
  with self.assertRaises(ValueError):run(dict(study=s))
  s=copy.deepcopy(studies[1]);s['observations'][0]['role']='train'
  with self.assertRaises(ValueError):run(dict(study=s))
 def test_worker_dispatch_json(self):
  engine=runpy.run_path(str(root/'public/Fluid Engine.py'));engine['dispatch_json'].__globals__['physical_dispatch']=run
  out=json.loads(engine['dispatch_json'](json.dumps(dict(task='physical',study=studies[0]))));self.assertEqual(out['kind'],'brine')
if __name__=='__main__':unittest.main()
