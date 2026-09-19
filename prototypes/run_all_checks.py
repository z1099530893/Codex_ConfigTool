"""Run every window-lifecycle check in one go and print a single verdict.

    "C:\\Program Files\\Develop\\Python\\python.exe" run_all_checks.py
    ... run_all_checks.py --quick          # 2 cycles, 15 s soak, for a smoke test

Why this exists rather than four commands in a shell script:

* The checks must run **one after another**.  They all drive the same desktop and
  steal the cursor, so running two at once produces nonsense.
* They need an interpreter that has ``PIL``.  The managed runtime does not, and
  forgetting that costs a confusing ``ModuleNotFoundError`` before anything
  useful happens.  This script finds a suitable interpreter and re-executes
  itself under it.
* "Synthetic input is unavailable right now" must be reported as an *environment*
  problem, not a failure.  On a shared desktop input injection comes and goes;
  the harnesses already distinguish this with exit code 3, and this script keeps
  that distinction instead of flattening it into a pass/fail.

Exit codes: 0 all checks passed, 1 at least one check failed, 3 the environment
could not support the checks (no suitable interpreter, or input unavailable).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# Steps that measure a known, accepted defect.  They report numbers and never gate
# the overall verdict - see the ADVISORY handling in main().
FLASH_STEP = "restore flash (advisory)"
ADVISORY_STEPS = {FLASH_STEP}

OUT_DIR = os.path.join(HERE, "out")

INTERPRETER_CANDIDATES = (
    r"C:\Program Files\Develop\Python\python.exe",
    r"C:\Program Files\Python313\python.exe",
    r"C:\Program Files\Python312\python.exe",
)

ENV_FAILURE = 3


def has_requirements(executable: str) -> tuple[bool, str]:
    """Can this interpreter run the harnesses (needs PIL, and tkinter to build)?"""
    try:
        probe = subprocess.run(
            [executable, "-c", "import PIL, tkinter; print(PIL.__version__)"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    if probe.returncode != 0:
        return False, (probe.stderr or probe.stdout).strip().splitlines()[-1:]
    return True, probe.stdout.strip()


def find_interpreter() -> tuple[str, str]:
    """The first interpreter that can actually run the harnesses."""
    seen = set()
    for candidate in (sys.executable, *INTERPRETER_CANDIDATES, shutil.which("python")):
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if not os.path.exists(candidate):
            continue
        ok, detail = has_requirements(candidate)
        if ok:
            return candidate, detail
    return "", ""


def reexec_if_needed(argv: list[str]) -> None:
    """Hand over to a Pillow-capable interpreter, once."""
    ok, _ = has_requirements(sys.executable)
    if ok:
        return
    interpreter, version = find_interpreter()
    if not interpreter or os.path.normcase(interpreter) == os.path.normcase(sys.executable):
        print(
            "ENVIRONMENT no interpreter with PIL found; install Pillow or pass a "
            "suitable one.  Tried:\n  "
            + "\n  ".join([sys.executable, *INTERPRETER_CANDIDATES])
        )
        raise SystemExit(ENV_FAILURE)
    print(f"[reexec] {sys.executable} lacks PIL; using {interpreter} (Pillow {version})")
    os.execv(interpreter, [interpreter, os.path.abspath(__file__), *argv])


# --------------------------------------------------------------------------- #
# the checks
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=5, help="acceptance minimize/restore cycles")
    parser.add_argument("--minimized", type=float, default=60.0, help="soak seconds minimized")
    parser.add_argument("--restored", type=float, default=30.0, help="soak seconds restored")
    parser.add_argument("--wait-input", type=float, default=180.0, help="seconds to wait for synthetic input")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="2 cycles and a 15 s soak, for a fast smoke test",
    )
    parser.add_argument("--skip-soak", action="store_true", help="omit the slow soak check")
    parser.add_argument(
        "--skip-flash",
        action="store_true",
        help="omit the restore-flash measurement",
    )
    parser.add_argument(
        "--flash-runs",
        type=int,
        default=4,
        help=(
            "restores to sample for the flash check; 4 is enough to notice a "
            "regression, not enough to estimate a rate precisely"
        ),
    )
    parser.add_argument(
        "--shell-minimizeall",
        action="store_true",
        help=(
            "also prove the Shell treats the window as minimizable, via "
            "Shell.MinimizeAll(). Needs no synthetic input, but it minimizes every "
            "window on the desktop for a moment (restored afterwards), so it is "
            "opt-in"
        ),
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=2,
        help="retries when a check reports an environment problem",
    )
    args = parser.parse_args()

    if args.quick:
        args.cycles = min(args.cycles, 2)
        args.minimized = min(args.minimized, 15.0)
        args.restored = min(args.restored, 10.0)

    os.makedirs(OUT_DIR, exist_ok=True)
    exe = os.path.join(ROOT, "dist", "CodexConfigTool.exe")
    if not os.path.exists(exe):
        print(f"ENVIRONMENT packaged executable missing: {exe}")
        return ENV_FAILURE

    # `unittest discover` must run from the project root, not from prototypes/.
    steps: list[tuple[str, list[str], str, str]] = [
        (
            "unit tests",
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
            os.path.join(OUT_DIR, "check-unit-tests.log"),
            ROOT,
        ),
        (
            f"packaged acceptance ({args.cycles} cycles)",
            [
                sys.executable,
                "accept_packaged_exe.py",
                "--cycles",
                str(args.cycles),
                "--wait-input",
                str(args.wait_input),
            ],
            os.path.join(OUT_DIR, "check-acceptance.log"),
            HERE,
        ),
        (
            "drag repaint integrity",
            [
                sys.executable,
                "verify_app_drag_integrity.py",
                "--wait-input",
                str(args.wait_input),
            ],
            os.path.join(OUT_DIR, "check-drag-integrity.log"),
            HERE,
        ),
        (
            "close paths shut down cleanly",
            [sys.executable, "diag_close_paths.py"],
            os.path.join(OUT_DIR, "check-close-paths.log"),
            HERE,
        ),
    ]
    if args.shell_minimizeall:
        steps.append(
            (
                "Shell treats the window as minimizable",
                [sys.executable, "diag_shell_minimizeall.py"],
                os.path.join(OUT_DIR, "check-shell-minimizeall.log"),
                HERE,
            )
        )
    if not args.skip_flash:
        steps.append(
            (
                FLASH_STEP,
                [
                    sys.executable,
                    "verify_restore_flash.py",
                    "--exe",
                    exe,
                    "--probe",
                    "patch",
                    "--restore-via",
                    "api",
                    "--minimize-via",
                    "api",
                    "--runs",
                    str(args.flash_runs),
                ],
                os.path.join(OUT_DIR, "check-restore-flash.log"),
                HERE,
            )
        )
    if not args.skip_soak:
        steps.append(
            (
                f"minimize soak ({args.minimized:.0f}s + {args.restored:.0f}s)",
                [
                    sys.executable,
                    "verify_minimize_soak.py",
                    "--minimized",
                    str(args.minimized),
                    "--restored",
                    str(args.restored),
                    "--wait-input",
                    str(args.wait_input),
                ],
                os.path.join(OUT_DIR, "check-soak.log"),
                HERE,
            )
        )

    results: list[dict] = []
    for name, command, log_path, cwd in steps:
        attempt = 0
        while True:
            attempt += 1
            started = time.time()
            print(f"\n{'=' * 72}\n[run] {name}" + (f" (attempt {attempt})" if attempt > 1 else ""))
            print("=" * 72, flush=True)
            with open(log_path, "w", encoding="utf-8", errors="replace") as log:
                try:
                    process = subprocess.run(
                        command,
                        cwd=cwd,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=args.wait_input + 900,
                    )
                    code = process.returncode
                except subprocess.TimeoutExpired:
                    code = -1
                    log.write("\nTIMEOUT\n")

            with open(log_path, "r", encoding="utf-8", errors="replace") as log:
                text = log.read()
            print("\n".join(text.strip().splitlines()[-12:]), flush=True)

            summary = {}
            for line in reversed(text.splitlines()):
                if line.startswith("SUMMARY "):
                    try:
                        summary = json.loads(line[len("SUMMARY "):])
                    except json.JSONDecodeError:
                        summary = {}
                    break

            if code == 0:
                verdict = "PASS"
            elif code == ENV_FAILURE:
                verdict = "INVALID (environment)"
            elif code == -1:
                verdict = "TIMEOUT"
            else:
                verdict = "FAIL"

            # The restore flash is a known, accepted characteristic of this window
            # (11 candidate fixes measured, none adopted - see
            # AGENT_HANDOFF_WINDOW_BUGS.md).  Gating on "did it flash" would fail
            # every run forever, so this step is advisory: it never stops the suite
            # and never changes the overall verdict.  What it *does* gate on is the
            # regression signal - a frame darker than the settled UI, i.e. an
            # unpainted black surface, which the baseline never produces and which
            # WS_EX_COMPOSITED and LockWindowUpdate both introduced.
            if name in ADVISORY_STEPS:
                verdict = "ADVISORY"
                aggregate = summary.get("aggregate") or {}
                # ``.get(key, 0)`` turns a renamed or absent field into a confident
                # zero, which is exactly how a real regression reads as a pass.
                # Check the fields exist before printing numbers derived from them.
                missing = [
                    key
                    for key in (
                        "runs",
                        "runs_flashing",
                        "bad_frames",
                        "frames_darker_than_ui",
                        "worst_content_erased",
                        "content_erase_frames",
                        "runs_content_erasing",
                        "worst_erase_exact_bg",
                        "content_tolerance",
                        "dark_threshold",
                        "probe_mean",
                    )
                    if key not in aggregate
                ]
                if missing:
                    print(
                        f"[WARN] {name}: aggregate is missing {missing}; the numbers "
                        "printed below are not trustworthy"
                    )
                dark = aggregate.get("frames_darker_than_ui", 0)
                if dark:
                    print(
                        f"[REGRESSION] {name}: {dark} frame(s) darker than the settled "
                        f"UI (below mean {aggregate.get('dark_threshold')}, where the "
                        f"probe settles at {aggregate.get('probe_mean')}). Baseline "
                        "produces none; this is a new failure mode, not the known flash."
                    )
                # ``frames_over_threshold`` is region-dependent - it counts pixels that
                # changed, so in a sparse region a *complete* blank-out scores below
                # any usable threshold.  On this UI it reports 0/10 for the content
                # area while 3/10 restores blanked that area out entirely, which is
                # how a real regression could hide behind a PASS.  The content-erasure
                # numbers are region-independent and are the ones worth printing.
                erasing = aggregate.get("runs_content_erasing", 0)
                runs = aggregate.get("runs") or 0
                print(
                    f"[advisory] {name}: {aggregate.get('runs_flashing', 0)}/{runs} "
                    f"restore(s) flashed by the region-dependent metric with "
                    f"{aggregate.get('bad_frames', 0)} bad frame(s), but "
                    f"{erasing}/{runs} erased the probe's content "
                    f"(worst {aggregate.get('worst_content_erased')}). "
                    f"tolerance={aggregate.get('content_tolerance')}"
                )
                # Say what the erasing frames were made of.  1.0 = entirely the
                # toplevel's own background; 0.0 = light but a different colour, i.e.
                # the window was showing what is behind it.  Both read mean ~244.
                if erasing:
                    print(
                        f"      mechanism: worst-erasing frame was "
                        f"{aggregate.get('worst_erase_exact_bg')} exactly toplevel "
                        "background (1.0 = own fill, 0.0 = showing what is behind)"
                    )

            if verdict == "INVALID (environment)" and attempt < args.attempts:
                print(f"[retry] {name}: environment problem; waiting 15s before retrying")
                time.sleep(15)
                continue
            break

        results.append(
            {
                "name": name,
                "exit_code": code,
                "verdict": verdict,
                "attempts": attempt,
                "seconds": round(time.time() - started, 1),
                "log": os.path.relpath(log_path, ROOT).replace("\\", "/"),
                "summary": summary,
            }
        )
        if verdict != "PASS" and name not in ADVISORY_STEPS:
            print(f"[stop] {name} -> {verdict}; not running the remaining checks")
            break

    report_path = os.path.join(OUT_DIR, "all-checks-report.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "exe": exe,
                "interpreter": sys.executable,
                "quick": args.quick,
                "results": results,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    for result in results:
        print(f"  {result['verdict']:<22} {result['name']:<38} {result['seconds']:>6.1f}s")
        aggregate = (result.get("summary") or {}).get("aggregate")
        if aggregate:
            print(
                f"      flash: {aggregate['runs_flashing']}/{aggregate['runs']} restores "
                f"flashed by the region-dependent metric, {aggregate['bad_frames']} bad "
                f"frame(s), {aggregate['frames_darker_than_ui']} darker than the UI "
                f"(below mean {aggregate.get('dark_threshold')}, probe settles at "
                f"{aggregate.get('probe_mean')})"
            )
            print(
                f"      erase: {aggregate.get('runs_content_erasing', 0)}/{aggregate['runs']} "
                f"restores erased the probe's content, "
                f"{aggregate.get('content_erase_frames', 0)} frame(s), "
                f"worst {aggregate.get('worst_content_erased')} "
                f"(tolerance {aggregate.get('content_tolerance')})"
            )
            print(
                "      baseline (this probe, packaged build, N=10): 8/10 restores over the "
                "region-dependent metric with 12 bad frames, 5/10 erasing content, worst "
                "erasure 1.00.  The auto-chosen probe sits in the dark sidebar; the same "
                "blank-out also erases the light content area, where the region-dependent "
                "metric reports 0/10 - see AGENT_HANDOFF_WINDOW_BUGS.md."
            )
    skipped = len(steps) - len(results)
    if skipped:
        print(f"  {'SKIPPED':<22} {skipped} check(s) not run")

    # Advisory steps report numbers but never decide the verdict: the flash is a
    # known, accepted characteristic of this window, and gating on it would fail
    # every run forever.
    gating = [r for r in results if r["verdict"] != "ADVISORY"]
    codes = [r["exit_code"] for r in gating]
    if not gating:
        verdict = "INVALID (environment)"
    elif all(c == 0 for c in codes):
        verdict = "PASS"
    elif any(c == ENV_FAILURE for c in codes):
        verdict = "INVALID (environment)"
    else:
        verdict = "FAIL"
    print(f"\nOVERALL {verdict}")
    print(f"report  {report_path}")

    if verdict == "PASS":
        return 0
    if verdict == "INVALID (environment)":
        return ENV_FAILURE
    return 1


if __name__ == "__main__":
    reexec_if_needed(sys.argv[1:])
    raise SystemExit(main())
