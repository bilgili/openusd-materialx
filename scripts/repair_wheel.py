#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.check_call(cmd)


def repair_one(wheel: Path, out_dir: Path) -> None:
    if sys.platform.startswith("linux"):
        if not shutil.which("auditwheel"):
            raise SystemExit("auditwheel not found. Install with: python -m pip install auditwheel")
        run(["auditwheel", "repair", str(wheel), "-w", str(out_dir)])
    elif sys.platform == "darwin":
        if not shutil.which("delocate-wheel"):
            raise SystemExit("delocate-wheel not found. Install with: python -m pip install delocate")
        run(["delocate-wheel", "-w", str(out_dir), "-v", str(wheel)])
    elif sys.platform == "win32":
        if not shutil.which("delvewheel"):
            raise SystemExit("delvewheel not found. Install with: python -m pip install delvewheel")
        run(["delvewheel", "repair", str(wheel), "-w", str(out_dir)])
    else:
        raise SystemExit(f"Unsupported platform: {sys.platform}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair one or more binary wheels using the platform's standard wheel repair tool"
    )
    # nargs="+" so a glob like wheelhouse/raw/openusd/*.whl that expands to several
    # wheels (e.g. a stale and a fresh build) is handled instead of erroring with
    # "unrecognized arguments".
    parser.add_argument("wheels", type=Path, nargs="+", metavar="wheel")
    parser.add_argument("--out-dir", type=Path, default=Path("wheelhouse"))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    for wheel in args.wheels:
        if not wheel.is_file():
            raise SystemExit(f"Wheel not found: {wheel}")
        repair_one(wheel, args.out_dir)


if __name__ == "__main__":
    main()
