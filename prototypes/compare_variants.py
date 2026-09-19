"""Compare flash-detector runs across variants, with a Fisher exact test.

Every variant log ends with one ``SUMMARY {...}`` line.  Counting "how many
restores blanked the probe's content" is the only metric that is comparable
across variants, because the region-dependent ``body_diff`` metric changes meaning
with the region it is applied to.

Usage:
    python compare_variants.py out/zone11-baseline-10.log out/zone11-layered-10.log ...
    python compare_variants.py --label base=out/a.log --label layered=out/b.log
"""

from __future__ import annotations

import argparse
import json
import os
from math import comb


def load_summary(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("SUMMARY "):
                return json.loads(line[len("SUMMARY ") :])
    return None


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for the 2x2 table [[a, b], [c, d]]."""
    n = a + b + c + d
    if n == 0:
        return 1.0
    row1, row2 = a + b, c + d
    col1 = a + c

    def prob(x: int) -> float:
        return (
            comb(row1, x) * comb(row2, col1 - x) / comb(n, col1)
            if 0 <= col1 - x <= row2
            else 0.0
        )

    observed = prob(a)
    total = 0.0
    for x in range(max(0, col1 - row2), min(row1, col1) + 1):
        p = prob(x)
        if p <= observed + 1e-12:
            total += p
    return min(1.0, total)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="*", help="log files; the label is the file name")
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        help="explicit name=path, repeatable",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="label to test every other variant against",
    )
    args = parser.parse_args()

    entries: list[tuple[str, str]] = []
    for spec in args.label:
        name, _, path = spec.partition("=")
        entries.append((name, path))
    for path in args.logs:
        entries.append((os.path.basename(path), path))

    rows = []
    for name, path in entries:
        summary = load_summary(path)
        if summary is None:
            print(f"[skip] {name}: no SUMMARY line in {path}")
            continue
        aggregate = summary.get("aggregate") or {}
        runs = aggregate.get("runs") or 0
        erasing = aggregate.get("runs_content_erasing", 0)
        rows.append(
            {
                "name": name,
                "runs": runs,
                "erasing": erasing,
                "clean": runs - erasing,
                "erase_frames": aggregate.get("content_erase_frames", 0),
                "worst": aggregate.get("worst_content_erased"),
                "worst_exact_bg": aggregate.get("worst_erase_exact_bg"),
                "flashing": aggregate.get("runs_flashing", 0),
                "bad_frames": aggregate.get("bad_frames", 0),
                "darker": aggregate.get("frames_darker_than_ui", 0),
                "cpu": aggregate.get("cpu_seconds_per_restore"),
            }
        )

    if not rows:
        print("nothing to compare")
        return 2

    width = max(len(row["name"]) for row in rows)
    print(
        f"{'variant':<{width}}  {'runs':>4}  {'erased':>6}  {'frames':>6}  "
        f"{'worst':>5}  {'exact_bg':>8}  {'flash':>5}  {'bad':>4}  {'dark':>4}  "
        f"{'cpu/restore':>11}"
    )
    for row in rows:
        cpu = f"{row['cpu']}" if row["cpu"] is not None else "-"
        print(
            f"{row['name']:<{width}}  {row['runs']:>4}  "
            f"{row['erasing']}/{row['runs']:<4}  {row['erase_frames']:>6}  "
            f"{row['worst']!s:>5}  {row['worst_exact_bg']!s:>8}  "
            f"{row['flashing']}/{row['runs']:<3}  {row['bad_frames']:>4}  "
            f"{row['darker']:>4}  {cpu:>11}"
        )

    if args.baseline:
        base = next((row for row in rows if row["name"] == args.baseline), None)
        if base is None:
            print(f"\nno row named {args.baseline!r}")
            return 2
        print(f"\n# Fisher exact vs {args.baseline} (restores that erased the probe)")
        for row in rows:
            if row is base:
                continue
            p = fisher_exact(
                row["erasing"], row["clean"], base["erasing"], base["clean"]
            )
            verdict = "significant" if p < 0.05 else "not significant"
            print(
                f"  {row['name']:<{width}}  {row['erasing']}/{row['runs']} vs "
                f"{base['erasing']}/{base['runs']}   p = {p:.3f}   ({verdict})"
            )
        pooled_erasing = sum(row["erasing"] for row in rows)
        pooled_runs = sum(row["runs"] for row in rows)
        print(f"\n# pooled over all listed variants: {pooled_erasing}/{pooled_runs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
