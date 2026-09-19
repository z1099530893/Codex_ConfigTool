"""Line the child-window message log up against the blank frames.

The toplevel's own message stream is identical whether or not a restore flashes,
so the difference has to be in a child.  ``instrumented_app.py --variant msgspy``
subclasses the window procedure of the child that covers the probe patch and logs
its messages with an absolute epoch; ``verify_restore_flash.py`` records the
absolute epoch of each restore and the offset of every bad frame.

Both processes run on one machine, so the two epochs are on the same clock and can
simply be subtracted.  This script does that and prints, for each run, the messages
that arrived inside the flash window - so a blank can be attributed to a message
instead of guessed at.

Usage:
    python align_message_spy.py [--report out/restore-flash-report.json]
                               [--log out/message-spy-wrapper.log]
                               [--window -20,150]
"""

from __future__ import annotations

import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load_messages(path: str) -> list[tuple[float, str, str, str]]:
    """Read ``<epoch> <name> <wparam> <lparam>`` lines, skipping the header."""
    messages: list[tuple[float, str, str, str]] = []
    if not os.path.exists(path):
        return messages
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 3)
            if len(parts) < 4:
                continue
            try:
                epoch = float(parts[0])
            except ValueError:
                continue
            messages.append((epoch, parts[1], parts[2], parts[3]))
    messages.sort(key=lambda row: row[0])
    return messages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=os.path.join(HERE, "out", "restore-flash-report.json"))
    parser.add_argument("--log", default=os.path.join(HERE, "out", "message-spy-wrapper.log"))
    parser.add_argument(
        "--window",
        default="-20,150",
        help="milliseconds before/after the restore epoch to print",
    )
    parser.add_argument(
        "--only-blank",
        action="store_true",
        help="print only runs whose worst frame erased the probe's content",
    )
    args = parser.parse_args()

    if not os.path.exists(args.report):
        print(f"no report at {args.report}")
        return 2
    with open(args.report, "r", encoding="utf-8") as handle:
        report = json.load(handle)

    before, after = (float(value) for value in args.window.split(","))
    messages = load_messages(args.log)
    print(f"# {len(messages)} message(s) in {os.path.basename(args.log)}")

    runs = report.get("runs") or []
    blanks = 0
    for run in runs:
        epoch = run.get("restore_epoch")
        if epoch is None:
            continue
        erasing = run.get("content_erase_frames", 0)
        if args.only_blank and not erasing:
            continue
        if erasing:
            blanks += 1
        # Every frame the harness scored, so the message timeline can be read
        # against the same instants the detector used.
        bad = [
            frame
            for frame in (run.get("timeline") or [])
            if (frame.get("content_erased") or 0.0) > 0.30
        ]
        label = "BLANK" if bad else "clean"
        print(f"\n=== run{run.get('run')}  ({label})  erased={run.get('worst_content_erased')} ===")
        for frame in bad:
            print(
                f"   >>> BLANK at +{frame.get('t_ms')}ms  "
                f"erased={frame.get('content_erased')} exact_bg={frame.get('exact_bg')}"
            )
        inside = [
            row
            for row in messages
            if -before / 1000.0 <= row[0] - epoch <= after / 1000.0
        ]
        if not inside:
            print("   (no messages in the window)")
        for stamp, name, wparam, lparam in inside:
            offset = (stamp - epoch) * 1000.0
            print(f"   +{offset:7.1f}ms  {name:<22} wparam={wparam}")

    print(f"\n# runs with a blank frame: {blanks}/{len(runs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
