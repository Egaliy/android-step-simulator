import unittest,copy
from activity_profile import enrich
class ProfileTest(unittest.TestCase):
 def batches(self):return [dict(steps=99+i%3,start='2026-11-03T10:00:00Z',end='2026-11-03T10:01:00Z') for i in range(80)]
 def test_exact_selected_profile(self):
  b=self.batches();b[-1]['steps']+=8000-sum(x['steps'] for x in b)
  enrich(b)
  self.assertAlmostEqual(sum(x['distance_m'] for x in b),5600)
  self.assertAlmostEqual(sum(x['active_kcal'] for x in b),320)
  self.assertEqual(sum(x['elevation_m'] for x in b),0)
  self.assertEqual(sum('workout_start' in x for x in b),1)
 def test_repeat_stable_without_steps_change(self):
  b=self.batches();steps=[x['steps'] for x in b];enrich(b);first=copy.deepcopy(b);enrich(b)
  self.assertEqual(first,b);self.assertEqual(steps,[x['steps'] for x in b])
 def test_invalid_profile(self):
  for v in [-1,float('nan'),float('inf')]:
   with self.assertRaises(ValueError):enrich(self.batches(),kcal_per_step=v)
 def test_climb_exact(self):
  b=self.batches();enrich(b,elevation_m=40)
  self.assertAlmostEqual(sum(x['elevation_m'] for x in b),40)
if __name__=='__main__':unittest.main()
