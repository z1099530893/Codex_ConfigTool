# Window-lifecycle prototypes and verification harnesses

These scripts exist to measure Windows window behaviour instead of guessing at
it. They were used to diagnose and fix the duplicate-title-bar bug and they are
kept so the next window change can be re-verified the same way.

Requires the system Python (it has `tkinter` and `PIL`):

```bat
"C:\Program Files\Develop\Python\python.exe" <script>
```

## Run everything

```bat
"C:\Program Files\Develop\Python\python.exe" run_all_checks.py
"C:\Program Files\Develop\Python\python.exe" run_all_checks.py --quick --skip-soak
```

`run_all_checks.py` runs the unit tests, the packaged acceptance test, the drag
repaint check and the minimize soak **in order**, writes one log per check to
`out/`, and prints a single verdict. Run them one at a time, not in parallel:
they all drive the same desktop and steal the cursor.

It also handles two things that are easy to get wrong by hand. It re-executes
itself under an interpreter that actually has `PIL` (the managed runtime does
not), and it keeps "synthetic input is unavailable right now" as an **environment**
verdict instead of flattening it into a pass or a fail, retrying once.

```text
  PASS                   unit tests                                7.2s
  PASS                   packaged acceptance (5 cycles)           46.1s
  PASS                   drag repaint integrity                   14.0s
  PASS                   close paths shut down cleanly            16.3s
  ADVISORY               restore flash (advisory)                 57.7s
      flash: 7/8 restores flashed by the region-dependent metric, 10 bad frame(s), 0 darker than the UI
      erase: 5/8 restores erased the probe's content, 8 frame(s), worst 1.0 (tolerance 4)
      mechanism: worst-erasing frame was 1.0 exactly toplevel background
      baseline (this probe, packaged build, N=10): 8/10 restores over the region-dependent
      metric with 12 bad frames, 5/10 erasing content, worst erasure 1.00.
  PASS                   minimize soak (60s + 30s)               100.6s

OVERALL PASS
```

> **The erasure rate moves between runs.** Three suite runs of the same sidebar probe at
> `--flash-runs 8` gave 2/8, 4/8 and 5/8 restores erasing content, and the packaged baseline
> at N=10 gave 5/10. That is a ~5-8 ms event sampled at 16.6 ms, so the per-run number is a
> sample of a 30-60% rate, not a constant. Compare like with like, and prefer a pooled or
> paired figure over a single row.

**The flash step is advisory** (`--skip-flash` to omit it, `--flash-runs N` to
change the sample). The restore flash is a known, accepted characteristic of this
window - eleven candidate fixes measured, none adopted - so gating on "did it
flash" would fail every run forever. The step reports the rate for comparison
against the recorded baseline and never changes the overall verdict. What it does
surface is the regression signal: a frame **darker than the settled UI**, i.e. an
unpainted black surface, which the baseline never produces and which
`WS_EX_COMPOSITED` and `LockWindowUpdate` both introduced. That prints
`[REGRESSION]`.

**It prints both metrics deliberately.** The region-dependent one can report `0/10`
- and a `PASS` - for a region that three restores in ten blanked out entirely; the
content-erasure numbers are the region-independent ones. The step also verifies the
aggregate carries every field it prints, because `.get(key, 0)` turns a renamed field
into a confident zero, which is how a real regression reads as a pass. It runs an
all-API cycle (`--restore-via api --minimize-via api`), so unlike the other checks it
needs no synthetic input.

Exit codes: `0` all passed, `1` a check failed, `3` the environment could not
support the checks.

Everything must run on a real interactive desktop session; a headless session
cannot create windows or capture screenshots.

## Files

| File | Purpose |
| --- | --- |
| `winapi.py` | Win32 helpers: HWND resolution, style bits, taskbar eligibility, minimize/restore, taskbar-button registration (`ITaskbarList::AddTab`), focus/monitor helpers, `describe()` for one-line diagnostics |
| `run_all_checks.py` | Runs the four checks below in order with the right interpreter and prints one verdict. Start here |
| `grab.py` | Screen/taskbar capture via ctypes + GDI `BitBlt` (no external binaries). `taskbar_rect()` gives the taskbar origin, which you must add to strip-image coordinates before clicking |
| `proto.py` | Standalone candidate explorer (`--mode a/a2/b/b2/e/e2/e3/e4/f/g/h/i`). Each mode is a different window architecture; the script drives 5 minimize/restore cycles and records geometry + taskbar evidence |
| `verify_app_window.py` | Drives the **real** `CodexConfigApp` (dialogs stubbed out) through 5 cycles using its own minimize path |
| `verify_app_drag.py` | Simulates a real mouse drag on the custom title bar and checks the window moves exactly, keeps its size and gains no native frame |
| `verify_app_drag_integrity.py` | Measures **repaint integrity during a drag**: captures the window off the screen mid-drag and compares its body against a stationary reference, plus a ghost check on the vacated area |
| `accept_packaged_exe.py` | Acceptance test for a **packaged** EXE: clicks the real minimize button and the real taskbar button with synthetic input. Refuses to run when the environment cannot support synthetic input. `--exe` targets another build (e.g. `--exe dist/CodexConfigTool-Qt.exe`), `--window-class Qt` matches the Qt top level (a prefix match, because the class embeds the Qt version: `Qt6110QWindowIcon` / `Qt6112QWindowIcon`), and `--report` keeps the two runs' JSON side by side instead of overwriting. Note it briefly writes the real `settings.json` to suppress onboarding and restores the original bytes verbatim afterwards |
| `verify_minimize_soak.py` | Holds the window minimized for 60 s and restored for 30 s, polling throughout for process death, HWND re-creation, wrong iconic state, size drift and frame reappearance. Targets the historical "exit after a delay" regression that a 1.5 s liveness check cannot see |
| `diag_crop.py` | Zoom into an x-range of several taskbar strips and stack them with a pixel ruler. `python diag_crop.py X0 X1 ZOOM name.png ...` |
| `diag_source_click.py` | Instruments the **source** app (real `CodexConfigApp`) and performs a real click on the actual minimize canvas, logging every lifecycle call. Use it to separate "the click never reached the button" from "the handler ran but the window did not stay minimized" |
| `diag_taskbar_restore.py` | Minimizes via Win32 and clicks the located taskbar button, then falls back to `WM_SYSCOMMAND`/`SC_RESTORE` and `ShowWindow(SW_RESTORE)` so the failing layer is identifiable |
| `diag_input_state.py` | Reports cursor position, mouse capture and `GetGUIThreadInfo` for the foreground thread. Run this first whenever clicks appear to do nothing |
| `diag_syscommand.py` | Reports the window's style bits and system menu, then tests `WM_SYSCOMMAND`/`SC_MINIMIZE`, `SC_RESTORE` and `PostMessage` against a direct `ShowWindow(SW_MINIMIZE)`. **Run this first when the taskbar button does not toggle** - it separates "the app ignores the request" from "the Shell never makes it" |
| `diag_taskbar_toggle.py` | Clicks the real taskbar button while the window is *normal and foreground* and checks that it minimizes, then clicks again to restore. Needs synthetic input |
| `diag_shell_minimizeall.py` | Proves the Shell's view without synthetic input, by running `Shell.MinimizeAll()` (the same `WS_MINIMIZEBOX` rule the taskbar uses). Disruptive but reversible; `--exe` runs it as a control against an old build |
| `proto_minimizebox.py` | Prototype: applies `WS_SYSMENU\|WS_MINIMIZEBOX` to a running packaged exe and measures that the frame stays `(0,0)`, the client stays 820x500, the system menu appears, the style survives a minimize/restore cycle, and Maximize still recovers the fixed size |
| `diag_close_paths.py` | Checks that the close paths `WS_SYSMENU` newly exposes (`WM_CLOSE` from the system menu / Alt+F4, and `SC_CLOSE` from the taskbar jump list) actually shut the whole process tree down rather than just hiding the window and holding the single-instance mutex |
| `verify_restore_flash.py` | Measures the restore flash. Captures the window as fast as possible through the restore and scores every frame against the settled UI. `--probe patch` samples one small auto-chosen region instead of the whole window and is the mode that actually works - see the note below. `--minimize-via click\|api` and `--restore-via taskbar\|api`: with both on `api` the whole check needs no synthetic input. Records `restore_epoch` (the absolute epoch of the restore call) in each run so the app's own trace can be aligned with the frame timeline, and writes an `aggregate` block so a caller does not have to re-derive the rate. Also samples the app's **CPU cost** (`cpu_seconds`, `cpu_seconds_per_restore`, `idle_cpu_seconds`, `idle_cpu_per_second`) via `GetProcessTimes`, because a change that presents the same frames by working harder is invisible to every frame metric. `--exe` is resolved to an absolute path and checked before launching, because the child runs with `cwd=ROOT` |
| `explain_flash_report.py` | Reads `out/restore-flash-report.json` and prints the frames around every offender with their rect, DWM bounds and the class of the window on top, so a repaint problem and a compositor artefact can be told apart |
| `instrumented_app.py` | Runs the app **from source** with `--variant a+b+c` (or `CODEX_VARIANT`). Each feature patches the app in memory (remove the Map handler, guard on `%W` in Tcl, strip style bits, add `WS_EX_COMPOSITED`, add `WS_EX_LAYERED`, disable DWM transitions, clear the erase brush, clear `WS_POPUP`, force a synchronous repaint, swallow `WM_ERASEBKGND` on the toplevel *or* on the child, hold `LockWindowUpdate`, stamp the clock, spy on window messages), so candidate fixes can be measured without editing `codex_config_tool.py`. Set `CODEX_TRACE=1` to log every style call |
| `align_message_spy.py` | Lines the child's message log up against the blank frames, by subtracting the restore epoch the harness records from the epoch the spy records (one machine, one clock). `--window=-10,120`; the `--window -10,120` form is parsed as an option |
| `compare_variants.py` | Tabulates the `SUMMARY` line of any number of detector logs and runs a two-sided Fisher exact test against a named baseline, so "is this variant different" is a number rather than an impression |
| `diag_idle_cpu.py` | Measures the app's idle CPU **with no harness attached** - it launches the app, waits, then samples the process's own user + kernel CPU over several consecutive windows. This is what rejects `WS_EX_COMPOSITED`: pixels cannot show that a slower app presents the same frames just later |
| `diag_idle_paint.py` | Asks *why* that cost exists: samples CPU with the window visible and again while minimized, and reads `out/idle-messages.log` from the in-process `idlecount` variant. A minimized window is not painted, so a presentation-driven burn collapses while iconic. Requires the positive control it runs, because an empty message log and a spy that never attached look identical |
| `proto_composited_children.py` | The smallest stand-in for the view layer - an `overrideredirect` window of the same size with N real Tk children. `--sweep` varies the count, `--area-sweep` varies each widget's area at a fixed count, which separates a **per-child** tax from a **per-pixel** one. Answer: per child. Runs the window in a child process, because a composited window owned by the foreground process kills the caller |
| `diag_child_windows.py` | Counts the window's child HWNDs and attributes them to rects, so "would a `Canvas` sidebar fix the flash?" is a measurement instead of a guess. Also shows that Tk nests every widget under one `TkChild`, so `GetWindow(GW_CHILD)` on the toplevel returns exactly one window |
| `proto_surface_count.py` | Builds the **same UI tree** four ways and counts the native Windows windows underneath each: `--tk` (52), `--tk-canvas` (2), `--tk-canvas-composited` (2, plus `WS_EX_LAYERED` via Tk's `-alpha`), `--qt` (0). `--both` runs all four; `--serve` shows a window, prints its top-level hwnd and idles so a driver can point at it |
| `proto_restore_flash.py` | Drives a served window through minimize/restore cycles and measures the same probe across architectures. `FastSampler` (reused memory DC + `CreateDIBSection`) samples in **16.7 ms = one display frame**, because GDI `BitBlt` is vblank-locked - so "1 blank frame" is frame-accurate. `--capture strip|window` (fast for timing, full-window images for looking at), `--composited`, `--save-all`, `--debug`, and a per-cycle `probe_valid` guard that rejects a window which has stopped painting. `--strip-top` / `--sidebar-max` / `--content-min` because the prototype's palette is not the app's. Targets: `tk`, `tk-canvas`, `tk-canvas-composited`, `qt` (stand-ins) and **`tk-app` / `qt-app`** (the shipping windows) |
| `serve_tk_app.py` | Serves the **shipping** `CodexConfigApp` for `--framework tk-app`. Same palette and geometry as the Qt build, so one `--strip-top` is valid for both and the two sets of numbers are a true before/after on the same program |
| `serve_qt_app.py` | Serves the **shipping** `CodexConfigWindow` for `--framework qt-app` - same construction flags, widget tree and style sheet as `codex_config_qt` |
| `sandbox_env.py` | Rebinds `SETTINGS_DIR` / `SETTINGS_FILE` and the config directory to a temp folder. Both servers import it. **Without it a measurement run rewrites the real `settings.json`** to point at a temp directory that is about to be deleted - which is exactly what happened on the first run |
| `smoke_qt_app.py` | Structural test for the Qt window: size and flags, all five pages and nav items, the profile table, the key-visibility toggle, the toast, all seven dialogs, the app's own minimise/restore, the style bits, the **native-window census** and a widget inventory. Redirects the config dir and restores the real settings file |
| `qt_visual_tour.py` | Screenshots every page and dialog of the real Qt window into `out/tour-*.png`. The flash numbers say it does not blank; this says it still looks like the application - a window that paints nothing also never flickers |
| `tk_visual_tour.py` | The same tour for the **shipping Tk window**, into `out/tk-tour-*.png`. Its absence is why the port shipped with a 200px hole in its page layout: there was a tour of the new build and none of the old one, so nobody ever put the two side by side. Pumps each page for 2.5s so the first-use toast has faded - shooting through it makes a correct layout look broken |
| `compare_layout.py` | Dumps the geometry (x/y/w/h) of a page's widgets from **either** front end into `out/layout-<framework>-<page>.json`, sorted by `y`. Layout fidelity is not a structural property: a widget can exist, be named right and be wired right while sitting in the wrong place. This is what turned "the right-hand pages look wrong" into "the entry is 29px where Tk's is 35px, and the row pitch is 41 where Tk's is 47". Scopes the walk to one page, because all five are stacked at the same coordinates |
| `verify_qt_app.py` | **The interactive functional test.** Drives the shipping Qt window with synthetic input while it runs and checks the seven standing requirements at once: real title-bar drags (with a mid-drag tear capture), both maximise paths (`SC_MAXIMIZE` and `SW_SHOWMAXIMIZED`), the taskbar button located by behaviour and then really clicked both ways, five minimise/restore cycles, and the whole configuration surface (nav + highlight, path回填, key masking and eye toggle, 新增配置 via the real `clicked` signal, save/edit/search/sort/switch/delete, official login, update check, all seven dialogs, final size). Two design rules it exists to enforce: a metric is only asserted when its **precondition** held (a tear score means nothing if the drag never happened), and a check the desktop made impossible is reported as `[ENV ]` and excluded from the failure count rather than silently passing or failing |
| `probe_sc_maximize.py` | The decisive comparison for the maximise requirement, run on **both** front ends back to back: sends `WM_SYSCOMMAND`/`SC_MAXIMIZE` and then `ShowWindow(SW_SHOWMAXIMIZED)` to the shipping Tk and Qt windows and prints the client rect after each. This is what showed the gap was **shared with the build being replaced**, not a port regression - and that the Qt build now ends stricter than the Tk one |
| `probe_minimize_cycle.py` | Step-by-step minimise/restore measurement that resolved a phantom "second title bar" failure. Logs `IsIconic`, the window rect, the title-band luminance and the Qt `windowState()` after each individual step, which is how it showed that `SW_SHOWMAXIMIZED` leaves `windowState()` at `WindowNoState` (so `changeEvent` never fires and `showNormal()` is a no-op), and that a minimised window reports a 160x28 icon-sized client rect at `(-32000,-32000)` |
| `probe_packaged_drag.py` | Bisects an injected drag on a **packaged** window. Runs several drag implementations side by side in one session - the acceptance harness's own function, a verbatim copy of its body, and an inline technique - and reports the move rate of each. This is what turned "0/4 vs 4/4" into a named cause: the preliminary click inside `click_app`, which on a `startSystemMove` window enters the OS move loop and leaves the following press unable to start one. Also demonstrates that a failure rate, not a single outcome, is what distinguishes a real defect from flakiness |
| `probe_font_metrics.py` | Renders the same five strings under Tk's and Qt's fonts and reports the natural width of each. Settles "is the port's text the wrong size?" with a number instead of an eyeball: every sample comes back at a **ratio of 1.000** with matching heights, so the two front ends share one font and any layout difference is padding, not type |
| `probe_qlabel_wrap.py` | Runs five `QLabel` word-wrap configurations side by side in one real `QVBoxLayout` and reports the geometry each ends up with (~38px means wrapped, ~23px means the second line is being **clipped**). `wordWrap` + `maximumWidth` alone wraps correctly in isolation, which is what proved the remaining problem was in the app's panel wrapper rather than the label |
| `compare_screens.py` | Puts the two front ends side by side, zoomed, for a named region (`cmp-sidebar.png`, `cmp-thead.png`), with a 1px red separator and Tk on the left. Requires the two tours to have run. Regions are absolute pixels because both windows are 820x500 - but the **table header is located per framework by colour**, because the two builds have drifted a few pixels apart vertically and one shared box would crop two different bands and show a difference that is only the crop |
| `probe_combo_arrow.py` | Measures the 启动默认模型 drop-down arrow in either front end: crops the arrow zone and prints the palette down its centre row and column. This is what turned "the drop-down button looks different" into "Tk paints exactly `#59616d`/`#a8adb2`/`#f7f8f9` and Qt paints a `#ffffff` bevel and a `#525353` triangle" |
| `probe_arrow_pixels.py` | Dumps the arrow as a **character grid**, `--framework tk` (grabbed from the located canvas) or `--framework qt` (`QWidget.grab()`, so no screen capture at all). Screen grabs depend on window position and DPI; this does not, which is how the chevron's half-pixel offset and its antialiasing were found. The two grids are comparable cell for cell - rows 12-16 now match exactly |
| `compare_round.py` | One image with several regions stacked, Tk above Qt, for a human reviewing a round of fixes (`out/cmp-round.png`). `compare_screens.py` does one region at a time; a round of fixes has to be looked at as a *set*, because a change that makes one element match while shifting its neighbour is only visible in context |
| `compare_layout_diff.py` | Pairs `out/layout-tk-<page>.json` with `out/layout-qt-<page>.json` and prints every widget's `dy`/`dh`. Reading the two tables side by side is how a 5px drift survived three rounds: the numbers were all there and nothing subtracted them. Pairs on text first, then on widget *family* (`Treeview` is `QTableWidget`, `TEntry` is `QLineEdit`) and deliberately **not** on depth, because the toolkits nest the same control differently. Unmatched rows are separated into containers (no counterpart exists) and genuine suspects, so a new unpaired widget still fails the run |
| `probe_tk_font.py` | Prints both front ends' **vertical** font metrics for every size/weight the stylesheets use, and derives the padding each label role needs. `probe_font_metrics.py` settles the horizontal side (identical); this settles the vertical one, and it is where the port's last few pixels lived: Tk's box is `linespace * lines + 6`, QLabel's is `QFontMetrics.height() * lines + padding`, and Tk's linespace is `lineSpacing() + 2` at every size - so a role is short by `leading + 2` per line. Also documents the trap that `heightForWidth()` already contains the stylesheet padding |
| `probe_header_gradient.py` | Tests which `qlineargradient` values Qt's QSS parser accepts on a `QHeaderView::section`, sampling **every** row because the bands under test are 1px tall. Answer: stop positions are parsed as 0 or 1 only, so the fractional/percentage form a 1-in-33 band needs silently collapses the declaration to a flat colour. This is why Tk's 1px heading highlight and shadow are not reproduced |
| `probe_dialog_button_order.py` | Opens each dialog in **both** front ends (each toolkit in its own subprocess, to keep the two event loops apart) and diffs the buttons' left-to-right order. Exists because the 是/否 pair came out **mirrored** in the Qt port: Tk packs with `side="right"`, so the first button *created* ends up rightmost, while a `QHBoxLayout` lays widgets out in *add* order — the two toolkits disagree about what "first" means, and reading both code paths side by side does not reveal it. Refuses to report agreement when either side measured nothing |
| `serve_qt_exe.py` | Serves the **packaged** window to `proto_restore_flash.py --framework qt-exe`. Needed because every flash number on record came from the source build, and the packaged window differs from it - with the onboarding dialog up it has two native child windows where the source has none. Points `%APPDATA%` at a scratch directory and pre-seeds `hide_onboarding`, so the measurement is of the shipping configuration and no modal dialog is in the way |
| `probe_native_children.py` | Launches the packaged build and the source build in turn and prints every visible top-level window they own, with class, rect, style and child count. This is what showed that the two native children belong to the onboarding-dialog startup path rather than to the packaged build, and that dismissing the dialog afterwards does not remove them |
| `verify_packaged_launch.py` | The parts of the packaged acceptance run that need no input: launch, window class, 820x500 client, zero frame, **zero native children**, taskbar styles, and that the real `settings.json` is untouched. `accept_packaged_exe.py` checks for input injection first and aborts, so a locked or disconnected desktop blocks even these - and it is a launch check, not an acceptance run |
| `verify_packaged_cycles.py` | The **minimise/restore cycles** of the packaged acceptance run, driven through the Win32 API instead of the mouse. Covers acceptance requirements 1, 3 (API path), 5 and 6 over 5 cycles: size stays 820x500, frame stays 0, no `WS_CAPTION` returns, native children stay 0, the process survives, and the real `settings.json` is untouched. **Not** a substitute for the acceptance run - it says in its own output that the title-bar drag, both click paths, and the existence of a real taskbar button are uncovered |
| `out/` | Screenshots and JSON reports produced by the runs |

## The measurement that matters

A window showing a native title bar reports a non-zero **non-client frame**:

```python
W.frame_thickness(hwnd)   # (horizontal, vertical)
```

- borderless → `(0, 0)`
- native title bar → roughly `(16, 39)`

Combined with `W.client_rect(hwnd)` this detects both the duplicate title bar and
any size drift, without needing to look at pixels.

For the taskbar button, see the dedicated section below — the naive
diff-against-a-pre-launch-baseline method is wrong on this machine.

## Measuring drag tearing objectively

Start/end position checks cannot see a repaint failure: the window can arrive at
exactly the right place while parts of it still show stale or foreign pixels.
`verify_app_drag_integrity.py` closes that gap without needing a human eye:

- It captures the window with GDI `BitBlt` **off the screen** (not
  `PrintWindow`, which would render fresh and hide the problem), so the image is
  the real composited result.
- The window body below the title bar is compared with a stationary reference.
  Content does not change during a move, so a correct repaint is **pixel
  identical**; only the title bar is excluded, because the cursor and the button
  hover state live there.
- Samples are taken both **paused** (strict comparison) and **in-flight** while
  the mouse is still moving (with a ±4 px alignment search, for gross tearing).
- A **ghost check** looks at the vacated area. Use a region with distinctive
  appearance: the dark sidebar gives 0.92 separation, whereas the light body
  gives only 0.41 and would be a weak detector. Polarity matters - a stale
  fragment makes the vacated region *keep matching* the app.

Result on the packaged build: 5/5 samples `body_diff 0.0` (including in-flight),
client `820x500` and frame `(0,0)` at every sample, moved exactly `[140, 80]`,
ghost match `0.084` (clean repaint).

## Checking the restore path in isolation
`WM_SYSCOMMAND`/`SC_RESTORE` and `ShowWindow(SW_RESTORE)` both restore the
window correctly, so the app's restore handling is sound. If a taskbar *click*
appears not to restore, suspect the harness or the environment (wrong button,
dead input injection) before the app — `diag_taskbar_restore.py` tells the two
apart in one run.

## Candidate results (why the final design was chosen)

| Mode | Architecture | Geometry | Taskbar button |
| --- | --- | --- | --- |
| `a` | `overrideredirect` + `WS_EX_APPWINDOW` | `820x500` stable | **absent** |
| `a2` | `a` + hide/show nudge | `820x500` stable | present normal/restored, absent minimized |
| `b` | normal toplevel, strip `WS_CAPTION` | grows `836→852→868` | present everywhere |
| `b2` | `b` + `WM_NCCALCSIZE` → 0 | grows | present everywhere |
| `e` | `overrideredirect` + clear `WS_POPUP` | `820x500` but **flaky** (`2x28`) | late |
| `e2`/`e4`/`f`/`g` | variants using hide/show | **collapses to `2x28`** | unreliable |
| `h` | `e` + `AddTab` | flaky | late |
| `i` | `overrideredirect` + `WS_EX_APPWINDOW` + `ITaskbarList::AddTab` | **`820x500` stable** | **present in every state** |

`i` is what shipped: the window stays an honest borderless popup, so Tk's
geometry maths is never contradicted, and the taskbar button comes from the
documented Shell API rather than from forcing a re-evaluation.

## Locating the app's taskbar button (this is easy to get wrong)

Two properties of the taskbar defeat the obvious approach:

1. **Buttons are packed rightward against the tray.** Adding our button pushes
   every other button to the left, so a strip captured *before* the app launched
   differs from a later strip across its **entire width** (~27% of pixels, with
   no horizontal shift explaining it). Picking the widest changed run in that
   diff lands on somebody else's button. This exact bug made one acceptance run
   click WeChat's button and report a bogus "did not restore" failure.
2. **Two buttons change when the app minimizes.** Our button loses its "active"
   highlight and the window that becomes active gains one. Both runs are the
   same width, so position alone cannot separate them.

The reliable method is to diff two strips captured moments apart with the app
already running (`normal` vs `minimized`, so the layout is identical) and then
pick the run that got **darker** — that is the button that was active and no
longer is:

```python
delta = run_luminance(normal_strip, run) - run_luminance(minimized_strip, run)
# our button: delta > 0 (active -> inactive).  other app: delta < 0.
```

Measured on a real run: `1513-1612 → +36.0` (ours) vs `1311-1410 → -34.2`
(the app that took focus). Strip coordinates are relative to the taskbar, so add
`grab.taskbar_rect()[:2]` before clicking.

**The `normal` strip must be captured while the app owns the foreground.** That
is the only time its button carries the active highlight, so a baseline taken
from a background window contains a button indistinguishable from its
neighbours and the diff finds nothing at all. `ensure_foreground()` (in
`accept_packaged_exe.py`) raises the window and waits for `GetForegroundWindow`
to agree before the capture, and records the result either way. Forgetting this
is what produced the soak test's first (false) `FAIL`: the app was behind
another window when the baseline was taken, so the only run in the diff was the
16 px clock.

## Why the taskbar icon did not toggle minimize/restore

Symptom: restoring *from* the taskbar worked, but clicking the icon while the
window was up did nothing. The app was innocent - it answered every minimize
request correctly:

```text
SendMessage(WM_SYSCOMMAND, SC_MINIMIZE)  -> iconic=True
PostMessage(WM_SYSCOMMAND, SC_MINIMIZE)  -> iconic=True
ShowWindow(SW_MINIMIZE)                  -> iconic=True
```

The Shell simply never *made* one. **The Shell decides whether a window can be
minimized from `WS_MINIMIZEBOX` alone** (Raymond Chen, "Why does adding
WS_MINIMIZEBOX change how my window behaves when the user presses Win+D?").
`overrideredirect` leaves the window `WS_POPUP` with no `WS_SYSMENU` and no
`WS_MINIMIZEBOX`, so Explorer treats the taskbar button as **activate-only**:

```text
before  style=0x96000008  WS_SYSMENU=False WS_MINIMIZEBOX=False  system menu: none
after   style=0x960a0008  WS_SYSMENU=True  WS_MINIMIZEBOX=True   Minimize=enabled
```

The fix is `WS_SYSMENU | WS_MINIMIZEBOX`. `WS_SYSMENU` is required for
`WS_MINIMIZEBOX` to mean anything, and it is what creates the system menu the jump
list reads. Neither bit draws a frame, so the non-client frame stays `(0, 0)` and
the client stays 820x500. Do **not** add `WS_MAXIMIZEBOX` - it requires
`WS_THICKFRAME`, which would add a native resizable border.

Two things to keep in mind:

* A re-map is when Tk may re-apply `overrideredirect` and drop the bits, so
  re-assert them from the `<Map>` handler rather than only at startup.
* Verify on the **packaged** build. `diag_syscommand.py` prints the style bits and
  the system menu in one line.

If synthetic input is unavailable and you still need proof, `diag_shell_minimizeall.py`
uses `Shell.MinimizeAll()` - the same rule the taskbar uses - and runs it against
both builds as a control. It is disruptive but fully reversible.

**Check what the new style bit exposes.** `WS_SYSMENU` does not only unlock
Minimize; it also makes `SC_CLOSE` reachable (Alt+F4, the system menu's Close, the
jump list's Close), and the window had no system menu at all before. Those paths
converge on the same `self.destroy()` the custom close button uses, so they are
safe here - but that is worth *verifying* rather than assuming, which is what
`diag_close_paths.py` does. It also has a lesson of its own: the first version
sampled `tasklist` once right after `process_alive()` flipped, caught the entry
before it cleared, and reported a failure that did not exist. Poll until
everything is gone.

## Measuring the restore flash

The reported symptom - *"the whole main UI flashes once when restoring from the
taskbar"* - is real and reproducible. `out/restore-flash-evidence.png` captures it in
consecutive frames: the **dark** navigation sidebar is replaced by a flat **light**
fill, then painted back from the bottom up.

The per-frame metric pins the fill down: the patch normally reads
`bg_fraction 0.222, mean 126.26` (dark sidebar), and during the flash
`bg_fraction 0.93-1.00, mean 244.0` - and `244.0` is the toplevel's own background
`#f3f4f7`. So on restore Tk invalidates the child frames, **the toplevel paints its own
background** there, and the dark children paint back over it. It is not an erase and not
a stale copy of the window behind; that earlier reading came from the full-window
evidence image, where "light region replaces dark sidebar" is easy to misread.

**Sampling rate is the whole problem.** A full-window `grab_window` costs ~20 ms per
frame, which is longer than the flash, so the first version detected it in only 10 of
20 restores and every conclusion drawn from those numbers was noise. `--probe patch`
captures a 180x120 region instead - chosen automatically from the reference as the
patch that is normally *least* background-coloured (the dark nav sidebar, 22%
background) - and skips the per-frame Win32 diagnostics. The blank-out then scores 78%
instead of 13%, and the flash is 10/10 reproducible.

> A detector whose sampling period is longer than the event it is hunting cannot
> measure that event. The insensitive version produced "baseline 57% -> 21% after the
> fix", which looked like a result and was pure noise.

### The tear is window-wide, not sidebar-only

The sidebar is where the tear is *visible*, not where it happens. Score one saved
full-window frame (`out/evidence/full/restore-flash-worst-run6.png`) in three separate
regions:

| region | `body_diff` | `content_erased` | exact `(243,244,247)` settled -> frame |
| --- | --- | --- | --- |
| sidebar `(0,200)` | 0.78 | **1.00** | 15.6% -> **100.0%** |
| content `(240,20)` | **0.14** | **1.00** | 37.4% -> **100.0%** |
| content `(320,200)` | **0.10** | **1.00** | 0.0% -> **100.0%** |

The content area is erased just as hard as the sidebar - 100% of its content in all three
regions - while `body_diff` reads 0.14 and 0.10, both below its 0.30 threshold. Region 3
normally contains **no** toplevel-background pixels at all and in this frame is **entirely**
toplevel background, which no amount of "the content changed colour" explains. By contrast
band, all three regions lose 100% of their card fill, borders, grey text and near-black
primary text (1874 + 863 primary-text pixels in the two content regions). The user's "the
whole main UI flashes" is literally correct.

`out/evidence/restore-flash-window-wide.png` is the side-by-side picture.

Live, packaged build, all-API cycle, N=10, probe in the content area
(`out/zone2-content-10.log`):

```
"verdict": "PASS", "runs_flashing": 0, "worst_content_erased": 1.0, "runs_content_erasing": 3
```

Three of ten restores blanked the content area out **completely** and the harness called
it a pass. A second run gave 2/10, and those frames were checked pixel by pixel: **100%
exactly `(243,244,247)`, `mean 244.0`** - the same toplevel fill as the sidebar, not an
inference from brightness. The affected frames are at `t_ms` **+26, +28, +26**; the
sidebar's worst frames sit at **23.0** and **23.5**. One window-wide event at ~+25 ms, not
two artefacts, and 2-3 in ten is what a ~5-8 ms event looks like sampled at 16.6 ms.
(Ignore the "+64-66 ms" in the `stamp` table below - that came from the old full-window
probe.)

### Pick the evidence frame by mechanism, not by size

The first version of the section above used `out/restore-flash-worst-run15.png`, chosen
because it was the largest artefact in `out/`. It is a **different failure mode**: its
content region is `(245,245,245)` and `(204,235,255)` - the colours of the editor window
*behind* the app - so that frame shows the window **transparent**, not filled with its own
background. `exact (243,244,247)` is 0.0% in both regions against 100% in the frame above.

`out/` accumulates frames from every variant run, so it is a mix. Classify before quoting:

| frame kind | signature | cause |
| --- | --- | --- |
| toplevel fill | `exact bg 100%`, `mean 244.0` | the mechanism described above |
| shows the window behind | `exact bg 0%`, `mean 243-245`, colours from the app behind | window transparent / unpainted |
| dark / unpainted | `mean < 150`, e.g. `(0,0,0)` | `LockWindowUpdate` / `WS_EX_COMPOSITED` variants |

The harness now reports this itself: every frame carries `exact_bg` (the fraction of
pixels *exactly* equal to the toplevel background) and the aggregate carries
`worst_erase_exact_bg`, so the mechanism is visible in the summary rather than something
you have to reconstruct from a saved image. Brightness cannot substitute for it - a
toplevel fill and a transparent window both read `mean ~244`.

One run of ten full-window captures produced 3 toplevel fill (runs 6, 7, 9), 3 "window
behind" (runs 2, 4, 5) and 4 settled captures - so two in ten were the clean window-wide
fill, matching the 2-3 in ten measured live on the content probe. Also check `Image.size`:
the `worst-runN.png` files are 820x500 from `--probe full` runs but 180x120 from
`--probe patch` runs, and `offender-runN-M.png` are always patch crops.

### `content_erased`: a region-independent metric

This UI's surfaces are only 4-12 units apart, which breaks any coarse threshold:

```
(243,244,247)  toplevel background      - the colour the flash paints
(247,248,249)  a second light surface   -  4 units away
(255,255,255)  the white card fill      - 12 units away
(32,36,43)     body text                - 211 units away
```

`BG_TOLERANCE = 12` counts the **entire white card** as background, and
`DIFF_THRESHOLD = 24` is applied to **luminance**, so a card blanking to the toplevel
background moves luminance by only ~11 and is not counted either. Both metrics are
*structurally* blind in a light region. Measured on `(240,20)`: 82.7% "background" at
tolerance 12, but **48.1% content at tolerance 4**.

`content_erase_fraction()` therefore normalises by the content count rather than the
region size:

```
content_erased = |reference content AND frame background| / |reference content|
```

The content mask uses the **per-channel maximum** distance (luminance is a weighted sum
and under-reports a tinted pixel), at `CONTENT_TOLERANCE = 4` - inside the 4..12 gap, so
the white card counts as content. The score becomes a property of the *event* instead of
the region: a blank-out reads ~1.0 whether the region is 84% content (sidebar) or 48%
(content area). Validated on the saved frames - the reference scores exactly `0.00` and a
complete blank-out scores `1.00`.

`--content-tolerance N` retunes it. If the settled frame ever scores `> 0.05`, the run is
flagged as having no noise floor rather than reported - a metric that cannot separate
settled from blanked cannot support any conclusion.

> `diff_fraction` is not wrong, it is **region-dependent**: it answers "how much of this
> region changed", which for a 22%-background sidebar is a fine proxy and for a
> 15%-content content area is useless. When a probe scores 0, check the region's content
> density before believing it.

### When does the app get control? (`stamp`, and a corrected alignment)

`instrumented_app.py` traces the app's own window calls, and its trace log carries an
**absolute** epoch as well as elapsed time - without that it cannot be aligned with the
harness's `restore_epoch`, which is recorded in another process on the same clock. Run it as
`CODEX_VARIANT=baseline CODEX_TRACE=1` with `--exe <path>\instrumented_app.py`.

Everything the app does to the window in the 150 ms after each restore, from one traced
8-run session (sidebar probe, `out/zone6-trace-8.log` + `out/window-trace.log`):

```
run4: make_window_minimizable  +8..+51ms over 114 call(s)
      BLANK at +26ms   erased=1.00  exact_bg=1.0
      BLANK at +42ms   erased=0.93  exact_bg=0.9444
run5: make_window_minimizable  +5..+49ms over 114 call(s)
      BLANK at +20ms   erased=1.00  exact_bg=1.0
run6: make_window_minimizable  +5..+50ms over 114 call(s)
      BLANK at +17ms   erased=1.00  exact_bg=1.0

<Map>-driven calls within 150 ms of a restore: 912
first at +5ms, last at +51ms
any OTHER window call (style re-apply, taskbar, minimize): NONE
```

**114 calls per restore, every one `make_window_minimizable`, and that function is read-only
once the style is set** (`if updated != style:` guards its only `SetWindowPos`). No
`register_appwindow_with_shell`, no `_set_appwindow_style`, no `ensure_taskbar_button` - the
`_taskbar_button_ready` guard does its job and the style is never re-applied.

That kills the obvious hypothesis, which this section previously implied: that the app's own
`SetWindowPos(..., SWP_FRAMECHANGED)` invalidates the window and causes the blank. **It is not
called at all.** The blank at +17..+42 ms falls *inside* the `<Map>` storm, and the 114
`<Map>` events *are* the descendants being re-shown - the toplevel paints its own background
while they are gone, and they paint back over it. The app's handler is a passive observer.

> The `+64-66 ms` figures in earlier revisions of this file came from the old full-window
> probe, whose 20 ms sampling and different alignment put the peak elsewhere. The patch probe
> puts the blank at **+17..+42 ms**, and that is the number to use.

### Candidates measured, with a paired control

All with `--probe patch --restore-via api`, all measured with the **region-dependent**
metric (`body_diff`), all with the auto-chosen sidebar probe. "bad frames" measures how
*long* the tear lasts, "darker than UI" counts runs whose worst frame was near-black.

The region-dependent metric is adequate *for this probe* (84% content, so a blank-out
reads 0.78 against a 0.30 threshold) - its region-dependence only invalidates
conclusions about sparse regions, which is why the `composited` row below was re-run.

| candidate | runs | flashing | bad frames | darker than UI |
| --- | --- | --- | --- | --- |
| baseline | 18 | 17/18 (94%) | 43 (2.4/run) | 0/18 |
| `sync-redraw` (`RDW_ALLCHILDREN \| RDW_UPDATENOW`) | 8 | 8/8 | 18 | 0 |
| `sync-redraw-idle` (same via `after_idle`) | 8 | 8/8 | 22 | 0 |
| `no-erasebkgnd` (return 1 from `WM_ERASEBKGND`) | 8 | 7/8 | 13 | 0 |
| `lockupdate` (`LockWindowUpdate` across the burst) | 18 | 13/18 (72%) | 14 (0.8/run) | 4/18 |
| `composited` (`WS_EX_COMPOSITED`) | 18 | 11/18 (61%) | 11 (0.6/run) | 3/18 |
| `composited+no-erasebkgnd` | - | breaks minimize | - | - |
| the app's `<Map>` handler (removed entirely) | 10 | 10/10 | 18 | 0/10 |
| the 114 Python callbacks (Tcl `%W` guard) | 10 | 10/10 | 18 | 0 |
| `WS_SYSMENU \| WS_MINIMIZEBOX`, the bits this project added | 6 | 6/6 | 13 | 0 |
| the DWM minimize/restore animation (`DWMWA_TRANSITIONS_FORCEDISABLED`) | 10 | 9/10 | 17 | 0 |
| clearing `GCLP_HBRBACKGROUND` | 6 | 6/6 | 18 | 0 |
| clearing `WS_POPUP` | - | breaks minimize | - | - |

* The sync-redraw family is the clearest negative result: it fires at +10 ms, before
  the storm ends at +55 ms, so it repaints a tree that is about to be invalidated again.
* `no-erasebkgnd` is the *right* test for the corrected mechanism, it fails, and the
  failure was verified to be real rather than an experiment that silently did nothing. A
  traced run shows `suppress_background_erase` returned `True`, the subclass stayed the
  current window procedure across every re-map (`still_current: True`), and it swallowed
  the erase messages (counter 1 -> 4) - while the flash was unchanged (7 bad frames over
  2 restores, worst `mean 244.0`). **Only ~1 `WM_ERASEBKGND` arrives per restore**, which
  is the actual reason: Tk paints the background inside `WM_PAINT`, so there is nothing
  to suppress. Note this is a different experiment from "clearing
  `GCLP_HBRBACKGROUND`", which clears a brush Tk never consults.
  **Superseded on one point:** "only ~1 `WM_ERASEBKGND` arrives per restore" is true of the
  *toplevel*, which is what this variant subclassed. The child that covers the probe receives
  **120**, so the variant patched a window the erase does not happen to. `no-erasebkgnd-child`
  redoes it on the right window (117 erases verified swallowed) and still changes nothing - see
  *The message spy: what the child actually does* above. The conclusion survives; the evidence
  for it is now the child, not the toplevel.
* `WS_EX_COMPOSITED` is the only lever that measurably helps, and the only one whose theory
  matches the mechanism. **Re-measured with the region-independent metric** (paired from
  source, same conditions, `--minimize-via api --restore-via api`, N=10 each), it looks
  considerably better than the old numbers suggested:

  | run | probe | erasing | worst erasure |
  | --- | --- | --- | --- |
  | packaged build | sidebar | 5/10 | 1.00 |
  | source baseline | sidebar | 3/10 | 1.00 |
  | packaged build | content | 3/10 | 1.00 |
  | source baseline | content | 6/10 | 1.00 |
  | **source `composited`** | sidebar | **0/10** | 0.24 |
  | **source `composited`** | content | **2/10** | 0.88 |

  Pooled: **baseline 17/40 (42%) -> composited 2/20 (10%), Fisher exact p = 0.017.** It does
  not just reduce the rate, it changes the *kind* of artefact - the complete window-wide
  blank-outs (`erasure 1.00`) become partial ones.

  Two caveats. N=10 is noisy: the packaged and source baselines differ 3/10 vs 6/10 on the
  same probe and that is not significant (Fisher p ≈ 0.37), so trust the pooled row, not a
  single 10-run line. And the "darker-than-UI frame" this row used to be charged with was a
  **metric defect**, not a property of the variant - see *The dark-frame threshold was a
  constant* below. With the corrected metric `composited` has zero darker-than-UI frames.

  So on pixels it is a **clean win**, and the fifth round's evidence said so. **It is still
  rejected**, on a measurement from a different instrument: 8x the CPU per restore and ~100x
  the idle CPU. See *What the fix costs the process* below. A frame metric cannot see cost.
* The comparison against `out/evidence/restore-flash-normal-patch.png` (mean 126.4, the
  settled sidebar) and `out/evidence/restore-flash-dark-frame-lockupdate.png` (mean 92.9 - a
  black region where the sidebar should be) still stands for `lockupdate`: anything that
  redirects or freezes painting risks presenting an unpainted surface, and black is more
  visible than light.

> **Repeat the control at the same N.** `composited` measured 4/8, then 7/10 - pooled
> 11/18. A 6-8 run sample of a ~50% effect is wide enough to support "this fixes it".

### The message spy: what the child actually does

The toplevel's message stream is identical in flashing and clean runs, so the difference has to
be in a child. `--variant msgspy` subclasses the window procedure of the child that covers the
probe and logs its messages with an absolute epoch; `align_message_spy.py` subtracts the
restore epoch the harness records and prints what arrived inside the flash window.

```powershell
$env:CODEX_VARIANT = "msgspy"; $env:CODEX_TRACE = "1"
python verify_restore_flash.py --exe ...\instrumented_app.py --probe patch `
    --restore-via api --minimize-via api --runs 6 --probe-patch 0,200
python align_message_spy.py --log out/message-spy-wrapper.log --window=-10,120
```

It settles three questions.

**The child is not hidden and re-shown.** `WM_SHOWWINDOW 0` then `WM_SHOWWINDOW 1` does occur,
but 3.0 seconds apart - that is the minimize/restore pair, not a hide/re-show during the blank:

```
wrapper   WM_SHOWWINDOW 0  at 1789480657.821921      <- minimize
wrapper   WM_SHOWWINDOW 1  at 1789480660.825700      <- restore, +3.004 s
```

**The blank arrives before the child does anything.** Runs 4-6 reproduced the toplevel-fill
blank, and the child's only `WM_PAINT` lands at +35..+49 ms while the blank starts at +17 ms:

| run | verdict | child's `WM_PAINT` | blank frames |
| --- | --- | --- | --- |
| 1 | clean | +49.5 ms | - |
| 2 | **BLANK** | +35.6 ms | +34.5 ms |
| 3 | clean | +49.3 ms | - |
| 4 | **BLANK** | +36.0 ms | +26.6 ms, +41.8 ms |
| 5 | **BLANK** | +38.3 ms | +17.6 ms, +32.9 ms, +49.1 ms |
| 6 | **BLANK** | +40.2 ms | +23.6 ms, +38.9 ms |

Run 3 is clean with a *longer* erase-to-paint gap (38.7 ms) than run 4 (24.6 ms), which blanks
twice. **No message distinguishes a flashing run from a clean one, on the toplevel or on the
child** - the blank is the window's surface being presented before the child has painted into
it.

**The erasing happens to a different window than the one the old variant patched.** The spy
counts one `WM_ERASEBKGND` per restore on the toplevel but **120** on the body container, so
`no-erasebkgnd` - which subclassed the toplevel - was a measurement of nothing. The same no-op
applied to the child (`no-erasebkgnd-child`) is verified to swallow 117 erases with the
subclass still current, and changes the outcome by **nothing**: 5/10 erasing, worst 1.0,
`exact_bg` 1.0, identical to baseline.

> Both variants were, on their first attempt, applied to a window the mechanism does not touch.
> `msgspy` compared **screen** coordinates against a window-relative 240px strip, so every
> overlap was negative and the child spy was never installed - silently, inside an `if best:`
> that never ran. `no-erasebkgnd-child` selected by "largest strip overlap", which the
> full-window wrapper wins (`142 x 500 = 71000`) over the body container (`65604`) - and the
> wrapper receives ~1 erase per restore. It measured 3/10 against a 5/10 baseline and looked
> faintly promising. **Log the census you selected from**, and exclude full-window children.

The census is the other thing worth keeping, because it measures the layout instead of assuming
it:

```
0xb01a10 'TkChild' rel(0,0,820x500)    FULL          the wrapper Tk nests everything under
0x510bda 'TkChild' rel(0,38,820x462)   strip=65604   the body container
0x2607a4 'TkChild' rel(0,38,142x462)   strip=65604   the navigation sidebar
0x2d0bc4 'TkChild' rel(142,38,678x462) strip=0       the content area
0xcf07be 'TkChild' rel(0,0,820x38)     strip=5396    the custom title bar
```

The sidebar is **142px** wide, not 240. And the client area is **completely covered by Tk
children** - there is no exposed parent background anywhere, so a blank reading 100%
`(243,244,247)` must be a *child* painting that colour. That is why `exact_bg` cannot separate
"the wrapper filled itself" from "the toplevel filled itself": both paint the same background,
and the parent has nowhere to paint anyway.

### All five variants in one session

Measured in one session, same probe patch, same all-API cycle, N=10 each, so the rows are
paired rather than assembled from different rounds. `p` is a two-sided Fisher exact test on
"restores that erased the probe", from `compare_variants.py`.

| variant | runs | erased | frames | worst | exact_bg | flash | bad | dark | p vs baseline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 10 | 5/10 | 8 | 1.0 | 1.0 | 9/10 | 12 | 0 | - |
| `layered` | 10 | 5/10 | 9 | 1.0 | 0.9411 | 10/10 | 28 | 0 | 1.000 |
| `no-erasebkgnd-child` | 10 | 5/10 | 9 | 1.0 | 1.0 | 9/10 | 13 | 0 | 1.000 |
| `no-erasebkgnd-child` (wrong target) | 10 | 3/10 | 5 | 1.0 | 1.0 | 8/10 | 10 | 0 | 0.650 |
| **`composited`** | 10 | **0/10** | **0** | **0.2441** | **0.0** | 3/10 | 3 | **1** | **0.033** |

`WS_EX_LAYERED` (`layered`) is a different redirection from `WS_EX_COMPOSITED` - DWM composites
the window instead of the window double-buffering its own painting - so it needed its own
measurement. It is worse, and its worst frame is byte-identical across all ten runs
(`body_diff 78.7%, mean 240.79`): a *deterministic* artefact rather than the intermittent one
under test. The settled frame still scores `content_erased 0.0`, so this is not a
reference-capture error.

### What the fix costs the process (this is what rejects `WS_EX_COMPOSITED`)

`WS_EX_COMPOSITED` is a clean win on pixels - see the table above. It is rejected on cost, and
**no frame metric can see that**: a slower app presents the *same* frames, just later. The
harness therefore samples the app process's own user + kernel CPU with `GetProcessTimes`
(`winapi.process_cpu_seconds`), reported as `cpu_seconds`, `cpu_seconds_per_restore`,
`idle_cpu_seconds` and `idle_cpu_per_second`.

```powershell
# with the harness attached
python verify_restore_flash.py --exe ...\instrumented_app.py --probe patch `
    --restore-via api --minimize-via api --runs 6 --probe-patch 0,200
# ...and with no harness attached at all, which is what makes the idle figure
# trustworthy rather than a property of the measurement rig
python diag_idle_cpu.py --variant composited --seconds 5 --windows 4
```

| | per restore | idle, per 5 s window | idle as % of one core |
| --- | --- | --- | --- |
| baseline | 0.0391 s | `[0.0, 0.0157, 0.0, 0.0]` | ~0% |
| `composited` | **0.3151 s** (8x) | `[0.5469, 0.5, 1.1093, 0.1563]` | **3.1% - 22.2%** |

Over 20 seconds of idling, `composited` consumes **2.31 s of CPU** where baseline consumes
**0.02 s** - roughly **100x**, and bursty rather than smooth, which is consistent with a
composite/repaint feedback loop rather than a fixed overhead. `exstyle=0x02040000` confirms the
bit was set in the `composited` runs.

The idle figure is sampled over **several consecutive windows on purpose**: one window cannot
distinguish a steady burn from the decaying tail of the startup settle, and those two call for
opposite decisions. Baseline reads exactly `0.0s` in three of four windows.

So `WS_EX_COMPOSITED` reduces the flash rate from ~45% to ~10% - it does not remove it - at 8x
the CPU per restore and ~100x the idle CPU, for an always-open configuration tool. **Do not
adopt it.** The lesson generalises: measure what a change costs the *process*, not only what it
does to the pixels.

### The dark-frame threshold was a constant, and that was wrong

`frames_darker_than_ui` asked "did an unpainted surface reach the screen?" with a hardcoded
`mean < 200`. That constant is meaningless for the auto-chosen probe: the sidebar patch settles
at **`mean 126.26`**, so a *partial blank* at `mean 168.5` is **42 units lighter** than the
settled UI and was counted as darker than it. `WS_EX_COMPOSITED` was charged with a black-frame
failure mode it does not have, and that charge was the main argument against it.

The check now compares against the probe's own settled brightness and scans the whole timeline
rather than only the max-`body_diff` frame:

```python
DARK_MARGIN = 20          # below (probe_mean - DARK_MARGIN) = unpainted
probe_mean = round(float(ImageStat.Stat(probe_reference.convert("L")).mean[0]), 2)
dark_threshold = round(probe_mean - DARK_MARGIN, 2)
```

`probe_mean`, `dark_threshold` and `dark_margin` are in the aggregate so the number is
interpretable, and `run_all_checks.py` prints the threshold next to the count. With the
correction, `composited` has **zero** darker-than-UI frames - identical to baseline.

**Two honest limits.** It corrects a *misclassification*, not a blind spot: the constant was
wrong for a light region and a partial blank, which is exactly what `WS_EX_COMPOSITED` produced.
It does **not** turn up dark frames the old check missed - in the first run with the new check,
the one dark frame it found was also the run's max-`body_diff` frame, so the old check would
have counted it too. The timeline scan is stricter in principle; it has not yet been shown to
catch something the worst-frame check did not.

### The baseline produces a rare dark frame too

The stricter check fired once on the **packaged build** (1 of 4 restores), and the frame is real
- `out/restore-flash-offender-run3-1.png`, at `+50.2 ms`, between two frames reading exactly the
settled UI (`mean 126.26`, `body_diff 0.0`):

```
mean 76.91   body_diff 0.7889   bg_fraction 0.305   exact_bg 0.1556

row 60, pixel runs:
  x   0- 17   light blue / white     the sidebar's own left edge, painted correctly
  x  18-141   (0, 0, 0)              the sidebar body - SOLID BLACK, 14880 px
  x 142-169   (243,244,247)          the content area at the toplevel background
  x 170-179   (255,255,255)          a content card
```

Not the light blank this investigation is about - a **partially painted frame** with an
unpainted black rectangle where the sidebar's buttons are. Black is more objectionable than a
light fill, and it is a *baseline* artefact: no variant produced it. It is rare (one frame in
~600 captured across 4 restores) and it is not what the user reported, which is why it had not
been isolated before. Track it separately rather than folding it into "the flash", and note that
"baseline never produces a dark frame" was too strong a claim.

> Correcting a metric can *weaken* your case. Here it removed the only argument against
> `WS_EX_COMPOSITED` on pixels, and the decision then had to be made on a measurement from a
> completely different instrument (CPU time). Fix the metric first, then decide - and do not
> treat "the only argument I had went away" as "the option is now good".

### Do not trust an older build as the control

`dist/CodexConfigTool.old.exe` was **not** a usable control: its style lacks
`WS_POPUP` and it regrows a native frame mid-run (820x500 -> 852x539), so it differs in
exactly the thing under test.

### What is left

Two options, and neither is a small change.

**1. The structural rewrite - and it now pays twice.** The only route to a real fix, and the
`WS_EX_COMPOSITED` cost turns out to be charged **per child window**, so the same change also
makes the one measured lever affordable. `diag_child_windows.py` counts the children so this
option is a number rather than a guess:

```
total descendant windows : 118
immediate children       : 1
by window class: 71 TkChild, 41 Static, 6 Button
descendants inside the left 240px strip (the navigation sidebar): 27 of 118 (23%)
```

A `Canvas` sidebar removes 27 of 118, **not most of them** - and now that the tear is known
to be window-wide, a sidebar-only change cannot fix it anyway: the content area is erased
just as hard. A meaningful reduction means redrawing the whole view layer into one surface,
so the parent's background and the child's paint become a single operation. Note also that
Tk nests every widget under a single `TkChild` spanning the client area, so
`GetWindow(GW_CHILD)` on the toplevel returns exactly one window; attribute descendants by
their own rect, not by their parent.

**2. Accept it.** It is one to three frames of a light fill at ~+17..+49 ms on roughly half of
restores, it does not affect any function of the program, and `run_all_checks.py` carries the
detector as an advisory step that reports both metrics, the mechanism and the process cost.

**`WS_EX_COMPOSITED` is still not on this list - but its cost is no longer a reason against the
rewrite.** It was the one measured lever and it was rejected on cost (8x the CPU per restore,
~100x the idle CPU). That cost is a **per-child-window** tax: at 2 children a composited window
measures 0.0000 s, at 118 it measures 0.3177 s per 3 s window. So a view layer with one or two
surfaces would carry almost none of it - the lever becomes available *as a consequence of the
fix*, not as a competing option. It reduces the flash rate rather than removing it, so it is a
second lever, not a substitute for the rewrite.

The window-lifecycle route is closed **twice over**, and the second closure is the strong one.
It is not "no more ideas for the app's code"; it is that the app has no message-level handle on
the event:

* the app makes no window-invalidating call around the blank (114 read-only
  `make_window_minimizable` calls, nothing else);
* the toplevel's message sequence is identical in flashing and clean runs;
* the child's message sequence is identical too, and the blank arrives *before* the child's
  first message;
* suppressing the erase on the window that receives 120 of them changes nothing;
* the child is not hidden and re-shown (the `WM_SHOWWINDOW` pair is 3 s apart, at
  minimize/restore).
**3. Accept it.** It is one to three frames of a light fill at ~+17..+49 ms on roughly half of
restores. `run_all_checks.py` carries the detector as an advisory step - it now prints both
metrics, because the region-dependent one reported `0/10` and a `PASS` for a content area that
three restores in ten blanked out entirely.

## Environment pitfalls that look like app bugs
- **Synthetic input can silently stop working.** `SetCursorPos` may return
  `FALSE` (with `GetLastError() == 0`) and `SendInput` may report success while
  the cursor never moves — the cursor simply stays parked, e.g. on a second
  monitor. Every click then lands at that parked position, which makes the app
  look broken. `accept_packaged_exe.py` now probes for this up front and exits
  with verdict `INVALID (environment)` instead of reporting app failures.
  `diag_input_state.py` diagnoses it.

  The bare "cursor parked at …" message says *what* but not *why*, and the three
  causes look identical from the outside — wrong window station or desktop, a
  locked workstation, or a foreground process swallowing the pointer — so the
  pre-flight now appends a discriminating summary (`describe_input_block()`):
  the `SetCursorPos` return value **and** `GetLastError`, the clip rectangle
  against the *virtual* screen, whether `OpenInputDesktop` succeeds, and the
  foreground window's class and title.

  Measured while the block was in force (2026-09-18), which is worth knowing
  because it rules out the usual suspects:

  ```
  cursor parked at (1512, 1059); requested (960, 540) (primary monitor 1920x1080)
   -- SetCursorPos -> 0 (GetLastError 0);
      foreground AfxMDIFrame140u 'Autodesk AutoCAD 2024 - [首钢.dwg]'
  ```

  `SendInput` returned **1** (the event was accepted) and the cursor still did
  not move. `GetClipCursor` reported the full virtual desktop, so nothing was
  clamping it. The window station was `WinSta0` and the desktop `Default` — the
  interactive ones — and `OpenInputDesktop` succeeded, so the workstation was
  **not** locked. The foreground window was a real application. Running the same
  probe with the command sandbox disabled fails identically, so this is a
  host-level condition and **not** the harness, the sandbox, or the build. Retry
  later; do not go looking for a defect.
- **`accept_packaged_exe.py` needs the *system* interpreter, not whichever
  `python` is first on `PATH`.** It imports PIL through `grab`, and the managed
  interpreter under `~/.workbuddy-ai/binaries/python/` does not ship it, so the
  run dies with `ModuleNotFoundError: No module named 'PIL'` before touching a
  window. Use `C:\Program Files\Develop\Python\python.exe`. (`verify_packaged_launch.py`
  needs no PIL and runs under either.) Note the split is about *driving* the
  harness only — the application under test is the packaged EXE and is
  independent of the interpreter.
- **The Shell task list is not readable on Windows 11, so it cannot answer "is
  there a taskbar button?".** `winapi.taskbar_button_labels()` walks the
  `MSTaskListWClass` button children and reads their window text — the classic
  Windows 7–10 taskbar. Measured here: `Shell_TrayWnd` present, `MSTaskListWClass`
  present, and **zero** text-bearing button descendants, so it returns `[]` for a
  window that plainly has a button. The function had never been called, which is
  why the claim went unchallenged; its docstring now says so. Presence in the real
  taskbar is only checkable by diffing screen captures across states, which is
  what `accept_packaged_exe.py` does — and that additionally needs the window to
  own the foreground for the active highlight to show.
- **Geometry read from a minimised window is meaningless.** An iconic window
  reports its *parked* rect, not its real one: the archived passing acceptance
  report records `client [0, 0], frame [160, 28]` in the minimised state for a
  820x500 window. Asserting the size while minimised invents failures — assert it
  after restore instead, and assert only the iconic flag and process liveness
  while minimised. (The acceptance harness records this geometry without
  asserting on it, which is why it never hit this.)
- **A transient dialog whose master is withdrawn is never mapped, and an unmapped
  widget has no position.** `show_custom_dialog` and friends call
  `dialog.transient(self)`; withdraw the root and the dialog stays unmapped, so
  `winfo_rootx()` returns the **toplevel's** x for every child. Hiding the main
  window to keep a measurement tidy costs the measurement its validity — leave the
  root visible.
- **Sorting on equal keys is not a sort — it is a silent fallback to creation
  order.** Those equal `rootx` values above sorted into the *order the buttons were
  created*, which is a plausible-looking answer that happened to be exactly
  backwards from the truth. Any "collect positions, sort, report" measurement must
  check that the keys are distinct and refuse to answer if they are not; both
  front ends of `probe_dialog_button_order.py` do.
- **Tk's `pack(side="right")` and a `QHBoxLayout` disagree about what "first"
  means.** Tk packs the first widget against the right edge, so the first button
  *created* is rightmost and the last created is leftmost; a `QHBoxLayout` lays
  widgets out in the order they are *added*, so the first added is leftmost. A port
  that reuses Tk's creation order therefore **mirrors** every right-aligned button
  pair. Measure the order, do not read it.
- **Another window may cover the click point.** Synthetic input goes to whatever
  is topmost under the cursor. A modal dialog from an unrelated application
  parked over the app's default position swallows every click. `W.ensure_clickable()`
  checks with `WindowFromPoint` and raises the window (pinning it topmost only as
  a last resort) before each click, and records what it had to do.
- **A preliminary click before a drag destroys the drag, on a window that uses
  `startSystemMove`.** This is the subtle one. `click_app` performs a complete
  press+release, and it was being called at the drag's start point before the drag's own
  press. On the Tk build that is harmless, because its title bar implements the drag by
  hand. On the Qt build the title strip calls `startSystemMove()`, which hands control to
  the OS's modal `SC_MOVE` loop: the preliminary click enters that loop and releases
  inside it, and the drag's own press then arrives while the loop is still winding down,
  so no new move starts. The drag reports `moved [0, 0]` while every part of the input
  channel is healthy. **Measured on the packaged Qt build: with the preliminary click 0/3
  drags moved, without it 3/3.** A drag needs no preliminary click - its own press is the
  press - and `ensure_clickable` raises the window *without* clicking, so call that
  instead. The lesson generalises: **on a window that delegates the drag to the window
  manager, an injected drag must be one clean press-move-release, with nothing injected
  in between.**
- **Bring the window to the foreground before a drag, and record that you did.** A
  synthetic press on a background window is consumed as an activation: the window is
  raised and the button-up arrives with no move in between, so the drag also reports
  `moved [0, 0]`. The taskbar cycles had always called `ensure_foreground` first; the drag
  step had not. This is a real second cause of the same symptom, which is why the entry now
  carries a `foreground` field - two different mechanisms produce an identical reading, and
  without the field the failure cannot be attributed.
- **`APPDATA` unset silently redirects the settings file.** The app builds its
  settings directory from `APPDATA`. With the variable unset, both the app and a harness
  that copies the same fallback resolve to `~/CodexConfigTool/settings.json` instead of
  `%APPDATA%\CodexConfigTool\settings.json`. The run then reads and writes a file the
  app never uses in normal use, leaves it behind, and looks perfectly healthy while
  testing the wrong settings. **A harness must resolve the settings path exactly as the
  app does and refuse to run when it cannot** (`sandbox_env.settings_path()` does;
  `accept_packaged_exe.py` exits 3 without it). Verify with
  `sha256sum "$APPDATA/CodexConfigTool/settings.json"` rather than a hardcoded
  `~/CodexConfigTool` path - the two are different files and only one of them is real.
  **Which of the two you get depends on the runner, so check rather than assume.**
  Measured on this machine: the Bash tool **does** export `APPDATA`
  (`C:\Users\Administrator\AppData\Roaming`), while a POSIX shim that scrubs the
  environment does not. The two failure modes are opposite and both are silent:
  - `APPDATA` **missing** → you test a stray file the app never touches, and a green
    result proves nothing about the real settings.
  - `APPDATA` **present and you did not isolate** → you read and write the **user's real
    settings**. A `sha256` taken afterwards tells you only "did *I* change it this
    round"; it is a tripwire, **not a specification of what the file should contain**,
    and never a reason to "restore" the user's own state.
  Both are why every harness here goes through `sandbox_env` rather than reading
  `os.environ` directly.
- **A saved report describes the artifact it ran on, not the one on disk now.** Every tool here
  takes a path (`--exe`, `--framework qt-exe`, `--out`) and nothing in the JSON records which
  bytes were at that path. Measured: `dist/CodexConfigTool-Qt.exe` was rebuilt at
  `2026-09-19 19:49:53` while `out/restore-flash.json` dated from `2026-09-18 09:48:48` - **older
  than the artifact** - so its "packaged build: `blank 0`, `native_descendants 0`, sidebar 91.0"
  belonged to the *previous* build. **Compare the report's mtime with the artifact's mtime before
  quoting it.** When a rebuild is expected, pass a new `--out` path instead of overwriting: the old
  report is the baseline, not stale data. `verify_packaged_launch.py` / `verify_packaged_cycles.py`
  are immune (they take `--exe` and run live); only the save-and-quote-later tools carry this.
- **Monitor gaps clamp the cursor.** Monitors need not be aligned: on this
  machine the primary is `(0,0)-(1920,1080)` and the secondary is
  `(1920,69)-(3840,1149)`, so the band `x < 1920, y >= 1080` belongs to no
  monitor and Windows silently clamps the cursor to the nearest edge. A probe
  that just offsets `+40, +40` from wherever the cursor sits walks into that
  band and reports "input injection unavailable" on a perfectly healthy
  desktop. Probe inside the primary monitor (`W.primary_monitor_size()`) and use
  `W.on_a_monitor(x, y)` / `W.monitor_rects()` to explain a clamped move.
- **Never leave the app pinned topmost when clicking the taskbar** — the taskbar
  is in the topmost band too, and the app would sit above it.

## Findings worth remembering

- `winfo_id()` returns Tk's inner child window. The window Windows manages (the
  one with the taskbar button, the one that gets minimized) is its **root
  ancestor**, class `TkTopLevel`. Never pass `winfo_id()` to `ShowWindow`.
- Tk marks `overrideredirect` windows `WS_POPUP` **and** `WS_EX_TOOLWINDOW`.
- The Shell decides about a taskbar button when the window is first shown; style
  changes afterwards are ignored until something forces re-evaluation.
- `ITaskbarList::AddTab` is the supported way to add the button and does not
  touch geometry. Its vtable slots are 3 `HrInit`, 4 `AddTab`, 5 `DeleteTab`
  (after `IUnknown`).
- `IAccessible` derives from `IDispatch`, so its methods start at vtable slot 7.
  Forgetting the `IDispatch` slots shifts every index and crashes the call.
- The Windows 10 task list (`MSTaskListWClass`) is owner-drawn and exposes zero
  accessible children, so MSAA cannot be used to enumerate taskbar buttons.
- Any hide/show of a borderless window makes Tk re-derive the geometry and can
  collapse it to `2x28`. Do not use hide/show as a re-evaluation nudge.
- **Anything that redirects or freezes painting can present an unpainted surface.**
  `WS_EX_COMPOSITED` and `LockWindowUpdate` both cut the light restore tear
  substantially, and both produced frames darker than the settled UI (down to near-black,
  `mean 24.0`) that the unmodified window never produced in 18 restores. Measure the *kind* of artefact, not just whether the
  original one went away.
- **Two processes on one machine share a clock.** `time.time()` written by the app and
  by the harness can be subtracted directly, which is how the app's first `<Map>`
  callback was placed at +10 ms against the restore. Cheap, and it beats inferring
  ordering from two independent relative timelines.

## The `WS_EX_COMPOSITED` cost is a per-child tax, so the rewrite pays twice

Round six rejected `WS_EX_COMPOSITED` on cost - ~100x the idle CPU. That cost had two possible
causes and they lead to opposite decisions: an **intrinsic** price of compositing a 118-child
window, or a **repaint loop** that something keeps re-triggering. Only the loop is fixable. It
is the loop.

### First, two broken instruments - both of which produced a confident empty answer

**The harness cannot spy on another process's window procedure.** `diag_idle_paint.py` v1
installed its message spy from the harness and printed `spy installed on 0/120 window(s)`:
`GetWindowLongPtrW(GWLP_WNDPROC)` returns 0 for a window owned by another process. Worse,
`spy_message_counts` returns `{}` both when a spy is installed and saw nothing and when no spy
exists, so "no repaints" and "no instrument" read identically. The script now runs a **positive
control** (nudge the window one pixel, require a recorded `WM_WINDOWPOSCHANGED`) and aborts
without it. Counting moved into the app process, as the new `idlecount` variant.

**Seven feature blocks shared one closure variable.** `build_features` is one function scope, so
every block that wraps `app.register_appwindow_with_shell` was capturing into the same local
name. The second block to run rebinds it and the first block's closure then calls **itself** -
`register_with_idlecount -> register_extras -> register_extras -> RecursionError`. Tk swallows
callback exceptions, so the app kept running with a half-applied style and no visible error, and
`composited+idlecount` measured **the baseline twice** while looking like a refutation. All
fourteen occurrences are now uniquely named. No earlier round used a combined variant (checked,
not assumed), so nothing before this was affected.

### What the in-process counter shows

`composited`, visible, idle: **55 child windows each receive `WM_NCPAINT` + `WM_ERASEBKGND` +
`WM_PAINT` about 22 times a second** (~3,600 messages/s). Baseline: **none**. Minimized: zero CPU
and no messages. The hot set is exactly the visible widgets - content container, sidebar, title
bar, every nav button and label. Note `child8 = 22paint/0erase`: a window that never receives
`WM_ERASEBKGND` is in the loop anyway, which by itself excludes erase suppression as a fix.

### The scaling, which is the part that matters

`proto_composited_children.py` builds the smallest stand-in - an `overrideredirect` window of the
same size with N real Tk children - and measures its own CPU.

| children | baseline | `composited` |
| --- | --- | --- |
| 2 | 0.0000 | 0.0000 |
| 8 | 0.0000 | 0.0052 |
| 24 | 0.0000 | 0.0000 |
| 56 | 0.0052 | **0.1615** |
| 118 | 0.0000 | **0.3177** |

With the count fixed at 56 and each widget's area varied 64x, the cost is **flat** (0.047 /
0.078 / 0.055 / 0.000). It is charged **per child HWND, not per painted pixel**.

So collapsing the view layer into one or two surfaces does two things at once: it shrinks the
unpainted interval behind the flash, **and** it makes `WS_EX_COMPOSITED` affordable (at 2
children it measures 0.0000 s). The rewrite is not the peer of "accept it" - it is the option
that pays twice.

### Three environment traps, all of which cost time here

* Applying `WS_EX_COMPOSITED` to a window owned by the **foreground** process terminates the
  caller - twice, with no output at all. Use a **subprocess**.
* `root.update()` **blocks** once the window is composited; drive the loop with `after()` +
  `mainloop()` instead.
* `OpenProcess` needs an explicit `restype`, or ctypes truncates the handle to 32 bits and
  `CloseHandle` kills the process silently.


## Why the Qt app in this workspace does not flicker (and why that is not a fix you can copy)

`Image-Management` is a second app in this workspace: PySide6/Qt, frameless main window
(`Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window`, `qt_app.py:1082`), custom title bar,
translucent on top of that - and **no flicker problem recorded anywhere**. It was worth checking
whether its maximize/minimize handling contained something borrowable.

It does not, and the reason is worth more than the answer.

### It has no flicker machinery at all

Its state handling (`qt_app_v20.py`: `showMaximized` 5671, `showNormal` 5677, `changeEvent` 5704,
`_normal_window_state` 5627, `_geometry_looks_maximized` 5636, `_remember_normal_window_geometry`
5649) is **geometry and state bookkeeping**. `_remember_normal_window_geometry` exists because
`showNormal()` after a taskbar restore does not always give back the pre-maximize size - a
geometry bug, not a painting bug.

A project-wide search finds no `WS_EX_COMPOSITED`, no `SetWindowPos` with redraw flags, no
`LockWindowUpdate`, no `RedrawWindow`, no `InvalidateRect`, no `setUpdatesEnabled(False)`, no
`WA_OpaquePaintEvent`, no `nativeEvent`. The only Win32 calls in the whole project are
`SetWindowCompositionAttribute` for **acrylic blur** (`qt_app.py:1250-1264`, a visual effect) and
`ShowWindow(window, 9)` for single-instance activation (`app_runtime.py:587`). `WA_TranslucentBackground`
exists so the app can draw a rounded, shadowed surface inset 16 px - the translucency is what makes
the corner radius and the shadow visible.

**It does not handle the flicker. It does not have it.**

### The difference is the number of native windows

* a **Tk widget is a native window** - `tk.Label`, `tk.Frame`, `tk.Button` are real `TkChild` /
  `Static` HWNDs.
* a **Qt widget is not** - `QWidget` paints into the top-level's backing store. One top-level
  `QWidget` is one HWND and the whole UI inside it is pixels in one surface.

`proto_surface_count.py` builds the same UI tree in both and counts:

| | native descendants | toolkit widgets |
| --- | --- | --- |
| Tk (`overrideredirect`) | **51** (46 `Static` + 5 `TkChild`) | 52 |
| Qt (`FramelessWindowHint` + `WA_TranslucentBackground`) | **0** | ~50 |

The mirror is faithful: its Tk geometry reproduces the real app's measured layout exactly
(content container `rel(142,38,678x462)`, sidebar `rel(0,38,142x462)`, title bar `rel(0,0,820x38)`).

### The same probe, the same cycles, only the framework differs

`proto_restore_flash.py --both` positions each window identically, runs the same positive control,
uses the same relative threshold (settled mean +/- 25) and the same ~33 ms capture rate:

```
 tk:  52 native windows, 8/8 cycles with a blanked sidebar   (sidebar 35.35 -> 220.81, byte-identical every cycle)
 qt:   0 native windows, 0/8 cycles with a blanked sidebar   (sidebar 34.15, max 34.15 - never moves by 0.01)
```

### What the blank actually is

Saving every frame of one cycle settles what the earlier rounds could only infer. At **+59.2 ms**
after `SW_RESTORE` the Tk window is **on top** - its title-bar labels are painted, over the browser
tab strip behind them - but its **body is not painted at all**: no light background, no dark
sidebar, the browser behind shows straight through. At **+88.7 ms** it is complete.

The Qt window, at **+49.0 ms** after the same `SW_RESTORE`, is already fully painted.

So the defect is not "the wrong background colour shows". It is: **the window is presented before
its content has been painted, and whatever the compositor has at that instant fills the gap** -
the toplevel's own `#f3f4f7` in the real app (measured `mean 244.0`, which is why the dark sidebar
is where you see it), and nothing at all in the lighter mirror. Same defect, same ~1-3 frames,
different thing behind it.

### This does not contradict the `layered` result

| | native windows | layered? | cycles that flashed |
| --- | --- | --- | --- |
| Tk mirror | 52 | no (`exstyle=0x00000080`) | 8 / 8 |
| Tk app + `WS_EX_LAYERED` + `SetLayeredWindowAttributes` | 119 | yes | **10 / 10** |
| Qt mirror (`WA_TranslucentBackground`) | 0 | **yes** (`exstyle=0x00080000`) | **0 / 8** |

Qt is layered *and* clean. Tk is not layered and flashes; made layered it gets worse. **Layering is
not the variable. The window count is.** Which is why the borrowable thing is not a flag.

### What this adds to "what is left"

It sharpens the rewrite's target. It is not "fewer widgets" - it is **one native window**. Anything
that still leaves the body of the UI as separate HWNDs has not addressed the mechanism. In Tk terms
the content must be drawn into a single native widget (a `Canvas`, or one widget that owns the
pixels), not merely reorganised into fewer frames.

## Can the Qt architecture be used here? (measured four ways)

The question is not whether the reference project contains a copyable trick - it does not. It is
whether its *architecture* can be adopted, and whether that is reachable from Tk. Build the same
UI four ways and run the same probe (`proto_surface_count.py` + `proto_restore_flash.py --both`):

| architecture | native windows | cycles with a blank frame | blank frames | repainted by |
| --- | --- | --- | --- | --- |
| Tk widgets (`overrideredirect`) | **52** | **8 / 8** | 17 / 241 | 45.0 ms |
| Tk, whole UI on one `Canvas` | **2** | **8 / 8** | 8 / 240 | 30.2 ms |
| Tk, one `Canvas` + `-alpha` (`WS_EX_LAYERED`) | **2** | **8 / 8** | 8 / 240 | 30.6 ms |
| Qt `FramelessWindowHint` | **0** | **0 / 8** | **0 / 240** | never |

### What it means

* **One `Canvas` in Tk halves the damage and does not fix it.** 17/241 -> 8/240 blank frames and
  45 ms -> 30 ms to repaint is a real ~33% improvement, but every cycle still flashes and the floor
  is ~30 ms = two 60 Hz frames.
* **The compositor redirection is not the variable.** The `-alpha` window is `WS_EX_LAYERED`,
  exactly what the Qt window carries, and its numbers are identical to the unlayered canvas. This
  matches the earlier result that layering the *widget* UI made it worse.
* **The real difference is a backing store plus one surface.** Qt can present the last complete
  frame the moment the window returns; Tk has no backing store and repaints by walking its widget
  tree through its own idle queue after the restore. That is where the ~30 ms lives, and it is a
  toolkit property, not something the application can call.

### Scope, if a Qt port were ever considered

From the source: `codex_config_tool.py` is 5598 lines, of which `CodexConfigApp(tk.Tk)` is
**~2133 lines / 75 methods**, with **87** `command=`/`.bind(` callbacks and **19** `tk.Toplevel`
dialogs. The other ~3465 lines (config, backups, process handling, HTTP, model lists) are plain
Python and would be reused unchanged. Packaging: the exe is 13.2 MB today and PySide6 adds the Qt
runtime.

### Two traps found while trying to test `WS_EX_COMPOSITED` on the canvas

* Applied to a **mapped** window (from the driver or from the app): the window stops painting
  entirely - the probe settles at pure white and never recovers. A threshold measured *relative*
  to the settled value then scores it as a flawless `0 blanks`. The harness now marks such a cycle
  `probe_valid: false` and excludes it; the guard turned a false `0/8` into
  `NO VALID CYCLES - the window stopped painting; the zero is meaningless`.
* Applied **before the first map** via `withdraw()` -> `SetWindowLongPtr` -> `deiconify()`: Tk never
  maps the window correctly (it stays `1x1`, `style=0x46000000`), so there was nothing to measure.
  Use Tk's own `-alpha` instead when a layered window is wanted.

## The fix: the Qt port, measured before and after

The scope note above stopped being hypothetical: `codex_config_qt.py` is that port, and
`codex_config_tool.py` is imported by it **unchanged** - byte-for-byte, so it stays the rollback and
doubles as the library. The Qt file is a view layer (2,508 lines, 15 classes, no new business
logic) plus the glue to drive it.

Two independent runs of 8 minimise/restore cycles each, on the **shipping** windows rather than
stand-ins:

```bash
python proto_restore_flash.py --framework tk-app --strip-top 300 --sidebar-max 120 --cycles 8
python proto_restore_flash.py --framework qt-app --strip-top 300 --sidebar-max 120 --cycles 8
```

| build | toplevel class | native children | cycles with a blanked sidebar | blank frames | unpainted span |
|---|---|---|---|---|---|
| **Tk, shipping** (`CodexConfigApp`) | `TkTopLevel` | **118** | **8/8**, **8/8** | **25/241**, **15/238** | 0 - 50.7 ms |
| **Qt, new** (`CodexConfigWindow`) | `Qt6112QWindowIcon` | **0** | **0/8**, **0/8** | **0/241**, **0/240** | **0.0 ms** |

The Tk side is the bug on demand: the sidebar reads exactly `244.7` - the toplevel's own `#f3f4f7`
background - where it should read `91.0`, for one to four sampled frames per restore.

The Qt side is stronger than "fewer blank frames". `sidebar_max = 91.0` on **every** cycle of both
runs means the probe never saw the sidebar deviate from its painted value by a single unit across
all 481 frames. `probe_valid` passed throughout, so it is not the masked failure described above:
the probe confirmed the window was genuinely painted (sidebar 91.0, content 244.67) before counting.

> These are the numbers **before** the maximise guards were added. The guards change the window's
> event handling, so the measurement was repeated afterwards and is recorded in
> [The flash, re-measured after the guards](#the-flash-re-measured-after-the-guards) below: still
> `0/241`, so the guards cost nothing.

### Why the app's own palette needed two new options

Both bounds in the positive control were hardcoded to the *prototype's* colours. The real app's
sidebar is `#5b5b5b`, mean **91.0**, and `sidebar_ref <= 90` rejects it by one unit. Worse, because
`probe_valid` was zeroing the count, the first Tk run printed a reassuring `blank 0 []` **while
`sidebar_max 244.67` sat beside it on the same line** - the flash was right there, and the verdict
said clean. `--sidebar-max` / `--content-min` now carry those bounds, and `--strip-top` moves the
probe band: the app's default 440 lands inside the donation QR code (mean 147), while 300 sits in a
flat stretch between the last nav row and the QR code. Pick a band that is vertically flat - one
crossing a selected nav row or an image reads noise.

### Two instrument bugs this round found in the instruments themselves

* **`_dump_probe_debug` profiled the whole window, not the strip**, despite the label. Averaging
  the full window height into each 20px column reads ~120 where the band is a flat 91 - a
  confidently wrong number of exactly the kind the dump exists to catch. It now profiles the band
  the probe samples.
* **The screenshot helper cropped the bottom off every dialog.** For a window, Qt's `pos()` already
  includes the frame while `width()`/`height()` are the client size, so `(x, y, x+w, y+h)` stops one
  title-bar short. That produced a convincing phantom "the profile editor is clipped" and a detour
  into dialog sizing. Use `frameGeometry()`.

### Seeing it rather than measuring it

```bash
python qt_visual_tour.py      # out/tour-*.png, every page and dialog
python smoke_qt_app.py        # structure, taskbar behaviour, native-window census
```

Both redirect the config directory and the settings file, so neither can touch a real
configuration.

## Driving the real window instead of inspecting it

The flash numbers and the structural checks are both **passive**: they read a window that is
sitting still. Neither can tell you whether pressing a button does anything. `verify_qt_app.py`
closes that gap - it injects synthetic mouse input into the shipping Qt window while it runs and
asserts the seven standing requirements in one pass:

```bash
python verify_qt_app.py > out/verify-qt-run.log 2>&1
```

| requirement | how it is driven | how it is judged |
|---|---|---|
| R1 无边框 | - | `frame_thickness == (0,0)`, no `WS_CAPTION`/`WS_THICKFRAME`, client `820x500` |
| R2 标题栏拖动 | real press/move/release on the title bar | window moved exactly; a mid-drag capture scores **tear** against a stationary reference |
| R3 不可最大化 | synthetic `SC_MAXIMIZE` **and** `ShowWindow(SW_SHOWMAXIMIZED)` | client rect still `820x500` after each |
| R4 任务栏最小化/恢复 | real click on the located taskbar button | `IsIconic()` toggles both ways, style keeps `WS_MINIMIZEBOX` |
| R5 恢复无第二标题栏 | 5 × (minimise → restore) | `frame == (0,0)`, `has_caption == False`, native children `0`, title band dark |
| R6 恢复后尺寸不变 | same 5 cycles | client `820x500` every time |
| R7 功能未受影响 | the whole configuration surface | see below |

R7 is where this earns its keep. It navigates all five pages and checks the nav highlight, checks
the path回填, the API-key masking and the eye toggle, presses **新增配置** through the real
`clicked` signal, saves a profile to disk, edits it and confirms the change persisted, then
exercises search, sort, switch, delete, official login and the update check. All seven dialogs are
constructed for real - `exec`/`run` are replaced with non-blocking stubs, but each dialog's
`__init__` is wrapped so that a constructor that raises is recorded rather than swallowed.

### Two rules the harness enforces on itself

Both exist because breaking them produced confident, wrong answers during development.

* **A metric is only asserted when its precondition held.** The tear score is meaningless if the
  drag never happened - and "the window did not move" is itself either a real failure or a dead
  input channel. The harness asserts *the drag happened* as its own named check and then gates the
  tear assertion on it. Before this, one run reported four tear failures that were entirely the
  desktop's fault.
* **A check the environment made impossible is not a failure.** `check(..., environment=True)`
  records the flag, prints `[ENV ]`, and keeps the entry out of the failure count; the exit code
  ignores environment skips. Without this, a desktop that clamped the cursor 3-4 px from the
  screen edge read as a broken application.

### Three real defects it found

The reason to inject input rather than read code. All three were found by this harness, fixed, and
re-verified:

1. **新增配置 on the current page did nothing.** `QPushButton.clicked` carries a `checked` bool,
   so passing `self._show_profile_editor` directly delivered that bool as the `record` argument and
   the editor then raised `AttributeError: 'bool' object has no attribute 'path'`. The recorder
   caught it verbatim: `{"dialog": "ProfileEditorDialog", "args": ["CodexConfigWindow", "bool"]}`.
   Both call sites now wrap the call in a lambda.
2. **`SC_MAXIMIZE` resized the window to `1920x1040`.** `WS_MAXIMIZEBOX` unset governs the button
   and the system-menu entry, **not** the command - `DefWindowProc` honours `SC_MAXIMIZE`
   regardless. Fixed in `nativeEvent`.
3. **`ShowWindow(SW_SHOWMAXIMIZED)` resized it and never reverted.** This one is invisible to Qt:
   it sets `WS_MAXIMIZE` and resizes directly, leaving `windowState()` at `WindowNoState`, so
   `changeEvent` never fires and `showNormal()` is a no-op. `probe_minimize_cycle.py` is what
   proved that. Fixed in `resizeEvent` by checking `IsZoomed()` and calling `SW_RESTORE`.

Defect 3's fix has two subtleties worth keeping, because both are easy to undo by accident: the
revert must **not** fire while minimised (Windows parks a minimised window at `(-32000,-32000)`
with a 160x28 icon-sized client rect, which is a size change that is not a maximise), and the
`changeEvent` path must keep re-asserting `WS_MINIMIZEBOX`, since `SW_RESTORE` rewrites the style
bits.

### Three traps in the measurement itself

* **A window must be created by the styled `QApplication`.** `codex_config_qt.main` sets the font
  and the style sheet; the harnesses each built their own app and one omitted the style sheet, so
  the window showed only hand-painted chrome - grey instead of the black title bar. The captured
  frame looked plausible (it *was* a window), which is why it survived several runs. Comparing the
  top-38-pixel mean against the verified tour screenshot gave it away: **5.7** for the real window,
  **203.7** for the unstyled one. There is now one shared `create_application()` factory.
* **`grab_window` is not `window_rect`.** `winapi.window_rect(hwnd)` returns `(left, top, width,
  height)`, not a `RECT`. Computing `right - left` from it captured the window at about a third
  size (`270x230`, `192x191`), which then produced a phantom "the sidebar is missing" failure.
* **The first synthetic press of a session never latches.** The opening drag moved 0 px while the
  window was demonstrably foreground. The harness now warms up with a real 40,20 drag-and-return
  before it measures anything, and nudges the cursor 1 px and back before `LEFTUP`, because the
  `SC_MOVE` loop reads the cursor when it pumps and can miss a `SetCursorPos` (drags landing
  10-12 px short).

### The flash, re-measured after the guards

Those fixes add a `resizeEvent` handler and a `nativeEvent` override to the window, so the obvious
question is whether they reintroduced the blank frame. They do not - both builds, same session,
8 cycles each:

| build | toplevel class | native descendants | cycles with a blanked sidebar | blank frames | unpainted span | repainted by |
|---|---|---|---|---|---|---|
| **Tk, shipping** (`CodexConfigApp`) | `TkTopLevel` | **118** | **8/8** | **12/241** | 0 - 15.4 ms | 41.7 - 62.4 ms |
| **Qt, post-guard** (`CodexConfigWindow`) | `Qt6110QWindowIcon` | **0** | **0/8** | **0/241** | **0.0 ms** | **never** |

Tk reads `sidebar max 244.67` on all eight cycles - the toplevel's own `#f3f4f7` background - where
the settled value is `91.0`. Qt reads `sidebar settled 91.0 max 91.0` on all eight: the probe never
saw the sidebar deviate by a single unit across 241 frames, and `repainted by None` means it never
needed repainting at all. Style values are unchanged (`style=0x960A0000`, `exstyle=0x00040000`;
Tk carries `WS_GROUP`, hence `0x960A0008`).

**One caveat on the class string.** It reads `Qt6110QWindowIcon` here and `Qt6112QWindowIcon` in
some earlier runs - more than one PySide6/Qt build is reachable on this machine and the class name
tracks it. Both produce 0 blank frames. These numbers come from the documented system interpreter
(`C:\Program Files\Develop\Python\python.exe`, Python 3.13.9, PySide6 6.11.0, Qt 6.11.0), which is
the same interpreter the interactive run used, so the functional test and the flash measurement
describe one build.

## Comparing the two front ends, because "does it look the same" is not a test

The port passed a structural test, an interactive test and a flash probe - three independent lines of
evidence, all green - and still shipped a page layout with a **200px hole** above the panel on
官方登录 and 新手引导, a **clipped last row** on 当前配置, and the title-bar buttons in **reverse
order**. Every widget involved existed, had the right object name and was wired to the right slot.
None of that is a *behaviour*, so no behavioural test could ever have seen it.

Two things were missing, and both are now here.

**A screenshot of the old build.** `qt_visual_tour.py` had no Tk counterpart, so the new pages had
never been put next to the pages they were replacing. `tk_visual_tour.py` is the counterpart.

**A way to compare geometry as numbers.** `compare_layout.py --framework tk|qt --page <key>` dumps
each widget's `x/y/w/h` and sorts by `y`, which turns "the right-hand pages look wrong" into a list
of differences you can act on:

| element (当前配置) | Tk | Qt before | Qt after |
|---|---|---|---|
| entry height | 35 | 29 | **35** |
| field row pitch | 47 | 41 | **47** |
| details panel inner height | 204 | 182 | **204** |
| first field row `y` | 227 | 199 | **225** |
| 官方登录 panel top `y` | 121 | 310 | **120** |
| 新手引导 panel height | 267 | 186 | **263** |
| 新手引导 first bullet | 40 (wrapped) | 23 (**clipped**) | **38 (wrapped)** |

### Three causes worth remembering

**`pack` and `QVBoxLayout` disagree about slack.** Tk gives each `fill="x"` widget its natural height
and leaves the remainder at the *bottom*; `QVBoxLayout` spreads it across every item that can grow,
which stretches the header and opens a gap above the first panel. A trailing `addStretch(1)` - here
`CodexConfigWindow._pack_top()` - reproduces `pack`. Do not add it to a page whose content expands
(切换配置's table, 推荐渠道's panel): the stretch would take half the slack and shrink them.

**Tk's `tk.Label` boxes are ~8px taller than Qt's `QLabel` for identical text.** This is *not* a font
difference: `probe_font_metrics.py` renders five strings in both and every one comes back at a width
ratio of **1.000** with matching heights. Tk's label carries padding Qt's does not, so the fix is QSS
padding on the affected label roles. Left alone it lifts every page's content ~16px above the Tk
original.

**`QLabel.setWordWrap(True)` does not make the layout give the label the wrapped height.** QLabel
reports it only through `heightForWidth()`, and the panels in between hand it a one-line height from
`sizeHint()`. The first attempt - `setMaximumWidth(500)` - made it worse: the label was clamped and
the text was **clipped mid-sentence** ("和启动默认模" instead of "和启动默认模型。"). A clipped line
is easy to miss because it looks like the sentence just ends there. `probe_qlabel_wrap.py` showed
`wordWrap` + `maximumWidth` wraps correctly *in isolation*, which located the real culprit one level
up: `_panel` pinned every panel to `QSizePolicy.Fixed` vertically, and a Fixed widget takes its
`sizeHint` height and never asks its children for a wrapped height. The working combination pins the
height explicitly, which is safe precisely because the two front ends share one font:

```python
bullet.setFixedWidth(500)
bullet.ensurePolished()
bullet.setMinimumHeight(bullet.heightForWidth(500))
```

### Smaller fidelity gaps, all from the same family

* Tk grids every row with `pady=6`, **including the first and last**; `QGridLayout`'s
  `verticalSpacing` only sits between rows. Needs `setContentsMargins(0, 6, 0, 6)`.
* Tk packs the guide page's separator with `pady=(3, 14)` after **every** section, the last one
  included.
* Tk's guide bullets use `wraplength=500` while the panel's content area is 580px.
* Tk's page buttons carry `ipady=3` (35px) but its dialog buttons use the style's own `(8,5)`
  (~30px). Qt's `APP_QSS` / `DIALOG_QSS` split maps onto exactly that.

### Round three: three more regressions, and the comparison that finds them

A second manual pass reported three more, all the same family - the sidebar's selection indicator, the
table header, and the combo box's drop-down arrow. Each was measured against Tk first, and each turned
out to be an element the port had *dropped* rather than drawn wrongly:

| reported | Tk | Qt before | Qt after |
|---|---|---|---|
| nav selection indicator | 13x42 at x=0 | **1px** wide | **13px** |
| nav caption's first ink | x=39 | x=27 | **x=38** |
| header top / bottom border | `#9e9a91` | none | `#9e9a91` |
| header height | 35px | 37px (39 after adding the border) | **35px** |
| combo arrow | 28x29 canvas, `#59616d` chevron | native bevel, `#ffffff` + `#525353` | identical rasterisation |
| profiles table top `y` | 194 | 185 | **194** |

**`tk.Label(width=1)` is one character cell, not one pixel.** In Microsoft YaHei UI that cell is 13px,
and the button's `padx=24` then puts the caption at x=37. The port read `width=1` literally, which cost
the green block *and* moved all five captions 12px left - so the user's "文字都不居中了" was really
"the text is no longer where it was". Same trap in the combo: `padding=(6, 5, 34, 5)` reserves 34px for
an arrow ttk is configured never to draw (`style.layout` lists only `Combobox.textarea`), and the
visible arrow is a separate `tk.Canvas` `place`d inside that reserve.

**A QSS border is added outside the padding.** Tk's `Treeview.Heading` is `padding=(8, 7)`, no border,
35px tall. Adding the two 1px borders to match Tk made the Qt header 37px and pushed the whole table
down. The padding has to give back the 2px: `padding: 5px 8px`. Re-measure - do not do the arithmetic
and assume.

**Compare where the element is, in both builds.** `compare_screens.py` crops the header *per
framework*, located by colour, because the two builds have drifted apart vertically in places; one
shared box crops two different bands and produces an image that shows the crop, not the difference.
`probe_arrow_pixels.py` goes further and renders the arrow as a character grid with no screen capture
at all, which is how the chevron's half-pixel offset and its antialiasing were found:

* Tk strokes a line centred on the coordinates it is given; Qt strokes one centred on the pixel
  **corners**. Tk's `(8,11) (13,16) (18,11)` needs to become `(8.5,12) (13.5,16.5) (18.5,12)`.
* Tk's canvas does not antialias. Leaving Qt's on produces blended greys along both legs, so the two
  pictures are measurably different even though they are visually close.

**Then compare the whole page.** Fixing the header exposed a 9px offset in the same region, which the
header crop could never show: `#hint` and `#channelUrl` were missing the `padding: 4px 0` that five
other label roles already carry to compensate for Tk's taller label boxes. Sweeping all five pages
(`compare_layout.py`, both frameworks) is what turned that up.

That sweep was read as "`current` / `official` / `recommended` now compare clean". **That was wrong**,
and it is the mistake round four exists to correct: the two tables were read by eye, and every page
was still 1-2px high. Nothing had *subtracted* them.

### Round four: the pixels that were never subtracted, and the law behind them

Round three left four measured-but-unfixed residuals (the 新手引导 spacing, the 切换配置 first-column
width, the header divider, the tree panel's border colour). Three were one-liners. The fourth was not,
and chasing it produced the general rule behind every remaining difference on **all five pages**:

```
tk.Label   height = linespace * lines + 6
QLabel     height = QFontMetrics.height() * lines + padding_top + padding_bottom
Tk's linespace = QFontMetrics.lineSpacing() + 2      (at every size this app uses)

  required padding = (leading + 2) * lines + 6
```

Tk lays a line out at `linespace`; QLabel lays one out at `height()`, which is `lineSpacing() -
leading`. So a role is short by `leading + 2` per line. The regular 9pt/8pt roles have `leading` 0 and
need the 8px (`padding: 4px 0`) they already had - which is why most labels matched and hid the
pattern. The **bold** roles have `leading` 1 and needed 9px, and a **wrapped** label is 2px short per
extra line.

| element | Tk | Qt before | Qt after |
|---|---|---|---|
| `pageTitle` (13pt bold) | 30px | 29px | **30px** |
| `sectionTitle` / `channelTitle` (10pt bold) | 25px | 24px | **25px** |
| `panelHeading` | 22px (8pt bold) | 21px (9pt bold - wrong size too) | **22px** |
| `currentName` (13pt bold, `borderwidth=0`) | 26px | 25px | **26px** |
| 新手引导 2-line bullet | 40px | 38px | **40px** |
| 推荐渠道 card | 71px | 73px | **71px** |
| 推荐渠道 icon | 40x40 | 36x36 | **40x40** |
| 切换配置 切换到该配置 (Tk `ipady=2`) | 35px | 31px | **35px** |
| 切换配置 search caption | 22px | 35px (stretched) | **22px** |
| 当前配置 / 官方登录 / 新手引导 / 推荐渠道 | - | 1-5px high | **0px** |

`compare_layout_diff.py` reports `ALL PAGES IN PLACE`, `worst |dy| = 0px`.

**Two instrument bugs were in the way, and both were the same mistake.** `compare_layout.py` dumped
every widget including *unmapped* ones, so the profiles page's hidden multi-select bar reported a
480px-tall button at y=38 and buried the real rows; and it read `ttk.Entry`'s text through
`cget("text")`, which ttk **aliases to `-textvariable`** - so the Tk table said `PY_VAR5` where the Qt
table said `C:\Users\...\.codex`, and nothing could be lined up. Filter to what is on screen, and read
the value rather than the variable's name.

**A widget's box is not its text position.** Qt stretches a `QLabel` to its row's height where Tk's
packer never stretches a `tk.Label`. The glyphs stay centred either way, so this is invisible - but it
is what `compare_layout.py` measures, and a box 13px taller than Tk's *hides* real drift from the
comparison. `_pin_height()` fixes the search caption to its natural height for that reason, not for
the look.

**`heightForWidth()` already contains the stylesheet's padding.** Recovering the line count by
dividing it by the font height rounds a two-line label up to three and gives it 17px of phantom
height - the first attempt at the guide bullet came out 57px instead of 40px.
`QFontMetrics.boundingRect(..., Qt.TextWordWrap, text)` returns the wrapped text box with no padding
in it, which divides cleanly. `probe_tk_font.py` prints both sides' metrics so the next person does
not have to rediscover this.

**A gradient cannot draw a 1px band inside a 33px box.** Tk's themed heading is 5 rows - border,
`#eeebe7` highlight, 31px fill, `#cfcdc8` shadow, border - and the stylesheet looked like the obvious
place for the two inner lines. It is not: `qlineargradient`'s stop positions are parsed as **0 or 1**
only, so `stop:0.0303` (and `stop:3%`) silently collapses the declaration to a flat colour, with no
parser warning and no log entry. `probe_header_gradient.py` measures this and includes a working
two-stop control, so the flat result is provably the parser's doing. The header keeps its two borders,
its 3px divider and its text; the two 1px inner lines are a documented, deliberate 2px shortfall.

**A colour-based locator has to know the whole palette.** `compare_screens.py` found the header by
matching `#eef0f2` alone, so it measured Tk's band as 31px against Qt's 33px and reported a phantom
1px drift on a header whose extent matched exactly. Once it accepted the highlight and shadow colours
too, it reported `+0px`. A locator that is narrower than the thing it locates invents differences.

### The flash probe had only ever measured the source build

Every restore-flash number in this document came from `serve_qt_app.py`, which runs
`CodexConfigWindow` from source. The thing that ships is `dist/CodexConfigTool-Qt.exe`. Those are not
interchangeable, and the difference is not cosmetic: a packaged launch was measured with **two native
child windows** on the main window - a 38px title strip and the 462px content area, both
`Qt6112QWindowIcon` - while the source window has none. The native-child count *is* the property the
probe exists to measure, so a packaged build with two of them would be exactly the regression the port
was supposed to eliminate, and no measurement in the document could have seen it.

`proto_restore_flash.py --framework qt-exe` closes that gap (`serve_qt_exe.py` launches the EXE, finds
its window, and reports it). Result, five cycles:

| build | native descendants | blank frames |
|---|---|---|
| source (`qt-app`) | 0 | 0 |
| **packaged (`qt-exe`)** | **0** | **0** |

So the shipped artifact does hold the property. But the two children were real, and the reason matters:
they appear when the app starts with the **onboarding dialog** up. Pre-seeding `hide_onboarding` in the
scratch `%APPDATA%` removes them. Dismissing the dialog afterwards does *not* - the handles are created
and stay for the life of the process. A window's native-child count is therefore a function of its
startup state, not a constant of the build, and a probe that measures one configuration has measured
one configuration. `probe_native_children.py` prints every top-level window the app owns with its
class, rect, style and children, which is how this was pinned down.

`verify_packaged_launch.py` covers the part of the packaged acceptance run that needs no input:
launch, class, 820x500 client, zero frame, zero native children, taskbar styles, and that the real
`settings.json` was never touched. It exists because `accept_packaged_exe.py` refuses to run at all
when the desktop will not accept synthetic input - correctly, but that check comes first, so a locked
session blocks even the checks that need no input. **It is not an acceptance run**: it injects no
input, so nothing about clicks or typing is covered.
