#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import openusd_materialx  # noqa: E402


def _macho_python_offenders(usd_root: Path, binaries: list[Path]) -> list[str]:
    otool = shutil.which("otool")
    if not otool:
        print("WARNING: otool not found; skipping macOS Python-portability check.")
        return []
    # Any dylib that links the Python framework or libpython by absolute path is non-portable.
    bad_dep = re.compile(r"/.*Python\.framework/.*/Python|/.*libpython[0-9.]*\.dylib")
    offenders: list[str] = []
    for f in binaries:
        try:
            deps = subprocess.check_output([otool, "-L", str(f)], text=True, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            continue
        for line in deps.splitlines()[1:]:
            dep = line.strip().split(" ", 1)[0]
            if dep.startswith("/") and bad_dep.search(dep):
                offenders.append(f"{f.relative_to(usd_root)} -> {dep}")
                break
    return offenders


def _elf_python_offenders(usd_root: Path, binaries: list[Path]) -> list[str]:
    # Prefer patchelf (prints just sonames); fall back to readelf -d.
    patchelf = shutil.which("patchelf")
    readelf = shutil.which("readelf")
    if not patchelf and not readelf:
        print("WARNING: neither patchelf nor readelf found; skipping Linux Python-portability check.")
        return []
    bad_dep = re.compile(r"libpython[0-9.]*\.so")
    offenders: list[str] = []
    for f in binaries:
        needed = ""
        try:
            if patchelf:
                needed = subprocess.check_output([patchelf, "--print-needed", str(f)], text=True, stderr=subprocess.DEVNULL)
            else:
                needed = subprocess.check_output([readelf, "-d", str(f)], text=True, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            continue
        for line in needed.splitlines():
            if bad_dep.search(line):
                # readelf line: "0x... (NEEDED) Shared library: [libpython3.13.so.1.0]"
                m = re.search(r"libpython[0-9.]*\.so[0-9.]*", line)
                offenders.append(f"{f.relative_to(usd_root)} -> {m.group(0) if m else line.strip()}")
                break
    return offenders


def check_python_portability(usd_root: Path) -> list[str]:
    """Return bundled binaries that hardcode a Python dependency (non-portable wheel).

    OpenUSD must be built with PXR_PY_UNDEFINED_DYNAMIC_LOOKUP=ON so the pxr binaries do
    NOT link a specific libpython. Otherwise the build interpreter's library is baked in
    and the wheel only imports on that exact Python, failing on a different CPython with:
      * macOS: "Library not loaded: .../Python.framework/.../Python"
      * Linux: "libpython3.x.so: cannot open shared object file"
    This guard catches a regression of that build flag before the wheel ships. Windows is
    intentionally NOT checked: extension modules MUST link pythonXX.lib there and the wheel
    is per-minor-version by design (python3XX.dll resolves from the host interpreter).
    """
    binaries = [f for f in usd_root.rglob("*") if f.suffix in {".so", ".dylib"} and f.is_file()]
    if sys.platform == "darwin":
        return _macho_python_offenders(usd_root, binaries)
    if sys.platform.startswith("linux"):
        return _elf_python_offenders(usd_root, binaries)
    return []


result = openusd_materialx.validate(verbose=True)
print(json.dumps(result, indent=2, sort_keys=True))

if not result.get("pxr_import"):
    raise SystemExit(1)

usd_root = Path(openusd_materialx.get_bundle_info().usd_root)
offenders = check_python_portability(usd_root)
if offenders:
    print(
        "ERROR: bundled binaries hardcode an absolute Python dependency (wheel is not "
        "Python-portable). Rebuild with -DPXR_PY_UNDEFINED_DYNAMIC_LOOKUP=ON. Offenders:"
    )
    for line in offenders[:20]:
        print("  ", line)
    if len(offenders) > 20:
        print(f"   ... and {len(offenders) - 20} more")
    raise SystemExit(3)

# Be lenient: some builds expose usdMtlx as descriptors but not as pxr.UsdMtlx.
if not result.get("usdmtlx_descriptors") and not result.get("usdmtlx_module_import"):
    print("WARNING: usdMtlx was not clearly found. Check OpenUSD build flags and bundled plugin layout.")
    raise SystemExit(2)
