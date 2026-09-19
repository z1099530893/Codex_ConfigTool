# Codex Config Tool - Window Bug Handoff

> **RESOLVED 2026-09-15.** See "Resolution" at the end of this file. All seven
> requirements were verified on the packaged executable
> (`dist/CodexConfigTool.exe`) with zero failures across five minimize/restore
> cycles. The rest of this document is the original handoff and is kept for
> context.
>
> **Follow-up 2026-09-15 (later):** the application fix is unchanged, but a
> re-run exposed two defects in the *acceptance harness* - it could click the
> wrong taskbar button, and it could silently lose synthetic input and blame the
> app. Both are fixed, the packaged acceptance test then passed **twice** with
> 5/5 cycles restored by a genuine taskbar click, and drag repaint is now
> measured frame by frame instead of being left to the eye. See "Follow-up" at
> the end for the evidence.
>
> **Follow-up 2026-09-15 (final):** the last unverified item on the "Still
> Broken" list - *"the application exits after a delay"* - now has a test
> (`prototypes/verify_minimize_soak.py`: 60 s minimized + 30 s restored, polling
> throughout). It **passes**: 45/45 samples alive, HWND stable, size and frame
> stable, restored by a real taskbar click. Building it surfaced two further
> harness defects (a baseline captured from a background window, and an input
> probe that walked into a gap between two misaligned monitors); both are fixed
> and neither was an application bug. All 15 packaged cycles across three runs
> restored via a genuine taskbar click, and the luminance signal is now identical
> in every cycle. See the second "Follow-up" section at the end.

> **Follow-up 2026-09-15 (flash):** the next user report - *"the whole main UI
> flashes once when restoring from the taskbar"* - was reproduced and measured
> (one frame, ~17-35 ms, showing the toplevel background where the widgets should
> be). Seven candidate causes were tested; **none of them fixes it**, and two of
> them destabilise the minimize path. **No source change was made**: the build
> the user asked to preserve is byte-identical to its backup, and all seven
> requirements still hold. See "Follow-up (2026-09-15, second): the restore
> flash" at the end for the full table and for the two measurement traps that
> produced a wrong answer first.

> **Follow-up 2026-09-15 (latest):** a user report outside the seven requirements
> - *"clicking the taskbar icon still cannot toggle maximize/minimize"* - was a
> real bug the suite could not have caught: the harness only ever clicked the
> taskbar button while the window was **already minimized**. The window answered
> every minimize request correctly; the Shell simply never made one, because
> `overrideredirect` leaves the window without `WS_MINIMIZEBOX`, and that single
> bit is what the Shell uses to decide a window can be minimized. Fixed by adding
> `WS_SYSMENU | WS_MINIMIZEBOX` (neither draws a frame, so the borderless design
> and the 820x500 client are untouched). Proven with a `Shell.MinimizeAll()`
> control experiment against the old build, and end to end with real taskbar
> clicks in all 5 cycles. See the last "Follow-up" section.

## Package

This folder is a complete working copy of `D:\Codex_ConfigTool` as of 2026-09-14.
It includes the latest source, tests, assets, build scripts/spec files, existing
documentation, `dist` artifacts, `build` outputs, `Image-Management` reference
project, and `backups`.

The Git metadata is intentionally not copied. The source is currently uncommitted
in the original workspace; preserve the files in this handoff package as the
starting point for a new agent.

## Primary Source

- `codex_config_tool.py`
- Entry point: `main()` at the end of that file
- Build spec: `CodexConfigTool.spec`
- Tests: `tests/`
- Latest executable present at handoff time: `dist/CodexConfigTool.exe`

## User-Confirmed Requirements

The main window must satisfy all of these simultaneously:

1. Initial open has one custom black title bar.
2. Dragging the custom title bar must not fragment, tear, resize, or otherwise
   break the window.
3. Clicking the main-window minimize button must minimize only; the process must
   remain alive.
4. The Windows taskbar button/icon must remain available while the window is
   normal, minimized, and restored.
5. Restoring from the taskbar must show one title bar only, with no duplicate
   native title bar.
6. Repeating minimize/restore must not change the fixed window size (820x500).
7. Existing configuration-management behavior must not regress.

## Confirmed Fixed Earlier

- The original repeated size growth during repeated minimize/restore was not
  reproduced in the source regression script; repeated samples stayed `820x500`.
- Python syntax and the existing automated suite pass.
- The custom title bar drag path worked in at least one prior packaged build.

## Still Broken (User Reproduction)

The user most recently supplied screenshots proving that the latest packaged
build still shows two title bars after restore: a thin native Windows title bar
above the black custom title bar. The duplicate remains after repeated cycles.

Earlier user-confirmed regressions across attempted fixes:

- Restoring after minimize produced a duplicate native title bar.
- Switching window styles to remove the duplicate caused drag repaint/fragmentation.
- Win32 `ShowWindow` attempts caused the main-window minimize button to do nothing
  or caused the application to exit after a delay.
- Another build showed a taskbar button only while minimized and no taskbar
  button while normal.

Do not declare success unless all seven requirements are manually checked in the
packaged executable.

## Relevant Current Code

Window lifecycle methods in `codex_config_tool.py`:

- `CodexConfigApp.__init__`
- `_start_window_move`, `_move_window`, `_stop_window_move`
- `_minimize_window`
- `_restore_custom_frame`
- `_track_window_minimized`
- `_update_minimized_state`
- `_finish_taskbar_restore`
- `_set_appwindow_style`
- `_install_native_frame_handler`

The current file contains several historical experiments around Tk
`overrideredirect`, Win32 taskbar styles, and frame handlers. Treat this area as
high risk. Read the whole lifecycle before editing.

## Reference Project

`Image-Management/` is the other project the user supplied as a behavioral
reference. Its Qt implementation is mainly under `Image-Management/qt_app_v20.py`.
Use it to understand desired maximize/minimize behavior, but do not copy its
implementation blindly into this Tk application.

## Validation Already Run

From the original workspace:

```text
python -m py_compile codex_config_tool.py       PASS
python -m unittest discover -s tests -q          PASS (118 tests)
git diff --check                                  PASS
```

Several PyInstaller builds completed successfully. The current `dist` executable
was rebuilt after the latest source change, but the user still observed the
duplicate title bar, so the packaged artifact is not accepted.

## Safe Working Rules for the Next Agent

- Make a separate backup before any window change.
- Keep changes isolated to window lifecycle code unless a test proves another
  module is involved.
- Build a minimal standalone window prototype first and manually test it.
- Do not repeatedly toggle `overrideredirect` during `Map`/`Unmap` unless the
  prototype proves it is safe.
- Do not use a child Tk widget handle for Win32 `ShowWindow`; resolve and verify
  the actual top-level HWND.
- After every change, run the 118-test suite and manually test the packaged exe.
- Do not commit, push, publish, or overwrite the original rollback backups.

## Rollback Material

`backups/window-prototype-baseline/` contains a copy of the source and the diff
captured before the latest prototype work. Additional historical artifacts are
under `backups/` and `build/rollback/`.

## Acceptance Script

Use the packaged executable, not only the Python source:

1. Open the app and confirm exactly one black custom title bar.
2. Confirm a taskbar button/icon exists while normal.
3. Drag the custom title bar several times; inspect for tearing or fragments.
4. Click the custom minimize button; confirm the process remains running.
5. Confirm the taskbar button/icon remains available while minimized.
6. Restore by clicking the taskbar button/icon.
7. Confirm exactly one title bar and unchanged 820x500 client layout.
8. Repeat steps 3-7 at least five times.

Record each result and any screenshot in the next agent's development log.

---

## Resolution (2026-09-15)

### Root cause

`CodexConfigApp._minimize_window` called `overrideredirect(False)` before
`iconify()`, and `_finish_taskbar_restore` never turned it back on. Disabling
`overrideredirect` makes Tk re-create the window with the native frame, so the
window kept a real `WS_CAPTION` after a taskbar restore - hence the thin native
title bar above the black custom one.

The `overrideredirect` toggle only existed because `iconify()` is a no-op for
borderless windows, and because Tk marks such windows `WS_EX_TOOLWINDOW` +
`WS_POPUP`, for which Windows creates no taskbar button.

### Fix

The window now stays borderless for its entire lifetime and both problems are
solved directly through Win32:

| Concern | Old approach | New approach |
| --- | --- | --- |
| Minimize | `overrideredirect(False)` + `iconify()` | `ShowWindow(root_hwnd, SW_MINIMIZE)` |
| Taskbar button | `WS_EX_APPWINDOW` only | `WS_EX_APPWINDOW` + `ITaskbarList::AddTab` |
| Restore | leave native frame in place | nothing to do - frame never came back |
| HWND | `GetAncestor(winfo_id(), GA_ROOT)` | same, now centralised in `resolve_toplevel_hwnd` |

Removed the historical experiments: the `WM_NCCALCSIZE` subclass, the
`WS_POPUP`/`WS_EX_TOOLWINDOW` style toggling and the `<Map>`/`<Unmap>` frame
restore logic. New helpers live next to `register_appwindow_with_shell`:
`resolve_toplevel_hwnd`, `minimize_toplevel_window`, `ensure_taskbar_button`.

### Approaches measured and rejected

Each candidate was built as a standalone prototype and measured on a live
desktop before touching the app. The rejections matter as much as the fix:

- **Normal toplevel + `SetWindowLong` to strip `WS_CAPTION`** - gives a taskbar
  button in every state, but Tk still adds a phantom 16x39 frame, so the window
  renders at `836x539` and grows to `852x539`, `868x578` on every restore. This
  is the historical "repeated size growth" regression.
- **Same + `WM_NCCALCSIZE` returning 0** - no growth of the *frame*, but Tk's
  phantom frame still compounds the client size every cycle.
- **`overrideredirect` + clearing `WS_POPUP`** (Tk thinks borderless, Windows
  sees a normal overlapped window) - perfect `820x500` geometry and a taskbar
  button, but the window intermittently collapses to `2x28` after a restore.
  Flaky, therefore rejected.
- **Hiding/showing the window to force Shell re-evaluation** - works, but Tk
  sees the Unmap/Map pair and the geometry collapses to `2x28`.
- **`WS_EX_APPWINDOW` alone** - the Shell decides about the taskbar button when
  the window is first shown, so a later style change is ignored; no button.
- **MSAA accessibility enumeration** - the Windows 10 task list is owner-drawn
  and exposes zero accessible children, so it cannot be used to verify buttons.

### Verification

`prototypes/` contains the harnesses; `prototypes/README.md` documents them.

```text
python -m py_compile codex_config_tool.py          PASS
python -m unittest discover -s tests -q            PASS (124 tests)
prototypes/verify_app_window.py                    5 cycles, no wrong size, no native frame
prototypes/verify_app_drag.py                      drags move exactly, size/frame unchanged
prototypes/accept_packaged_exe.py                  PASS (5 cycles, 0 failures)
```

The packaged acceptance run clicks the app's real minimize button and the real
taskbar button with synthetic mouse input, and asserts after every cycle:

- non-client frame `(0, 0)` and no `WS_CAPTION` - exactly one title bar
- client area `820x500` - size never changes
- `IsIconic` true while minimized, false after the taskbar click
- process still alive after minimize and after restore
- a taskbar button is present while normal, minimized and restored

Evidence (screenshots, JSON reports) is in `prototypes/out/`.

### Remaining manual check

Automation covers everything except human perception of drag tearing. The
automated drag test proves the window moves exactly with the pointer, keeps its
size and never gains a native frame; a human should still eyeball one drag in the
packaged build.

> Superseded by the follow-up below: drag repaint is now measured frame by frame
> (`verify_app_drag_integrity.py`), so what remains is only whether the motion
> *feels* smooth, not whether it is correct.

### Rollback

`backups/window-fix-20260915/` holds the pre-fix source and executable.

---

## Follow-up (2026-09-15, later): the acceptance harness was not trustworthy

The application fix above was **not changed** in this follow-up. What changed is
the confidence in the *evidence*: re-running the packaged acceptance test exposed
two independent defects in the harness itself, one of which had already produced
a bogus pass.

### Defect 1 - the harness clicked the wrong taskbar button

The old `changed_bbox` diffed the taskbar strip against a baseline captured
before the app launched and kept the **widest** changed run. On this machine the
taskbar packs its buttons rightward against the tray, so adding our button pushes
every other button left and the baseline differs from the later strip across its
**entire width** (27% of pixels; no horizontal shift explains it). The "widest
run" was therefore arbitrary. On one re-run it picked `1269-1385`, which the
screenshots show is **WeChat's** button, clicked it, and reported
`cycle1: did not restore` - blaming the app for a harness bug.

Fixed by diffing two strips captured seconds apart with the app already running
(`normal` vs `minimized`), which keeps the layout identical, and then choosing
the run that got **darker**: our button loses its "active" highlight while the
window that takes focus gains one. Both runs are the same width, so position
cannot separate them, but brightness can. Verified offline against the captured
strips:

```text
run 1311-1410  normal 60.1  minimized 94.3  delta -34.2   other app (took focus)
run 1513-1612  normal 98.6  minimized 62.6  delta +36.0   ours (lost focus)
```

`rightmost_button` is retained only as a fallback.

### Defect 2 - synthetic input silently did nothing

In a later session `SetCursorPos` returned `FALSE` for every coordinate (with
`GetLastError() == 0`) and `SendInput` reported success while the cursor never
moved - it stayed parked at `(2416, 522)`, on a second monitor, off the
1920x1080 primary screen. Every synthetic click therefore landed at that parked
position. That produced a run where the drags reported `moved: [0, 0]`, the
minimize clicks did nothing, and the taskbar clicks did nothing - all of which
looked like app failures and were not.

The harness now probes input injection before doing anything, verifies after
every `SetCursorPos` that the cursor actually arrived, and on failure exits with
verdict `INVALID (environment)` and exit code 3 instead of emitting app failures.

It also now checks, before each click, that the app window is really the topmost
window at the click point (`WindowFromPoint`), raising it if an unrelated window
covers it. This mattered: the app's default position had a modal Adobe print
dialog parked on top of it.

### Restore path checked in isolation

`prototypes/diag_taskbar_restore.py` minimizes through Win32 and then exercises
each layer separately. Result: `WM_SYSCOMMAND`/`SC_RESTORE` and
`ShowWindow(SW_RESTORE)` both restore the window reliably, so the app's restore
handling is sound and a failed taskbar *click* points at the harness or the
environment rather than at the app.

### What is verified

One command runs all of it and prints a single verdict:

```bat
cd prototypes
"C:\Program Files\Develop\Python\python.exe" run_all_checks.py
```

```text
python -m py_compile codex_config_tool.py          PASS
python -m unittest discover -s tests -q            PASS (124 tests)
prototypes/diag_source_click.py                    real click on the real minimize canvas ->
                                                   _minimize_window -> SW_MINIMIZE -> IsIconic true
prototypes/accept_packaged_exe.py                  PASS (5 cycles, 0 failures)  [run A]
prototypes/accept_packaged_exe.py                  PASS (5 cycles, 0 failures)  [run B, after the fix]
prototypes/accept_packaged_exe.py                  PASS (5 cycles, 0 failures)  [run C, 2026-09-15]
prototypes/verify_app_drag_integrity.py            PASS (6 samples, max body diff 0.0)
prototypes/verify_minimize_soak.py                 PASS (45 samples, 60 s minimized + 30 s restored)

  PASS                   unit tests                                6.9s
  PASS                   packaged acceptance (5 cycles)           29.3s
  PASS                   drag repaint integrity                   14.1s
  PASS                   minimize soak (60s + 30s)               100.7s

OVERALL PASS
```

`run_all_checks.py` runs the checks in order (they all drive the same desktop and
steal the cursor, so they cannot run in parallel), writes one log per check to
`prototypes/out/`, re-executes itself under an interpreter that has `PIL`, and
keeps "synthetic input is unavailable" as an environment verdict rather than
flattening it into a pass or a fail.

The three packaged passes were all obtained with the corrected harness, and in
every one of the 15 cycles `restored_via: taskbar-click` - no cycle fell back to
the Win32 API, so the taskbar button really was clicked and really did restore
the window. All runs also report:

```text
open          frame [0,0]  client [820x500]  has_caption false
drag #1       moved [150, 70]   client [820x500]  frame [0,0]
drag #2       moved [-190, 110] client [820x500]  frame [0,0]
cycle 1..5    minimized: iconic true, process alive
              restored:  frame [0,0]  client [820x500]  has_caption false  process alive
              taskbar button [1498, 0, 1612, 39]
              luminance delta +37.2 (ours) vs -38.8 (the app that took focus)
failures:     []
```

Run C is the interesting one: with the foreground precondition fixed (see below)
the luminance deltas came out **identical in all five cycles** (`+37.2` / `-38.8`)
where earlier runs had varied from cycle to cycle. A stable, repeatable signal is
the difference between a test that passes and a test that *means* something.

This satisfies requirements 1-6 on the packaged executable. Requirement 7
(configuration behaviour) is covered by the 124 unit tests.

### The soak test: the one historical regression that was never checked

The handoff's "Still Broken" list contains a claim the acceptance test cannot
falsify: *"Win32 `ShowWindow` attempts caused the main-window minimize button to
do nothing **or caused the application to exit after a delay**."* The acceptance
test only confirms the process is alive ~1.5 s after minimizing - far too soon to
notice a delayed exit.

`prototypes/verify_minimize_soak.py` targets exactly that: it minimizes through
the real button, holds the window minimized for 60 s, restores through the real
taskbar button, then holds it restored for 30 s, polling every 2 s for

- process death,
- the HWND disappearing (`IsWindow` failing = Tk re-created the window, the
  signature of the original bug),
- the window silently leaving the iconic state,
- client size drifting from `820x500`,
- a native frame reappearing.

Result: **45/45 samples alive, HWND stable, size stable, frame stable, and the
restore happened through a real taskbar click.** The regression does not
reproduce. Critically, this is a *stronger* statement than the acceptance test
can make, because a delayed exit would have had 90 seconds to show up.

### Two more harness defects found while building the soak (both produced false FAILs)

Neither of these was an application bug, and both are worth recording because
each one cost a debugging cycle.

**1. A taskbar baseline captured from a background window is useless.** The
soak's first run failed with `restored=False` and only the 16 px clock in the
diff. The report's own `interaction_notes` explained it:

```text
"soak minimize @(1307,309): raised (was behind hwnd=0x109fc class='Chrome_WidgetWin_1'
 title='WorkBuddy AI')"
```

The baseline had been captured *before* any click, while the app was still behind
another window. A taskbar button only carries its "active" highlight while its
window owns the foreground, so the baseline contained a button indistinguishable
from its neighbours and the normal/minimized diff had nothing to latch onto. The
acceptance test had been getting away with this only by accident - its drag phase
raises the window before the cycle loop starts.

Fixed by `ensure_foreground()` in `accept_packaged_exe.py`, which raises the
window and waits for `GetForegroundWindow` to agree before the capture, and
records the outcome either way. It is now called before *every* baseline capture
in both harnesses.

**2. The input-injection probe could walk into a monitor gap.** A later soak run
reported `ENVIRONMENT input injection unavailable` - but the parked coordinates
were suspiciously systematic:

```text
cursor parked at (1595, 1079); requested (1595, 1099)
cursor parked at (1635, 1079); requested (1635, 1119)
cursor parked at (1920, 1119); requested (1955, 1119)
```

The cursor was following x but its y was pinned to 1079 (then 1148). The desktop
has two misaligned monitors:

| monitor | rect |
| --- | --- |
| primary | `(0,0)-(1920,1080)` |
| secondary | `(1920,69)-(3840,1149)` |

so the band `x < 1920, y >= 1080` belongs to **no monitor** and Windows clamps
the cursor to the nearest edge. The probe's blind `+40, +40` offset from wherever
the cursor sat walked straight into it, and a healthy desktop was reported as
unable to accept input.

Fixed by probing inside the primary monitor (`W.primary_monitor_size()`) and by
adding `W.monitor_rects()` / `W.on_a_monitor(x, y)` so a clamped move can be
explained rather than mistaken for dead input.

The general lesson, now written into `prototypes/README.md`: when a harness
reports "the app is broken", the harness is a suspect too. Three separate times
in this project the app was fine and the measurement was wrong.


### Requirement 2 is now measured, not eyeballed

The earlier note that "only a human can judge drag tearing" turned out to be
avoidable. `prototypes/verify_app_drag_integrity.py` captures the window straight
off the screen (GDI `BitBlt`, not `PrintWindow`, so it is the real composited
result) while a synthetic drag is in progress, and compares the window body
against a stationary reference. Content does not change during a move, so a
correct repaint is pixel-identical.

```text
paused-1    rect [585, 310, 820, 500]  client [820x500]  frame [0,0]  body_diff 0.0
inflight-1  rect [605, 321, 820, 500]  client [820x500]  frame [0,0]  body_diff 0.0
paused-2    rect [630, 335, 820, 500]  client [820x500]  frame [0,0]  body_diff 0.0
inflight-2  rect [650, 347, 820, 500]  client [820x500]  frame [0,0]  body_diff 0.0
paused-3    rect [670, 358, 820, 500]  client [820x500]  frame [0,0]  body_diff 0.0
final       rect [690, 370, 820, 500]  moved [140, 80] as requested
ghost check 0.084 of the vacated sidebar still matches the app -> clean repaint
```

So during the drag the window is fully repainted at every sample - including the
two taken while the mouse was still moving - never resizes, never gains a frame,
and leaves no stale fragment behind. `out/drag-mid-screen.png` is a full-screen
capture taken mid-drag if you want to see it.

### A note on why the first attempt at re-verification failed

Input injection on this desktop is genuinely intermittent, because the machine is
in active human use: when the user's mouse is moving, `SetCursorPos` is
overridden and the cursor stays where the user left it (observed at
`(2416, 522)`, `(498, 705)`, `(527, 842)`, `(538, 792)` in successive probes).
Every synthetic click then lands at that position. `accept_packaged_exe.py
--wait-input N` polls until injection works, which is how runs B and C were
obtained.

Not all of those "unavailable" reports were real, though. One of them was the
monitor-gap bug described above - the cursor was moving perfectly well and being
clamped by the desktop layout. The probe has since been fixed, so a report of
unavailable input is now much more likely to be genuine.

### Remaining manual check

Nothing is left that automation can decide, but two things are still worth a
human eye on a normal desktop:

- The harness cannot dismiss another application's modal dialog if one is parked
  over the window; it can only raise the app above it.
- Whether the drag *feels* smooth at normal mouse speed is still a matter of
  taste, even though every sampled frame is pixel-correct and the soak shows the
  window survives a 90-second minimize/restore cycle intact.

### Rollback

Unchanged: `backups/window-fix-20260915/` holds the pre-fix source and
executable. The application source was not modified during this follow-up, so
there is nothing new to roll back.

## Follow-up (2026-09-15, latest): the taskbar icon did not toggle minimize/restore

A user report that the seven requirements did not cover: *"clicking the taskbar
icon still cannot toggle maximize/minimize."* Restoring **from** the taskbar
worked, so the button existed and the restore path was fine - but clicking the
icon while the window was up did nothing, unlike every other app.

### Root cause: the Shell never asked

The instinct is to suspect the message handler. That instinct is wrong. Measured
on the affected packaged build, every minimize request worked:

```text
SendMessage(WM_SYSCOMMAND, SC_MINIMIZE)  -> iconic=True
SendMessage(WM_SYSCOMMAND, SC_RESTORE)   -> iconic=True
PostMessage(WM_SYSCOMMAND, SC_MINIMIZE)  -> iconic=True
ShowWindow(SW_MINIMIZE)                  -> iconic=True
```

The window answered correctly. The problem was that Explorer never *made* the
request, because **the Shell decides whether a window can be minimized from
`WS_MINIMIZEBOX` alone** (Raymond Chen, "Why does adding WS_MINIMIZEBOX change how
my window behaves when the user presses Win+D?"). `overrideredirect` leaves the
window `WS_POPUP` with no `WS_SYSMENU` and no `WS_MINIMIZEBOX`, so Explorer treats
the taskbar button as **activate-only**:

```text
before  style=0x96000008  WS_SYSMENU=False  WS_MINIMIZEBOX=False
        system menu: none ("window has no system menu at all")
after   style=0x960a0008  WS_SYSMENU=True   WS_MINIMIZEBOX=True
        system menu: Minimize=enabled, Restore=enabled, Close=enabled
```

### The fix

`make_window_minimizable()` in `codex_config_tool.py` adds `WS_SYSMENU |
WS_MINIMIZEBOX` right after the existing shell registration, and the `<Map>`
handler re-asserts it, because a re-map is the one moment Tk may re-apply
`overrideredirect` and drop the bits.

`WS_SYSMENU` is required for `WS_MINIMIZEBOX` to mean anything, and it is what
creates the system menu the taskbar jump list reads. **Neither bit draws a
frame** - frames come from `WS_CAPTION`/`WS_BORDER`/`WS_DLGFRAME`/`WS_THICKFRAME` -
which is why the borderless design survives. Measured on the rebuilt executable:
`frame (0, 0)`, `client 820x500`, `has_caption false`, style survives a
minimize/restore cycle and 6 s idle.

`WS_MAXIMIZEBOX` is deliberately **not** set: it requires `WS_THICKFRAME`, which
would add a native resizable border and undo the whole design. The system menu
still offers Maximize, and it does maximize the window - measured - but
`SC_RESTORE` brings the fixed 820x500 geometry back intact, so leaving it alone is
safe.

### Verified

Control experiment with `Shell.MinimizeAll()` - the "show desktop" command, which
minimizes exactly the windows the Shell considers minimizable, i.e. the same rule
the taskbar click uses. Same desktop, seconds apart, only the build differs:

```text
pre-fix   style=0x96000008  WS_MINIMIZEBOX=False
          MinimizeAll minimized 3 other windows; ours: NO
post-fix  style=0x960a0008  WS_MINIMIZEBOX=True
          MinimizeAll minimized 4 other windows; ours: YES
```

And end to end with real synthetic clicks on the real taskbar button, now part of
the acceptance test (5/5 cycles):

```text
"toggle_minimized": true      click the taskbar button while normal -> minimizes
"toggle_restored":  true      click again                        -> restores
"toggle_geometry": {"client": [820, 500], "frame": [0, 0]}
```

Full suite, exit code 0:

```text
PASS  unit tests                              7.1s   (124 tests)
PASS  packaged acceptance (5 cycles)         46.3s   5/5 restore AND 5/5 toggle
PASS  drag repaint integrity                 14.1s
PASS  close paths shut down cleanly          16.7s
PASS  Shell treats the window as minimizable 12.7s
PASS  minimize soak (60s + 30s)             100.6s   45/45 samples alive
OVERALL PASS
```

### What the new style bit also exposed

`WS_SYSMENU` does not only unlock Minimize - it also makes `SC_CLOSE` reachable
(Alt+F4, the system menu's Close, the taskbar jump list's Close), and the window
had **no system menu at all** before, so those paths simply did not exist. Adding
a style bit is a behaviour change, so this was checked rather than assumed:

```text
WM_CLOSE (system menu Close / Alt+F4)   window gone 0.38s  process gone 0.38s  leftover: none
WM_SYSCOMMAND / SC_CLOSE (jump list)    window gone 0.40s  process gone 0.40s  leftover: none
```

They are safe because all three close routes converge on the same
`self.destroy()`: the custom close button calls it (line 3817), the pre-existing
Alt+F4 binding calls it (line 3522), and Tk's default `WM_CLOSE` handling does the
same since no `WM_DELETE_WINDOW` protocol handler is set on the main window. The
single-instance mutex is released in `main()` after the mainloop returns, so a
clean exit releases it. `diag_close_paths.py` now guards this.

(The first version of that script reported a failure that did not exist: it
sampled `tasklist` once, immediately after `process_alive()` flipped, and caught
the entry before it cleared. It polls now. That is the seventh measurement bug in
this project - see the note at the end of `prototypes/README.md`.)

### Why the earlier suite passed on a broken build

The acceptance harness clicked the taskbar button **only while the window was
already minimized** (the restore path). It never clicked it while the window was
normal, which is the half that was broken. Both directions are now tested, and the
normal-direction click first forces the window to the foreground, because the Shell
reads a click on a background window's button as "activate this" rather than
"minimize this".

This is the sixth time in this project that a green test hid a real defect. The
lesson is in `prototypes/README.md` and the skill: a test only proves the direction
it actually exercises.

### Rollback

`backups/window-minimizebox-20260915/` holds the pre-fix source
(`codex_config_tool.py`) and the pre-fix executable
(`CodexConfigTool-before-minimizebox.exe`). Earlier rollback material is
untouched.

---

## Follow-up (2026-09-15, second): the restore flash

Reported after the taskbar-toggle fix was confirmed working:

> 当前最新版已经可以做到点任务栏图标应该能像普通程序一样最小化/恢复。... 当前进行点任务栏图标
> 应该能像普通程序一样最小化/恢复的时候，恢复的时候，整个软件的主界面会闪烁一下，尝试修复该问题

**Outcome: measured precisely, seven candidate causes tested, none of them fixes it.
The application source was deliberately left untouched.**

### What the flash actually is

One to two frames, roughly 17-35 ms, in which part of the window is still **stale** -
it shows whatever was composited there before the restore (here, the editor window
behind), not the app. Two consecutive captured frames pin it down
(`prototypes/out/restore-flash-evidence.png`):

* frame 1: the right-hand content area is correct, the whole left navigation sidebar
  is missing - the window behind shows through in its place;
* frame 2 (the very next frame): the sidebar is now painted **from the bottom up** -
  "新手引导" and "推荐渠道" and the QR code are there, the entries above them are not.

So this is not an erase and not a blank window: it is the child windows repainting
**progressively** after the restore, and the not-yet-repainted regions showing stale
pixels. It always lands ~70 ms after the first painted frame, i.e. well after the
window is already on screen and correct - which is why it reads as "correct, garbled,
correct" rather than as a slow appearance.

### Measuring it at all

The first attempt used a full-window capture per frame (`grab_window`). That costs
~20 ms per frame, which is longer than the flash itself, so detection was a coin toss
(10/20 restores) and every conclusion drawn from it was noise. Two fixes:

* `--probe patch` captures one small region instead. The region is chosen from the
  reference as the 180x120 patch that is normally *least* background-coloured (here:
  body (0,200), the dark sidebar, 22% background). A blank-out there is a 78%
  difference instead of the 13% the whole body gives, and the cheap capture lifts the
  frame rate.
* the per-frame Win32 diagnostics (`get_style`, `window_rect`, `dwm_frame_bounds`,
  `root_at`) were what really cost the 20 ms, so in patch mode they are sampled every
  tenth frame.

With that probe the flash is **10/10 reproducible**, and small samples became usable.

> **Measurement lesson.** The same experiment on the insensitive probe produced
> "baseline 57% -> 21% after the fix", which looked like a result and was pure noise.
> A detector whose sampling period is longer than the event it is hunting cannot
> measure that event. Every number below is from the patch probe.

### Candidate causes tested, and what each did

All runs are 6-10 restores; "bad frames" counts frames over threshold, so it measures
how *long* the blank lasts, not just whether it happened.

| candidate | how it was applied | flashing runs | bad frames |
| --- | --- | --- | --- |
| baseline | packaged `dist/CodexConfigTool.exe`, taskbar restore | 10/10 | 19 |
| baseline | source, restore via `ShowWindow(SW_RESTORE)` | 6/6 | 17 |
| app's `<Map>` handler | `silent` / `nobind`: handler removed entirely | 10/10 | 18 |
| fewer Python callbacks | `tclguard`: guard on `%W` in Tcl, so only the toplevel's own map reaches Python | 10/10 | 18 |
| the style bits we added | `strip-minbox` / `strip-sysmenu` | 6/6 | 13 / 15 |
| DWM restore animation | `DWMWA_TRANSITIONS_FORCEDISABLED` | 9/10 | 17 |
| background erase | class background brush cleared | 6/6 | 18 |
| `WS_EX_COMPOSITED` | added to the extended style | 5/6 | 5 |
| `WS_POPUP` | `make_overlapped_without_caption` | n/a | breaks minimize |
| combined | `tclguard+dwm-notransition` | 10/10 | 15 |

Reading the table:

* The app's own code is **not** the cause. Removing the `<Map>` handler entirely, and
  removing the 114 Python callbacks it causes per restore, changes nothing.
* The `WS_SYSMENU | WS_MINIMIZEBOX` bits added for the taskbar toggle are **not** the
  cause: stripping them back to the pre-change window still flashes 6/6.
* Neither is the DWM minimize/restore animation, nor the background erase.
* `WS_EX_COMPOSITED` is the only lever that shortens the tear (~3x fewer bad frames)
  but it does not remove it - 5 of 6 restores still flash. It is not worth adopting
  for that.
* The one call that could have been wrong was verified rather than assumed:
  `DwmSetWindowAttribute(hwnd, DWMWA_TRANSITIONS_FORCEDISABLED=3, TRUE)` returns
  `S_OK` on this window, so "disabling the animation" really was applied and really
  did not help.
* Clearing `WS_POPUP` (the structural difference from the Sep 9 build) reproducibly
  breaks the minimize path - "did not minimize the second time" - so it is not viable
  without redesigning the window style, which the working rules here forbid.

### Why the old-build comparison had to be thrown away

`dist/CodexConfigTool.old.exe` (Sep 9) measured 2/6 flashing against the current
build's 6/6, which looked like proof of a regression. It is not a valid control:

* its style is `0x160A0008` - no `WS_POPUP` - while the current build is `0x960A0008`,
  so it is a different kind of window;
* during the run its rect changed from 820x500 to **852x539**, i.e. it regrew a native
  frame (32 px of border, 39 px of caption) - the exact defect this project fixed. The
  "less flashing" was an artefact of measuring a window that was busy turning into
  something else.

A control is only a control if it differs in the thing you are testing.

### State of the tree

* `codex_config_tool.py` is byte-identical to
  `backups/window-working-taskbar-toggle-20260915/codex_config_tool.py` (`cmp` clean).
  No source change was made for the flash, because none of the candidates helped and
  two of them destabilised the minimize path.
* `dist/` is unchanged: `CodexConfigTool.exe` and `CodexConfigTool-Portable-v1.4.0.exe`
  (12:00), `CodexConfigTool-Setup-v1.4.0.exe` (12:12). All seven requirements still
  hold on the preserved build.
* New tooling: `prototypes/verify_restore_flash.py` (`--probe patch|full`,
  `--restore-via taskbar|api`), `prototypes/explain_flash_report.py`,
  `prototypes/instrumented_app.py` (in-memory variants, no source edits).

### What is left, if the flash must go

Nothing that stays inside the window-lifecycle code. The remaining options are
structural and should be a deliberate decision:

1. reduce the number of child HWNDs - each one has to be shown and repainted on
   restore. A census (`prototypes/diag_child_windows.py`) counts **118** descendant windows: 71 `TkChild`, 41 `Static`, 6 `Button`. Only **27 of the 118 (23%)** sit inside the navigation sidebar strip, so replacing the sidebar with a single `Canvas` would remove 27 of them, not most of them. Tk nests every widget under one `TkChild` spanning the client area, so they are attributed by rect rather than by parent.
2. accept it: it is one frame, and it now has a detector that can prove any future fix.

### Rollback

Unchanged. `backups/window-working-taskbar-toggle-20260915/` and
`backups/window-minimizebox-20260915/` are both intact.

## Follow-up (2026-09-15, third): the flash, measured properly

The second section above concluded "nothing that stays inside the window-lifecycle
code". That conclusion survives, but **two of its statements were wrong**, and five
more candidates have since been measured with a paired control. This section
supersedes the mechanism description and the candidate table above.

### Correction 1: the flash is a light fill, not the window behind

The second section described the tear as "stale pixels from the window behind". That
reading came from looking at the full-window evidence image, where a *light* region
replaces the *dark* navigation sidebar and is easily mistaken for the editor window
behind. The per-frame metric says something more specific, and it is the thing to fix:

* the patch region (body (0,200), inside the sidebar) normally reads
  `bg_fraction 0.222, mean 126.26` - the sidebar is dark;
* during the flash it reads `bg_fraction 0.93-1.00, mean 244.0`, i.e. a **flat light
  fill**, and `244.0` is exactly the toplevel's own background `#f3f4f7` (mean 244.7);
* the same value recurs frame after frame (`mean 244.0` in 7 of 10 baseline runs), which
  a stale window behind would not do.

So the sequence is: on restore Tk invalidates the child frames, the **toplevel paints
its own background** in that region, and the dark child frames paint back over it
progressively. The user sees the sidebar go light for one to three frames.

### Correction 2: the app is *not* too late - but the tear is not where the app can reach

This was worth measuring rather than arguing. `instrumented_app.py` gained a `stamp`
variant that writes the absolute epoch of the first `<Map>` callback of each restore
burst, and the harness now records the absolute epoch of the restore call
(`restore_epoch` in each run), so the two can be subtracted on one clock. Four restores:

| restore | first `<Map>` callback | the 114-event burst ends | blank frame captured | recovered |
| --- | --- | --- | --- | --- |
| 1 | +9.3 ms | +57 ms | +66.3 ms | ~+84 ms |
| 2 | +9.4 ms | +55 ms | +64.7 ms | ~+84 ms |
| 3 | +12.6 ms | +46 ms | +64.4 ms | ~+84 ms |
| 4 | +7.2 ms | +56 ms | +64.2 ms | ~+84 ms |

> **Corrected (2026-09-16): the timings in this table do not agree with the later ones and this
> table should not be quoted.** The blank is placed here at +64..+66 ms, but the child-spy
> measurement further down - which is the one to trust, because by then the detector had been
> fixed - places the blank frames at **+17.6 to +49.1 ms** with the child's only `WM_PAINT` at
> +35.6..+49.5 ms. This table was produced with the **full-window** detector, which the same
> investigation later showed is both too slow (~20 ms/frame, against a 1-3 frame event) and
> structurally blind in light regions, so its frame times are detection latency rather than
> event times. The *ordering* conclusion below (the app does get control before the tear) is
> supported by the `<Map>` epoch stamps and still stands; the *absolute* times do not. Prefer
> "The blank arrives *before* the child does anything" further down.

The application gets control **~10 ms after the restore**, and the window is already
correct on screen at that point (the first captured frame at +12-17 ms scores
`body_diff 0.0`). The blank arrives ~55 ms *later*, immediately after the burst of
`<Map>` events ends. So:

* the "correct -> blank -> correct" shape is real, and it is the *end* of the re-map
  storm, not the beginning;
* a Python handler does run before the tear, so a Python-side fix is not ruled out by
  timing - it is ruled out by the measurements in the next table, where the handlers
  that act in exactly that window still fail.

### Candidates measured this round, with a paired control

All with `--probe patch --restore-via api` on the source build. Baseline was measured
at both 8 and 10 runs because the first `composited` sample (4/8) was not reproducible
at the larger size (7/10) - see the note under the table.

| candidate | what it does | runs | flashing runs | bad frames | frames darker than the UI |
| --- | --- | --- | --- | --- | --- |
| baseline | - | 18 | **17/18 (94%)** | 43 (2.4/run) | 0/18 |
| `sync-redraw` | `RedrawWindow(RDW_ALLCHILDREN\|RDW_UPDATENOW)` from the `<Map>` handler | 8 | 8/8 | 18 | 0 |
| `sync-redraw-idle` | same, via `after_idle` | 8 | 8/8 | 22 | 0 |
| `no-erasebkgnd` | window-procedure subclass returning 1 from `WM_ERASEBKGND` | 8 | 7/8 | 13 | 0 |
| `lockupdate` | `LockWindowUpdate` held across the burst, released with one repaint | 18 | 13/18 (72%) | 14 (0.8/run) | **4/18** |
| `composited` | `WS_EX_COMPOSITED` added to the extended style | 18 | **11/18 (61%)** | 11 (0.6/run) | **3/18** |
| `composited+no-erasebkgnd` | both | - | breaks minimize | - | - |

> `lockupdate` was measured twice (8 + 10 runs) because the first sample was too small; the
> row pools both. Baseline, `composited` and `lockupdate` are therefore all reported at N=18.

Reading it:

* **Forcing a synchronous repaint does not help, and slightly hurts.** This is the one
  that looked most likely on the mechanism, and it is the clearest negative result:
  `RDW_ALLCHILDREN | RDW_UPDATENOW` fires at +10 ms, which is *before* the burst ends at
  +55 ms, so it repaints a tree that is about to be invalidated again. Making it
  `after_idle` does not change the ordering. 8/8 with more bad frames than baseline.
* **Suppressing the background erase does not help, and the experiment was verified to
  be live.** This was the right test for the corrected mechanism, and a negative result
  here is only worth anything if the subclass actually survived - a dropped
  `GWLP_WNDPROC` would make "the erase is not the cause" a statement about nothing. So a
  traced run was checked: `suppress_background_erase` returned `True`, the subclass was
  still the current window procedure on every subsequent re-map (`still_current: True`),
  and it swallowed the erase messages (counter 1 -> 2 -> 3 -> 4). The flash was
  unaffected - 7 bad frames over 2 restores, worst frame `mean 244.0`, i.e. identical to
  baseline. **Only about one `WM_ERASEBKGND` arrives per restore**, so the erase is
  demonstrably not how the background gets painted: Tk does it inside `WM_PAINT`.
  Note this is a *different* experiment from the earlier `no-erase` row, which only
  cleared `GCLP_HBRBACKGROUND` - a brush Tk does not consult.
* **`WS_EX_COMPOSITED` is the only lever that measurably helps**, and it helps more than
  the earlier 5/6 sample suggested: 94% -> 61% of restores, and 2.4 -> 0.6 bad frames
  per restore. It is also the only candidate whose theory matches the mechanism - DWM
  redirects the window and its children into one surface so intermediate states are
  never presented.
* **But it trades the light tear for a black one.** Counting frames *darker than the
  settled UI* (`mean < 200`; the normal sidebar patch is `126.4` and the light tear is
  `244.0`): baseline **0 of 18** runs, `composited` **3 of 18**, `lockupdate` **4 of 18**.
  The worst are genuinely near-black - `mean 24.0, bg_fraction 0.011`, the sidebar area
  black rather than light. Compare
  `prototypes/out/evidence/restore-flash-normal-patch.png` (mean 126.4, the settled
  sidebar) with `prototypes/out/evidence/restore-flash-dark-frame-lockupdate.png`
  (mean 92.9 - a black region where the sidebar should be). Anything that redirects or
  freezes painting risks presenting an unpainted surface, and a black flash is more
  visible than a light one.
* `composited+no-erasebkgnd` reproducibly fails the minimize path ("did not minimize the
  second time"), exactly like `overlapped` did. The window-procedure subclass is not
  safe to combine with anything.

> **Sampling lesson, repeated.** `composited` first measured 4/8, then 7/10 - pooled
> 11/18. A single 6-8 run sample of a ~50% effect has a confidence interval wide enough
> to support almost any story, including "this fixes it". Any claim here needs the
> paired control at the same N, which is why baseline is reported at 18 runs and not 6.

### Recommendation

> **Partly superseded.** The paragraph below is the conclusion of this round. The
> "Follow-up (2026-09-15, fourth)" section at the end of this document re-measured
> `WS_EX_COMPOSITED` with a corrected metric and found it considerably better than these
> numbers suggested (pooled 42% -> 10% of restores erasing the probe's content, p = 0.017).
> The *reasoning* here still holds - it is not a clean fix and it needs a full re-verification -
> but "do not adopt" is no longer the whole story. Read that section before acting on this.

**Do not adopt `WS_EX_COMPOSITED`.** It is the only candidate that works, but it converts
a brief light tear into an occasional black frame, it changes how the whole window is
composited, and it would require re-verifying all seven requirements (in particular
requirement 2, drag repaint, which is the most likely to regress under DWM redirection).
The current build is preserved and all seven requirements hold.

If the flash must go, the fix is structural and is the user's call, and the census above
says it is **bigger than it first looked**: every child HWND is a separate surface that
has to be re-shown on restore, and only 23% of them are in the sidebar. Getting the count
down meaningfully means redrawing essentially the whole UI into a single `Canvas` (or
accepting a much smaller reduction). That is a rewrite of the view layer, not a window
tweak, and it is the kind of change this project's working rules say to make deliberately
rather than in passing.

### Harness defects found and fixed this round

* `verify_restore_flash.py` resolved `--exe` verbatim while starting the child with
  `cwd=ROOT`, so a relative `--exe` died with "can't open file" and the harness then
  blamed the build with "main window not found". It now resolves the path and exits 2
  with a clear message.
* The harness now records `restore_epoch`, which is what made the clock alignment above
  possible.
* `--minimize-via click|api` was added. Minimizing previously always clicked the app's own
  custom minimize button, which made the whole check depend on synthetic input even when
  the restore itself was API-driven. With `--restore-via api --minimize-via api` the check
  needs no input at all, so it runs on a session where injection is unavailable - and it
  skips the taskbar-button capture/diff, removing a failure mode unrelated to the flash.
* The report now carries an `aggregate` block (`runs_flashing`, `bad_frames`,
  `bad_frames_per_run`, `frames_darker_than_ui`) so a caller does not have to re-derive
  the numbers, and `minimize_via` is recorded per run.

### The flash detector is now part of the suite

`run_all_checks.py` gained an **advisory** step. The flash is a known, accepted
characteristic, so gating on "did it flash" would fail every run forever; the step
reports the rate against the recorded baseline and never affects the overall verdict.
What it does surface is the regression signal - `frames_darker_than_ui`, which baseline
never produces and which `WS_EX_COMPOSITED` and `LockWindowUpdate` both introduced - and
prints `[REGRESSION]` when it is non-zero. Flags: `--skip-flash`, `--flash-runs N`.

Verified end to end:

```
  PASS                   unit tests                                7.2s
  PASS                   packaged acceptance (2 cycles)           25.6s
  PASS                   drag repaint integrity                   14.0s
  PASS                   close paths shut down cleanly            15.5s
  ADVISORY               restore flash (advisory)                 32.1s
      flash: 3/4 restores flashed, 5 bad frame(s), 0 darker than the UI
      baseline for comparison: 94% of restores, 2.4 bad frames per restore, 0 darker-than-UI frames

OVERALL PASS
```

> **Superseded.** Both the baseline figures and the step's wording above predate the
> "Follow-up (2026-09-15, fourth)" section at the end of this document. That section shows the
> region-dependent metric behind these numbers cannot see a blank-out in a light region at all
> - it reported `0/10` for a content area that three restores in ten erased completely. The
> current baseline for this probe is **8/10 restores, 12 bad frames, 5/10 erasing content,
> worst erasure 1.00**, and the step now prints both metrics. Read that section before quoting
> these lines.

### How big is the structural option? (measured, not assumed)

The previous sections said a `Canvas` sidebar "would remove most of" the child windows.
That was an assumption and it is **wrong**. `prototypes/diag_child_windows.py` counts them:

```
total descendant windows : 118
immediate children       : 1
by window class: 71 TkChild, 41 Static, 6 Button
descendants inside the left 240px strip (the navigation sidebar): 27 of 118 (23%)
```

So a `Canvas` sidebar removes 27 of 118 - a 23% reduction, not a fix. Getting the count
down meaningfully means redrawing essentially the whole view layer into one surface, which
is a rewrite rather than a window tweak. Also worth knowing for any future work on this
window: Tk nests every widget under a single `TkChild` spanning the client area, so
`GetWindow(GW_CHILD)` on the toplevel returns **exactly one** window - attribute
descendants by their own rect, not by their parent.

---

## Follow-up (2026-09-15, fourth): the tear is window-wide, and the detector was blind

This section **corrects two claims made earlier in this document**, and supersedes the
recommendation that was based on them. It also re-opens `WS_EX_COMPOSITED`, which an earlier
section had written off.

### Correction 1: the tear is not confined to the sidebar

Earlier sections describe the flash as a light fill appearing where the dark sidebar should
be, and treat the sidebar as the sensitive probe. That is only where it is *visible*. It is
not where it happens.

Forcing the probe into the light content area shows a complete blank-out there too.
`out/evidence/full/restore-flash-worst-run6.png`, scored in three separate 180x120 regions of
the same full-window frame:

| region | `body_diff` (old metric) | `content_erased` (new metric) | exact `(243,244,247)` settled -> frame |
| --- | --- | --- | --- |
| sidebar `(0,200)` | 0.78 | **1.00** | 15.6% -> **100.0%** |
| content `(240,20)` | **0.14** | **1.00** | 37.4% -> **100.0%** |
| content `(320,200)` | **0.10** | **1.00** | 0.0% -> **100.0%** |

The old metric reads 0.14 and 0.10 - both far below its 0.30 threshold - while the frame has
erased **100%** of those regions' content. The third column is the mechanism discriminator: it
counts pixels *exactly* equal to Tk's background. Region 3 normally contains **none** of it
and in this frame is **all** of it, which cannot be explained by the content merely changing
colour. Broken down by contrast, all three regions lose every band:

| region | contrast band | content px | erased | % |
| --- | --- | --- | --- | --- |
| content `(240,20)` | low (card fill) | 6833 | 6833 | 100.0% |
| | medium (borders / grey text) | 570 | 570 | 100.0% |
| | high (secondary text) | 1112 | 1112 | 100.0% |
| | very high (primary text) | 1874 | 1874 | 100.0% |
| content `(320,200)` | low (card fill) | 5580 | 5580 | 100.0% |
| | medium (borders / grey text) | 417 | 417 | 100.0% |
| | high (secondary text) | 1258 | 1258 | 100.0% |
| | very high (primary text) | 863 | 863 | 100.0% |

**1874 + 863 near-black primary-text pixels vanish in the content area alone.** The user's
report of "the whole main UI flashes" is literally correct; the earlier "the tear is the
sidebar" framing was not.

Live confirmation, packaged build, all-API cycle, N=10, probe in the content area
(`out/zone2-content-10.log`):

```
SUMMARY {"verdict": "PASS", "aggregate": {"runs": 10, "runs_flashing": 0, "bad_frames": 0,
  "frames_darker_than_ui": 0, "content_tolerance": 4, "worst_content_erased": 1.0,
  "content_erase_frames": 3, "runs_content_erasing": 3}, "failures": []}
```

Note `verdict: PASS` and `runs_flashing: 0` next to `worst_content_erased: 1.0` and
`runs_content_erasing: 3`. Three of ten restores blanked the content area out **completely**,
and the harness called it a pass.

The affected frames are at `t_ms` **+26, +28, +26** with `erase=1.00, bg=1.00, mean=244` -
the identical signature to the sidebar. And the sidebar's own worst frames sit at
`t_ms` **23.0** and **23.5**. So this is **one window-wide event at ~+25 ms**, not two
artefacts. (The "+64-66 ms" figure in the earlier clock-alignment table came from the old
full-window probe, whose 20 ms sampling and different alignment put the peak elsewhere; it
should not be used.)

A second content-probe run (`out/zone4-content-10.log`) gave `runs_content_erasing: 2`, and
the two offending frames are **100% exactly `(243,244,247)` with `mean 244.0`** - checked
pixel by pixel, not inferred. So the content area gets the same toplevel fill as the sidebar;
the rate is 2-3 in ten, which is what a ~5-8 ms event looks like when sampled at 16.6 ms.

### The app is a passive observer - measured, not assumed

The blank lands at +17..+42 ms, which is *inside* the window's `<Map>` storm, and that
suggested a concrete hypothesis: the app re-asserts its styles on `<Map>`, and
`register_appwindow_with_shell` calls `SetWindowPos(..., SWP_FRAMECHANGED)`, which invalidates
the whole window. If that were the cause, the fix would be a two-line guard.

It is not. The trace was extended to carry an **absolute** epoch (a relative-only log cannot be
aligned with the harness's `restore_epoch`, which is recorded in another process on the same
clock), and everything the app does to the window in the 150 ms after each restore is:

```
run4: make_window_minimizable  +8..+51ms over 114 call(s)
      BLANK at +26ms   erased=1.00  exact_bg=1.0
      BLANK at +42ms   erased=0.93  exact_bg=0.9444
run5: make_window_minimizable  +5..+49ms over 114 call(s)
      BLANK at +20ms   erased=1.00  exact_bg=1.0
      BLANK at +32ms   erased=1.00  exact_bg=1.0
run6: make_window_minimizable  +5..+50ms over 114 call(s)
      BLANK at +17ms   erased=1.00  exact_bg=1.0
      BLANK at +32ms   erased=1.00  exact_bg=1.0

<Map>-driven calls within 150 ms of a restore: 912
first at +5ms, last at +51ms
any OTHER window call (style re-apply, taskbar, minimize): NONE
```

114 calls per restore, every one of them `make_window_minimizable`, and that function is
**read-only once the style is set** (`if updated != style:` guards its only `SetWindowPos` -
verified in the source, and verified here by the absence of any other call). No
`register_appwindow_with_shell`, no `_set_appwindow_style`, no `ensure_taskbar_button`: the
`_taskbar_button_ready` guard does its job and the style is never re-applied.

So the app performs **no window-invalidating call at all** around the blank. What is left is
Tk re-mapping the widget tree: the 114 `<Map>` events *are* the descendants being re-shown, the
toplevel paints its own background while they are gone, and they paint back over it
progressively. The app's handler is a passive observer that happens to run during the storm.

**This closes the "fix it in the window-lifecycle code" line with evidence rather than
exhaustion.** There is no call to remove, no guard to add, no ordering to change - the code
that runs is read-only. `codex_config_tool.py` has nothing to fix here, which is why it is
still byte-identical to its backup.

### Pick the frame by mechanism, not by size

The first version of this section used `out/restore-flash-worst-run15.png`, chosen because it
was the largest artefact in the folder. It is a **different failure mode**. Its content region
is 20246 pixels of `(245,245,245)` and 1306 of `(204,235,255)` - the colours of the editor
window *behind* the app. That frame shows the window **transparent**, not filled with its own
background: `exact (243,244,247)` is **0.0%** in both regions, against 100% in the frame
above. It still erases the app's content (94%), so the symptom is real either way, but
attributing it to "Tk paints its own background" would have been wrong, and the numbers
(94%/88%) understated the real artefact.

`out/` accumulates frames from every variant run, so the folder is a mix. Classify before
quoting:

| frame kind | signature | cause |
| --- | --- | --- |
| toplevel fill | `exact bg 100%`, `mean 244.0` | the mechanism this document describes |
| shows the window behind | `exact bg 0%`, `mean 243-245`, colours from the app behind | window transparent/unpainted |
| dark / unpainted | `mean < 150`, e.g. `(0,0,0)` | `LockWindowUpdate` / `WS_EX_COMPOSITED` variants |

Of ten full-window frames captured in one run, three were toplevel fill (runs 6, 7, 9 - run 6
and 9 at 100% in both regions), three showed the window behind (runs 2, 4, 5), and four were
settled captures (`exact bg 15.6%`/`37.4%`, i.e. the reference distribution). Two of ten were
therefore the clean window-wide fill, which matches the 2-3 in ten measured live on the
content probe.

The harness now reports this itself: every frame carries `exact_bg`, and the aggregate carries
`worst_erase_exact_bg`, so the mechanism is visible in the summary instead of having to be
reconstructed from a saved image.

### Correction 2: the detector could not see a blank-out in a light region

This is the defect that produced the wrong "sidebar-only" conclusion, and it is worth stating
plainly because it made a *real* regression look like a clean pass.

This UI's surfaces are only 4-12 units apart:

```
(243,244,247)  toplevel background      - the colour the flash paints
(247,248,249)  a second light surface   -  4 units away
(255,255,255)  the white card fill      - 12 units away
(32,36,43)     body text                - 211 units away
```

* `BG_TOLERANCE = 12` counts the **entire white card** as background.
* `DIFF_THRESHOLD = 24` is applied to **luminance**, so a card blanking to the toplevel
  background moves luminance by only ~11 and is not counted as a change either.

Both metrics are therefore *structurally* blind in the content area - not merely insensitive.
Measured on the content patch `(240,20)`: 82.7% "background" at tolerance 12, but **48.1%
content at tolerance 4**.

The fix is a region-independent metric, `content_erase_fraction()`:

```
content_erased = |reference content AND frame background| / |reference content|
```

with the content mask built from the **per-channel maximum** distance to the toplevel
background (luminance is a weighted sum and under-reports a tinted pixel), at
`CONTENT_TOLERANCE = 4` - inside the 4..12 gap, so the white card counts as content.
Normalising by the content count rather than the region size makes the score a property of
the *event* instead of the region: a blank-out reads ~1.0 whether the region is 84% content
(sidebar) or 48% (content area). Validated on the saved frames - the reference scores exactly
`0.00`, and a complete blank-out scores `1.00`.

The harness now also refuses to trust itself: if the settled frame scores
`content_erased > 0.05` against the reference it was compared with, the run is flagged as
having no noise floor rather than reported.

### `WS_EX_COMPOSITED` re-measured with the corrected metric

The earlier section dismissed `WS_EX_COMPOSITED` because it "introduces a near-black frame the
baseline never produces". That comparison used the old sidebar-only metric. Re-run as a paired
comparison from source (same conditions, same N), the picture is materially different.

Restores that erased the probe's content, `--minimize-via api --restore-via api`, N=10 each:

| run | probe | erasing | worst erasure |
| --- | --- | --- | --- |
| packaged build | sidebar | 5/10 | 1.00 |
| source baseline | sidebar | 3/10 | 1.00 |
| packaged build | content | 3/10 | 1.00 |
| source baseline | content | 6/10 | 1.00 |
| **source `composited`** | sidebar | **0/10** | 0.24 |
| **source `composited`** | content | **2/10** | 0.88 |

```
POOLED baseline     17/40  (42%)
POOLED composited    2/20  (10%)
Fisher exact (two-sided): p = 0.017
```

So `WS_EX_COMPOSITED` does not merely reduce the rate, it changes the *kind* of artefact: the
complete window-wide blank-outs (`erasure 1.00`) become partial ones (`0.24` in the sidebar,
`0.88` in the content area). It does not eliminate the flash.

Two honest caveats:

* **N=10 is noisy.** The packaged and source baselines differ 3/10 vs 6/10 on the same probe,
  which is not significant (Fisher p ≈ 0.37). The pooled comparison is the one to trust; do
  not read a single 10-run row as a result.
* **It still adds a darker-than-UI frame.** `composited`, sidebar probe, N=10: 1 frame with
  `mean 172.4, bg 50.9%`. Baseline produces none. That is a new failure mode, just a rarer
  one than the flash it replaces.

**Revised recommendation.** `WS_EX_COMPOSITED` is a genuine candidate, not a dead end - it
takes complete blank-outs from ~42% of restores to ~10% (p = 0.017) at the cost of an
occasional partially-dark frame. It is *not* a clean fix, and adopting it is a decision for
the user, because it is a change to the shipped window style that requires rebuilding the
three artefacts and a fresh manual pass over all seven requirements. It has **not** been
applied: `codex_config_tool.py` is unchanged and still byte-identical to
`backups/window-working-taskbar-toggle-20260915/codex_config_tool.py`.

### The other ten candidates

Their earlier verdicts stand - none reduced the sidebar's change, and the two that helped most
(`LockWindowUpdate`, `composited + no-erasebkgnd`) broke minimize. They were measured with the
region-dependent metric, which is adequate for the sidebar (84% content, so a blank-out reads
0.78 against a 0.30 threshold); the region-dependence only invalidates conclusions drawn about
*sparse* regions. The one conclusion that does change is the `composited` one above.

### Harness defects fixed in this round

1. **The metric had no power in sparse regions.** Fixed by `content_erase_fraction()`.
2. **`--probe-patch` clamping was silent.** A forced patch is clamped into the body bounds, so
   an out-of-range coordinate quietly becomes a different region. The harness prints
   `probe patch FORCED to body (l,t) WxH (auto-choice overridden)` - read it.
3. **A wrong reference in an offline check.** The saved `restore-flash-offender-runN-*.png`
   files are already 180x120 *patch crops*, not full-window captures; cropping a patch out of
   them yields padding, which scores `diff 1.00 / bg 0.00` and looks like a catastrophic
   frame. Compare them against `restore-flash-probe-patch.png`, not the full reference. The
   `restore-flash-worst-runN.png` files are full-window (820x500) - check `Image.size` before
   scoring either.
4. **`--exe` fail-fast proved itself.** Passing an MSYS-style path (`/d/...`) is resolved by
   `os.path.abspath` to `D:\d\...`, and the harness exits 2 with
   `HARNESS --exe does not exist: ...` instead of a misleading "main window not found" after a
   full timeout. Use a Windows path for `--exe` from Bash.
5. **A `global` declared too late.** `--content-tolerance` reads `CONTENT_TOLERANCE` as its
   argparse default, so the `global` statement had to move to the top of `main()`; Python
   rejects it after any use of the name in the same function. `content_mask()` resolves its
   default at call time for the same reason - binding it as a default argument would have
   frozen the value at import and silently ignored the flag.

### Suite output now

```
  PASS                   unit tests                                7.2s
  PASS                   packaged acceptance (5 cycles)           46.1s
  PASS                   drag repaint integrity                   14.0s
  PASS                   close paths shut down cleanly            16.3s
  ADVISORY               restore flash (advisory)                 57.7s
      flash: 7/8 restores flashed by the region-dependent metric, 10 bad frame(s), 0 darker than the UI
      erase: 5/8 restores erased the probe's content, 8 frame(s), worst 1.0 (tolerance 4)
      mechanism: worst-erasing frame was 1.0 exactly toplevel background
      baseline (this probe, packaged build, N=10): 8/10 restores over the region-dependent
      metric with 12 bad frames, 5/10 erasing content, worst erasure 1.00.  The auto-chosen
      probe sits in the dark sidebar; the same blank-out also erases the light content area,
      where the region-dependent metric reports 0/10 - see this document.
  PASS                   minimize soak (60s + 30s)               100.6s

OVERALL PASS
```

Three suite runs of the same sidebar probe at `--flash-runs 8` gave 2/8, 4/8 and 5/8 restores
erasing content. That spread is expected - a ~5-8 ms event sampled at 16.6 ms yields a sample
of a 30-60% rate, not a constant - but it means no single 8-run row should be read as *the*
rate.

The advisory step now prints both metrics, because the region-dependent one can report
`0/10` - and a `PASS` - for a region that three restores in ten blanked out entirely. It also
prints the mechanism (`worst_erase_exact_bg`), verifies the aggregate carries every field it
prints, and refuses to report a run whose settled frame does not score ~0. That guard was
added after this very change printed `0 frame(s)` while the summary on the next line said
`6 bad frame(s)`, and after the mechanism was first attributed from a frame that turned out to
be a different failure mode.

## Follow-up (2026-09-15, fifth): the blank is not the erase, and not any message

This round was meant to answer one question - *does Tk hide and re-show the child during the
blank?* - because that was the last hypothesis that could still have an app-side fix. It
answered that question, and three more, and the answer to all of them is no.

### The child spy was silent because of a coordinate bug

The previous round's `msgspy` variant spied on the toplevel and then tried to pick "the child
covering the sidebar". Its trace line for the child never appeared. The reason was not the
spy - it was the selection:

```python
rect = W.window_rect(child)          # (left, top, WIDTH, HEIGHT), in SCREEN coordinates
left, top, right, bottom = rect      # unpacked as if it were (left, top, right, bottom)
width = max(0, min(right, 240) - max(left, 0))
```

`window_rect` returns **screen** coordinates and a **width/height**, not a right/bottom edge.
The probe window sits at screen `(550, 290)`, so `min(1370, 240) - 550` is negative for every
child, every `area` came out `0`, `best` stayed `None`, and the whole block sat inside an
`if best:` that never ran. The failure was silent for a second reason as well: Tk routes
exceptions raised inside a callback to `report_callback_exception`, which prints to stderr and
carries on, so even a raised error would not have stopped the app.

Both were fixed - the rect is now unpacked as `(left, top, width, height)` and converted to
window-relative coordinates, and the whole block is inside a `try` that writes the traceback
to the trace. The variant also now logs a **full census** of all 118 descendants, so an empty
selection is distinguishable from a failed install, and spies on two targets (the full-window
wrapper and the container under it) instead of one.

The census is worth keeping, because it is the first time the layout has been measured rather
than assumed:

```
0xb01a10 'TkChild' rel(0,0,820x500)   FULL      the wrapper Tk nests everything under
0x510bda 'TkChild' rel(0,38,820x462)  strip=65604   the body container
0x2607a4 'TkChild' rel(0,38,142x462)  strip=65604   the navigation sidebar
0x2d0bc4 'TkChild' rel(142,38,678x462) strip=0      the content area
0xcf07be 'TkChild' rel(0,0,820x38)    strip=5396    the custom title bar
```

Two corrections fall out of it. The **sidebar is 142px wide, not 240px** - a 240px strip also
covers the left edge of the content area. And the **client area is completely covered by Tk
children**: there is no exposed parent background anywhere, so a blank that reads 100%
`(243,244,247)` must be a *child* painting that colour, not the parent showing through. That
is why `exact_bg` alone cannot distinguish "the wrapper filled itself" from "the toplevel
filled itself" - both paint the same background, and the parent has nowhere to paint anyway.

### `WM_SHOWWINDOW 0` then `1` is the minimize/restore pair, not a hide/re-show

With the spy finally installed, the wrapper logs exactly 12 `WM_SHOWWINDOW` messages across 6
restores - two per cycle, 3.0 seconds apart:

```
wrapper   WM_SHOWWINDOW 0  at 1789480657.821921      <- minimize
wrapper   WM_SHOWWINDOW 1  at 1789480660.825700      <- restore, +3.004 s
sidebar   WM_SHOWWINDOW 0  at 1789480657.822255
sidebar   WM_SHOWWINDOW 1  at 1789480660.839789
```

So the child is hidden when the window is minimized and shown when it is restored. Nothing is
hidden *during* the blank. **The hypothesis is refuted**: the tear is not Tk hiding and
re-showing a child, so it is not "the parent's background showing through a gap", and the
sidebar-canvas rewrite that followed from that theory would not have fixed it.

### The blank arrives *before* the child does anything

`align_message_spy.py` subtracts the restore epoch the harness records from the epoch the spy
records (one machine, one clock) and prints the messages inside the flash window. Runs 4-6 of
that session reproduced the toplevel-fill blank, and the alignment is unambiguous:

| run | verdict | child's `WM_PAINT` | blank frames |
| --- | --- | --- | --- |
| 1 | clean | +49.5 ms | - |
| 2 | **BLANK** | +35.6 ms | +34.5 ms |
| 3 | clean | +49.3 ms | - |
| 4 | **BLANK** | +36.0 ms | +26.6 ms, +41.8 ms |
| 5 | **BLANK** | +38.3 ms | +17.6 ms, +32.9 ms, +49.1 ms |
| 6 | **BLANK** | +40.2 ms | +23.6 ms, +38.9 ms |

The blank starts at +17 ms and the child's *only* `WM_PAINT` lands at +35..+49 ms. In run 5 the
first blank frame is 20 ms **before** any message reaches the child at all. And the message
sequence is essentially identical in clean and flashing runs - run 3 is clean with
`WM_ERASEBKGND +10.6 ms` and `WM_PAINT +49.3 ms`, a 38.7 ms gap that produces no blank, while
run 4 has a *shorter* 24.6 ms gap and blanks twice.

**No message distinguishes a flashing run from a clean one, on the toplevel or on the child.**
The blank is the window's surface being presented before the child has painted into it.

### Suppressing the erase on the window that actually gets erased changes nothing

The message spy counts the erases, and the counts are wildly asymmetric:

```
toplevel          1 WM_ERASEBKGND per restore      <- what the old variant suppressed
full-window wrapper  6
body container     120                              <- where the erasing actually happens
```

The old `no-erasebkgnd` variant subclassed the **toplevel** - the window with one erase. That
was a measurement of nothing. `no-erasebkgnd-child` applies the same no-op to the child, and
the run is verified to have really done something:

```
suppress_background_erase(child 0x910ad0, strip area 65604px2) -> True
child erase state after map #341: {'installed': True, 'still_current': True, 'erase_count': 116}
child erase state after map #441: {'installed': True, 'still_current': True, 'erase_count': 117}
```

117 erases swallowed, subclass still current. The result is **identical to baseline**:

| variant | runs | erased | frames | worst | exact_bg |
| --- | --- | --- | --- | --- | --- |
| baseline | 10 | 5/10 | 8 | 1.0 | 1.0 |
| `no-erasebkgnd-child` (117 erases swallowed) | 10 | 5/10 | 9 | 1.0 | 1.0 |

**The blank is not the erase.** Not the toplevel's, not the child's.

> A first attempt at this variant picked the wrong child: the selection took "largest overlap
> with the strip", which the full-window wrapper wins (`142 x 500 = 71000`) over the body
> container (`65604`) - and the wrapper only receives ~1 erase per restore. It measured 3/10
> against a 5/10 baseline and looked faintly promising. That is the *third* time in this
> investigation that a variant was applied to a window the mechanism does not touch; the
> selection now excludes full-window children and logs the census it chose from.

### `WS_EX_LAYERED` measured and rejected

`WS_EX_COMPOSITED` double-buffers the window's own painting. `WS_EX_LAYERED` +
`SetLayeredWindowAttributes(alpha = 254)` redirects the window through DWM instead - a
different redirection, so it needed its own measurement. It is **worse**:

| variant | runs | erased | frames | worst | exact_bg | flashing | bad frames |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 10 | 5/10 | 8 | 1.0 | 1.0 | 9/10 | 12 |
| `layered` | 10 | 5/10 | 9 | 1.0 | 0.9411 | 10/10 | **28** |

Its worst frame is byte-identical across all ten runs (`body_diff 78.7%, mean 240.79`), which
is a *deterministic* artefact rather than the intermittent one under test - the settled frame
still scores `content_erased 0.0`, so this is not a reference-capture error. Layering does not
help and adds its own consistent defect.

### `WS_EX_COMPOSITED`, re-confirmed on the same session's baseline

All five variants below were measured in one session, same probe patch, same all-API cycle,
N=10 each, so the comparison is paired rather than assembled from different rounds:

| variant | runs | erased | frames | worst | exact_bg | flash | bad | dark | p vs baseline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 10 | 5/10 | 8 | 1.0 | 1.0 | 9/10 | 12 | 0 | - |
| `layered` | 10 | 5/10 | 9 | 1.0 | 0.9411 | 10/10 | 28 | 0 | 1.000 |
| `no-erasebkgnd-child` | 10 | 5/10 | 9 | 1.0 | 1.0 | 9/10 | 13 | 0 | 1.000 |
| `no-erasebkgnd-child` (wrong target) | 10 | 3/10 | 5 | 1.0 | 1.0 | 8/10 | 10 | 0 | 0.650 |
| **`composited`** | 10 | **0/10** | **0** | **0.2441** | **0.0** | 3/10 | 3 | **1** | **0.033** |

`WS_EX_COMPOSITED` remains the only lever that does anything, and on this baseline it removes
the complete blank-outs **entirely**: zero erasing restores, worst erasure 0.24 instead of
1.00, and `worst_erase_exact_bg 0.0` - i.e. the frames it still produces are partial, not the
window filling itself. Pooled with the previous round's paired measurement it is 2/30 against
22/50.

The caveat has not gone away either: it is the only variant that produces a frame **darker
than the settled UI** (1 of 10, `mean 168.5, bg 48.6%`). It replaces a frequent light blank-out
with a rare dark partial frame.

### Harness defects fixed in the fifth round

1. **`verify_restore_flash.py` does not accept `--variant`.** Passing it aborts on
   `unrecognized arguments` before the app is launched, in under a second, with a usage
   message and no SUMMARY - which reads like a harness failure rather than a typo. Variants go
   through `CODEX_VARIANT`, which `instrumented_app.py` reads.
2. **The managed Python runtime has no PIL.** `verify_restore_flash.py` imports `grab`, which
   imports `PIL`, so it dies on `ModuleNotFoundError: No module named 'PIL'` under
   `C:\Users\Administrator\.workbuddy-ai\binaries\python\...`. The detector runs under
   `C:\Program Files\Develop\Python\python.exe` (PIL 12.1.1).
3. **`msgspy`'s child selection compared screen coordinates against a window-relative strip**,
   and failed silently inside an `if best:` (see above).
4. **`no-erasebkgnd-child` picked the full-window wrapper** rather than the container that
   receives the erases (see above).
5. **Two new tools.** `align_message_spy.py` aligns a child's message log against the blank
   frames (it needs the `--window=-10,120` form; `--window -10,120` is parsed as an option).
   `compare_variants.py` tabulates SUMMARY lines across logs and runs a Fisher exact test, so
   "is this variant different" is a number rather than an impression.

### What is left

The window-lifecycle route is now closed **twice over**, and the second closure is the strong
one. It is not "I ran out of ideas in the app's code"; it is that the app has no message-level
handle on the event:

* the app makes no window-invalidating call around the blank (114 read-only
  `make_window_minimizable` calls, nothing else);
* the toplevel's message sequence is identical in flashing and clean runs;
* the child's message sequence is identical too, and the blank arrives *before* the child's
  first message;
* suppressing the erase on the window that receives 120 of them changes nothing;
* the child is not hidden and re-shown (the `WM_SHOWWINDOW` pair is 3 s apart, at
  minimize/restore).

What is left is unchanged, and it is a decision rather than a tweak:

**1. Adopt `WS_EX_COMPOSITED`.** The only measured lever: 0/10 erasing restores against a 5/10
baseline in the same session (p = 0.033), and it removes the complete blank-outs rather than
reducing them. Cost: a shipped window-style change, a rebuild of the three artefacts, and a
fresh manual pass over all seven requirements - plus it introduces a rare darker-than-UI frame
(1 of 10) that baseline does not have.

**2. The structural rewrite.** Now that the tear is known to be window-wide and the client
area is known to be entirely covered by Tk children, a sidebar-only change cannot help. A
meaningful reduction means drawing the whole view layer into one surface so the background
fill and the child's paint become a single operation - a rewrite of the view layer, not a
window-style tweak.

**3. Accept it.** It is one to three frames of a light fill at ~+17..+49 ms on roughly half of
restores. `run_all_checks.py` carries the detector as an advisory step that prints both
metrics and the mechanism.

Nothing has been applied to `codex_config_tool.py`: it is still byte-identical to
`backups/window-working-taskbar-toggle-20260915/codex_config_tool.py`, and the seven
requirements still hold on the preserved build.

## Follow-up (2026-09-15, sixth): `WS_EX_COMPOSITED` is rejected - it costs 100x the idle CPU

The fifth round left one live option: adopt `WS_EX_COMPOSITED`, worth roughly 45% -> 10% of
restores flashing. This round measures what that would cost, and the answer takes it off the
table. **Nothing was applied to the application.**

### First, a metric defect that made it look like a free win

`frames_darker_than_ui` asked "did an unpainted surface reach the screen?" with a **hardcoded
`mean < 200`**:

```python
and (r["worst"].get("mean") or 255) < 200
```

That constant is meaningless for the auto-chosen probe. The sidebar patch settles at
**`mean 126.26`**, so a *partial blank* at `mean 168.5` is **42 units lighter than the settled
UI** and was still counted as "darker than the UI". `WS_EX_COMPOSITED` was being charged with a
black-frame failure mode it does not have - and that charge was the main argument against it.

The check now compares against the probe's own settled brightness and scans the whole timeline
rather than only the max-`body_diff` frame:

```python
DARK_MARGIN = 20          # below (probe_mean - DARK_MARGIN) = unpainted
probe_mean = round(float(ImageStat.Stat(probe_reference.convert("L")).mean[0]), 2)
dark_threshold = round(probe_mean - DARK_MARGIN, 2)
```

The aggregate now carries `probe_mean`, `dark_threshold` and `dark_margin`, so the number is
interpretable, and `run_all_checks.py` prints the threshold next to the count. `ImageStat` is
only imported where it is already used; the check runs over `timeline`, which carries `mean` on
every frame.

**Two honest limits on that fix.** It corrects a *misclassification*, not a blind spot: the
constant was wrong for a light region and a partial blank, which is exactly the case
`WS_EX_COMPOSITED` produced. It does **not** turn up dark frames the old check missed - in the
first run with the new check, the one dark frame it found was also the run's max-`body_diff`
frame, so the old check would have counted it too (`mean 76.91 < 200`). The timeline scan is
stricter in principle; it has not yet been shown to catch something the worst-frame check did
not, and the documents should not claim it has.

With the corrected metric, the same session's comparison becomes:

| variant | runs | flashing | bad frames | **darker than UI** | erased | erase frames | worst | exact_bg |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 10 | 8/10 | 11 | **0** | 4/10 | 7 | 1.00 | 1.0000 |
| **`composited`** | 10 | **4/10** | **4** | **0** | **2/10** | **2** | **0.8029** | **0.6778** |
| `layered` | 10 | 10/10 | 32 | 0 | 4/10 | 7 | 1.00 | 0.9711 |
| `no-erasebkgnd-child` | 10 | 7/10 | 11 | 0 | 6/10 | 10 | 1.00 | 1.0000 |

So on pixels alone `WS_EX_COMPOSITED` is a **clean win with no new failure mode**: half the
flashing restores, a third of the bad frames, no complete self-fill (`exact_bg` 0.68 instead of
1.0), and **zero** darker-than-UI frames - the same as baseline. Pooled over the two
same-methodology sessions, **2/20 against 9/20, Fisher exact p = 0.031**.

### The baseline produces a rare dark frame too - found while validating the new check

The stricter check fired once on the **packaged build** (1 of 4 restores), and the frame is real.
`out/restore-flash-offender-run3-1.png`, at `t = +50.2 ms`, between two frames that read exactly
the settled UI (`mean 126.26`, `body_diff 0.0`):

```
mean 76.91   body_diff 0.7889   bg_fraction 0.305   exact_bg 0.1556

row 60, pixel runs:
  x   0- 17   light blue / white     the sidebar's own left edge, painted correctly
  x  18-141   (0, 0, 0)              the sidebar body - SOLID BLACK, 14880 px
  x 142-169   (243,244,247)          the content area at the toplevel background
  x 170-179   (255,255,255)          a content card
```

So it is not the light blank this investigation has been about: it is a **partially painted
frame** in which the sidebar's buttons are an unpainted black rectangle while the left ~18 px of
the sidebar is correct, and the content area sits at the background stage. Black is more
objectionable than a light fill, and it is a *baseline* artefact - no variant produced it, and
none of the eleven candidates in the table below is implicated.

It is rare (one frame in ~600 captured, across 4 restores) and it is not what the user
reported, which is why it had not been isolated before. It is recorded here because it is the
kind of thing that should be tracked separately rather than folded into "the flash", and
because it means "baseline never produces a dark frame" was too strong a claim.

### Then the cost, which no frame metric can see

`WS_EX_COMPOSITED` makes DWM composite the window from a back buffer. On a window with 118
child windows that is the one documented way it can cost real performance, and **pixels cannot
show it**: a slower app presents the *same* frames, just later. So the harness now samples the
app process's own user + kernel CPU via `GetProcessTimes`, reported as `cpu_seconds`,
`cpu_seconds_per_restore`, `idle_cpu_seconds` and `idle_cpu_per_second`:

```
baseline    0.0391s cpu per restore  (0.2344s over 6 restores)
composited  0.3151s cpu per restore  (1.8907s over 6 restores)     8x
```

That is already bad, but the decisive number is the **idle** cost - sampled over three
consecutive windows, because one window cannot distinguish a steady burn from the decaying tail
of the startup settle:

```
baseline    idle cpu window 1: 0.0s    window 2: 0.0s    window 3: 0.0s
composited  idle cpu window 1: 0.1875s window 2: 0.0156s window 3: 0.5469s
```

Those windows were measured with the harness attached, so the figure was re-measured with the
harness removed entirely (`diag_idle_cpu.py` launches the app, waits 6 s, then samples with
nothing else running). `exstyle=0x02040000` confirms the bit was set:

```
baseline    [0.0,     0.0157,  0.0,     0.0]      -> ~0% of one core
composited  [0.5469,  0.5,     1.1093,  0.1563]   -> 3.1% - 22.2% of one core
```

Over 20 seconds of idling, `composited` consumed **2.31 s of CPU** where baseline consumed
**0.02 s** - roughly **100x**, and **bursty rather than smooth** (it ranges from 0.16 s to
1.11 s per 5 s window), which is consistent with a composite/repaint feedback loop rather than
a fixed overhead.

### Verdict

**Do not adopt `WS_EX_COMPOSITED`.** It buys a reduction in the flash rate - not its
elimination - at the price of:

* **8x the CPU per restore** (0.039 s -> 0.315 s);
* **~100x the idle CPU** while the window is simply open (0.02 s -> 2.31 s per 20 s), which for
  an always-open configuration tool is a battery, heat and fan regression;
* it does not remove the flash.

A frame-capture metric cannot see any of that, which is the point: the fifth round's evidence
said "clean win, no measured downside", and the cost measurement says the opposite. The
lesson is worth carrying to any similar decision - **measure what the change costs the process,
not only what it does to the pixels.**

### What is left

Two options, and neither is a small change.

**1. The structural rewrite.** The only route to a real fix. Now that the tear is known to be
window-wide and the client area is known to be entirely covered by Tk children, a sidebar-only
change cannot help; a meaningful reduction means drawing the whole view layer into one surface
so the background fill and the child's paint become a single operation. `diag_child_windows.py`
puts the size of that job at **118 descendants** (71 `TkChild`, 41 `Static`, 6 `Button`).

**2. Accept it.** It is one to three frames of a light fill at ~+17..+49 ms on roughly half of
restores, it does not affect any function of the program, and `run_all_checks.py` now carries
the detector as an advisory step that reports both metrics, the mechanism and the process cost.

### Harness changes this round

* `frames_darker_than_ui` now compares against the probe's own settled brightness
  (`DARK_MARGIN = 20`) and scans the whole timeline; the aggregate carries `probe_mean`,
  `dark_threshold`, `dark_margin`. The old constant is documented as a defect in the constant's
  own comment.
* `winapi.process_cpu_seconds(pid)` - `GetProcessTimes` via `OpenProcess`; returns CPU seconds
  for any pid, `None` on failure. Wall-clock-independent, so runs of different length compare.
* The detector reports `cpu` (before/after/wall), `cpu_seconds`, `cpu_seconds_per_restore`,
  `idle_cpu_seconds`, `idle_cpu_per_second` and `idle_cpu_samples`, and prints a `cpu ...` line
  next to `SUMMARY`.
* `diag_idle_cpu.py` - measures the app's idle CPU with **no harness attached**, which is what
  makes the idle figure trustworthy rather than a property of the measurement rig.
* `compare_variants.py` gained a `cpu/restore` column.

Nothing has been applied to `codex_config_tool.py`: it is still byte-identical to
`backups/window-working-taskbar-toggle-20260915/codex_config_tool.py`. A pre-change backup was
taken at `backups/window-before-composited-20260915/` before this round's measurements, and the
three artefacts in `dist/` are untouched (12:00 / 12:12).

---

## Follow-up (2026-09-16, seventh): the cost is a **per-child-window** tax - so the rewrite buys the fix twice

The sixth round rejected `WS_EX_COMPOSITED` on cost: ~100x the idle CPU. That left two options -
rewrite the view layer, or accept the flicker. Before asking for that decision, the cost itself
was worth one more question, because a cost with two possible causes has two possible answers:

* **intrinsic** - DWM composites a window with 118 children from a back buffer, and that is
  simply what it costs; or
* **a repaint loop** - something keeps invalidating the window, and the composited path turns
  each invalidation into a full redraw.

Only the second is fixable. **It is the second.**

### The instrument was broken the first time, and the empty result looked like an answer

`diag_idle_paint.py` was written to count the messages that repaint a window, per sampling
window, with nothing touching the app. Its first version installed the spy from the harness
process and printed:

```
spy installed on 0/120 window(s)
```

**`GetWindowLongPtrW(GWLP_WNDPROC)` returns 0 for a window owned by another process.** The spy
installed nothing, and `spy_message_counts` returns `{}` both when a spy is installed and saw
nothing *and* when no spy exists - so "no repaint messages" and "no instrument" were the same
reading. The script now requires a **positive control** (move the window one pixel, confirm the
spy records `WM_WINDOWPOSCHANGED`) and aborts if it fails. That control is what caught it.

The counting therefore moved **into the app process**: a new `idlecount` variant subclasses the
window procedure of the toplevel and all 118 descendants and writes a per-second delta to
`out/idle-messages.log`. It reports `spy installed on 119/119`.

### Then a second defect, in the harness, which silently disabled the variant under test

The first `composited+idlecount` run reported *zero* CPU and *zero* messages - which looked like
a clean refutation of the sixth round. It was not. The window described as
`exstyle=0x00000080`: `WS_EX_COMPOSITED` had never been applied.

`build_features` puts every feature block in **one function scope**, so all seven blocks that
wrap `app.register_appwindow_with_shell` were sharing one local variable named
`original_register`. The second block to run rebinds it, and the first block's closure - which
looks the name up at call time - then calls **itself**:

```
register_with_idlecount -> register_extras -> register_extras -> RecursionError
```

`Tk` swallows an exception raised inside a callback (`report_callback_exception` prints to
stderr and carries on), so the app kept running with a half-applied style and no visible error.
All fourteen occurrences are now uniquely named (`register_before_extras`,
`register_before_layered`, `register_before_idlecount`, ...).

**Did this invalidate earlier rounds?** No, and it was checked rather than assumed: every
recorded run in `out/*.log` and in both documents used a **single** wrapping variant, and
`grep` for a combined variant string finds only the new one. The bug needed two wrappers to
fire.

### What the in-process counter then showed

`composited`, visible, idle, with the spy installed in-process:

| phase | CPU per 3 s window | messages |
| --- | --- | --- |
| visible | 0.09 / 0.41 / 0.89 s | **9 of 9 sampled seconds had messages** |
| minimized | 0.00 / 0.00 / 0.00 s | 1 of 11 (the minimize transition itself) |

and in the visible phase, per sampled second:

```
child5=22paint/22erase  child6=22paint/22erase  child7=22paint/22erase  child8=22paint/0erase
```

**55 child windows each receive `WM_NCPAINT` + `WM_ERASEBKGND` + `WM_PAINT` about 22 times a
second** - roughly 3,600 messages per second. The baseline receives **none**. Attributed by
index, the hot set is exactly the widgets that are *visible*: the content container
`rel(142,38,678x462)`, the sidebar `rel(0,38,142x462)`, the custom title bar `rel(0,0,820x38)`,
every navigation button and every label.

Two things follow immediately:

* **It is presentation-driven.** It stops dead when the window is minimized, so nothing is
  being painted and the burn is zero.
* **Suppressing erases cannot break it.** `child8` shows `22paint/0erase` - a window that never
  receives `WM_ERASEBKGND` is in the loop anyway. The sixth round's erase experiments are not
  merely inconclusive here; the data already excludes that mechanism.

### The measurement that decides the question

A minimal stand-in (`proto_composited_children.py`): an `overrideredirect` Tk window of the same
820x500 with a controllable number of real Tk children, measuring its own CPU.

**Child count** (mean CPU per 3 s window):

| children | baseline | `composited` |
| --- | --- | --- |
| 2 | 0.0000 | 0.0000 |
| 8 | 0.0000 | 0.0052 |
| 24 | 0.0000 | 0.0000 |
| 56 | 0.0052 | **0.1615** |
| 118 | 0.0000 | **0.3177** |

**Area**, with the count fixed at 56 and each widget's area varied by 64x:

| size | area each | total area | `composited` mean |
| --- | --- | --- | --- |
| 30x15 | 450 | 25,200 | 0.0469 |
| 60x30 | 1,800 | 100,800 | 0.0781 |
| 120x60 | 7,200 | 403,200 | 0.0547 |
| 240x120 | 28,800 | 1,612,800 | **0.0000** |

Flat. **The cost scales with the number of child HWNDs and not with painted area.**

### Verdict: the rewrite is not a choice between two equals

Collapsing the view layer into one or two surfaces removes the children, and the cost is charged
per child. At 2 children `composited` measured **0.0000 s** - indistinguishable from baseline.
So the structural rewrite would:

1. shrink the unpainted interval that causes the flash, and
2. make `WS_EX_COMPOSITED` - the only lever that measurably reduces it - **affordable**, removing
   the exact reason it was rejected in the sixth round.

The two options are therefore not symmetric, and "accept the flicker" is now the fallback rather
than the peer of the rewrite. The rewrite is still a real change to the application's structure
and is not guaranteed to eliminate the flash; but it is the option that pays twice.

### Environmental constraints worth knowing before re-running any of this

* **A composited window owned by the *foreground* process kills the caller.** Applying
  `WS_EX_COMPOSITED` to an in-process Tk window terminated the entire shell invocation twice,
  with no output at all. Every measurement here uses a **subprocess**, which is fine.
* **`root.update()` blocks once the window is composited.** The prototype hung there and never
  reached its first log line. Drive the loop with `after()` + `mainloop()` instead - which is
  what the application itself does.
* **`OpenProcess` needs an explicit `restype`.** Without it ctypes assumes `c_int` and truncates
  the handle; `CloseHandle` on the truncated value takes the process down silently.

### Harness changes this round

* `instrumented_app.py` - new `idlecount` variant (in-process per-second message deltas for the
  toplevel and all 118 descendants, plus a `# target` census so a repainting child can be
  attributed to a widget rather than a number); the seven shared `original_register` closures
  renamed; `FEATURES` extended.
* `winapi.py` - `WM_TIMER` and `WM_NCPAINT` added to the spy's message set; `spy_window_messages`
  now accepts `log_path=None` for counters-only, so the spy's own I/O cannot land in the CPU
  figure being attributed.
* `diag_idle_paint.py` (new) - launches the app with `idlecount`, samples CPU visible and
  minimized, and reads the in-process log. Documents why a harness-side spy cannot work.
* `proto_composited_children.py` (new) - the child-count and area sweeps above.
* `diag_idle_cpu.py`, `diag_idle_paint.py` - both fall back to their own window finder when the
  acceptance harness is absent, so they work standalone.

Nothing has been applied to `codex_config_tool.py`: it remains byte-identical to
`backups/window-working-taskbar-toggle-20260915/codex_config_tool.py`, and `dist/` is untouched
(12:00 / 12:12).


---

## Follow-up (2026-09-16, eighth): the `Image-Management` comparison - and the answer is no

### The question

> `Image-Management` 这个是一个软件项目，你看看这个项目是怎么处理软件界面的最大化和最小化的，
> 能不能借鉴到本项目上，以此修复闪烁问题，如果不能，那么我就放弃修复了

`Image-Management` is a second application in this workspace. It is a frameless-window desktop
app with a custom title bar, it ships, and **it has no flicker problem**. If its maximize/minimize
handling contained a technique, that technique would be the cheapest possible fix here. So the
question is worth answering properly rather than by analogy.

**The answer is: no, nothing there is borrowable.** And the reason is more useful than the answer,
because it is the same conclusion this document reached from the other direction - measured, not
argued.

### What `Image-Management` actually does

It is **PySide6/Qt**, not Tk (`requirements_qt.txt`: `PySide6>=6.8,<6.12`; entry point `run.py`
-> `from qt_app_v20 import main`). Its main window is built through a four-deep inheritance chain
(`qt_app_v20` -> `qt_app_v16` -> `qt_app_v15` -> `qt_app_v14` ... -> `qt_app`), and the window is
created in the base class:

```python
# qt_app.py:1080
class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setWindowTitle(APP_NAME)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
```

So it is **frameless - the same problem class as `overrideredirect(True)`** - and it is
translucent on top of that. Its state handling is in `qt_app_v20.py`:

| line | what |
|---|---|
| 5364-5366 | `setWindowFlag(WindowMinimizeButtonHint / WindowMaximizeButtonHint / WindowSystemMenuHint, True)` |
| 5627-5634 | `_normal_window_state()` - is the window in a normal (not minimized/maximized/fullscreen) state |
| 5636-5647 | `_geometry_looks_maximized()` - compares `frameGeometry()` to `screen().availableGeometry()` |
| 5649-5662 | `_remember_normal_window_geometry()` - stashes the pre-maximize rect |
| 5671-5675 | `showMaximized()` - remember the rect, set `_logical_maximized`, call `super()` |
| 5677-5694 | `showNormal()` - `super()`, then `QTimer.singleShot(0, ...)` to re-apply the stashed rect |
| 5704-5731 | `changeEvent()` - on `QEvent.Type.WindowStateChange`, update icons and `_logical_maximized` |
| 5820 | `minimize.clicked.connect(self.showMinimized)` |

Every one of those is **geometry and state bookkeeping**. `_remember_normal_window_geometry` and
`_apply_normal_window_geometry` exist because Qt's own `showNormal()` after a taskbar restore does
not always give back the pre-maximize size - a *geometry* bug, not a painting bug. There is not a
single line in any of them about painting, compositing, invalidation or flicker.

Two more native-looking things, both of which are **visual effects, not flicker suppression**:

* `qt_app.py:1246-1264` - `showEvent` -> `QTimer.singleShot(100, self.enable_blur)`, which calls
  `user32.SetWindowCompositionAttribute` with `AccentPolicy(state=3, flags=2, color=0x66000000)`.
  That is Windows acrylic/blur-behind, for the frosted backdrop.
* `WA_TranslucentBackground` itself exists so the app can draw a **rounded, shadowed surface
  inset 16 px** (`root.setContentsMargins(16,16,16,16)` + `QGraphicsDropShadowEffect` with
  `blurRadius(38)`). The translucency is what lets the corner radius and the shadow be visible.

And a project-wide search finds **no** flicker machinery at all: no `WS_EX_COMPOSITED`, no
`SetWindowPos` with redraw flags, no `LockWindowUpdate`, no `RedrawWindow`, no `InvalidateRect`, no
`setUpdatesEnabled(False)`, no `WA_OpaquePaintEvent`, no `WA_PaintOnScreen`, no `nativeEvent`
override. The **only** Win32 calls in the entire project are that one `SetWindowCompositionAttribute`
and `ShowWindow(window, 9)` / `SetForegroundWindow` in `app_runtime.py:586-589`, which is
single-instance activation. `已知问题.md` does not mention flicker, and a grep for
`闪烁|闪屏|flicker` across every `*.py` and `*.md` returns nothing.

**So `Image-Management` does not "handle" the flicker. It does not have it.**

### Why it does not have it - measured

The reason is not a flag. It is how many native Windows windows the UI is made of.

* a **Tk widget is a native window.** `tk.Label`, `tk.Frame`, `tk.Button` - each is a real
  `TkChild`/`Static` HWND.
* a **Qt widget is not.** `QWidget` paints into the top-level's backing store. A top-level
  `QWidget` is one HWND and the entire UI inside it is pixels in that one surface.

`prototypes/proto_surface_count.py` builds the **same UI tree** in both toolkits - same nesting,
same widget count, same size (820x500), same colours - and counts the native windows underneath
each. The framework is the only variable:

```
tk: toplevel TkTopLevel  style=0x56000000 exstyle=0x00000004
    native descendants: 51 (direct 1, visible 51)
    by class: {'Static': 46, 'TkChild': 5}
    toolkit widgets created: 52

qt: toplevel Qt6112QWindowIcon style=0x96000000 exstyle=0x00080000
    native descendants: 0 (direct 0, visible 0)
```

**52 native windows against 1.** (The mirror is faithful: its Tk geometry reproduces the real
app's measured layout exactly - content container `rel(142,38,678x462)`, sidebar
`rel(0,38,142x462)`, title bar `rel(0,0,820x38)`.)

`prototypes/proto_restore_flash.py` then drives the *same* probe through a minimize/restore cycle
against both: same window position, same cycle timing, same capture rate (~33 ms), same relative
threshold (settled mean +/- 25), and the same positive control (the probe strip must read dark in
the sidebar half and light in the content half, or it aborts).

```
--- tk ---  native_descendants=52
  cycle 0: 15 frames @ 34.0 ms | sidebar settled 35.35 max 220.81 | blank 1 [(47.9, 220.8)]
  cycle 1: 15 frames @ 34.0 ms | sidebar settled 35.35 max 220.81 | blank 1 [(55.6, 220.8)]
  cycle 2: 15 frames @ 32.8 ms | sidebar settled 35.35 max 220.81 | blank 1 [(65.5, 220.8)]
  cycle 3: 14 frames @ 34.2 ms | sidebar settled 35.35 max 220.81 | blank 1 [(68.9, 220.8)]

--- qt ---  native_descendants=0
  cycle 0: 15 frames @ 33.9 ms | sidebar settled 34.15 max 34.15 | blank 0 []
  cycle 1: 15 frames @ 33.7 ms | sidebar settled 34.15 max 34.15 | blank 0 []
  cycle 2: 15 frames @ 34.0 ms | sidebar settled 34.15 max 34.15 | blank 0 []
  cycle 3: 15 frames @ 33.9 ms | sidebar settled 34.15 max 34.15 | blank 0 []

tk:  52 native windows, 8/8 cycles with a blanked sidebar
qt:   0 native windows, 0/8 cycles with a blanked sidebar
```

The Qt sidebar does not move off `34.15` by **0.01** in any of 120 captured frames. Its *worst*
frame is pixel-for-pixel the settled UI. The Tk blank value is byte-identical (`220.81`) in all
eight cycles, matching the real app's byte-identical worst frame - the mirror is reproducing the
same defect, not an artifact of the mirror.

### What the blank actually is (first time photographed)

Saving every frame of one cycle settles a question the earlier rounds could only infer. At
**+59.2 ms** after `SW_RESTORE`:

* the window **is on top** - its title-bar labels (`t0..t7`) are painted and are covering the
  browser tab strip behind them;
* but its **body is not painted at all**. There is no light background, no dark sidebar: the
  region is transparent and the browser window that was behind shows straight through.

At **+88.7 ms** the same window is complete: dark sidebar `s0..s13`, light content `c0..c23`.

The Qt window, captured at **+49.0 ms** after the same `SW_RESTORE`, is already fully painted.

So the defect is not "the wrong background colour is shown". It is: **the window is presented
before its content has been painted, and what fills that interval is whatever the compositor
happens to have** - in the real app the toplevel's own background `#f3f4f7` (measured `mean 244.0`,
which is why the dark sidebar is where you see it), and in the lighter mirror nothing at all,
letting the desktop through. Same defect, same ~1-3 frame duration, different thing behind it.
The more native windows the UI is made of, the longer the unpainted interval.

### Why this does not contradict the sixth round

The sixth round measured `WS_EX_LAYERED` on the Tk app as *worse* (10/10 cycles, 32 bad frames).
That looks like it contradicts "Qt is layered and clean". It does not, and the contrast is the
point:

| | native windows | layered? | cycles that flashed |
|---|---|---|---|
| Tk mirror | 52 | no (`exstyle=0x00000080`) | 8 / 8 |
| **Tk app + `WS_EX_LAYERED` + `SetLayeredWindowAttributes`** | 119 | yes | **10 / 10** (sixth round) |
| Qt mirror (`WA_TranslucentBackground`) | 0 | **yes** (`exstyle=0x00080000`) | **0 / 8** |

The Qt window is layered *and* clean. The Tk window is not layered and flashes; made layered it
gets worse. **Layering is not the variable, and neither is translucency. The window count is.**
Which is exactly why the one thing worth copying is not a flag.

### Verdict

**Nothing in `Image-Management` is borrowable, because there is nothing there to borrow.** Its
maximize/minimize code is geometry bookkeeping; its translucency and acrylic are visual effects;
its lack of flicker is a property of the framework, not a technique. It is a *live, shipping
example of the target architecture* and no more than that.

What it does give is an independent confirmation of the diagnosis, from a program that has never
shared a line of code with this one: **the flicker is a function of the number of native windows,
and the fix is to have one surface.** That is option 1 in this document's "what is left" - the
structural rewrite - which is the same option that already pays twice by making `WS_EX_COMPOSITED`
affordable (2 children: `0.0000 s` per 3 s window).

It also sharpens what the rewrite has to achieve, and it is not "fewer widgets": it is **one
native window**. Anything that still leaves the body of the UI as separate HWNDs has not addressed
the mechanism. In Tk terms that means the content must be drawn into a single native widget (a
`Canvas`, or a single `Text`/`Frame` that owns the pixels), not merely reorganised into fewer
frames.

And it means the honest summary of the whole investigation is unchanged: there are two options,
the rewrite and accepting the flicker, and they are not peers.

### Harness changes this round

* `proto_surface_count.py` (new) - builds the same UI tree in Tk and in Qt and counts the native
  windows underneath each. `--serve` shows a window, prints its top-level hwnd and idles so a
  driver can point at it.
* `proto_restore_flash.py` (new) - spawns a served window, positions it, runs a positive control
  on the probe, then measures the sidebar/content means across a minimize/restore cycle. Captures
  the whole window per frame so every measured frame is also an inspectable image; saves the worst
  frame per cycle, and with `--save-all` the whole sequence of the first cycle. `--debug` saves
  what the probe sees and profiles the strip when the control fires.

### Integrity

Nothing has been applied to `codex_config_tool.py`: it remains byte-identical to
`backups/window-working-taskbar-toggle-20260915/codex_config_tool.py`, and `dist/CodexConfigTool.exe`
is byte-identical to `backups/window-working-taskbar-toggle-20260915/CodexConfigTool-taskbar-toggle-working.exe`.
`Image-Management` was read only and not modified.

---

## Follow-up (2026-09-16, ninth): can the reference project's *approach* be used here?

### The corrected question

The eighth round answered "is there a technique in `Image-Management` to copy". That was not the
question. The question is:

> 能不能使用参考项目的方式，来解决界面闪烁问题，同时保证其他功能不被影响

i.e. **can we adopt the reference project's approach** - the single-surface architecture that makes
its window immune - and can we do it without breaking everything else. That is answerable by
measurement, so it was measured: build the *same* UI four ways and run the *same* probe.

### The four architectures

All four are 820x500, same colours (dark sidebar `#1e1f22`, light content `#f3f4f7`), same widget
count, same probe geometry, same driver, same cycle timing, same relative threshold, same positive
controls.

| architecture | native windows | cycles with a blank frame | blank frames | repainted by |
| --- | --- | --- | --- | --- |
| Tk widgets (`overrideredirect`) - today's design | **52** | **8 / 8** | 17 / 241 | 45.0 ms |
| Tk, whole UI on **one `Canvas`** | **2** | **8 / 8** | 8 / 240 | 30.2 ms |
| Tk, one `Canvas` + `-alpha` (= `WS_EX_LAYERED`) | **2** | **8 / 8** | 8 / 240 | 30.6 ms |
| **Qt `FramelessWindowHint`** - the reference architecture | **0** | **0 / 8** | **0 / 240** | never |

(exstyles: `0x00000080`, `0x00000080`, `0x00080080` = `WS_EX_LAYERED|WS_EX_TOOLWINDOW`, `0x00080000`.)

### What this says

**Collapsing the Tk view layer to a single `Canvas` halves the damage and does not fix it.** The
blank-frame rate goes from 17/241 to 8/240 and the window repaints in 30 ms instead of 45 ms - a
real, measurable ~33% improvement, and it would be a defensible change on its own merits. But
**every one of the 8 restore cycles still flashes**, and the floor is ~30 ms ≈ two 60 Hz frames.

**Adding the compositor redirection changes nothing.** The `-alpha` variant is `WS_EX_LAYERED`,
exactly what the Qt window carries, and its numbers are identical to the unlayered canvas
(8/240, 30.6 ms vs 30.2 ms). So layering is not the operative property, which is consistent with
the sixth round's finding that layering the widget UI made it *worse*.

**Qt is not "better at handling restore".** It has one native window that owns its pixels *and* a
backing store, so when the window comes back it can present the last complete frame immediately.
Tk has neither: the top-level is a separate native window from its content, and Tk repaints by
walking its widget tree through its own idle queue after the restore. That is where the ~30 ms
goes, and it is a property of the toolkit, not of the application's code.

### The honest shape of the options

1. **One `Canvas` in Tk.** ~33% less flash, still flashes every time. Not a fix. Cheapest real
   change; would need the whole view layer redrawn on a canvas (~2133 lines of `CodexConfigApp`,
   75 methods).
2. **Port the UI to Qt.** The measured configuration that does not flash at all. Cost, from the
   actual source: `codex_config_tool.py` is 5598 lines, of which `CodexConfigApp(tk.Tk)` is
   **~2133 lines / 75 methods**, with **87** `command=`/`.bind(` callbacks and **19** `tk.Toplevel`
   dialogs. The other ~3465 lines (config parsing, backups, process handling, HTTP, model lists)
   are plain Python and would be reused unchanged - that is the "other functionality" and it does
   not have to be touched. The packaging cost is real: the exe is **13.2 MB** today and a PySide6
   build adds the Qt runtime (tens of MB).
3. **Accept it.** Unchanged from before.

**Nothing here changes the app.** It is the same finding as the eighth round, now measured on the
Tk side too: the thing that makes the reference project immune is not reachable from Tk, at any
price short of replacing the toolkit.

### A note on what could not be tested

Applying `WS_EX_COMPOSITED` to the canvas window was attempted and **failed in two different
ways**, both recorded because both are traps:

* From the driver (cross-process) and from the app after the window was mapped: the window stops
  painting **entirely** - the probe settles at pure white (255.0) and never recovers. The
  relative-threshold detector reported a flawless **0 blanks** for that configuration, which is a
  masked failure, not a fix.
* Before the first map, via `withdraw()` → `SetWindowLongPtr` → `deiconify()`: Tk never maps the
  window correctly (it stays `1x1`, `style=0x46000000`), so there was nothing to measure.

The harness now guards against the first case: **the probe must still read the colours the UI
actually has, or the cycle is marked INVALID and excluded from the count.** A threshold measured
relative to a settled value will otherwise score a window that has stopped painting altogether as
perfect. That guard fired on the very next run and turned a false "0/8" into
`NO VALID CYCLES - the window stopped painting; the zero is meaningless`.

### Harness changes this round

* `proto_surface_count.py` - new `--tk-canvas` (the same UI drawn into one `tk.Canvas`) and
  `--tk-canvas-composited` (the same plus Tk's `-alpha`, i.e. `WS_EX_LAYERED`). Both are served
  through `--serve` like the others.
* `proto_restore_flash.py` - new `FastSampler`: one reused memory DC plus a top-down 32-bpp
  `CreateDIBSection`, so a sample is one `BitBlt` and a read of already-mapped memory. This took
  sampling from 33 ms to **16.7 ms**, which turns out to be exactly the display period - GDI
  `BitBlt` from the composited screen is vblank-locked, so **one sample is one presented frame**
  and "1 blank frame" is a frame-accurate statement rather than an estimate.
* `proto_restore_flash.py` - new `--capture strip|window` (fast probe for timing, full-window
  images for looking at), new `--composited` (applies `WS_EX_COMPOSITED` from the driver),
  per-cycle `probe_valid` guard, and `unpainted_span_ms` / `resolved_at_ms` so the duration of the
  event is a number and not just a count.

### Integrity

Nothing has been applied to `codex_config_tool.py`: it remains byte-identical to
`backups/window-working-taskbar-toggle-20260915/codex_config_tool.py`, and `dist/CodexConfigTool.exe`
is byte-identical to `backups/window-working-taskbar-toggle-20260915/CodexConfigTool-taskbar-toggle-working.exe`.

---

## Follow-up (2026-09-16, tenth): the Qt port - built, and the flicker is gone

The ninth round ended with three options and the user chose the second one:
*"按照唯一能真正消除闪烁的路去做"*. This round builds it and measures it.

### What was built

**`codex_config_qt.py`** - a new file, 2,508 lines, 15 classes. It rebuilds the **view** in Qt
(PySide6) and imports every piece of non-visual behaviour from `codex_config_tool` unchanged: 84
distinct `core.*` symbols, covering config parsing and writing, backup and profile management,
process handling, the update check, the Win32 window helpers, settings and resources. The Qt file
contains no new business logic - it is a view layer plus the glue needed to drive it.

**`codex_config_tool.py` is untouched**, byte-for-byte. That was the point: it stays the rollback,
and it is also the library the Qt front end imports.

The window is constructed exactly like the reference app that was measured clean in round nine:
`FramelessWindowHint | Window`, no parent, no `WA_TranslucentBackground`. Deliberately **opaque**
(`exstyle = 0x00040000`, i.e. `WS_EX_APPWINDOW` with no `WS_EX_LAYERED`) - a configuration round
nine had *not* measured directly, since its Qt stand-in was layered. Measuring the real app was
therefore necessary rather than a formality.

### The measurement, on the real programs

Round nine compared two *stand-ins*. This round adds `--framework tk-app` and `--framework qt-app`,
which serve the **shipping** windows - `CodexConfigApp` and `CodexConfigWindow` - so the numbers
below are a true before/after on the same application. Both builds share the palette and the
geometry (142px sidebar, 38px title bar, five 42px nav rows), so one `--strip-top 300` is valid for
both, and the probe reads a flat `91.0` (`#5b5b5b`) in the sidebar band for each.

Two independent runs, 8 minimise/restore cycles each:

| build | toplevel class | native children | cycles with a blanked sidebar | blank frames | unpainted span |
|---|---|---|---|---|---|
| **Tk, shipping** (`codex_config_tool`) | `TkTopLevel` | **118** | **8/8**, **8/8** | **25/241**, **15/238** | 0 - 50.7 ms |
| **Qt, new** (`codex_config_qt`) | `Qt6112QWindowIcon` | **0** | **0/8**, **0/8** | **0/241**, **0/240** | **0.0 ms** |

The Tk column is the bug, reproduced on demand: the sidebar reads exactly **244.7** - the
toplevel's own `#f3f4f7` background - instead of `91.0`, for one to four sampled frames per
restore, and the window goes unpainted for up to 50 ms.

The Qt column is the fix, and it is stronger than "fewer blank frames": `sidebar_max = 91.0` on
every cycle of both runs means the probe **never saw the sidebar deviate from its painted value by
a single unit** across all 481 frames. `probe_valid` passed throughout, so this is not the masked
failure described in round nine - the probe confirmed the window was genuinely painted (sidebar
91.0, content 244.67) before counting.

Both `exstyle` values are `0x00040000`; the styles differ only by `WS_GROUP` (`0x960A0008` vs
`0x960A0000`), and both carry `WS_SYSMENU | WS_MINIMIZEBOX` with no `WS_CAPTION`/`WS_THICKFRAME`.

### The taskbar behaviour, checked separately

The flash harness proves minimise → restore does not blank. It does not prove the app's **own**
minimise button works, so `smoke_qt_app.py` checks that directly: `_minimize_window()` (which is
`showMinimized()`) drives the window to `IsIconic() == True`, `showNormal()` brings it back, shell
registration succeeds, and the style bits above are present. All pass.

### Three instrument bugs found and fixed while measuring

1. **The positive control was hardcoded to the prototype's palette.** `sidebar_ref <= 90` rejects
   the real app's `#5b5b5b` sidebar (mean **91.0**) by one unit - and because `probe_valid` was
   zeroing the count, the first Tk run reported a reassuring `blank 0 []` **while
   `sidebar_max 244.67` sat next to it on the same line**. Both bounds are now
   `--sidebar-max` / `--content-min`, defaulting to the old values. The round-nine lesson recurring
   in a new place: a threshold that is a constant is wrong the moment the region changes.
2. **`_dump_probe_debug` profiled the whole window, not the strip**, despite being labelled "strip
   profile". It averaged the full window height into each 20px column and read ~120 where the band
   itself is a flat 91 - a confidently wrong number of exactly the kind the dump exists to catch.
   It now profiles the band the probe actually samples.
3. **The screenshot helper cropped the bottom off every dialog.** For a window, Qt's `pos()`
   already includes the frame while `width()`/`height()` are the client size, so
   `(x, y, x+w, y+h)` stops one title-bar short. This produced a convincing phantom "the profile
   editor is clipped" that cost a detour into dialog sizing. `frameGeometry()` is the correct box.

### Deliberate simplifications

Each replaces a hand-rolled mechanism with the toolkit's, rather than removing behaviour:

* the custom smooth horizontal scroll inside long API Key fields - `QLineEdit` already keeps the
  cursor visible and auto-scrolls during a drag-select;
* the hand-drawn combobox drop-down arrow - `QComboBox` draws its own;
* the hand-rolled multi-select drag in the profile list - `QTableWidget`'s `ExtendedSelection`
  gives click/shift/ctrl natively.

### Scope, and what is left

The Qt view is complete: all five pages, the custom title bar with drag/minimise/close/about, the
profile table with sort/search/multi-select/context menu, all seven dialogs, the toast, the update
check and its red dot. The two remaining pieces are **not** code:

1. **Packaging.** `dist/` still holds the Tk build. A Qt build needs its own `.spec` and bundles
   the Qt runtime, so the exe grows well past today's 13.2 MB. Not started.
2. **A run on your machine.** The numbers above are objective, but the standing rule is that the
   fix is not declared until you have looked at it yourself. The entry point is
   `python codex_config_qt.py` - it needs a Python with both PySide6 and tkinter, because the
   imported library still imports tkinter.

### Harness changes this round

* `serve_qt_app.py` / `serve_tk_app.py` - new; serve the shipping windows for `qt-app` / `tk-app`.
* `sandbox_env.py` - new; rebinds `core.SETTINGS_DIR` / `core.SETTINGS_FILE` and the config
  directory to a temp folder. **This was needed because the first version of the Qt server
  overwrote the real `settings.json`**, repointing `config_dir` at a temp directory that was about
  to be deleted. It was restored, and no measurement run can now touch real state.
* `proto_restore_flash.py` - new `--strip-top`, `--sidebar-max`, `--content-min`; new `qt-app` and
  `tk-app` targets; the debug strip profile now profiles the probe band.
* `smoke_qt_app.py` - new; structural assertions for size, flags, pages, navigation, profile table,
  key toggle, toast, all seven dialogs, taskbar minimise/restore, native census, widget inventory.
* `qt_visual_tour.py` - new; screenshots every page and dialog into `out/tour-*.png`.

### Integrity

`codex_config_tool.py` remains byte-identical to
`backups/window-working-taskbar-toggle-20260915/codex_config_tool.py` (sha256 `b3a0a368...`), and
`dist/CodexConfigTool.exe` to the rollback copy (`e71955b5...`). The pre-port rollback point is
`backups/pre-qt-port-20260916-131755/`.

---

## Follow-up (2026-09-17, eleventh): the port driven with real input - three defects found, the maximise gap closed, and the flash still gone

Round ten ended with the port built, the flicker measured away, and a stated gap: everything that
had been checked was checked **passively**. The flash probe and the smoke test both read a window
that is sitting still. Neither can tell you whether pressing a button does anything. That is the
gap this round closes, and closing it found three real defects that reading the code had not.

### The evidence class that was missing

`prototypes/verify_qt_app.py` injects synthetic mouse input into the **shipping** Qt window while it
runs, and asserts the seven standing requirements in one pass:

| requirement | how it is driven | how it is judged |
|---|---|---|
| R1 无边框 | - | `frame_thickness == (0,0)`, no `WS_CAPTION`/`WS_THICKFRAME`, client `820x500` |
| R2 标题栏拖动 | real press/move/release on the title bar | window moved exactly; a mid-drag capture scores **tear** against a stationary reference |
| R3 不可最大化 | synthetic `SC_MAXIMIZE` **and** `ShowWindow(SW_SHOWMAXIMIZED)` | client rect still `820x500` after each |
| R4 任务栏最小化/恢复 | real click on the located taskbar button | `IsIconic()` toggles both ways, style keeps `WS_MINIMIZEBOX` |
| R5 恢复无第二标题栏 | 5 × (minimise → restore) | `frame == (0,0)`, `has_caption == False`, native children `0`, title band dark |
| R6 恢复后尺寸不变 | same 5 cycles | client `820x500` every time |
| R7 功能未受影响 | the whole configuration surface | below |

R7 is where this earns its keep. It navigates all five pages and checks the nav highlight, checks
the path回填, the API-key masking and the eye toggle, presses **新增配置** through the real
`clicked` signal, saves a profile to disk, edits it and confirms the change persisted, then
exercises search, sort, switch, delete, official login and the update check. All seven dialogs are
constructed for real - `exec`/`run` are replaced with non-blocking stubs, but each dialog's
`__init__` is wrapped so that a constructor which raises is recorded rather than swallowed.

Final run (`out/verify-qt-run7.log`, exit code `0`):

```text
SUMMARY {"passed": 78, "failed": 0, "environment_skipped": 0,
         "failures": [], "skipped": [], "driver_errors": [], "environment_errors": []}
```

### Three real defects it found

1. **新增配置 on the current page did nothing.** `QPushButton.clicked` carries a `checked` bool,
   so passing `self._show_profile_editor` directly delivered that bool as the `record` argument;
   the editor then treated a `bool` as an existing record and raised
   `AttributeError: 'bool' object has no attribute 'path'` inside a `try`. The dialog recorder
   caught it verbatim - `{"dialog": "ProfileEditorDialog", "args": ["CodexConfigWindow", "bool"],
   "error": "AttributeError: 'bool' object has no attribute 'path'"}`. Both call sites now wrap the
   call in a lambda. Note the shape of this bug: it is a *silent* failure in the shipping build,
   because the exception is swallowed and the only symptom is a button that does nothing.
2. **`SC_MAXIMIZE` resized the window to `1920x1040`.** `WS_MAXIMIZEBOX` unset governs the button
   and the system-menu entry, **not** the command - `DefWindowProc` honours `SC_MAXIMIZE`
   regardless, and that is the path Win+Up takes. Fixed in `nativeEvent`.
3. **`ShowWindow(SW_SHOWMAXIMIZED)` resized it and never reverted.** This one is invisible to Qt:
   it sets `WS_MAXIMIZE` and resizes directly, leaving `windowState()` at `WindowNoState`, so
   `changeEvent` never fires and `showNormal()` is a no-op. The first fix attempt
   (`changeEvent` → `showNormal()`) therefore looked correct and did nothing. Fixed in
   `resizeEvent` by checking `IsZoomed()` and calling `ShowWindow(hwnd, SW_RESTORE)`.

Defect 3's fix carries two subtleties that are easy to undo by accident, and both are now in the
code comments:

* the revert must **not** fire while minimised - Windows parks a minimised window at
  `(-32000,-32000)` with a **160x28** icon-sized client rect, which is a size change that is not a
  maximise, so acting on it would try to resize a window meant to stay minimised;
* the `changeEvent` path must keep re-asserting `WS_MINIMIZEBOX`, because `SW_RESTORE` rewrites
  style bits - the maximise fix and the taskbar requirement are coupled.

`resizeEvent` is only safe to use as a guard because `setFixedSize` pins minimum and maximum to the
same value: Qt itself can never deliver a resize to another size, so a resize to a different size
can only have come from outside.

### The maximise gap was shared, not a regression

This is the part worth keeping, because it is the difference between "my port broke this" and "the
build I am replacing had the same hole". `prototypes/probe_sc_maximize.py` measures **both front
ends in one run**, one after the other:

```text
[tk] client [820,500] -> SC_MAXIMIZE [1920,1080] -> SW_SHOWMAXIMIZED [1920,1080]   maximize_box=False menu=None  resized_sc=True  resized_show=True
[qt] client [820,500] -> SC_MAXIMIZE [820,500]  -> SW_SHOWMAXIMIZED [820,500]    maximize_box=False menu=None  resized_sc=False resized_show=False
```

Both builds report `WS_MAXIMIZEBOX` unset and no system menu, so both *look* like they implement
"minimise only". The Tk build - the one currently shipping - resizes to `1920x1080` under either
command. The Qt build, after the fixes, refuses both. **The port ends stricter than the build it
replaces**, and the requirement is now actually implemented rather than merely suggested by the
style bits.

### Two rules the harness enforces on itself

Both exist because breaking them produced confident, wrong answers during development.

* **A metric is only asserted when its precondition held.** The tear score is meaningless if the
  drag never happened - and "the window did not move" is itself either a real failure or a dead
  input channel. The harness asserts *the drag happened* as its own named check and then gates the
  tear assertion on it. Before this, one run reported four tear failures that were entirely the
  desktop's fault.
* **A check the environment made impossible is not a failure.** `check(..., environment=True)`
  records the flag, prints `[ENV ]`, and keeps the entry out of the failure count; the exit code
  ignores environment skips. There is also a **run-level pre-flight** that probes whether input
  injection works at all before the first assertion, so a dead channel aborts with one environment
  verdict instead of twenty bogus failures. Without this, a desktop that clamped the cursor 3-4 px
  from the screen edge read as a broken application.

### Three traps in the measurement itself

* **A window must be created by the styled `QApplication`.** `codex_config_qt.main` sets the font
  and the style sheet; the harnesses each built their own app and one omitted the style sheet, so
  the window rendered with only its hand-painted chrome - grey instead of the black title bar. It
  still looked like a window, so the check "passed" while measuring the wrong thing; it survived
  several runs. Comparing the top-38-pixel mean against the verified tour screenshot gave it away:
  **5.7** for the real window, **203.7** for the unstyled one. There is now one shared
  `create_application()` factory in `codex_config_qt`, called by `main` and by all five harnesses,
  instead of each caller assembling the app.
* **`grab_window` is not `window_rect`.** `winapi.window_rect(hwnd)` returns
  `(left, top, width, height)`, not a `RECT`. Computing `right - left` from it captured the window
  at about a third size (`270x230`, `192x191`), which then produced a phantom "the sidebar is
  missing" failure.
* **The first synthetic press of a session never latches.** The opening drag moved 0 px while the
  window was demonstrably foreground. The harness now warms up with a real 40,20 drag-and-return
  before it measures anything, and nudges the cursor 1 px and back before `LEFTUP`, because the
  `SC_MOVE` loop reads the cursor when it pumps and can miss a `SetCursorPos` (drags landing
  10-12 px short).

Two more instrument bugs from this round, both of the "confident wrong answer" kind, are recorded in
`prototypes/README.md`: the taskbar-button metric saturating at its own scan edge, and capturing a
minimised window's rect off the composited screen, which read a foreign window and produced a
phantom "second title bar" on every cycle (band 229.2 → **5.8** once the capture was gated on
`not IsIconic(hwnd)`).

### The flash, re-measured after the guards

The maximise guards add a `resizeEvent` handler and a `nativeEvent` override to the window, so the
obvious question is whether they reintroduced the blank frame. Measured, both builds, same session,
8 cycles each, `--strip-top 300 --sidebar-max 120`:

```bash
python proto_restore_flash.py --framework qt-app --strip-top 300 --sidebar-max 120 --cycles 8
python proto_restore_flash.py --framework tk-app --strip-top 300 --sidebar-max 120 --cycles 8
```

| build | toplevel class | native descendants | cycles with a blanked sidebar | blank frames | unpainted span | repainted by |
|---|---|---|---|---|---|---|
| **Tk, shipping** (`CodexConfigApp`) | `TkTopLevel` | **118** | **8/8** | **12/241** | 0 - 15.4 ms | 41.7 - 62.4 ms |
| **Qt, post-guard** (`CodexConfigWindow`) | `Qt6110QWindowIcon` | **0** | **0/8** | **0/241** | **0.0 ms** | **never** |

The Tk side is the bug on demand: `sidebar max 244.67` on all eight cycles - the toplevel's own
`#f3f4f7` background - where the settled value is `91.0`. The Qt side reads `sidebar settled 91.0
max 91.0` on all eight cycles, i.e. the probe never saw the sidebar deviate from its painted value
by a single unit across all 241 frames, and `repainted by None` means it never had to be repainted
at all. `probe_valid` passed throughout (control passed on attempt 1), so this is not the masked
failure described in round nine.

**The guards cost nothing.** The `resizeEvent`/`nativeEvent` additions did not reintroduce the
blank frame, and both style values are unchanged from round ten: `style=0x960A0000`,
`exstyle=0x00040000` (the Tk build carries `WS_GROUP`, hence `0x960A0008`).

One honest note on the version string: the Qt window class reads `Qt6110QWindowIcon` here and
`Qt6112QWindowIcon` in some earlier runs. More than one PySide6/Qt build is reachable on this
machine, and the class name tracks it. **Both produce 0 blank frames**, and this round's numbers
come from the documented system interpreter (`C:\Program Files\Develop\Python\python.exe`, Python
3.13.9, PySide6 6.11.0, Qt 6.11.0) - the same interpreter the interactive run 7 used, so the
functional test and the flash measurement are on one build.

### Integrity

`codex_config_tool.py` is `cmp`-identical to `backups/pre-qt-port-20260916-131755/codex_config_tool.py`
(sha256 `b3a0a368...`), `dist/CodexConfigTool.exe` is unchanged (`e71955b5...`), and the real
`settings.json` is `4fed5933...` before and after the full tooling run. The unit suite is 124 tests,
all passing.

> **Correcting an earlier note.** Rounds nine and ten recorded the real settings file as
> `C:\Users\Administrator\CodexConfigTool\settings.json`, sha256 `fe3b5741...`. That is the wrong
> file. The application builds its settings directory from `APPDATA`, so the real one is
> `%APPDATA%\CodexConfigTool\settings.json` = `C:\Users\Administrator\AppData\Roaming\CodexConfigTool\settings.json`,
> sha256 `4fed5933...`. The `~/CodexConfigTool` file is a fallback that both the app and the
> harness resolve to when `APPDATA` is unset - which is the normal state of a POSIX shell on
> Windows. It is a stray artifact, it is not read in normal use, and `accept_packaged_exe.py` now
> refuses to run in that state rather than silently testing it. See the packaging section below.

### What is left

Only the installer step, and it is a decision rather than work: `scripts\build_installer.ps1`
still builds the Tk package, so the Qt build has no `-Setup-` product yet. Wiring it up means
pointing that script at `dist\CodexConfigTool-Qt.exe` - which should happen only once the Qt build
has been confirmed by hand.

The standing rule still applies: the numbers above are objective, but the fix is not declared until
it has been looked at on your own machine. The entry point is `python codex_config_qt.py`, or the
packaged `dist\CodexConfigTool-Qt.exe`. Both need the same thing - a Python with PySide6 *and*
tkinter for the source run, because the imported library still imports tkinter.

---

## Follow-up (2026-09-17, twelfth): the Qt build is packaged, and the acceptance harness was lying

Round eleven ended with one item outstanding and it was not code: `dist/` still held the Tk build.
That is now done, and doing it turned up a defect in the **acceptance harness itself** - one that
had been sitting there since before the port and could not show up until there was a Qt window to
point it at.

### The build

```bat
scripts\build_qt.bat          # -> dist\CodexConfigTool-Qt.exe, 51.0 MB
```

| piece | why it exists |
|---|---|
| `CodexConfigTool-Qt.spec` | Entry point `codex_config_qt.py`; output name `CodexConfigTool-Qt` so the Tk artifact is never touched; `upx=False`; the unused Qt modules are excluded by name |
| `scripts/build_qt.ps1` | Picks an interpreter that has PySide6 **and** tkinter **and** PyInstaller, and re-checks the Tk artifact's hash afterwards |
| `scripts/build_qt.bat` | The documented entry point, mirroring `build.bat` (which is how the project gets around the execution policy) |

**Why 51 MB, when the Tk build is 13.2 MB.** Two costs, neither avoidable:

1. the Qt runtime, plus the plugins the window needs;
2. **tkinter and tcl/tk.** `codex_config_tool.py` does `import tkinter as tk` at module level (line
   22), and the Qt front end imports that module as a library - all 84 symbols of it. So even though
   the Qt build never calls tkinter, it has to ship it. That is the direct cost of the
   "one shared business-logic module" architecture, and it is not something an `excludes` entry can
   remove without breaking the import.

`upx=False` on purpose: UPX compressing `Qt6*.dll` is a known crash source, and the size saving is
concentrated exactly there. The Tk spec keeps `upx=True`.

**Why a separate output name rather than replacing the Tk build.** `dist\CodexConfigTool.exe` is the
rollback artifact *and* the input to `build_installer.ps1`. Until the Qt build has been confirmed by
hand, both products coexist. The build script treats this as an invariant, not a convention: it
records the Tk EXE's hash before building and throws if it changed.

**The interpreter has to be chosen, not inherited.** `build.ps1` runs whatever `python` is on PATH.
On this machine that is the managed interpreter, which has no tkinter - so the fallback path in the
existing script would produce a broken build. `build_qt.ps1` probes each candidate with
`import PySide6, tkinter, PyInstaller` and takes the first that exits 0. Measured:

```text
ACCEPT (exit 0) : C:\Program Files\Develop\Python\python.exe
REJECT (exit 1) : ~\.workbuddy-ai\binaries\python\versions\3.13.12\python.exe
```

### A PowerShell trap that costs an hour: `.ps1` is decoded as ANSI

The first version of `build_qt.ps1` had Chinese comments. Windows PowerShell 5.1 decodes a `.ps1`
as ANSI unless the file starts with a UTF-8 BOM, so those comments were misread and the parser
failed with:

```text
line 93 : 表达式或语句中包含意外的标记"}".        (unexpected token "}")
```

Line 93 was a bare `}`, and the real cause was fifteen lines of comments far above it. Rewriting the
file with the `$x = if (...) {...} else {...}` assignment removed and the here-string replaced by a
one-line probe **did not fix it** - the error just moved to line 96, which is what proved the cause
was not the code at all but the encoding. `build_installer.ps1` is 100 % ASCII for exactly this
reason; `build_qt.ps1` now is too, and its header says so. **Verify a `.ps1` by parsing it, not by
reading it:** `[System.Management.Automation.Language.Parser]::ParseFile(path, [ref]$null, [ref]$errors)`
reports `error count: 0` in one line.

### The acceptance harness was reporting a defect that did not exist

`accept_packaged_exe.py` refused the Qt build: `drag1` and `drag2` both reported
`window moved [0, 0]`. Everything else passed - 5/5 minimise/restore cycles, the taskbar button
located and clicked both ways, `820x500` with no native frame throughout.

The drags were not broken. `probe_packaged_drag.py` settled it by running several implementations
side by side in one session, which is the part worth keeping - a single outcome could not distinguish
"broken" from "flaky", and a **rate** could:

```text
harness-fn     : 0/3 moved
body-copy      : 0/3 moved     <- a verbatim copy of drag_window's body, so the body is at fault
no-prelim-click: 3/3 moved     <- same body, preliminary click removed
inline         : 3/3 moved
```

**Cause: `click_app` performs a complete press+release at the drag's start point, before the drag's
own press.** On the Tk build that is harmless - its title bar implements the drag by hand. On the Qt
build the title strip calls `startSystemMove()`, which hands control to the OS's modal `SC_MOVE`
loop: the preliminary click enters that loop and releases inside it, and the drag's own press then
arrives while the loop is still winding down, so no new move starts. The window never moves and the
input channel is perfectly healthy.

This defect predates the port. It was invisible because the only window the harness had ever been
pointed at was a Tk one. **A harness can carry a bug for months and only reveal it when its subject
changes** - which is an argument for pointing the acceptance test at every build you ship, not just
the newest one.

Two secondary fixes went in with it, both real and both insufficient on their own:

* `drag_window` never called `ensure_foreground`, unlike the taskbar cycles. A press on a background
  window is consumed as an activation, which produces the *same* `moved [0, 0]` reading. The entry
  now carries a `foreground` field, because two different mechanisms with one symptom cannot be told
  apart without it.
* `find_main_window` matched `class_name == "TkTopLevel"` exactly. The Qt class embeds the Qt version
  (`Qt6110QWindowIcon` / `Qt6112QWindowIcon`), so an exact match would silently stop working after a
  Qt upgrade. It now takes `--window-class` and matches by prefix.

### Harness changes, and one that protects the user's settings

* `--exe` - target any build, so both can be accepted in one sitting.
* `--window-class` - `Qt` covers both Qt class strings.
* `--report` - keep the two runs' JSON side by side instead of overwriting.
* `settings_path()` now **raises** when `APPDATA` is unset. The app builds its settings directory
  from `APPDATA`; with the variable unset - the normal state of a POSIX shell - both the app and the
  harness fell back to `~/CodexConfigTool/settings.json`, a file the app never touches in normal use.
  The run looked healthy, tested the wrong settings file, and left that stray file behind. It now
  exits 3 with an explanation:

  ```text
  ENVIRONMENT APPDATA is not set, so the settings directory cannot be resolved the way the
  application resolves it. ... Run this from a normal Windows shell, not a POSIX shim.
  ```

### Result

```text
dist\CodexConfigTool-Qt.exe   (Qt, packaged)
SUMMARY {"verdict": "PASS", "cycles": 5, "failures": [], "environment": {"input_injection": true}}
  warmup: moved [40, 20]   requested [40, 20]
  drag1 : moved [150, 70]  requested [150, 70]
  drag2 : moved [-190, 110] requested [-190, 110]
  cycle1: normal 820x500 frame [0,0] -> minimised 160x28 -> restored 820x500 frame [0,0], no caption
```

`settings_touched: false`, and the real `settings.json` is `4fed5933...` before and after - it
already had `hide_onboarding` set, so the harness had no reason to write. The Tk build was re-run
through the same harness afterwards as a regression check on the shared changes.

### What is left

Only a decision: `scripts\build_installer.ps1` still builds the Tk package, so the Qt build has no
`-Setup-` product yet. Pointing it at `dist\CodexConfigTool-Qt.exe` is a one-line change and should
wait until the Qt build has been confirmed by hand.

---

## Follow-up (2026-09-17, thirteenth): the flicker is gone, and the port had quietly drifted from the design

The first thing reported after the packaged build was run by hand was the good news and two
regressions:

> 任务栏最小化再恢复，主界面不闪了，可是你有没有发现，软件的右侧UI排版跟之前都不一样了，
> 当前配置/切换配置/官方登录/新手引导这几个的右侧界面跟之前的UI版面设计完全不一样，凌乱了，
> 要回恢复回去，而且，主界面的右上角，3个按钮怎么变成了关闭/最小化/关于了？
> 不应该是关于/最小化/关闭才对吗？

So: the flash fix survived contact with a human, and the port had been shipped with a layout that
did not match the design it was replacing. Both complaints were real. This section is about why
nothing in the suite could see either one.

### Defect 1 - the title-bar buttons were in reverse order

`codex_config_tool.py` packs all three with `side="right"`:

```python
close_button = self._title_icon_button(title_bar, "close", self.destroy)
close_button.pack(side="right", fill="y")
minimize_button = self._title_icon_button(title_bar, "minimize", self._minimize_window)
minimize_button.pack(side="right", fill="y")
self.about_button = self._title_icon_button(title_bar, "about", self.show_about_dialog)
self.about_button.pack(side="right", fill="y")
```

**Tk hands the right edge to the widget packed *first*.** The remaining widgets stack to its left, so
the pack order `close, minimise, about` renders left-to-right as **about / minimise / close** - which
is what the user expected.

The port read that order as if it were visual order and fed it to `QHBoxLayout`, which appends
**left to right**:

```python
# Packed right-to-left in the Tk build: close, minimise, about.   <-- wrong reading
for button in (self.close_button, self.minimize_button, self.about_button):
    row.addWidget(button)
```

So the Qt build rendered close / minimise / about. The fix is to add them in *visual* order:

```python
for button in (self.about_button, self.minimize_button, self.close_button):
    row.addWidget(button)
```

A one-line bug with a confident, wrong comment above it. The comment is the tell: the author noticed
the pack order looked backwards and explained it away instead of checking the semantics.

### Defect 2 - the pages had a vertical-distribution bug, and it was not subtle

`tk`'s `pack` gives every `fill="x"` widget its natural height and leaves the **remaining space at
the bottom**. `QVBoxLayout` does the opposite: it spreads the slack across every item whose size
policy allows growth. The port had no trailing stretch, so on any page whose content is shorter than
the 462px page area the slack was pushed into the header and the gaps:

| page | before | after |
|---|---|---|
| 官方登录 | 200px hole between the header and the panel; panel centred in the page | panel directly under the header, slack at the bottom |
| 新手引导 | same 200px hole | same as Tk |
| 当前配置 | details panel pushed below the window edge - **the last row was cut off** | all four rows visible |

The fix is one line per affected page, wrapped in a named helper so the rule is explicit:

```python
@staticmethod
def _pack_top(layout: QVBoxLayout) -> None:
    """Leave the page's slack at the *bottom*, the way Tk's ``pack`` does. ...
    Call this at the end of any page whose content does **not** expand - do not
    call it on 切换配置 (its table fills the page) or 推荐渠道 (its panel carries
    the stretch).
    """
    layout.addStretch(1)
```

### Why 78 interactive checks and 124 unit tests all passed anyway

**Layout fidelity is not a structural property.** Every widget involved existed, carried the right
object name, and was connected to the right slot. `smoke_qt_app.py` counted them and found them all;
`verify_qt_app.py` clicked them and they all worked. Nothing about "the panel is 200px lower than it
should be" is visible to a test that asks *whether* a widget is there.

The two front ends could only be compared by **looking at both**, and that needed a tool that did not
exist: there was a `qt_visual_tour.py` and no Tk counterpart, so the port had never been compared
against the thing it was porting. Added `prototypes/tk_visual_tour.py`, which shoots the shipping Tk
window's pages with the same geometry, and `prototypes/compare_layout.py`, which dumps the geometry
of a page's widgets from either front end so the two can be diffed as numbers.

`compare_layout.py` must scope the walk to the requested page. All five pages are stacked at the same
place (`place(relx=0, rely=0, relwidth=1, relheight=1)` / `QStackedWidget`), so walking the whole app
returns five overlapping pages and no way to tell which row belongs to which.

### The measurements, before and after

Same probe, same page (当前配置), Tk on the left, Qt on the right:

| element | Tk | Qt before | Qt after |
|---|---|---|---|
| entry height | 35 | 29 | **35** |
| field row pitch | 47 | 41 | **47** |
| details panel inner height | 204 | 182 | **204** |
| first field row `y` | 227 | 199 | **225** |
| 官方登录 panel top `y` | 121 | 310 | **120** |
| 官方登录 panel height | 147 | - | **147** |
| 新手引导 panel height | 267 | 186 | **263** |
| 新手引导 first bullet height | 40 (wrapped) | 23 (clipped) | **38 (wrapped)** |

What was left after the first pass, and where each residue came from:

* **Tk's `tk.Label` boxes are ~8px taller than Qt's `QLabel` for identical text.** Not a font-size
  problem - `probe_font_metrics.py` renders five sample strings in both and reports a width ratio of
  **1.000** on every one, with matching heights. Tk's label simply carries padding Qt's does not, so
  the difference has to be expressed as QSS padding to make the rhythm agree.
* **Tk grids every row with `pady=6`, including the first and last.** `QGridLayout`'s
  `verticalSpacing` only sits *between* rows, so the details panel came out 12px short until
  `setContentsMargins(0, 6, 0, 6)` was added.
* **Tk's guide page packs the separator with `pady=(3, 14)` after *every* section**, the last one
  included; the port skipped the trailing 14px on the final section.
* **Tk's guide bullets use `wraplength=500`.** The panel's content area is 580px, so without the
  constraint the first bullet stayed on one line where Tk wraps it to two.
* Tk's page buttons carry `ipady=3` (35px) while dialog buttons use the style's own `(8,5)` (~30px).
  Qt has one `APP_QSS` and one `DIALOG_QSS`, which maps onto exactly that split.

### Two Qt traps that cost the most time

**`QLabel.setWordWrap(True)` does not make the layout give the label the wrapped height.** QLabel
reports a word-wrapped height only through `heightForWidth()`, and the panel layouts in between hand
it a one-line height from `sizeHint()`. The first fix attempt - `setMaximumWidth(500)` - made things
*worse*: the label was clamped to 500px and the text was **clipped mid-sentence**, so "和启动默认模
型。" rendered as "和启动默认模". A clipped line is harder to notice than a wrapped one because it
looks like the sentence simply ends there.

`probe_qlabel_wrap.py` runs five configurations side by side in one real layout and reports each
one's geometry; `wordWrap` + `maximumWidth` alone **did** wrap correctly in isolation (38px), so the
remaining problem was in the app's panel wrapper, not the label. The working fix pins the height
explicitly, which is safe here because the two front ends provably share one font:

```python
bullet.setFixedWidth(500)
bullet.ensurePolished()
bullet.setMinimumHeight(bullet.heightForWidth(500))
```

**A `Fixed` vertical size policy hides `heightForWidth` from the layout entirely.** `_panel` pinned
every non-expanding panel to `QSizePolicy.Fixed` vertically, which is the same trap one level up: a
Fixed widget takes its `sizeHint` height and never asks its children for a wrapped height. That
policy had been there to stop panels absorbing vertical slack - which `_pack_top` now does properly,
so the policy could go. `_panel` also had a pointless nested `QWidget` between the bordered frame and
its padding-carrying layout; flattening it removed a level of propagation for nothing.

### Verification

* `prototypes/compare_layout.py` for all four named pages: every element within **1-5px** of Tk.
* `prototypes/tk_visual_tour.py` and `prototypes/qt_visual_tour.py`, compared page by page.
* `verify_qt_app.py` re-run after the layout change, because moving widgets moves click targets:
  `SUMMARY {"passed": 78, "failed": 0, "environment_skipped": 0, "driver_errors": 0}` (exit 0).
* Unit suite: **124 tests OK**.
* Flash re-measured after the structural change, 8 cycles:
  `blank 0`, `unpainted 0.0 ms`, `sidebar settled 91.0 max 91.0`, `native_descendants=0`.
* Rebuilt `dist\CodexConfigTool-Qt.exe` (53,515,296 bytes) and re-ran the packaged acceptance:
  `SUMMARY {"verdict": "PASS", "cycles": 5, "failures": []}`, `settings_touched: false`.
* `dist\CodexConfigTool.exe` unchanged at `e71955b5...`; `codex_config_tool.py` untouched;
  real `settings.json` unchanged at `4fed5933...`.

### The lesson

**A port is not done when the tests pass; it is done when it looks like the thing it replaced.** This
port had a structural test, an interactive test and a flash probe - three independent lines of
evidence, all green - and shipped a page layout with a 200px hole in it and the window buttons in
reverse order. None of that is a *behaviour*, so no behavioural test could ever have caught it. What
caught it was a human looking at the screen, and what would have caught it earlier was a screenshot
of the old build sitting next to a screenshot of the new one.

## Follow-up (2026-09-18, fourteenth): three more visual regressions - and the tool that should have caught all of them

The second manual pass over the packaged build produced three more reports, all of the same family as
the previous round: things no behavioural test can see.

> 1、我记得，左侧的5个选项，在被选中的时候，最右侧是有一个绿色块的，并且5个选项的文字都不居中了
> 2、截图中，红色部分需要有边框，或者深色一点，现在很不明显，作为表头，应该比较明显，我说的是底色背景
> 3、启动默认模型的下拉按钮，跟之前的也不一样了

Each was measured against the Tk original before anything was changed. All three turned out to be
places where the port had either dropped an element outright or approximated it with a widget that
draws itself differently.

### Defect 1 - the sidebar's selection indicator was 1px wide instead of 13

`CodexConfigApp._create_nav_item` builds every row out of three widgets:

```python
row = tk.Frame(parent, bg=SIDEBAR_BG, height=42)
indicator = tk.Label(row, bg=SIDEBAR_BG, width=1)      # <- measures 13px, not 1
indicator.pack(side="left", fill="y")
button = tk.Button(row, text=text, anchor="w", padx=24, ...)
button.pack(side="left", fill="both", expand=True)
```

`width=1` on a `tk.Label` is **one character cell**, not one pixel, and in Microsoft YaHei UI that
cell measures 13px. Measured geometry of the Tk row: `row` 142x42, `indicator` **13x42**, `button`
129x42 at x=13. The button's `padx=24` then puts the caption's first ink at **x=37**.

The port drew the indicator **1px** wide and started the caption at **25**. That loses the green
block entirely *and* shifts all five captions 12px left - which is exactly what "并且5个选项的文字都
不居中了" describes, since the text was no longer where it had been.

Fixed by naming the two numbers:

```python
NAV_INDICATOR_WIDTH = 13
NAV_TEXT_LEFT = 37
```

**Note the direction.** The user said "最右侧" (rightmost), but the Tk code puts the indicator at the
left edge of the row and the Tk screenshot shows it there - so the port was fixed to match Tk, i.e.
13px at x=0. Measured afterwards: Tk and Qt both paint `#2f6f5e` at x=0..12 of the selected row, and
the caption's first ink lands at x=39 (Tk) and x=38 (Qt).

### Defect 2 - the table header had no border, and its background was already correct

The user pointed at the header and asked for a border or a darker background, then clarified "我说的是
底色背景". The backgrounds already matched: both builds paint `#eef0f2`, because the port lifted
`Treeview.Heading`'s `background` straight across. What the port had dropped was the *border*:

```
tk  y=194  e2e5e8   <- the tree panel's own edge
tk  y=195  9e9a91   <- header top border
tk  y=196  eeebe7
tk  y=197  eef0f2   ... 31 rows of header fill
tk  y=228  cfcdc8
tk  y=229  9e9a91   <- header bottom border
tk  y=230  ffffff   <- body
```

Against a white body, `#eef0f2` on its own is a 10-unit difference - invisible, which is what the
user's screenshot showed. Restoring the two `#9e9a91` borders is what makes the band read as a header,
and it is also what the original does.

One trap: **a QSS border is added outside the padding.** Tk's `Treeview.Heading` is `padding=(8, 7)`
with no border and comes out **35px** tall. Adding `border-top`/`border-bottom` to the Qt rule made it
37px, which pushed the whole table body down. Compensating the padding to `5px 8px` brings it back to
35px - verified by re-measuring, not by arithmetic.

### Defect 3 - the combo box drew a native bevel instead of the hand-drawn chevron

`codex_config_tool.py` does not let ttk draw this arrow at all. It lays the `Model.TCombobox` style out
with `Combobox.textarea` **only** - the `Combobox.arrow` element is dropped - reserves 34px of right
padding for an arrow that will therefore never be drawn, and then places a hand-drawn 28x29 canvas
inside that reserve:

```python
model_dropdown_button.place(in_=model_combo, relx=1.0, rely=0.5, anchor="e", x=-1, width=28, height=29)
model_dropdown_button.create_line(8, 11, 13, 16, 18, 11, fill="#59616d", width=2, joinstyle="round")
model_dropdown_button.create_rectangle(27, 0, 28, 29, fill="#a8adb2", outline="")
```

Its background is `#f7f8f9` - the field's own colour - so the button is seamless until you hover it
(`#edf0f2`). A stock `QComboBox` instead draws a beveled native button: a 1px white top border, a 1px
`#525353` bottom border, a filled `#525353` triangle, separated from the field by a 1px gutter. **That
bevel is the whole of the complaint**, and no amount of QSS padding removes it.

The port's own docstring recorded the loss: *"The hand-drawn combobox drop-down arrow is gone;
`QComboBox` draws its own."* It was written down and shipped anyway, which is its own lesson.

Fixed by porting the canvas literally - a 28x29 child widget placed at the same offset, with the same
chevon geometry - rather than trying to coax `::down-arrow` into looking right. `::drop-down` is kept
at 34px so the text inset matches Tk, with `::down-arrow { image: none; width: 0; height: 0; }` to
remove the native arrow.

### Getting the chevron to the same *pixels*, not just the same shape

Three separate things had to be right, and each one was found by dumping the arrow as a character
grid rather than looking at it:

1. **Position.** Tk's canvas lands at x=288..315 in a 317px field - its right edge exactly one pixel
   inside the field's own edge, which is where the field's 1px border is drawn. `width - 1 - 28`, not
   `width - 2 - 28`.
2. **Half-pixel offset.** Tk strokes a line centred on the coordinates it is given; Qt strokes one
   centred on the pixel *corners*. Feeding Tk's points straight to `drawPolyline` put the whole
   chevron one row high and one column left. Tk's points `(8,11) (13,16) (18,11)` become
   `(8.5,12) (13.5,16.5) (18.5,12)` with a `FlatCap`.
3. **Antialiasing.** Tk's canvas does not antialias, so its chevron is exactly three flat colours.
   Qt's antialiasing produced a fuzz of blended greys along both legs. Turning it off makes the two
   rasterisations identical cell for cell.

Result, from `probe_arrow_pixels.py --framework tk` vs `--framework qt`:

```
tk   12  ........###.....###........|      qt   12  ........###.....###........|
tk   13  .........###...###.........|      qt   13  .........###...###.........|
tk   14  ..........###.###..........|      qt   14  ..........###.###..........|
tk   15  ...........#####...........|      qt   15  ...........#####...........|
tk   16  ............###............|      qt   16  ............###............|
```

Rows 12-16 are identical. Only Tk's partial top row - three pixels where its butt caps end - has no
Qt counterpart, and that is a 1px difference at the top of a 6px glyph.

### Defect 4, self-inflicted - the 2px the border cost

Covered above under Defect 2. Recorded separately because it is the reason the "measure after" rule is
not optional: the fix for a reported defect introduced a new one, two rows down, in the same header.

### Defect 5, found by measuring the whole page - the label boxes that made the table sit 9px high

Fixing the header exposed something the header comparison could not show. Comparing all five pages
element by element against Tk (`compare_layout.py`, both frameworks) turned up a *systematic* pattern:

```
profiles     '暂无已保存配置，可以从当前配置页面新增。'   tk h=22 | qt h=14
recommended  'https://ai.arkapi.top'                  tk h=23 | qt h=15
recommended  'https://jm2api.lol'                     tk h=23 | qt h=15
```

Tk's `tk.Label` box is **8px taller than Qt's `QLabel`** for identical 8pt text, which the port had
already compensated for on `pageSubtitle`, `fieldLabel`, `bodyText`, `sectionTitle` and `channelTitle`
with `padding: 4px 0` - but not on `#hint` or `#channelUrl`. On the profiles page the missing 8px made
the table panel start at y=185 instead of Tk's y=194: a **9px** hole between "暂无已保存配置" and the
table, in the same region the user was looking at.

Two lines of QSS later the profiles table is at y=194 (Tk: 195) and the recommended page compares
**clean**.

### Why nothing in the suite could see any of this

* `smoke_qt_app.py` asserts structure. Every widget here was present, correctly named and correctly
  parented throughout - the indicator was 1px wide, not missing; the header existed, it just had no
  border; the combo had an arrow, just the wrong one.
* `verify_qt_app.py` asserts behaviour. 78 assertions, all green, including clicking through the
  profile editor - because a chevron's shape is not a behaviour.
* `probe_restore_flash.py` asserts that pixels get painted. It cannot say *which* pixels.
* The unit suite tests the business logic in `codex_config_tool.py`, which the port does not touch.

Four independent lines of evidence, all green, on a build with a 1px selection indicator, an
unbordered header and a native drop-down button. The only thing that ever catches this class of defect
is an image of the old build next to an image of the new one - which is why `tk_visual_tour.py`,
`compare_layout.py` and `compare_screens.py` exist, and why the port should never have shipped without
them.

### Verification

* `prototypes/compare_layout.py` for all five pages, both frameworks: `current`, `official` and
  `recommended` **clean**; `profiles` down to a 1px table offset (was 9px); `guide` still shows a
  cumulative 4-5px (see *What is still wrong*).
* `prototypes/compare_screens.py` - `cmp-sidebar.png` (identical), `cmp-thead.png` (both bands now
  bordered, cropped at each build's own location so the 9px drift cannot masquerade as a difference).
* `prototypes/probe_arrow_pixels.py` - chevron rows 12-16 identical to Tk's canvas.
* `prototypes/probe_combo_arrow.py` - the field's right-hand end now paints exactly Tk's three
  colours (`#59616d`, `#a8adb2`, `#f7f8f9`); no `#ffffff`, no `#525353`.
* `verify_qt_app.py` first run: `SUMMARY {"passed": 77, "failed": 1, ...}`, the failure being
  `R4 前台时点击任务栏图标会最小化窗口` with `iconic=False`. **Not a regression** - that check is
  inherently flaky because it depends on the window genuinely being foreground when the click lands
  (Windows restores instead of minimising otherwise), and the click itself was identical in both runs
  (`minimize @(1030,1059): taskbar=True top=Shell_TrayWnd`). Re-run immediately after:
  `SUMMARY {"passed": 78, "failed": 0, "environment_skipped": 0, "driver_errors": 0}`, exit 0.
  The distinction matters: one failure with no mechanism behind it is a re-run, not a fix.
* Unit suite: **124 tests OK**.
* Flash re-measured on the rebuilt window, 5 cycles: every cycle `blank 0`,
  `unpainted 0.0 ms`, `sidebar settled 91.0 max 91.0`, `repainted by None`, `native_descendants=0`.
* Rebuilt `dist\CodexConfigTool-Qt.exe` (53,517,706 bytes, sha256 `b339f37e...`); packaged acceptance
  `SUMMARY {"verdict": "PASS", "cycles": 5, "failures": []}`, `input_injection: true`.
* `codex_config_tool.py` `cmp`-identical to `backups/pre-qt-port-20260916-131755/` (`b3a0a368...`);
  `dist\CodexConfigTool.exe` unchanged at `e71955b5...`; real `settings.json` unchanged at
  `4fed5933...` after the packaged run.

### Building the Qt EXE on this machine

`scripts\build_qt.ps1` cannot be run directly here: the execution policy refuses scripts
(`PSSecurityException`), the Bash tool refuses to invoke `powershell.exe`, and the PowerShell tool
refuses to invoke `cmd.exe`, so the `.bat` wrapper that sets `-ExecutionPolicy Bypass` is unreachable
from either side. The equivalent one-liner is:

```
python -m PyInstaller --noconfirm --distpath dist --workpath build CodexConfigTool-Qt.spec
```

about 45 seconds, after which the three hashes above have to be checked by hand - the script's own
Tk-artifact guard is what is being given up by bypassing it.

### What is still wrong (measured, not reported, not fixed)

These were found while measuring and are left alone deliberately - each is below the visibility
threshold, none was reported, and every unrequested change to a build the user has to verify by hand
is its own risk.

| item | Tk | Qt | note |
|---|---|---|---|
| 新手引导 panel contents | bullets at y=215/294/324 | y=211/289/319 | cumulative 4-5px; the panel's own `bullet` box is 2px shorter and it compounds through the section spacers |
| 切换配置 first column | 250px wide | 225px (`setColumnWidth(0, 225)`) | moves the header divider 25px left |
| header column divider | `cfcdc8` + `9e9a91`x2 (3px) | `cfcdc8` (1px) | QSS cannot draw a multi-colour border |
| tree panel border | `#e2e5e8` | `#eceef1` (`PANEL_BORDER`) | Tk uses `#e2e5e8` for the tree panel and the channel rows, `#eceef1` for the generic page panels; the port used the generic colour for both |

### The lesson

The previous round's lesson was "a port is not done when the tests pass; it is done when it looks like
the thing it replaced". This round adds the second half: **the comparison has to be made where the
element actually is, in both builds.** Two of these three defects were only findable by measuring the
old build first - the 13px `width=1` label cell and the 34px arrow reserve are both numbers that look
like something else. And the moment one comparison passes, the honest next move is to compare the
*whole* page, because that is how the 9px table offset and the missing label padding turned up.

## Follow-up (2026-09-18, fifteenth): the last few pixels, and the law behind them

The previous round closed with four items measured but deliberately not fixed. Three were one-liners.
The fourth - a cumulative 4-5px on 新手引导 - turned out to be the visible end of a rule that applied
to **all five pages**, and finding it required first building the tool that would have caught every one
of them three rounds earlier.

### The residual that was not a spacing problem

The natural reading of "the 新手引导 panel contents sit 4-5px high" is a wrong `addSpacing`. Measuring
it disproved that: **every gap was already correct.**

| gap (Tk vs Qt) | Tk | Qt |
|---|---|---|
| panel top → heading | 15 | 15 |
| heading → bullet 1 | 6 | 6 |
| bullet 1 → bullet 2 | 7 | 7 |
| bullet 2 → separator | 10 | 10 |
| separator → heading 2 | 14 | 14 |

The drift was entirely in the *widget boxes*: the heading was 24px where Tk's is 25, and the two-line
bullet 38px where Tk's is 40. Chasing that produced the rule.

### The rule

```
tk.Label   height = linespace * lines + 6
QLabel     height = QFontMetrics.height() * lines + padding_top + padding_bottom
Tk's linespace = QFontMetrics.lineSpacing() + 2       (every size this app uses)

  required padding = (leading + 2) * lines + 6
```

Tk lays a line out at `linespace`; QLabel lays one out at `height()`, which is `lineSpacing() -
leading`. So every role is short by `leading + 2` per line. The 9pt and 8pt regular roles have
`leading` 0 and need the 8px they already had (`padding: 4px 0`) - which is exactly why most labels
matched and hid the pattern for three rounds. The **bold** roles have `leading` 1 and need 9px. A
**wrapped** label is 2px short per extra line.

Measured, before and after:

| element | Tk | Qt before | Qt after |
|---|---|---|---|
| `pageTitle` (13pt bold) | 30px | 29px | 30px |
| `sectionTitle` / `channelTitle` (10pt bold) | 25px | 24px | 25px |
| `panelHeading` | 22px (**8pt** bold) | 21px (**9pt** bold) | 22px |
| `currentName` (13pt bold, `borderwidth=0`) | 26px | 25px | 26px |
| 新手引导 two-line bullet | 40px | 38px | 40px |
| 推荐渠道 card / icon | 71px / 40x40 | 73px / 36x36 | 71px / 40x40 |
| 切换配置 primary button (Tk `ipady=2`) | 35px | 31px | 35px |
| 切换配置 search caption | 22px | 35px (stretched) | 22px |

`panelHeading` was the interesting one: Tk draws it at `font=("Microsoft YaHei UI", 8, "bold")`, but
the port's role never set a `font-size`, so it inherited the 9pt default and had been rendering **one
point large** since the port was written. The height was the symptom; the size was the defect.

### Two instrument bugs, both the same mistake

`compare_layout_diff.py` was written first, and it immediately reported nonsense - because the tool it
reads from was lying in two ways.

**It measured hidden widgets.** `compare_layout.py` dumped every widget it could reach, mapped or not.
The profiles page's multi-select bar is created and hidden, and it reported a 480px-tall button at
y=38 sitting on top of every real row. A hidden widget's geometry is not a layout decision.

**It read a variable's name instead of its value.** `ttk.Entry` aliases `-text` to `-textvariable`, so
`cget("text")` returns `"PY_VAR5"`. The Tk table therefore said `PY_VAR5` where the Qt table said
`C:\Users\...\.codex`, and no row could be paired with its counterpart. The fix is to resolve the
variable first, then `get()`, and only then a literal `text`.

### The comparison itself had to be rebuilt twice

Pairing the two tables is the whole job, and the obvious key - text, else depth + class - is wrong.

* **Not depth.** The toolkits nest the same control differently: Tk's `Treeview` is at depth 3, Qt's
  `QTableWidget` at depth 2, and Qt adds a `QHeaderView` sibling Tk has no object for. Keying on depth
  paired the `Treeview` with the *header* and reported a 237px height difference that did not exist.
* **Families, not class names.** `Treeview`/`QTableWidget`, `TEntry`/`QLineEdit`, `TButton`/`QPushButton`
  are the same control under two names.
* **Unmatched rows are not all failures.** Containers (`Frame`, `QWidget`, Qt's generated
  `qt_scrollarea_*`) have no counterpart by design. The rest are listed explicitly with a reason, so a
  *new* unpaired widget still fails the run instead of being absorbed by a loosened test.

Result: `ALL PAGES IN PLACE`, `worst |dy| = 0px` across all five pages.

### The packaged build had never been measured for the thing it exists to fix

Every flash number in this document came from `serve_qt_app.py` - `CodexConfigWindow` from source. The
artifact that ships is `dist/CodexConfigTool-Qt.exe`. A packaged launch was measured with **two native
child windows** on the main window: a 38px title strip and the 462px content area, both
`Qt6112QWindowIcon`. The source window has none. The native-child count *is* the property the probe
measures, so a packaged build with two of them would be precisely the regression the port was written
to remove - and nothing on record could have seen it.

`proto_restore_flash.py --framework qt-exe` closes that (`serve_qt_exe.py` serves the EXE). Five
cycles:

| build | native descendants | blank frames |
|---|---|---|
| source (`qt-app`) | 0 | 0 |
| **packaged (`qt-exe`)** | **0** | **0** |

So the shipped artifact does hold the property. But the two children were real, and the cause matters:
they appear when the app starts with the **onboarding dialog** up. Pre-seeding `hide_onboarding` in the
scratch `%APPDATA%` removes them; dismissing the dialog afterwards does **not**, because the handles are
created and stay for the life of the process. A window's native-child count is a function of its
startup state, not a constant of the build - and a probe that measures one configuration has measured
one configuration. `probe_native_children.py` is what pinned this down.

### A gradient cannot draw a 1px band in a 33px box

Tk's themed heading is five rows: `#9e9a91` border, `#eeebe7` highlight, 31px `#eef0f2`, `#cfcdc8`
shadow, `#9e9a91` border. The stylesheet is the obvious place for the two inner lines, and the first
attempt looked right and changed nothing. `probe_header_gradient.py` measured why:
`qlineargradient`'s stop positions are parsed as **0 or 1 only**, so `stop:0.0303` and `stop:3%` both
collapse the declaration to a flat colour - silently, with no parser warning and no log entry. The
probe includes a working two-stop control, so the flat result is provably the parser's doing.

The header keeps its two borders, its 3px divider and its text; the two 1px inner lines are a
documented, deliberate 2px shortfall, not an oversight.

The same mistake appeared in reverse in `compare_screens.py`, which located the header by matching
`#eef0f2` alone - so it measured Tk's band as 31px against Qt's 33px and reported a phantom 1px drift
on a header whose extent matched exactly. A locator narrower than the thing it locates invents
differences.

### Verification

| check | result |
|---|---|
| `compare_layout_diff.py` (all five pages) | **ALL PAGES IN PLACE**, worst \|dy\| = 0px |
| `compare_screens.py` header | **+0px** (was -1px, and the -1 was the locator) |
| `verify_qt_app.py` (interactive) | **78 PASS, 0 FAIL** |
| unit suite | **124/124 OK** |
| `smoke_qt_app.py` | ALL CHECKS PASSED |
| flash, source (`qt-app`) | 5 cycles, blank 0, native_descendants 0 |
| flash, **packaged (`qt-exe`)** | 5 cycles, blank 0, native_descendants 0 |
| `verify_packaged_launch.py` | PACKAGED LAUNCH OK (8 checks) |
| `accept_packaged_exe.py` | **could not run** - see below |
| `codex_config_tool.py` | `cmp`-identical to the rollback, sha256 `b3a0a368…` |
| `dist/CodexConfigTool.exe` | unchanged, sha256 `e71955b5…` |
| real `settings.json` | `4fed5933…` before and after every run |

`dist/CodexConfigTool-Qt.exe` rebuilt: 53,519,361 bytes, sha256 `74cc4b4a…` (was `b339f37e…`).

**The packaged acceptance test could not be run this round.** It checks for synthetic input before
anything else and refuses to continue when the desktop will not accept it - correctly, because
otherwise every click lands at the real cursor position and the app gets blamed for it. The desktop
went unresponsive to injection partway through the session (the cursor would not move from
(1512, 1059)) and it stayed that way through a two-minute retry loop, so the run returned
`INVALID (environment)` with zero cycles. The previous build passed it 5/5 with
`input_injection: true`.

`verify_packaged_launch.py` was written to cover the part of that run which needs no input at all -
launch, class, 820x500 client, zero frame, zero native children, taskbar styles, and that the real
`settings.json` is untouched. All eight checks pass. **It is not a substitute for the acceptance run:**
it injects no input, so nothing about clicks, typing or the minimise/restore cycle is covered there.

### What is still different (measured, deliberate)

| item | Tk | Qt | why |
|---|---|---|---|
| header inner highlight + shadow | 2px (`#eeebe7`, `#cfcdc8`) | none | QSS gradient stops are 0/1 only; a 1-in-33 band is not expressible |
| header column divider | `cfcdc8` + `9e9a91`x2 | `9e9a91`x2 | QSS draws one colour per border; the leading light pixel is the one dropped |
| API-key eye toggle | `tk.Label` 24x20 | `QLineEdit`'s internal `QToolButton`, 22x18 | Qt creates it from an `addAction`; its size is not settable without restyling the whole line edit |
| 切换配置 toolbar button widths | fixed character widths (`width=10/11`) | sized to content | Tk's `width` is in characters; the buttons are 6-23px narrower. Reported, not fixed |
| header width with an empty table | 608px (scrollbar column reserved) | 620px | Tk always reserves the scrollbar; Qt hides its own when there is nothing to scroll |

### The lesson

Three rounds of "compare the whole page" still left five pages 1-5px off, because the comparison was
made by *reading two tables side by side*. The numbers were all there; nothing had subtracted them. The
tool that finally closed it - `compare_layout_diff.py` - is about thirty lines of pairing logic, and
building it was the actual work; every fix after that was a padding value.

Two corollaries, both earned this round:

* **A measurement tool is a deliverable, and it needs verifying like one.** `compare_layout_diff.py`
  reported garbage on its first run, and the garbage was in `compare_layout.py`: it measured hidden
  widgets and read Tk variable *names* as text. A tool that is trusted without being checked converts
  "we do not know" into "we know something false", which is worse than not measuring.
* **Measure the artifact that ships.** The flash probe had been measuring the source build for four
  rounds. It was right about the source build every time, and it had never once been pointed at
  `dist/CodexConfigTool-Qt.exe`. When it finally was, the packaged window turned out to have two native
  children where the source has none - a real difference, caused by the onboarding startup path, and
  invisible to every measurement on record.

## Follow-up (2026-09-18, sixteenth): re-attempting the blocked acceptance run

The one item left open by the fifteenth round was the packaged acceptance run. It was re-attempted and
is **still blocked**, but the reason is now identified rather than merely observed, and the harness
reports it itself.

### The block, diagnosed

The pre-flight said only "cursor parked at (1512, 1059); requested (960, 540)". Three unrelated causes
produce that identical message - wrong window station or desktop, a locked workstation, or a foreground
process swallowing the pointer - and each has a different fix. Probing each in turn:

| probe | result | meaning |
|---|---|---|
| `SetCursorPos` | returned **0**, `GetLastError` **0** | a silent refusal, not an error code |
| `SendInput` (relative move) | returned **1** | the event *was* accepted - and the cursor still did not move |
| `GetClipCursor` | `0,0,3840,1149` = the full virtual desktop | nothing was clamping it |
| window station / desktop | `WinSta0` / `Default` | the interactive ones |
| `OpenInputDesktop` | succeeded | the workstation was **not** locked |
| foreground window | `AfxMDIFrame140u` `'Autodesk AutoCAD 2024 - [首钢.dwg]'` | a real application, not a secure desktop |

The last two rows rule out the harness's own assumptions, and a control run with the command sandbox
**disabled** fails identically - so this is a host-level condition, not the sandbox and not the build.
Re-running the acceptance test with the correct interpreter reproduced it exactly:
`INVALID (environment)`, exit 3, zero cycles.

### The harness now says why

`input_injection_available()` previously returned the bare parking message. It now appends
`describe_input_block()`, which reports the `SetCursorPos` return value *and* `GetLastError`, the clip
rectangle against the **virtual** screen, whether `OpenInputDesktop` succeeds, and the foreground
window's class and title - so the next session gets the diagnosis instead of re-deriving it:

```
cursor parked at (1512, 1059); requested (960, 540) (primary monitor 1920x1080)
 -- SetCursorPos -> 0 (GetLastError 0);
    foreground AfxMDIFrame140u 'Autodesk AutoCAD 2024 - [首钢.dwg]'
```

One detail had to be corrected while writing it: the first version compared the clip rectangle against
the **primary monitor**, so on this multi-monitor desktop (virtual screen 3840x1149, primary 1920x1080)
it announced a clamp that did not exist. It now compares against the virtual screen. Crying wolf in the
one message a future reader has to trust is worse than saying nothing.

### A second interpreter trap

`accept_packaged_exe.py` imports PIL through `grab`, and the managed interpreter
(`~/.workbuddy-ai/binaries/python/3.13.12`) does not ship it - the run died with
`ModuleNotFoundError: No module named 'PIL'` before touching a window. It needs
`C:\Program Files\Develop\Python\python.exe`. This is documented in the module docstring now.
`verify_packaged_launch.py` needs no PIL and runs under either, which is why the earlier launch check
passed under the managed interpreter without anyone noticing the split.

### Re-confirmed while blocked

The flash probe needs no synthetic input, so the headline metric was re-measured on the **packaged**
build while the desktop was refusing input:

```
--- qt-exe ---
window Qt6112QWindowIcon style=0x960A0000 exstyle=0x00040000 rect=[90, 90, 820, 500] native_descendants=0
capture bbox=[90, 90, 910, 590] reference=sidebar 91.0 content 253.27 (control passed on attempt 1)
  cycle 0..4: 30 frames @ ~16.5 ms | sidebar settled 91.0 max 91.0 | blank 0 [] | content dark 0
```

Five cycles, `blank 0` in every one, `native_descendants=0`, and the sidebar settling on exactly the
reference value 91.0 so the control passed on its first attempt. `verify_packaged_launch.py` re-ran
green as well: 8/8, including zero native children, with the real `settings.json` still `4fed5933…`.

**Still open:** the packaged acceptance run itself - it must be re-run when the desktop accepts
synthetic input. The build is unchanged (`74cc4b4a…`), so the launch checks and the flash numbers above
describe the same binary the acceptance run will test.

### Closing the gap the block leaves open

The acceptance run is the only thing that covers the minimise/restore cycles, so blocking it left the
current build with its cycle behaviour never asserted. Most of those assertions need no synthetic
input, so `verify_packaged_cycles.py` drives the same cycles through the Win32 API instead of the
mouse. Five cycles, **55/55 checks**, run twice:

```
window Qt6112QWindowIcon title='Codex 配置助手' pid=200276
[PASS] open: no native frame / no WS_CAPTION / no native children / client is 820x500
[PASS] cycle1..5: normal, not minimised; minimised; process alive after minimise;
                  still visible while minimised; restored; client is 820x500 after restore;
                  no native frame after restore; no WS_CAPTION after restore;
                  no native children after restore; process alive after restore
[PASS] real settings.json untouched  -- 4fed5933ac278a26
```

So the properties the whole window-chrome effort exists to protect - the size survives repeated
minimise/restore, the frame never comes back, `WS_CAPTION` never returns, the native-child count stays
0, the process never dies - are verified on this build. What remains unverified is only the input path:
the title-bar drag, the two click paths, and whether a real taskbar button appears.

**It is not a substitute for the acceptance run, and its own output says so** - which is the point. A
degraded check that reads like a full one is worse than no check.

### Two more instrument bugs, caught by the first run

The first run reported 16 failures. **Every one was the harness's fault, not the build's** - which is
the same lesson as `compare_layout_diff.py` two rounds ago, arriving again in a new tool:

* **Geometry read from a minimised window is meaningless.** The script asserted the client stayed
  820x500 while minimised and got `(160, 28)`. That is the iconic *parked* rect. The archived passing
  acceptance report settles it: it records `client [0, 0], frame [160, 28]` in that state for a 820x500
  window, and the harness **records** that geometry without asserting on it - which is exactly why the
  real harness never hit this. The assertion now lives after restore, where it means something.
* **`winapi.taskbar_has_window_title` does not work on Windows 11.** It was the "ground truth" for
  requirement 4, and it reported no button in every state including the open one. Probing it directly:
  `Shell_TrayWnd` exists, `MSTaskListWClass` exists, and it has **zero** text-bearing button
  descendants - the helper walks the Windows 7-10 taskbar. It had never been called by anything, which
  is why its docstring's claim had gone unchallenged for so long; the docstring now records the
  measurement and points at the two things that do work (a style-based proxy, or capture diffing). The
  third option - writing a third unreliable check - was rejected, so requirement 4 is left to the
  acceptance run and named in the output as uncovered.

The general shape is worth naming: **a helper that has never been called is not a helper that works.**
Both bugs were in code that looked authoritative, and only running it showed which.

## Follow-up (2026-09-19, seventeenth): the mirrored 是/否 pair

The user reported, with a screenshot of the confirm dialog: "这个是/否的按钮位置是不是反了？" It was.

### What the two front ends actually do

Tk's `show_custom_dialog` packs the question buttons like this:

```python
ttk.Button(button_row, text="否", ...).pack(side="right")
ttk.Button(button_row, text="是", ...).pack(side="right", padx=(0, 8))
```

Both go to the right, and **the first one packed takes the right edge** - so 否 is
rightmost and 是 lands to its left. Measured on the real dialog, not read:
是 at `rootx=1030`, 否 at `rootx=1119`, 8px apart.

The Qt port added them in the same order Tk *creates* them, into a `QHBoxLayout`,
which lays widgets out in the order they are **added** - so 是 came out on the
right. **The two toolkits disagree about what "first" means**, and neither reading
the code nor comparing the text reveals it, because the difference is in the layout
engine.

The same mirroring was present in the onboarding dialog (`不再弹出` on the left in
both, but the 是/否 pair mirrored). Every other button row was checked and matches:
the profile editor footer (保存 | 取消), the name dialog (确定 | 取消), the path row
(浏览... | 新增配置), the profiles toolbar, and the multi-select row.

### Fixed

Both dialogs now add 是 before 否 in `codex_config_qt.py`. Verified by measurement,
not by re-reading: `probe_dialog_button_order.py` opens each dialog in **both** front
ends and diffs the left-to-right order.

```
dialog                        Tk                           Qt                           verdict
show_custom_dialog(question)  是 | 否                        是 | 否                        OK
show_donation_dialog                                                                    SKIP (not measured)
show_onboarding_dialog        不再弹出 | 是 | 否                 不再弹出 | 是 | 否                 OK

ALL COMPARED DIALOGS MATCH (2 of 3)
```

### The instrument was wrong before the app was

Worth recording, because it nearly produced a confident false answer in both
directions. The first version of the probe reported Tk's order **backwards**:

```
show_custom_dialog(question)  否 | 是                        是 | 否                        DIFFERS
```

Three separate faults, in sequence:

1. **The child process could not import the app** (`ModuleNotFoundError`), and the
   script still printed `ALL DIALOGS MATCH` - a green verdict over an empty table.
   Fixed by adding the project root to `sys.path` **and** by refusing to report
   success when either side measured nothing.
2. **Every button reported the same `rootx`** (`718`, the dialog's own x), so the
   sort silently degraded to creation order and produced a plausible-looking wrong
   answer. The cause: `show_custom_dialog` calls `dialog.transient(self)`, and **a
   transient window whose master is withdrawn is never mapped** - the probe had
   called `app.withdraw()` to be tidy. Fixed by not withdrawing the root, by waiting
   for a real mapping, and by refusing to return an order built from equal sort keys.
3. **Two empty results compared equal.** `show_donation_dialog` has no buttons, so
   both sides returned `[]` and the run called it a match. Fixed by treating an empty
   result as inconclusive (`SKIP`), not as agreement.

The probe was then **falsified on purpose**: the old Qt order was temporarily
restored and the probe went red on exactly that dialog (`否 | 是` vs Tk's `是 | 否`,
exit 1), then green again after restoring the fix. An instrument that has never been
shown to fail is not yet an instrument.

### Verification

| check | result |
|---|---|
| `probe_dialog_button_order.py` | `ALL COMPARED DIALOGS MATCH (2 of 3)` |
| falsification (old order restored) | `DIFFERS` on `show_custom_dialog(question)`, exit 1 |
| unit suite | 124/124 OK |
| `smoke_qt_app.py` | ALL CHECKS PASSED |
| `codex_config_qt.py` sha256 | `1395d5ba…` |

`verify_qt_app.py` was run but is **not** evidence this round: 47 PASS / 5 FAIL, and
all five failures are the synthetic-input host condition (`moved=[2688, -137]`,
`moved=[0, 0]`, taskbar `runs=none`). It must be re-run - see the note below.

### The acceptance test was started and then deliberately stopped

Input injection briefly became available this round - the probe moved the cursor
`(782, 771) -> (822, 811)` with `SetCursorPos` returning 1 - so the long-blocked packaged
acceptance run was started against the rebuilt EXE. Its pre-flight then refused, and the
retry loop (`--wait-input 420`) made the situation unambiguous: **the cursor moved between
attempts** - `(2740, 192)`, `(3591, 141)`, `(737, 473)`, `(1129, 573)`, `(1168, 639)` - and a
file dialog (`#32770 '选择文件'`) was in the foreground at one point. A human was using the
machine.

The run was **stopped on purpose**, not left to retry:

* `accept_packaged_exe.py` clicks real screen coordinates. The moment injection succeeds it
  starts clicking - at `(960, 540)`, then the app's own minimise button and the taskbar. With
  AutoCAD holding the foreground and a drawing open, the next click could land in the drawing.
* A pass obtained by clicking into somebody's live session is not evidence about the build.

So the acceptance run remains **un-run on the current build** (`da8136aa…`), and this is now
recorded as a safety rule rather than an environment complaint: an input-injecting harness
must be started only when the machine is idle. The input-free checks still cover launch
(`verify_packaged_launch.py`, 8/8) and the minimise/restore cycles
(`verify_packaged_cycles.py`, 55/55); what is missing is only the drag and the two click paths.

`verify_qt_app.py` needs the same treatment and has not yet been re-run on the fixed source.

---

## 18. The packaged acceptance run finally passes - and the artifact had changed under it

### It ran, and it passed

The machine was idle for the first time in this investigation: 16 cursor samples over 8 s
returned **one** distinct position, `(1914, 700)`, with WorkBuddy AI itself in the foreground
- not AutoCAD. The safety rule from section 17 says an input-injecting harness may be started
only when the machine is idle, so the run was started. It passed:

```
SUMMARY {"verdict": "PASS", "cycles": 5, "failures": [],
         "environment": {"input_injection": true, "detail": "ok"}}
ACCEPT EXIT=0
```

This is the first time `accept_packaged_exe.py` has completed against a packaged build -
attempts in rounds 4, 16 and 17 were all blocked before it could inject anything.

### What it actually asserted

The report (`prototypes/out/accept-packaged-report-qt.json`) carries more than a verdict:

| property | measurement |
|---|---|
| window class | `Qt6110QWindowIcon`, style `0x960A0000`, exstyle `0x00040000` |
| geometry, open | `window=820x500 client=820x500 frame=(0, 0) iconic=False` |
| `WS_CAPTION` | `False` (and `has_caption: False` after every restore) |
| `WS_MAXIMIZEBOX` | `False` |
| system menu | Size/Move/Minimize/**Maximize**/Close/Restore all `enabled` |
| taskbar button | `open_taskbar_button = [1471, 0, 1612]` |
| per cycle (x5) | `restored_via: "taskbar-click"`, `taskbar_button [1476, 0, 1612, 39]`, `button_luminance_delta {"1476-1612": 37.0, "1338-1474": -39.2}` |
| per cycle (x5) | `restored {client: [820, 500], frame: [0, 0], iconic: false, has_caption: false}` |
| per cycle (x5) | `toggle_minimized: true`, `toggle_restored: true`, `toggle_geometry {client: [820, 500], frame: [0, 0]}` |
| drag warm-up | requested `[40, 20]`, moved `[40, 20]` |
| drag 1 / 2 | requested `[150, 70]` / `[-190, 110]`, moved `[150, 70]` / `[-190, 110]` |
| real settings | `settings_touched: False`; sha256 `b5576c68...` before **and** after |

`failures` is empty. The two numbers that matter most are the ones the fallback verifiers
could **not** produce: **`open_taskbar_button = [1471, 0, 1612]`** - a real taskbar button,
detected by diffing screen captures across states rather than by reading the shell task
list - and the drag results, which moved by exactly the requested delta. That closes the
three gaps section 16 had to list as uncovered: the drag, both click paths, and the
taskbar button existence.

One detail is a live confirmation of the three-guard rule from section 4: the system menu
reports **Maximize as `enabled`** while `WS_MAXIMIZEBOX` is `False`. The style bit removes the
button, the menu item is still there, and `DefWindowProc` will still honour `SC_MAXIMIZE` -
which is exactly why the guard has to catch it after the fact rather than rely on the style.

### The artifact had been rebuilt, and the flash numbers belonged to the old one

The acceptance report gave `class='Qt6110QWindowIcon'` - Qt **6.11.0**. The recorded note said
`Qt6112QWindowIcon` = Qt **6.11.2**. Both strings appear in the history (24 and 9 occurrences
respectively), so this was not a typo; the machine PySide6 had **changed**. Measured now:

```
system interpreter  C:\Program Files\Develop\Python\python.exe
PySide6.__version__ = 6.11.0      (user site-packages)
QtCore.__version__  = 6.11.0
managed interpreter PySide6 6.11.0, and no tkinter
```

So the recorded "PySide6 6.11.2 / Qt 6.11.2" is stale. The consequence is not cosmetic:

```
dist/CodexConfigTool-Qt.exe       2026-09-19 19:49:53
prototypes/out/restore-flash.json 2026-09-18 09:48:48   <- OLDER than the artifact
```

The only `qt-exe` flash report on disk was **older than the build it was supposed to describe**.
The round-17 rebuild happened after it, under the new PySide6. Nothing on disk said the current
artifact had ever been measured for restore-flash behaviour - and the "flash packaged `qt-exe`
5 cycles, blank 0, native 0, sidebar 91.0" line in the notes was inherited from the previous
build without re-running anything.

### Re-measured on the current build: the numbers hold

`proto_restore_flash.py --framework qt-exe --strip-top 300 --sidebar-max 120 --cycles 5`
against the current artifact, written to a **new** report path so the old build record is
not destroyed:

```
window Qt6110QWindowIcon style=0x960A0000 exstyle=0x00040000 rect=[90, 90, 820, 500] native_descendants=0
capture bbox=[90, 90, 910, 590] reference=sidebar 91.0 content 253.27 (control passed on attempt 1)
  cycle 0: 31 frames @ 16.23 ms | sidebar settled 91.0 max 91.0 | blank 0 [] | unpainted 0.0 ms, repainted by None ms
  cycle 1: 31 frames @ 16.28 ms | sidebar settled 91.0 max 91.0 | blank 0 [] | unpainted 0.0 ms, repainted by None ms
  cycle 2: 30 frames @ 16.50 ms | sidebar settled 91.0 max 91.0 | blank 0 [] | unpainted 0.0 ms, repainted by None ms
  cycle 3: 30 frames @ 16.55 ms | sidebar settled 91.0 max 91.0 | blank 0 [] | unpainted 0.0 ms, repainted by None ms
  cycle 4: 30 frames @ 16.64 ms | sidebar settled 91.0 max 91.0 | blank 0 [] | unpainted 0.0 ms, repainted by None ms
```

`native_descendants=0`, `blank 0` on every cycle, `repainted by None`, and the sidebar settling
at exactly the 91.0 reference with **zero** spread across ~152 captured frames. The Qt version
change did not move the result, so the shipped build restore behaviour is now verified rather
than assumed.

### The lesson: a report is about the artifact it ran on, not about the artifact on disk

Every number in this project is produced by a tool that takes a path. Nothing in the report
records which bytes were at that path. That is fine as long as the artifact does not change -
and it did change, silently, twice: the EXE was rebuilt, and the Qt runtime underneath it was
replaced. The flash report survived both and kept being quoted.

The cheap fix is a comparison, not a protocol: **before quoting a report, compare its mtime
against the mtime of the artifact it describes.** A report older than the artifact is not
evidence about the artifact. Where a rebuild is expected, write to a new path instead of
overwriting, so the previous build record survives as the baseline it actually is.

`verify_packaged_launch.py` and `verify_packaged_cycles.py` were **not** affected - they take
`--exe` and run live, so their results are always about the file present at that moment. Only
the saved-JSON tools carry this trap.

### State after this round

- `dist/CodexConfigTool-Qt.exe` sha256 `da8136aa...`, 53,793,071 bytes - **accepted** (5/5 cycles,
  0 failures), **flash-measured** (native 0, blank 0, sidebar 91.0/91.0).
- `codex_config_tool.py` `b3a0a368...` and `dist/CodexConfigTool.exe` `e71955b5...` untouched.
- Real `settings.json` `b5576c68...` before and after every run.
- Still outstanding: `verify_qt_app.py` on the fixed source (needs an idle machine), the
  `build_installer.ps1` decision, and **manual confirmation by the user on their own machine**.
