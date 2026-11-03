import datetime as dt
import unittest
from unittest.mock import patch
import subprocess
import simulate

class ScenariosTest(unittest.TestCase):
    def setUp(self):
        self.end = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(minutes=1)

    def test_matrix_uses_nonoverlapping_exact_intervals(self):
        plan = simulate.scenarios([100, 500, 1000, 5000], 60, self.end, 'matrix')
        self.assertEqual([x['steps'] for x in plan], [100, 500, 1000, 5000])
        self.assertEqual(len({x['scenario_id'] for x in plan}), 4)
        for left, right in zip(plan, plan[1:]):
            self.assertEqual(left['end'], right['start'])
        self.assertEqual(plan[-1]['end'], simulate.iso(self.end))

    def test_invalid_values(self):
        for counts, minutes, sid in [([0], 1, 'ok'), ([-1], 1, 'ok'), ([1000001], 1, 'ok'),
                                      ([1], 0, 'ok'), ([1], 1441, 'ok'), ([1], 1, '../bad')]:
            with self.subTest(counts=counts, minutes=minutes, sid=sid):
                with self.assertRaises(ValueError):
                    simulate.scenarios(counts, minutes, self.end, sid)

    def test_future_and_old_ranges_rejected(self):
        for end in [self.end + dt.timedelta(days=1), self.end - dt.timedelta(days=30)]:
            with self.assertRaises(ValueError):
                simulate.scenarios([100], 60, end, 'ok')

    def test_timezone_normalized(self):
        self.assertEqual(simulate.iso(simulate.parse_time('2026-01-01T12:00:00+01:00')), '2026-01-01T11:00:00Z')
        with self.assertRaises(ValueError):
            simulate.parse_time('2026-01-01T12:00:00')

    @patch('simulate.run')
    def test_adb_success_is_not_health_connect_success(self, run):
        run.side_effect = [subprocess.CompletedProcess([], 0, '', ''),
                           subprocess.CompletedProcess([], 0, 'Starting', ''),
                           subprocess.CompletedProcess([], 0, '{"scenario_id":"s-0","status":"ERROR","error":"denied"}', '')]
        result = simulate.execute('adb', 'emulator-5554', dict(scenario_id='s-0', steps=100, start='x', end='y'), 1)
        self.assertEqual(result['status'], 'ERROR')

if __name__ == '__main__':
    unittest.main()
