import unittest,datetime as dt
import menu_control as m
class MenuSessionTest(unittest.TestCase):
 def setUp(self):
  self.now=dt.datetime(2026,11,3,12,tzinfo=dt.timezone.utc)
  self.old=dict(date='2026-11-03',timezone='Europe/Belgrade',baseline=235)
  self.state=dict(completed={'old':dict(actual=84,start='2026-11-03T07:57:00Z',end='2026-11-03T07:58:00Z')},skipped={})
 def test_preserves_confirmed_and_exact_budget(self):
  p=m.session_plan(self.old,self.state,8000,80,self.now,'test')
  self.assertEqual(p['target'],8319)
  self.assertEqual(p['session']['baseline'],319)
  self.assertEqual(sum(b['steps'] for b in p['batches'])+p['baseline'],8319)
  self.assertEqual(p['batches'][0]['scenario_id'],'old')
  new=p['batches'][1:]
  self.assertEqual(len(new),80)
  self.assertAlmostEqual(sum(b["distance_m"] for b in new),5600)
  self.assertAlmostEqual(sum(b["active_kcal"] for b in new),320)
  self.assertNotIn("distance_m",p["batches"][0])
  for a,b in zip(new,new[1:]):self.assertEqual(a['end'],b['start'])
 def test_invalid_or_cross_midnight(self):
  for steps,mins in [(0,80),(8000,0),(8000,1)]:
   with self.assertRaises(ValueError):m.session_plan(self.old,self.state,steps,mins,self.now,'x')
  with self.assertRaises(ValueError):m.session_plan(self.old,self.state,8000,80,self.now.replace(hour=22),'x')
 def test_low_count_does_not_change_interval_length(self):
  p=m.session_plan(self.old,self.state,10,80,self.now,'low')
  for b in p['batches'][1:]:self.assertEqual((m.d.dt_of(b['end'])-m.d.dt_of(b['start'])).total_seconds(),60)
if __name__=='__main__':unittest.main()
