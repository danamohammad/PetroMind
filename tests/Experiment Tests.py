"""Physical invariants for translated volumes and ordered PVT experiments."""
from pathlib import Path
import unittest,runpy,copy,json
root=Path(__file__).resolve().parents[1];e=runpy.run_path(str(root/'public/Fluid Engine.py'));base=runpy.run_path(str(root/'tests/Engine Tests.py'))
class ExperimentTests(unittest.TestCase):
 def req(self):return copy.deepcopy(base['request']())
 def protocol(self):return dict(id='DL test',type='differential',temperature=100,stages=[{'pressure':5000},{'pressure':2500},{'pressure':1000},{'pressure':200},{'pressure':14.7}],observations=[dict(stage=2,Bo=1.2),dict(stage=4,Rs=0)],referenceTemperature=15.56,referencePressure=14.7)
 def test_volume_shift_preserves_vle_and_changes_density(self):
  q=self.req();f,z,*_=e['build'](q);before=e['flash'](f,z,100,1500);p=e['saturation'](f,z,100,0)['pressure']
  for c in q['catalog']:c['volumeShift']=1e-6
  ff,zz,*_=e['build'](q);after=e['flash'](ff,zz,100,1500)
  self.assertAlmostEqual(before['vaporFraction'],after['vaporFraction'],12);self.assertAlmostEqual(p,e['saturation'](ff,zz,100,0)['pressure'],8)
  for phase in ['liquid','gas']:
   self.assertAlmostEqual(before[phase]['volume']-after[phase]['volume'],1e-6,12);self.assertGreater(after[phase]['density'],before[phase]['density'])
 def test_temperature_shift_preserves_equilibrium_at_two_temperatures(self):
  q=self.req();f,z,*_=e['build'](q)
  for c in q['catalog']:c['volumeShiftT']=1e-8
  ff,zz,*_=e['build'](q)
  for t in [40,100]:
   a=e['flash'](f,z,t,1500);b=e['flash'](ff,zz,t,1500)
   self.assertAlmostEqual(a['vaporFraction'],b['vaporFraction'],12)
   self.assertAlmostEqual(a['liquid']['volume']-b['liquid']['volume'],1e-8*(t-25),12)
 def test_depletion_balance_and_residual_reference(self):
  q=self.req();f,z,*_=e['build'](q);out=e['simulate_experiment'](f,z,self.protocol());rows=out['rows']
  self.assertLess(out['balance'],1e-10);self.assertEqual(rows[-1]['Rs'],0)
  self.assertAlmostEqual(sum(r['removedGasMoles'] for r in rows)+rows[-1]['liquidMoles'],1,10)
  self.assertGreater(rows[0]['Rs'],rows[2]['Rs']);self.assertGreater(rows[0]['Bo'],rows[-1]['Bo'])
  flash=e['flash'](f,z,100,200);self.assertGreater(max(abs(a-b) for a,b in zip(rows[3]['liquidComposition'],flash['liquid']['z'])),.001)
 def test_reference_at_final_temperature_makes_bo_one(self):
  q=self.req();f,z,*_=e['build'](q);ex=self.protocol();ex['referenceTemperature']=100
  out=e['simulate_experiment'](f,z,ex);self.assertAlmostEqual(out['rows'][-1]['Bo'],1,7)
 def test_all_stages_remain_in_holdout(self):
  q=self.req();q['experiments']=[self.protocol()];a=e['experiment_comparison'](q);q['experiments'][0]['observations']=[dict(stage=4,Rs=0)];b=e['experiment_comparison'](q)
  self.assertEqual(a['experiments'][0]['rows'],b['experiments'][0]['rows'])
 def test_depletion_rejects_nonmonotone_pressures(self):
  q=self.req();f,z,*_=e['build'](q);ex=self.protocol();ex['stages'][2]['pressure']=4000
  with self.assertRaisesRegex(ValueError,'decreasing'):e['simulate_experiment'](f,z,ex)
 def test_negative_translated_volume_rejected(self):
  q=self.req()
  for c in q['catalog']:c['volumeShift']=.0005
  f,z,*_=e['build'](q)
  with self.assertRaisesRegex(ValueError,'nonpositive'):e['flash'](f,z,100,5000)
 def test_separator_feed_gor_equals_sum_stage_gor(self):
  q=self.req();f,z,*_=e['build'](q);ex=dict(id='separator',type='separator',feed=dict(temperature=100,pressure=5000),stages=[dict(temperature=50,pressure=100),dict(temperature=15.56,pressure=14.7)],observations=[],referencePressure=14.7)
  rows=e['simulate_experiment'](f,z,ex)['rows'];self.assertAlmostEqual(rows[0]['Rs'],sum(r['stageGOR'] for r in rows[1:]),8);self.assertAlmostEqual(rows[-1]['Bo'],1,7)
 def test_lbc_matches_documented_example(self):
  from chemicals.viscosity import Lorentz_Bray_Clarke
  value=Lorentz_Bray_Clarke(T=300,P=1e6,Vm=.0023025,zs=[.4,.3,.3],MWs=[16.04246,30.06904,44.09562],Tcs=[190.564,305.32,369.83],Pcs=[4599000,4872000,4248000],Vcs=[9.86e-5,.0001455,.0002])
  self.assertAlmostEqual(value,9.925488160761484e-6,14)
 def test_reference_curve_uses_training_only_without_extrapolation(self):
  ex=dict(id='measured',type='viscosity',stages=[dict(pressure=p) for p in [5000,4000,3000,2000,1000]],observations=[dict(stage=0,viscosity=5),dict(stage=2,viscosity=3),dict(stage=3,viscosity=2),dict(stage=1,viscosity=99,role='validation'),dict(stage=4,viscosity=1,role='validation')])
  curves,check=e['reference_curves']([ex]);self.assertEqual(len(curves),1);self.assertAlmostEqual(check[0]['predicted'],4);self.assertIsNone(check[1]['predicted'])
 def test_tuning_recovers_translation_without_validation_leakage(self):
  q=self.req();q['lab']=[];ex=self.protocol();ex['observations']=[];q['experiments']=[ex]
  truth=copy.deepcopy(q);next(c for c in truth['catalog'] if c['id']=='C20+')['volumeShift']=.00002
  f,z,*_=e['build'](truth);rows=e['simulate_experiment'](f,z,ex)['rows']
  ex['observations']=[dict(stage=i,density=r['density']) for i,r in enumerate(rows[:3])]+[dict(stage=3,density=9999,role='validation')]
  q['tuningParameters']=[dict(kind='volumeShift',name='C20+',lower=-.00005,upper=.00005)]
  fit=e['tune'](q);self.assertTrue(fit['eligible']);self.assertLess(abs(fit['parameters'][0]['after']/.00002-1),.002);self.assertEqual(len(fit['rows']),3)
if __name__=='__main__':unittest.main(verbosity=2)
