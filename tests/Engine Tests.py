from pathlib import Path
import runpy,json,time,unittest
root=Path(__file__).resolve().parents[1]
e=runpy.run_path(str(root/'public/Fluid Engine.py'))
base=json.loads((root/'public/Fluid Catalog.json').read_text())
def request():
 return dict(catalog=base['catalog'],interactions=base['interactions'],composition=base['sample'],model='PR',conditions=dict(temperature=129.44,pressure=3450,separatorTemperature=25,separatorPressure=100,tankTemperature=15.56,tankPressure=14.7,standardTemperature=15.56,standardPressure=14.7,minPressure=100,maxPressure=6000,points=12))
class EngineTests(unittest.TestCase):
 def test_composition_rejects_bad_total(self):
  r=request();r['composition']=[dict(component='C1',fraction=.5),dict(component='C2',fraction=.3)]
  with self.assertRaisesRegex(ValueError,'total'): e['build'](r)
 def test_duplicate_rejected(self):
  r=request();r['composition']=[dict(component='C1',fraction=.5),dict(component='C1',fraction=.5)]
  with self.assertRaisesRegex(ValueError,'Duplicate'): e['build'](r)
 def test_blank_numeric_rejected(self):
  with self.assertRaises(ValueError): e['finite']('', 'input')
 def test_heavy_sample_and_balances(self):
  r=request();t=time.time();out=e['calculate'](r)
  print('\nSample runtime',time.time()-t,'state',out['state']['phase'],'vapor fraction',out['state']['vaporFraction'],'Bo',out['surface']['Bo'],'Rs',out['surface']['Rs'],'saturation',out['saturation'])
  self.assertLess(out['state']['balance'],1e-8)
  self.assertGreater(out['surface']['Bo'],0)
  self.assertLess(out['surface']['balance'],1e-8)
  self.assertTrue(all('error' not in row for row in out['sweep']))
  (root/'references/Sample Results.json').write_text(json.dumps(out,indent=2))
 def test_gas_does_not_invent_oil(self):
  r=request();r['composition']=[dict(component='C1',fraction=.9),dict(component='C2',fraction=.1)];r['conditions']['pressure']=100
  f,z,*_=e['build'](r);s=e['flash'](f,z,100,100);p=e['surface'](f,z,s,100,100,r['conditions'])
  self.assertEqual(s['phase'],'Vapor');self.assertIsNone(p['Bo']);self.assertIsNone(p['Rs']);self.assertGreater(p['Bg'],0)
 def test_lab_missing_property_and_zero_measured(self):
  r=request();r['lab']=[dict(pressure=3450,Bo=0)]
  o=e['comparison'](r);self.assertIsNone(o['rows'][0]['relativeError']);self.assertIsNone(o['metrics'][0]['AARD'])
 def test_import_is_data_not_code(self):
  import base64
  r=dict(filename='sample.csv',data=base64.b64encode(b'Component,Mole Fraction\nC1,0.8\nC2,0.2').decode())
  o=e['read_file'](r);self.assertEqual(len(o['rows']),2)
 def test_saturation_rejects_supercritical_trivial_root(self):
  r=request();r['composition']=[dict(component='C1',fraction=.5),dict(component='NC4',fraction=.5)]
  f,z,*_=e['build'](r);s=e['saturation'](f,z,400,0)
  self.assertIsNone(s['pressure']);self.assertTrue(s['error'])
 def test_excel_preserves_dates_and_zero(self):
  import base64,io,openpyxl,datetime
  book=openpyxl.Workbook();sheet=book.active;sheet.append(['date','oil_rate','water_rate']);sheet.append([datetime.date(2026,1,1),1000,0]);buf=io.BytesIO();book.save(buf)
  req=dict(task='import',filename='Production.xlsx',data=base64.b64encode(buf.getvalue()).decode())
  out=json.loads(e['dispatch_json'](json.dumps(req)))
  self.assertEqual(out['rows'][0],{'date':'2026-01-01','oil_rate':1000,'water_rate':0})
if __name__=='__main__':unittest.main(verbosity=2)
