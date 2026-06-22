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
    # On Linux a DT_NEEDED on the bare libpython SONAME (libpython3.x.so.1.0) is portable:
    # it resolves from the already-loaded interpreter at import, exactly like PyPI usd-core,
    # and is required for the standalone USD executables (sdfdump, ...) to link at all. The
    # only non-portable case is an absolute RPATH/RUNPATH baked at build time that points
    # into a specific Python install, so check that instead of the SONAME dependency.
    patchelf = shutil.which("patchelf")
    if not patchelf:
        print("WARNING: patchelf not found; skipping Linux Python-portability check.")
        return []
    abs_python = re.compile(r"python", re.IGNORECASE)
    offenders: list[str] = []
    for f in binaries:
        try:
            rpath = subprocess.check_output(
                [patchelf, "--print-rpath", str(f)], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except subprocess.CalledProcessError:
            continue
        for entry in rpath.split(":"):
            if entry.startswith("/") and abs_python.search(entry):
                offenders.append(f"{f.relative_to(usd_root)} -> RPATH {entry}")
                break
    return offenders


def check_python_portability(usd_root: Path) -> list[str]:
    """Return bundled binaries that hardcode an *absolute* Python dependency (non-portable).

    A wheel is portable when the pxr binaries reference Python only by something that
    resolves from the loaded interpreter, not by a build-time absolute path:
      * macOS: built with PXR_PY_UNDEFINED_DYNAMIC_LOOKUP=ON (no Python.framework link);
        a residual absolute ``.../Python.framework/.../Python`` or ``/.../libpython*.dylib``
        is the failure ("Library not loaded" on a different CPython).
      * Linux: links libpython by bare SONAME (portable, like usd-core); only an absolute
        RPATH/RUNPATH into a specific Python install is non-portable.
    Windows is intentionally NOT checked: extension modules MUST link pythonXX.lib and the
    wheel is per-minor-version by design (python3XX.dll resolves from the host interpreter).
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
        "Python-portable). On macOS rebuild with -DPXR_PY_UNDEFINED_DYNAMIC_LOOKUP=ON; on "
        "Linux strip the absolute Python RPATH. Offenders:"
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
