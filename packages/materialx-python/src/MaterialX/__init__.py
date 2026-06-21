"""Shim that exposes the bundled ASWF MaterialX Python package as `MaterialX`."""
from __future__ import annotations

from pathlib import Path

from materialx_python.bootstrap import find_real_materialx_init, prepare

prepare()
_real_init = find_real_materialx_init()
if _real_init is None:
    raise ImportError(
        "Bundled MaterialX package was not found. Build the bundle first with "
        "scripts/build_materialx_python_bundle.py."
    )

# Make extension submodules and resources resolve from the real package directory.
__file__ = str(_real_init)
__path__ = [str(_real_init.parent), *list(globals().get("__path__", []))]
__package__ = "MaterialX"

_code = compile(Path(_real_init).read_text(encoding="utf-8"), str(_real_init), "exec")
exec(_code, globals(), globals())
