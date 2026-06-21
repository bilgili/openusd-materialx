#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import openusd_materialx  # noqa: E402

result = openusd_materialx.validate(verbose=True)
print(json.dumps(result, indent=2, sort_keys=True))

if not result.get("pxr_import"):
    raise SystemExit(1)

# Be lenient: some builds expose usdMtlx as descriptors but not as pxr.UsdMtlx.
if not result.get("usdmtlx_descriptors") and not result.get("usdmtlx_module_import"):
    print("WARNING: usdMtlx was not clearly found. Check OpenUSD build flags and bundled plugin layout.")
    raise SystemExit(2)
