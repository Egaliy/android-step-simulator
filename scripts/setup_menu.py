#!/usr/bin/env python3
"""Build a local, ad-hoc signed macOS menu app. Does not start or write health records."""
import os, plistlib, shutil, subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
r=root/'work/daily-steps.nosync';code=r/'code';code.mkdir(parents=True,exist_ok=True)
for name in ['daily_steps.py','simulate.py','menu_control.py']:
    shutil.copy2(root/'scripts'/name,code/name)
if not (r/'config.json').exists():shutil.copy2(root/'scheduler/config.json',r/'config.json')
app=root/'work/menu-build.nosync/Step Menu.app';contents=app/'Contents';(contents/'MacOS').mkdir(parents=True,exist_ok=True)
sdk=os.environ.get('ANDROID_HOME',str(Path.home()/'Library/Android/sdk'))
info=dict(CFBundleIdentifier='lab.steps.menu',CFBundleName='Step Menu',CFBundleExecutable='StepMenu',CFBundlePackageType='APPL',CFBundleVersion='1',LSUIElement=True,StepLabRoot=str(root),StepLabSDK=sdk,NSHighResolutionCapable=True)
with (contents/'Info.plist').open('wb') as f:plistlib.dump(info,f)
subprocess.run(['xcrun','swiftc',str(root/'menu/StepMenu.swift'),'-o',str(contents/'MacOS/StepMenu'),'-framework','AppKit'],check=True)
subprocess.run(['xattr','-cr',str(app)],check=True)
subprocess.run(['codesign','--force','--sign','-',str(app)],check=True)
print(app)
