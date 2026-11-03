# Android Step Simulator

Generate synthetic step records in Android Health Connect and manage test sessions from the macOS menu bar.

A Kotlin app handles Health Connect permissions, writes `StepsRecord` entries, and reads them back for verification. A Python controller schedules records through ADB. A native AppKit menu provides session controls and progress tracking.

## Features

- **Custom sessions** — choose a step count and duration, such as 8,000 steps over 80 minutes.
- **Daily schedules** — distribute a daily target across sessions with varied lengths, changing cadence, and short pauses.
- **Verified writes** — read each record back and check its count, interval, and source.
- **Retry protection** — reuse the original record identifier when retrying an interrupted operation.
- **Menu bar controls** — start or stop a session, view recorded progress, or shut down Android to free memory.
- **Headless Android** — start the emulator without opening its window.

Records retain the `lab.steps` source and manual-entry metadata. This tool tests data storage and integration behavior; it does not emulate motion sensors. Acceptance and display of synthetic records depend on the receiving application.

## How it works

```text
macOS menu / Python scenario
            │ ADB
            ▼
     Kotlin Android app
            │ write + read back
            ▼
       Health Connect
            │ optional integration
            ▼
     Compatible fitness app
```

## Requirements

| Component | Requirement |
| --- | --- |
| Host | macOS; Command Line Tools for building the menu app |
| Python | 3.9 or newer |
| Java | JDK 17 |
| Android SDK | Platform 36, required Build Tools, Platform Tools, and Emulator |
| Virtual device | Android 14 or newer, named `StepLabPlay` |

Create the virtual device in Android Studio. A Google Play image is useful when testing integrations with apps distributed through Google Play.

The default SDK location is `~/Library/Android/sdk`. For a different location, set `ANDROID_HOME` before building the menu app. Keep the checkout locally available; cloud file offloading can interrupt emulator startup.

## Quick start

### 1. Install the Android app

Open the project in Android Studio and start the `StepLabPlay` virtual device. Then build and install the debug app:

```sh
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"

./gradlew assembleDebug
"$ANDROID_HOME/platform-tools/adb" install -r app/build/outputs/apk/debug/app-debug.apk
"$ANDROID_HOME/platform-tools/adb" shell am start -n lab.steps/.MainActivity
```

In Step Simulator, grant permission to read and write steps in Health Connect. Keep only one emulator connected during setup.

To test another application, install it separately, sign in, and configure its Health Connect integration. Account credentials, emulator images, and device data are not included in this repository.

### 2. Build the macOS menu app

Install Command Line Tools if needed:

```sh
xcode-select --install
```

Build and open the menu app:

```sh
python3 scripts/setup_menu.py
open "work/menu-build.nosync/Step Menu.app"
```

Click the walking-person icon in the menu bar, enter the step count and duration, and start a session. The application interface and status messages are in English.

| Control | Behavior |
| --- | --- |
| Start session | Replace the rest of today's plan with a new session, preserving confirmed records |
| Stop | Finish any write already in progress, then stop generation |
| Shut down Android | Stop generation and terminate the emulator |
| Close menu | Close the menu app while leaving generation running |

The progress bar shows confirmed records for the current session. The timeline displays its start, end, and elapsed minutes. The count in the menu bar covers records tracked by this tool, not every source in the connected account.

If no emulator is running, starting a session launches Android without a window. An existing `StepLabPlay` emulator is reused as-is. The menu controller does not select physical phones.

### 3. Run a scenario from Python

Preview a scenario without writing data:

```sh
python3 scripts/simulate.py --dry-run --steps 100 500 1000 5000
```

Write and verify a 100-step record:

```sh
python3 scripts/simulate.py --steps 100 --minutes 2 --output reports/test.json
```

For a retry with identical content, reuse both `--run-id` and `--end`. Reports contain record identifiers and time intervals; review them before sharing.

## Scheduling and state

The daily configuration template is `scheduler/config.json`. Menu setup copies it to `work/daily-steps.nosync/config.json` only when no working configuration exists.

Default settings:

| Setting | Default |
| --- | --- |
| Daily target | 20,000 steps |
| Sessions | 5 |
| Scheduling window | 08:00–22:00 |
| Time zone | Europe/Belgrade |
| Record method | Manual entry |

Each day's plan is persisted and reused after a restart. Editing the template does not change an existing working configuration or saved plan.

A custom session replaces the remaining schedule for that day. The previous schedule does not resume after the session ends. If the worker remains running, it can generate the regular daily plan on the following day. Use **Stop** to end generation.

Runtime files, pending-write journals, reports, built apps, and device data are excluded from version control.

## Operational limits

- The Mac must remain awake. This is a local tool, not a hosted service.
- Records are submitted in minute-sized batches. Downstream synchronization may lag behind Health Connect.
- Intervals missed by more than two minutes are skipped rather than backfilled. The recorded total can therefore be lower than the target.
- A pending write is retried with its original identifier to avoid creating a duplicate.
- Running without a window still consumes Android resources: the emulator is configured with 2,560 MB of guest RAM, plus host overhead.
- The menu app is built for the checkout's local path. Run `setup_menu.py` again after moving the project.
- Login-item registration and Codex automations are not installed by this repository.

## Development and verification

Run the Python checks:

```sh
python3 -m unittest discover -s scripts -v
```

Build and lint the Android app:

```sh
./gradlew assembleDebug lintDebug
```

The Python suite covers daily budgets, interval boundaries, daylight-saving transitions, pauses, persisted state, emulator selection, and custom-session calculations. The menu app has been built and launched on macOS; complete automated UI coverage is not included. Local checks do not verify delivery to a third-party fitness service.

## Project structure

| Path | Purpose |
| --- | --- |
| `app/` | Kotlin app, permissions, and Health Connect read/write operations |
| `app/src/debug/` | Debug-only ADB command entry point |
| `scripts/simulate.py` | Scenario submission and record verification |
| `scripts/daily_steps.py` | Daily planning, worker process, and retry journal |
| `scripts/menu_control.py` | Session and emulator management |
| `scripts/setup_menu.py` | Local menu app build and runtime setup |
| `menu/StepMenu.swift` | Native AppKit menu interface |
| `scheduler/config.json` | Default daily configuration |

## References

- [Health Connect documentation](https://developer.android.com/health-and-fitness/health-connect)
- [Health Connect client releases](https://developer.android.com/jetpack/androidx/releases/health-connect)
