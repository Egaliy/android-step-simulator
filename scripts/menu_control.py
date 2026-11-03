#!/usr/bin/env python3
"""Commands for the native menu app; all writes retain manual-entry provenance."""
import argparse, datetime as dt, fcntl, json, os, random, subprocess, sys, time, uuid
from pathlib import Path
from zoneinfo import ZoneInfo
import daily_steps as d
from activity_profile import enrich

ROOT = Path(os.environ.get('STEP_LAB_ROOT', str(Path(__file__).resolve().parents[1])))
R = ROOT / 'work/daily-steps.nosync'
SDK = Path(os.environ.get('ANDROID_HOME', str(Path.home() / 'Library/Android/sdk')))
ADB = str(SDK / 'platform-tools/adb')

def event(state, message):
    d.save(R/'control.json',dict(state=state,message=message,updated_at=d.simulate.iso(dt.datetime.now(dt.timezone.utc))))

def stop():
    (R/'stop.request').touch()
    for _ in range(120):
        if not d.running(R): return
        time.sleep(.5)
    raise RuntimeError('A write is still finishing. Try stopping again shortly.')

def devices():
    return [x.split()[0] for x in d.simulate.run([ADB,'devices']).stdout.splitlines()[1:] if len(x.split())==2 and x.split()[0].startswith('emulator-')]

def ready():
    if not devices():
        event('starting','Starting Android without a window…')
        env=dict(os.environ,ANDROID_HOME=str(SDK))
        with (R/'headless-emulator.log').open('a') as log:
            subprocess.Popen([str(SDK/'emulator/emulator'),'-avd','StepLabPlay','-no-window','-no-snapshot','-no-audio','-memory','2560','-cores','4','-feature','-Vulkan','-no-boot-anim'],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    for _ in range(90):
        try:
            serial=d.emulator_ready(ADB)
            if d.simulate.run([ADB,'-s',serial,'shell','getprop','sys.boot_completed']).stdout.strip()=='1':return serial
        except Exception: pass
        time.sleep(2)
    raise RuntimeError('Android did not boot within 3 minutes. Check headless-emulator.log.')

def session_plan(old, state, steps, minutes, now, seed):
    if not 1 <= steps <= 50000 or not 1 <= minutes <= 720:
        raise ValueError('Steps: 1–50000; minutes: 1–720.')
    if steps > minutes*180:
        raise ValueError('Duration is too short: maximum 180 steps per minute.')
    start=now+dt.timedelta(seconds=10)
    end=start+dt.timedelta(minutes=minutes)
    zone=ZoneInfo(old['timezone'])
    if start.astimezone(zone).date()!=end.astimezone(zone).date():
        raise ValueError('The session must finish before midnight in Europe/Belgrade.')
    rng=random.Random(seed)
    n=minutes
    weights=[rng.uniform(.85,1.15) for _ in range(n)]
    counts=[int(steps*w/sum(weights)) for w in weights]
    for i in range(steps-sum(counts)):counts[i%n]+=1
    past=[dict(scenario_id=k,steps=v['actual'],start=v['start'],end=v['end']) for k,v in state['completed'].items()]
    batches=list(past)
    for i,count in enumerate(counts):
        if count:
            a=start+dt.timedelta(seconds=60*minutes*i/n)
            z=start+dt.timedelta(seconds=60*minutes*(i+1)/n)
            batches.append(dict(scenario_id=f'menu-{seed}-{i:03d}',steps=count,start=d.simulate.iso(a),end=d.simulate.iso(z)))
    enrich(batches[len(past):])
    base=d.confirmed(old,state)
    return dict(date=old['date'],timezone=old['timezone'],target=base+steps,baseline=old['baseline'],seed=seed,synthetic=True,batches=sorted(batches,key=lambda b:b['start']),session=dict(steps=steps,minutes=minutes,baseline=base,start=d.simulate.iso(start),end=d.simulate.iso(end)))

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','stop','shutdown']);p.add_argument('--steps',type=int,default=8000);p.add_argument('--minutes',type=int,default=80);args=p.parse_args()
    R.mkdir(parents=True,exist_ok=True)
    with (R/'control.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another command is still running.')
        event('busy','Preparing…');stop()
        if args.action!='start':
            if args.action=='shutdown' and devices():
                serial=d.emulator_ready(ADB);d.simulate.run([ADB,'-s',serial,'emu','kill'])
            event('stopped','Session stopped.' if args.action=='stop' else 'Android shut down. Memory is being released.');return
        c=d.load(R/'config.json');day=dt.datetime.now(ZoneInfo(c['timezone'])).date().isoformat();pp=R/f'{day}-plan.json';sp=R/f'{day}-state.json'
        old=d.load(pp) or d.build_plan(dt.date.fromisoformat(day),c,uuid.uuid4().hex)
        state=d.load(sp,dict(completed={},skipped={}))
        session_plan(old,state,args.steps,args.minutes,dt.datetime.now(dt.timezone.utc),uuid.uuid4().hex[:12]) # validate before boot/write
        ready()
        pending=d.load(R/'pending.json')
        if pending:
            event('busy','Checking the pending record…')
            result=d.write_batch(ADB,pending['batch'])
            osp=R/(pending['date']+'-state.json');os_=d.load(osp,dict(completed={},skipped={}))
            os_['completed'][pending['batch']['scenario_id']]=result;d.save(osp,os_);(R/'pending.json').unlink();state=d.load(sp,state)
        plan=session_plan(old,state,args.steps,args.minutes,dt.datetime.now(dt.timezone.utc).replace(microsecond=0),uuid.uuid4().hex[:12])
        d.save(R/f'{day}-before-menu-{int(time.time())}.json',old)
        d.save(sp,state);d.save(pp,plan)
        subprocess.run([sys.executable,str(R/'code/daily_steps.py'),'start','--config',str(R/'config.json'),'--runtime',str(R),'--adb',ADB],check=True)
        event('running','Session started. Writing once per minute.')

if __name__=='__main__':
    try:main()
    except Exception as e:
        event('error',str(e));print(str(e),file=sys.stderr);sys.exit(1)
