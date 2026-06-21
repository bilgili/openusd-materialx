"""Bootstrap a bundled OpenUSD install with usdMtlx MaterialX support.

Usage:

    import openusd_materialx
    from pxr import Usd

Set OPENUSD_MATERIALX_AUTO_BOOTSTRAP=0 before import to disable automatic bootstrap.
"""

from __future__ import annotations

import os

from .bootstrap import BundleInfo, get_bundle_info, prepare, validate

__all__ = ["BundleInfo", "get_bundle_info", "prepare", "validate"]

if os.environ.get("OPENUSD_MATERIALX_AUTO_BOOTSTRAP", "1") not in {"0", "false", "False"}:
    prepare()
