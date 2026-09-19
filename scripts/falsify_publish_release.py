"""Falsify the new publish_release tests: undo the fixes, confirm the tests go red.

An instrument that has never been shown to fail is not yet evidence. This script
re-introduces, one at a time, the three defects the new tests are supposed to catch,
runs only those tests against the mutated copy, and restores the file afterwards.

Writes nothing permanent: the original **bytes** are held in memory and restored in a
``finally`` block. Bytes, not text, on purpose - an earlier version round-tripped through
``read_text``/``write_text``, which silently rewrote every LF in the file as CRLF and so
left the file changed while the script still announced a clean restore.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "publish_release.py"
PYTHON = sys.executable

MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "preflight: the blank list entry that made every check fail",
        '    if problems:\n        joined = "\\n  ".join(problems)\n',
        '    problems.append("")\n    if problems:\n        joined = "\\n  ".join(problems)\n',
        "test_preflight_accepts_a_complete_tree",
    ),
    (
        "resolve_token: stop skipping the helper-selector git",
        '        if "helper-selector" in credential_helper(candidate):\n'
        "            skipped.append(candidate)\n"
        "            continue\n",
        "",
        "test_token_resolution_never_invokes_a_helper_selector_git",
    ),
    (
        "publish: stop verifying before flipping the draft public",
        "    if cmd_verify(ctx) != 0:\n",
        "    if False:\n",
        "test_publish_refuses_when_verification_fails",
    ),
]


def run_tests(pattern: str) -> tuple[int, str]:
    result = subprocess.run(
        [PYTHON, "-m", "unittest", "discover", "-s", "tests", "-p", "test_publish_release.py", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


def main() -> int:
    original_bytes = TARGET.read_bytes()
    original = original_bytes.decode("utf-8")
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    print(f"original sha256 = {original_hash}  ({len(original_bytes)} bytes)")
    print()

    baseline_code, baseline_out = run_tests("test_publish_release.py")
    print(f"[baseline] exit={baseline_code} (expected 0)")
    if baseline_code != 0:
        print(baseline_out)
        return 1
    print()

    failures: list[str] = []
    restore_ok = False
    try:
        for label, old, new, expected_test in MUTATIONS:
            if old not in original:
                print(f"[SKIP] {label}: anchor text not found, the test may be stale")
                failures.append(label)
                continue
            mutated = original.replace(old, new, 1)
            TARGET.write_bytes(mutated.encode("utf-8"))
            code, out = run_tests("test_publish_release.py")
            caught = expected_test in out and ("FAIL" in out or "ERROR" in out)
            status = "RED as expected" if code != 0 and caught else "NOT CAUGHT - the test is worthless"
            print(f"[{status}] {label}")
            print(f"           expected the failure to land on: {expected_test}")
            if code == 0 or not caught:
                failures.append(label)
            for line in out.splitlines():
                if line.startswith(("FAIL:", "ERROR:")):
                    print(f"           -> {line}")
            print()
    finally:
        TARGET.write_bytes(original_bytes)
        restored = hashlib.sha256(TARGET.read_bytes()).hexdigest()
        restore_ok = restored == original_hash
        print(f"restored sha256 = {restored}")
        print(f"restore verified: {restore_ok}")

    code, _ = run_tests("test_publish_release.py")
    print(f"\n[after restore] exit={code} (expected 0)")

    # The restore check is part of the verdict, not a note beside it. Announcing success
    # while this was False is exactly the failure this whole script exists to prevent.
    if failures or code != 0 or not restore_ok:
        print("\nRESULT: falsification incomplete")
        for item in failures:
            print("  -", item)
        if not restore_ok:
            print("  - the file was NOT restored to its original bytes")
        if code != 0:
            print("  - the test suite is not green after the restore")
        return 1
    print("\nRESULT: every mutation was caught, and the file is back to its original bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
