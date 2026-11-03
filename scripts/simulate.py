#!/usr/bin/env python3
"""Submit synthetic step scenarios to the debug APK and retrieve verified results."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

PACKAGE = 'lab.steps'

def iso(value):
    return value.astimezone(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def parse_time(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Time must include Z or an offset, such as +01:00')
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0)

def scenarios(counts, minutes, end, run_id):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}', run_id):
        raise ValueError('ID: 1–60 ASCII letters, digits, hyphens or underscores')
    if not counts or any(not 1 <= n <= 1_000_000 for n in counts):
        raise ValueError('Each step count must be between 1 and 1,000,000')
    if not 1 <= minutes <= 1440:
        raise ValueError('Duration: 1–1440 minutes')
    now = dt.datetime.now(dt.timezone.utc)
    first = end - dt.timedelta(minutes=minutes * len(counts))
    if end > now or first < now - dt.timedelta(days=29):
        raise ValueError('All intervals must be in the past, within the last 29 days')
    return [dict(scenario_id=f'{run_id}-{i}', steps=n,
                 start=iso(first + dt.timedelta(minutes=minutes*i)),
                 end=iso(first + dt.timedelta(minutes=minutes*(i+1))))
            for i, n in enumerate(counts)]

def find_adb(explicit=None):
    candidates = [explicit, shutil.which('adb')]
    for sdk in [os.environ.get('ANDROID_HOME'), os.environ.get('ANDROID_SDK_ROOT'),
                str(Path.home() / 'Library/Android/sdk')]:
        if sdk:
            candidates.append(str(Path(sdk) / 'platform-tools/adb'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise RuntimeError('ADB not found. Set --adb or install Android SDK Platform-Tools.')

def run(command, check=True):
    result = subprocess.run(command, text=True, capture_output=True, timeout=20)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result

def execute(adb, serial, scenario, timeout):
    prefix = [adb, '-s', serial]
    sid = scenario['scenario_id']
    target = f'files/results/{sid}.json'
    # Remove only the previous local report, never the Health Connect record.
    run(prefix + ['shell', 'run-as', PACKAGE, 'rm', '-f', target])
    args = prefix + ['shell', 'am', 'start', '-W', '-n', f'{PACKAGE}/.CommandActivity']
    for key, value in scenario.items():
        args.extend(['--es', key, str(value)])
    launched = run(args)
    if 'Error:' in launched.stdout or 'Exception' in launched.stderr:
        raise RuntimeError(launched.stdout + launched.stderr)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = run(prefix + ['exec-out', 'run-as', PACKAGE, 'cat', target], check=False)
        if response.returncode == 0:
            try:
                result = json.loads(response.stdout)
            except json.JSONDecodeError:
                time.sleep(0.5)
                continue  # Android may expose an empty report briefly during startup.
            if result.get('scenario_id') != sid:
                raise RuntimeError('Result ID does not match the scenario')
            return result
        time.sleep(0.5)
    raise RuntimeError('No result: check the emulator screen and Health Connect permissions. '
                       'The record may have been saved; retry with the same --run-id and --end to avoid duplicates.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steps', nargs='+', type=int, default=[10000])
    parser.add_argument('--minutes', type=int, default=60, help='Duration of each non-overlapping interval in minutes')
    parser.add_argument('--end', help='End of the last interval, ISO 8601 with a time zone')
    parser.add_argument('--run-id', default=str(uuid.uuid4()))
    parser.add_argument('--serial', help='ADB serial, for example emulator-5554')
    parser.add_argument('--adb')
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('reports/latest.json'))
    args = parser.parse_args()
    try:
        end = parse_time(args.end) if args.end else dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(seconds=10)
        plan = scenarios(args.steps, args.minutes, end, args.run_id)
        if args.timeout <= 0:
            raise ValueError('Timeout must be positive')
        if args.dry_run:
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 0
        adb = find_adb(args.adb)
        devices = [line.split()[0] for line in run([adb, 'devices']).stdout.splitlines()[1:]
                   if len(line.split()) == 2 and line.split()[1] == 'device']
        serial = args.serial
        if serial is None:
            if len(devices) != 1:
                raise RuntimeError('One Android device is required; use --serial when multiple devices are connected.')
            serial = devices[0]
        if serial not in devices:
            raise RuntimeError('The selected device is disconnected or unauthorized')
        report = dict(run_id=args.run_id, end=iso(end), plan=plan, results=[])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        for scenario in plan:
            try:
                result = execute(adb, serial, scenario, args.timeout)
            except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
                result = dict(scenario_id=scenario['scenario_id'], status='ERROR', error=str(exc))
            report['results'].append(result)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
            print(json.dumps(result, ensure_ascii=False))
            if result.get('status') != 'PASS':
                return 1
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
