import datetime as dt
import fcntl
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
import daily_steps as d

C = dict(timezone='Europe/Belgrade',daily_target=20000,start_hour=8,end_hour=22,
         sessions=5,baseline_by_date={'2026-11-03':100},late_grace_seconds=120,
         synthetic=True,recording_method='manual_entry')

class DailyPlanTest(unittest.TestCase):
    def test_thirty_daily_plans_hit_target_without_overlap(self):
        for i in range(30):
            day = dt.date(2026,11,3) + dt.timedelta(days=i)
            p = d.build_plan(day,C,str(i))
            self.assertEqual(p['baseline'] + sum(b['steps'] for b in p['batches']),20000)
            self.assertEqual(len({b['scenario_id'] for b in p['batches']}),len(p['batches']))
            previous = None
            for b in p['batches']:
                a,z=d.dt_of(b['start']),d.dt_of(b['end'])
                self.assertEqual((z-a).total_seconds(),60)
                self.assertGreater(b['steps'],0)
                self.assertLessEqual(b['steps'],140)
                self.assertGreaterEqual(a.astimezone(ZoneInfo(C['timezone'])).hour,8)
                self.assertLessEqual(z.astimezone(ZoneInfo(C['timezone'])).hour,22)
                if previous:self.assertGreaterEqual(a,previous)
                previous=z

    def test_variable_walk_budgets_and_short_pauses(self):
        p=d.build_plan(dt.date(2026,11,3),C,'variation')
        totals=[0]*5
        for b in p['batches']:
            offset=int(b['scenario_id'].rsplit('-',1)[1])
            totals[min(4,offset*5//840)]+=b['steps']
        self.assertGreater(len(set(totals)),1)
        gaps=[(d.dt_of(b['start'])-d.dt_of(a['end'])).total_seconds()
              for a,b in zip(p['batches'],p['batches'][1:])]
        self.assertTrue(any(60 <= gap <= 180 for gap in gaps))

    def test_seed_is_stable_and_changes_timing(self):
        day=dt.date(2026,11,3)
        self.assertEqual(d.build_plan(day,C,'a'),d.build_plan(day,C,'a'))
        self.assertNotEqual(d.build_plan(day,C,'a')['batches'],d.build_plan(day,C,'b')['batches'])

    def test_dst_full_day_has_exact_total(self):
        c=dict(C,start_hour=0,end_hour=24)
        for day in [dt.date(2026,3,29),dt.date(2026,10,25)]:
            p=d.build_plan(day,c,'dst')
            self.assertEqual(sum(b['steps'] for b in p['batches']),20000)
            for b in p['batches']:
                self.assertEqual(d.dt_of(b['start']).astimezone(ZoneInfo(c['timezone'])).date(),day)

    def test_second_counter_monotonic_and_exact(self):
        p=d.build_plan(dt.date(2026,11,3),C,'counter')
        b=p['batches'][0]
        values=[d.planned_count(p,d.dt_of(b['start'])+dt.timedelta(seconds=i)) for i in range(61)]
        self.assertEqual(values,sorted(values))
        self.assertEqual(values[0],100)
        self.assertEqual(values[-1],100+b['steps'])
        self.assertLessEqual(max(y-x for x,y in zip(values,values[1:])),3)

    def test_late_slots_are_skipped_instead_of_bulk_backfill(self):
        p=d.build_plan(dt.date(2026,11,3),C,'late')
        state=dict(completed={},skipped={})
        now=d.dt_of(p['batches'][0]['end'])+dt.timedelta(minutes=10,seconds=6)
        due=d.due_batch(p,state,now,120)
        self.assertIn(p['batches'][0]['scenario_id'],state['skipped'])
        self.assertIsNotNone(due)
        self.assertLessEqual((now-d.dt_of(due['end'])).total_seconds(),120)

    def test_finished_batch_is_not_selected_again(self):
        p=d.build_plan(dt.date(2026,11,3),C,'done')
        b=p['batches'][0]
        state=dict(completed={b['scenario_id']:dict(actual=b['steps'])},skipped={})
        self.assertIsNone(d.due_batch(p,state,d.dt_of(b['end'])+dt.timedelta(seconds=6),120))
        self.assertEqual(d.confirmed(p,state),100+b['steps'])

    def test_atomic_journal_roundtrip_and_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            p=d.build_plan(dt.date(2026,11,3),C,'journal')
            pending=dict(date=p['date'],batch=p['batches'][0])
            d.save(root/'pending.json',pending)
            self.assertEqual(d.load(root/'pending.json'),pending)
            self.assertFalse(d.running(root))
            with (root/'worker.lock').open('a+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                self.assertTrue(d.running(root))
            self.assertFalse(d.running(root))

    @patch('daily_steps.simulate.run')
    def test_physical_phone_is_never_selected(self, run):
        import subprocess
        run.return_value=subprocess.CompletedProcess([],0,'List of devices attached\nphone123\tdevice\n','')
        with self.assertRaises(RuntimeError):d.emulator_ready('adb')

    def test_baseline_can_cover_whole_target(self):
        c=dict(C,baseline_by_date={'2026-11-03':20000})
        p=d.build_plan(dt.date(2026,11,3),c,'complete')
        self.assertEqual(p['batches'],[])

if __name__=='__main__':unittest.main()
