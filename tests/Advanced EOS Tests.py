"""Regression, continuation and synthetic parameter-recovery tests."""
from pathlib import Path
import runpy,copy,json,unittest
root=Path(__file__).resolve().parents[1]
r=runpy.run_path(str(root/'tests/Engine Tests.py'));e=r['e']
class AdvancedTests(unittest.TestCase):
 def binary(self):
  q=copy.deepcopy(r['request']());q['composition']=[dict(component='C1',fraction=.5),dict(component='NC4',fraction=.5)];return q
 def test_binary_envelope_critical_and_turns(self):
  out=e['envelope'](self.binary());self.assertTrue(out['complete']);self.assertLess(abs(out['critical']['temperature']-100.7426342364),.001);self.assertLess(abs(out['critical']['pressure']-1427.94225),.01)
  self.assertGreater(out['extrema']['cricondentherm']['temperature'],out['critical']['temperature']+5)
  self.assertGreater(out['extrema']['cricondenbar']['pressure'],out['critical']['pressure']+100)
  self.assertEqual(out['endpoints'],['Pressure floor','Pressure floor'])
  for p in out['rows']:
   self.assertLess(p['fugacityResidual'],1e-6);self.assertLess(p['compositionResidual'],1e-7)
   self.assertAlmostEqual(sum(p['liquidComposition']),1,places=7);self.assertAlmostEqual(sum(p['gasComposition']),1,places=7)
 def test_heavy_envelope_complete(self):
  out=e['envelope'](r['request']());self.assertTrue(out['complete']);self.assertGreater(out['extrema']['cricondentherm']['temperature'],450);self.assertLess(abs(out['critical']['temperature']-392.4221),.01)
 def test_temperature_cutoff_is_partial(self):
  q=self.binary();q['envelopeMax']=80;out=e['envelope'](q);self.assertFalse(out['complete']);self.assertIn('Maximum temperature',out['endpoints']);self.assertIsNone(out['critical'])
 def test_synthetic_fit_and_input_preservation(self):
  demo=json.loads((root/'public/Tuning Example.json').read_text());q=demo['input'];q['lab']=demo['lab'];q['tuningParameters']=[dict(kind='kij',name='C1|NC4',lower=-.1,upper=.15)];old=copy.deepcopy(q);out=e['tune'](q)
  self.assertEqual(q,old);self.assertTrue(out['eligible']);self.assertAlmostEqual(out['parameters'][0]['after'],.06,places=5);self.assertGreater(out['improvementPercent'],99.9)
  # Prediction at an unseen pressure, not used to fit.
  true=copy.deepcopy(q);true['interactions']['C1|NC4']=.06;true['lab']=[dict(pressure=2750,temperature=25,density=1)]
  target=e['comparison'](true)['rows'][0]['predicted'];fitted=copy.deepcopy(q);fitted.update(out['candidate']);fitted['lab']=true['lab'];self.assertLess(abs(e['comparison'](fitted)['rows'][0]['predicted']-target),.001)
 def test_duplicate_parameters_and_bounds_rejected(self):
  q=self.binary();q['lab']=[dict(pressure=2000,temperature=25,density=470)]*4;p=dict(kind='kij',name='C1|NC4',lower=-.1,upper=.1);q['tuningParameters']=[p,dict(p,name='NC4|C1')]
  with self.assertRaisesRegex(ValueError,'Duplicate'):e['tune'](q)
  q['tuningParameters']=[dict(p,lower=.1)]
  with self.assertRaisesRegex(ValueError,'Bounds'):e['tune'](q)
 def test_insufficient_measurements_rejected(self):
  q=self.binary();q['lab']=[dict(pressure=2000,temperature=25,density=470)];q['tuningParameters']=[dict(kind='kij',name='C1|NC4',lower=-.1,upper=.1)]
  with self.assertRaisesRegex(ValueError,'at least'):e['tune'](q)
 def test_cce_volume_at_bubble_is_one(self):
  q=self.binary();f,z,*_=e['build'](q);pb=e['saturation'](f,z,25,0)['pressure'];q['lab']=[dict(pressure=pb,temperature=25,relativeVolume=1)]
  out=e['comparison'](q);self.assertAlmostEqual(out['rows'][0]['predicted'],1,places=5)
if __name__=='__main__':unittest.main()
