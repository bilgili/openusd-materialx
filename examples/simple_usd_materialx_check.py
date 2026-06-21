from __future__ import annotations

import openusd_materialx

openusd_materialx.prepare()

from pxr import Plug, Sdf, Usd  # noqa: E402

print("USD version:", Usd.GetVersion())
print("mtlx file format:", Sdf.FileFormat.FindByExtension("mtlx"))

registry = Plug.Registry()
plugins = registry.GetAllPlugins()
mtlx_plugins = [p for p in plugins if "mtlx" in p.name.lower() or "mtlx" in p.path.lower()]
print("MaterialX-ish USD plugins:")
for plugin in mtlx_plugins:
    print(" -", plugin.name, plugin.path)
