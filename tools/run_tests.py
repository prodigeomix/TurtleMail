#!/usr/bin/env python3
"""
tools/run_tests.py
==================
Unified verification runner for TurtleMail.
Executes all static audit gates:
  1. Strict Lua 5.0 and WoW 1.12 syntax & API constraints.
  2. AST scope and global leak detection.
"""

import os
import subprocess
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

CHECKS = [
    ("Lua 5.0 Compliance (validate_lua50.py)", ["python", os.path.join(SCRIPT_DIR, "validate_lua50.py")]),
    ("Global Scope Leaks (scan_global_leaks.py)", ["python", os.path.join(SCRIPT_DIR, "scan_global_leaks.py")]),
]

def run_suite():
    print("=" * 80)
    print("TURTLEMAIL AUTOMATED VERIFICATION SUITE")
    print("=" * 80)
    print()

    suite_start = time.time()
    results = []

    for name, cmd in CHECKS:
        print(f">>> Running {name}...")
        start = time.time()
        proc = subprocess.run(cmd, cwd=ADDON_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        elapsed = time.time() - start

        # Indent output for readable hierarchy
        for line in proc.stdout.splitlines():
            if line.strip():
                print(f"    {line}")
        if proc.stderr:
            for line in proc.stderr.splitlines():
                if line.strip():
                    print(f"    [STDERR] {line}")

        passed = (proc.returncode == 0)
        results.append((name, passed, elapsed))
        status_tag = "[PASS]" if passed else "[FAIL]"
        print(f"    --> {status_tag} ({elapsed:.2f}s)")
        print()

    total_time = time.time() - suite_start
    print("=" * 80)
    print("SUITE EXECUTION SUMMARY")
    print("=" * 80)

    all_passed = True
    for name, passed, elapsed in results:
        tag = "[PASS]" if passed else "[FAIL]"
        if not passed:
            all_passed = False
        print(f"  {tag:<8} {name:<45} ({elapsed:.2f}s)")

    print("-" * 80)
    passed_count = sum(1 for _, p, _ in results if p)
    total_count = len(results)
    verdict = "ALL" if all_passed else f"{passed_count}/{total_count}"
    print(f"OVERALL RESULT: {verdict} CHECKS PASSED (Total time: {total_time:.2f}s)")
    print("=" * 80)

    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    run_suite()
