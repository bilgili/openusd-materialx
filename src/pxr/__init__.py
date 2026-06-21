"""Shim that exposes the bundled OpenUSD `pxr` package as top-level `pxr`.

The bundled OpenUSD install lives under ``openusd_materialx/_usd/lib/python/pxr``
rather than directly on ``sys.path``. Importing :mod:`openusd_materialx` runs
``prepare()``, which prepends that directory to ``sys.path`` (and sets the USD
plugin / MaterialX search-path env vars). This shim makes ``from pxr import Usd``
"just work" without the caller having to ``import openusd_materialx`` first —
mirroring the sibling ``MaterialX`` shim shipped by materialx-python-standalone.
"""
from __future__ import annotations

from pathlib import Path

import openusd_materialx

# Prepend the bundled pxr directory to sys.path and register USD plugins.
openusd_materialx.prepare()


def _find_real_pxr_init() -> Path | None:
    for python_path in openusd_materialx.get_bundle_info().python_paths:
        candidate = Path(python_path) / "pxr" / "__init__.py"
        if candidate.is_file():
            return candidate
    return None


_real_init = _find_real_pxr_init()
if _real_init is None:
    raise ImportError(
        "Bundled OpenUSD `pxr` package was not found. The openusd-materialx wheel is "
        "missing its _usd/lib/python/pxr tree; rebuild it with "
        "scripts/build_openusd_bundle.py."
    )

# Become the real pxr package: resolve submodules (pxr.Usd, pxr.Sdf, ...) and
# package resources from the bundled directory, then execute the real __init__
# body into this module's namespace.
__file__ = str(_real_init)
__path__ = [str(_real_init.parent), *list(globals().get("__path__", []))]
__package__ = "pxr"

_code = compile(Path(_real_init).read_text(encoding="utf-8"), str(_real_init), "exec")
exec(_code, globals(), globals())
