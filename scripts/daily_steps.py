#!/usr/bin/env python3
"""Daily synthetic step lab. Minute writes, second-level planned counter, no sensor spoofing."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time
from zoneinfo import ZoneInfo
import simulate

PROJECT = Path(__file__).resolve().parents[1]
WORK = PROJECT / 'work'
RUNTIME = WORK / 'daily-steps.nosync'
CONFIG = PROJECT / 'scheduler/config.json'
UTC = dt.timezone.utc


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w') as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)


def load(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def validate(c):
    ZoneInfo(c['timezone'])
    if not (0 <= c['start_hour'] < c['end_hour'] <= 24):
        raise ValueError('Hours: 0 <= start < end <= 24')
    if not 1 <= c['daily_target'] <= 50000 or not 1 <= c['sessions'] <= 12:
        raise ValueError('Target: 1–50000; sessions: 1–12')
    if not c.get('synthetic') or c.get('recording_method') != 'manual_entry':
        raise ValueError('Only explicitly synthetic manual-entry records are supported')
    if not 5 <= c['late_grace_seconds'] <= 300:
        raise ValueError('Late tolerance: 5–300 seconds')
    if any(not isinstance(v, int) or v < 0 for v in c['baseline_by_date'].values()):
        raise ValueError('The baseline must be a nonnegative integer')


def build_plan(day, c, seed):
    validate(c)
    rng = random.Random(seed)
    zone = ZoneInfo(c['timezone'])
    midnight = dt.datetime.combine(day, dt.time(), zone)
    start = (midnight + dt.timedelta(hours=c['start_hour'])).astimezone(UTC)
    end = (midnight + dt.timedelta(hours=c['end_hour'])).astimezone(UTC)
    available = int((end - start).total_seconds() // 60)
    baseline = c['baseline_by_date'].get(day.isoformat(), 0)
    remaining = max(0, c['daily_target'] - baseline)
    walks = min(c['sessions'], remaining)
    batches = []
    # Unequal walk lengths, with an exact daily budget.
    weights = [rng.uniform(0.6, 1.4) for _ in range(walks)]
    budgets = [int(remaining * w / sum(weights)) for w in weights]
    for i in range(remaining - sum(budgets)):
        budgets[i % walks] += 1
    for walk, budget in enumerate(budgets):
        if not budget:
            continue
        left, right = available * walk // walks, available * (walk + 1) // walks
        cadence = rng.uniform(85, 115)
        slots = []
        todo = budget
        active_minutes = 0
        while todo:
            cadence = max(65, min(130, cadence + rng.uniform(-7, 7)))
            count = min(todo, max(1, round(cadence + rng.uniform(-4, 4))))
            slots.append(count)
            todo -= count
            active_minutes += 1
            if todo and active_minutes >= 5 and rng.random() < 0.12:
                slots.extend([0] * rng.randint(1, 3))
                active_minutes = 0
        if len(slots) > right - left:
            raise ValueError('Not enough time for the requested step count')
        offset = rng.randint(left, right - len(slots))
        for i, count in enumerate(slots):
            if count == 0:
                continue  # A pause creates no Health Connect record.
            begin = start + dt.timedelta(minutes=offset + i)
            batches.append(dict(scenario_id=f'labday-{day:%Y%m%d}-{offset+i:04d}',
                                steps=count, start=simulate.iso(begin),
                                end=simulate.iso(begin + dt.timedelta(minutes=1))))
    return dict(date=day.isoformat(), timezone=c['timezone'], target=c['daily_target'],
                baseline=baseline, seed=seed, synthetic=True, batches=batches)


def dt_of(value):
    return simulate.parse_time(value)


def planned_count(plan, now):
    count = plan['baseline']
    for b in plan['batches']:
        elapsed = (now - dt_of(b['start'])).total_seconds()
        if elapsed >= 60:
            count += b['steps']
        elif elapsed > 0:
            # Deterministic jitter inside each minute. No steps before their planned second.
            rng = random.Random(b['scenario_id'] + plan['seed'])
            period = 60 / b['steps']
            count += sum((i + 0.5 + rng.uniform(-0.2, 0.2)) * period <= elapsed
                         for i in range(b['steps']))
    return count


def due_batch(plan, state, now, grace):
    for b in plan['batches']:
        key = b['scenario_id']
        if key in state['completed'] or key in state['skipped']:
            continue
        late = (now - dt_of(b['end'])).total_seconds()
        if late < 5:
            return None
        if late > grace:
            state['skipped'][key] = b['steps']
            continue
        return b
    return None


def confirmed(plan, state):
    return plan['baseline'] + sum(r['actual'] for r in state['completed'].values())


def running(runtime):
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / 'worker.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True


def emulator_ready(adb):
    devices = [line.split()[0] for line in simulate.run([adb, 'devices']).stdout.splitlines()[1:]
               if len(line.split()) == 2 and line.split()[1] == 'device'
               and line.split()[0].startswith('emulator-')]
    # Never select a physical phone or an ambiguous set of emulators.
    if len(devices) != 1:
        raise RuntimeError('Exactly one running StepLabPlay emulator is required')
    serial = devices[0]
    name = simulate.run([adb, '-s', serial, 'emu', 'avd', 'name']).stdout.splitlines()[0].strip()
    if name != 'StepLabPlay':
        raise RuntimeError(f'Expected StepLabPlay, found {name}')
    return serial


def write_batch(adb, batch):
    serial = emulator_ready(adb)
    # Avoid overlapping commands left by an interrupted previous controller run.
    simulate.run([adb, '-s', serial, 'shell', 'am', 'force-stop', simulate.PACKAGE])
    result = simulate.execute(adb, serial, batch, 60)
    if result.get('status') != 'PASS' or result.get('actual') != batch['steps']:
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    try:
        simulate.run([adb, '-s', serial, 'shell', 'am', 'start', '-n',
                      'com.fitbit.FitbitMobile/com.fitbit.HealthBrandedAlias'])
    except Exception as exc:
        result['health_open_warning'] = str(exc)
    return result


def daemon(config_path, runtime, adb):
    c = load(config_path); validate(c)
    runtime.mkdir(parents=True, exist_ok=True)
    lock = (runtime / 'worker.lock').open('a+')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Already running'); return
    stop = False
    def halt(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, halt)
    signal.signal(signal.SIGINT, halt)
    zone = ZoneInfo(c['timezone'])
    next_retry = 0.0
    last_error = None
    pending_file = runtime / 'pending.json'
    try:
        while not stop and not (runtime / 'stop.request').exists():
            now = dt.datetime.now(UTC)
            day = now.astimezone(zone).date()
            plan_path = runtime / f'{day}-plan.json'
            plan = load(plan_path)
            if plan is None:
                plan = build_plan(day, c, os.urandom(16).hex())
                save(plan_path, plan)
            state_path = runtime / f'{day}-state.json'
            state = load(state_path, dict(completed={}, skipped={}))
            pending = load(pending_file)
            if pending:
                # A retry keeps the original date, ID, count and interval, even across midnight.
                old_state_path = runtime / f"{pending['date']}-state.json"
                old_state = load(old_state_path, dict(completed={}, skipped={}))
                if pending['batch']['scenario_id'] in old_state['completed']:
                    pending_file.unlink(); pending = None
            if pending is None:
                batch = due_batch(plan, state, now, c['late_grace_seconds'])
                save(state_path, state)
                if batch:
                    pending = dict(date=plan['date'], batch=batch)
                    save(pending_file, pending)
            if pending and time.monotonic() >= next_retry:
                try:
                    result = write_batch(adb, pending['batch'])
                    old_state_path = runtime / f"{pending['date']}-state.json"
                    old_state = load(old_state_path, dict(completed={}, skipped={}))
                    old_state['completed'][pending['batch']['scenario_id']] = result
                    save(old_state_path, old_state)
                    pending_file.unlink()
                    last_error = None
                    print(json.dumps(result, ensure_ascii=False), flush=True)
                except Exception as exc:
                    last_error = str(exc)
                    next_retry = time.monotonic() + 60
                    print(json.dumps(dict(error=last_error), ensure_ascii=False), flush=True)
                state = load(state_path, state)
                pending = load(pending_file)
            now = dt.datetime.now(UTC)
            future = [b for b in plan['batches'] if dt_of(b['end']) > now]
            save(runtime / 'status.json', dict(
                state='error' if last_error else 'running', pid=os.getpid(), date=plan['date'],
                timezone=c['timezone'], target=plan['target'], baseline=plan['baseline'],
                planned_so_far=planned_count(plan, now), confirmed_health_connect=confirmed(plan, state),
                skipped_steps=sum(state['skipped'].values()), pending=pending,
                next_interval=future[0] if future else None, last_error=last_error,
                updated_at=simulate.iso(now)))
            time.sleep(1)
    finally:
        status = load(runtime / 'status.json', {})
        status.update(state='stopped', updated_at=simulate.iso(dt.datetime.now(UTC)))
        save(runtime / 'status.json', status)
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status', 'watch', 'plan', '_run'])
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--runtime', type=Path, default=RUNTIME)
    parser.add_argument('--adb', default=str(WORK / 'toolchain/sdk/platform-tools/adb'))
    parser.add_argument('--date', type=dt.date.fromisoformat)
    args = parser.parse_args()
    c = load(args.config); validate(c)
    args.runtime.mkdir(parents=True, exist_ok=True)
    if args.action == '_run':
        daemon(args.config, args.runtime, args.adb)
    elif args.action == 'plan':
        day = args.date or dt.datetime.now(ZoneInfo(c['timezone'])).date()
        plan = load(args.runtime / f'{day}-plan.json') or build_plan(day, c, day.isoformat())
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    elif args.action == 'start':
        if running(args.runtime):
            print('Already running'); return
        (args.runtime / 'stop.request').unlink(missing_ok=True)
        with (args.runtime / 'worker.log').open('a') as log:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_run',
                              '--config', str(args.config.resolve()), '--runtime', str(args.runtime.resolve()),
                              '--adb', args.adb], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=True, close_fds=True)
        for _ in range(50):
            if running(args.runtime):
                print('Daily synthetic test started.'); return
            time.sleep(0.1)
        raise RuntimeError('Could not start the worker. See worker.log')
    elif args.action == 'stop':
        (args.runtime / 'stop.request').touch()
        print('Stop requested; any write already in progress will finish.')
    else:
        while True:
            status = load(args.runtime / 'status.json', {})
            status['process_running'] = running(args.runtime)
            if args.action == 'status':
                print(json.dumps(status, indent=2, ensure_ascii=False)); return
            plan = load(args.runtime / f"{status.get('date')}-plan.json")
            local = planned_count(plan, dt.datetime.now(UTC)) if plan else 0
            print(f"\rPlanned now: {local} | Recorded in HC: {status.get('confirmed_health_connect', 0)}"
                  f" / {status.get('target', c['daily_target'])} | {status.get('state', 'not running')}    ",
                  end='', flush=True)
            time.sleep(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
