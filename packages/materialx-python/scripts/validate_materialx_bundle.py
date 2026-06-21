#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
SRC = PKG_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import materialx_python  # noqa: E402

# 1. Structural validation: bundle layout and path discovery.
result = materialx_python.validate(verbose=True)
print(json.dumps(result, indent=2, sort_keys=True))
if not result.get("materialx_import"):
    raise SystemExit(1)

# 2. Shim validation in a clean subprocess.
#
# validate() above calls prepare(), which prepends the bundled real MaterialX
# package to sys.path *before* `import MaterialX`. That shadows the shim, so the
# in-process check never exercises shim code. A pip-installed wheel always imports
# through the shim, so a shim bug (e.g. a broken find_real_materialx_init) passes
# the in-process check yet fails for real users. Test the shim explicitly: a fresh
# interpreter whose only path entry is SRC, with no prior prepare() call, so
# `import MaterialX` resolves to the shim exactly like an installed wheel.
print("\n=== shim import check (subprocess) ===")
code = (
    "import MaterialX as mx; "
    "v = mx.getVersionString(); "
    "print('shim import OK, version', v); "
    "assert mx.createDocument() is not None, 'createDocument() returned None'"
)
env = {**os.environ, "PYTHONPATH": str(SRC)}
proc = subprocess.run(
    [sys.executable, "-c", code],
    cwd=str(PKG_ROOT),  # neutral cwd: no top-level MaterialX/ here to shadow the shim
    env=env,
    capture_output=True,
    text=True,
)
sys.stdout.write(proc.stdout)
if proc.stderr:
    sys.stderr.write(proc.stderr)
if proc.returncode != 0:
    raise SystemExit(
        "Shim import failed: the MaterialX shim could not load the bundled package. "
        "This is the code path a pip-installed wheel uses."
    )
