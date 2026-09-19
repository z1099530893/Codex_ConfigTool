"""Explain a restore-flash report: where the bad frames are and what they look like.

Reads ``out/restore-flash-report.json`` and, for every offending frame, prints the
frames around it together with the window rect and the class of whatever is on top
at the window's centre.  That combination separates the two ways a frame can be
wrong:

* rect unchanged and the app is on top -> the app painted a blank body
  (a repaint race, fixable in the app),
* rect unchanged but the background window shows through -> the frame was captured
  mid-transition, i.e. a compositor artefact rather than an app defect.

Usage:
    python explain_flash_report.py [path]
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "out", "restore-flash-report.json")
THRESHOLD = 0.02
CONTEXT = 3


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    with open(path, encoding="utf-8") as handle:
        report = json.load(handle)

    reference = report.get("reference") or {}
    print(f"exe {report.get('exe')}")
    print(
        "reference  body_diff={body_diff} bg={bg_fraction} mean={mean}".format(**reference)
        if reference
        else "reference  (not recorded)"
    )

    total_runs = len(report["runs"])
    flashing = [r for r in report["runs"] if r["frames_over_threshold"]]
    print(f"runs {total_runs}, flashing {len(flashing)}, failures {len(report['failures'])}")
    print()

    for entry in report["runs"]:
        timeline = entry.get("timeline") or []
        bad = [i for i, f in enumerate(timeline) if f["body_diff"] > THRESHOLD]
        head = (
            f"run {entry['run']:>2} via={entry['restore_via']:<18} "
            f"frames={entry['frames']:>3} bad={len(bad):>2} "
            f"first={entry['first_frame_ms']}ms "
            f"rects={entry.get('distinct_rects')} "
            f"dwm_mismatch={entry.get('dwm_mismatch_frames')}"
        )
        if not bad:
            print(head + "  clean")
            continue
        print(head)
        for index in bad:
            lo, hi = max(0, index - CONTEXT), min(len(timeline), index + CONTEXT + 1)
            print(f"   worst frame #{index}")
            for position in range(lo, hi):
                frame = timeline[position]
                marker = "  <<<" if position == index else ""
                print(
                    "     t={t_ms:>7}ms diff={body_diff:<6} bg={bg_fraction:<6} "
                    "mean={mean:<7} rect={rect} dwm={dwm} top={top_class}{marker}".format(
                        dwm=frame.get("dwm"), marker=marker, **frame
                    )
                )
        print()

    if report["failures"]:
        print("failures:")
        for failure in report["failures"]:
            print("  - " + failure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
