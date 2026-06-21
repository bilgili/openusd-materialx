from __future__ import annotations

import dataclasses
import os
import platform
import sys
from pathlib import Path
from typing import Iterable

_BOOTSTRAPPED = False
_REGISTERED_PLUGIN_PATHS: list[Path] = []
_ADDED_DLL_DIRS: list[object] = []

PACKAGE_ROOT = Path(__file__).resolve().parent
USD_ROOT = PACKAGE_ROOT / "_usd"


@dataclasses.dataclass(frozen=True)
class BundleInfo:
    package_root: Path
    usd_root: Path
    python_paths: tuple[Path, ...]
    library_paths: tuple[Path, ...]
    executable_paths: tuple[Path, ...]
    plugin_paths: tuple[Path, ...]
    materialx_paths: tuple[Path, ...]
    platform: str


def _existing(paths: Iterable[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except FileNotFoundError:
            resolved = path
        key = os.path.normcase(str(resolved))
        if path.exists() and key not in seen:
            out.append(path)
            seen.add(key)
    return out


def _prepend_env_path(name: str, paths: Iterable[Path]) -> None:
    sep = os.pathsep
    new_values = [str(p) for p in _existing(paths)]
    if not new_values:
        return

    old = os.environ.get(name, "")
    old_values = [p for p in old.split(sep) if p]
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*new_values, *old_values]:
        key = os.path.normcase(os.path.abspath(value))
        if key not in seen:
            merged.append(value)
            seen.add(key)
    os.environ[name] = sep.join(merged)


def _candidate_python_paths() -> list[Path]:
    candidates = [
        USD_ROOT / "python",  # MaterialX CMake installs Python here by default.
        USD_ROOT / "lib" / "python",
        USD_ROOT / "lib64" / "python",
        USD_ROOT / "Library" / "lib" / "python",
    ]

    # Some custom installs put pxr under site-packages.
    for base in [USD_ROOT / "lib", USD_ROOT / "lib64", USD_ROOT / "Library" / "lib"]:
        if base.exists():
            candidates.extend(base.glob("python*/site-packages"))
            candidates.extend(base.glob("python*/dist-packages"))

    return _existing(candidates)


def _candidate_library_paths() -> list[Path]:
    return _existing(
        [
            USD_ROOT / "lib",
            USD_ROOT / "lib64",
            USD_ROOT / "bin",  # Windows DLLs often live here.
            USD_ROOT / "Library" / "bin",
            USD_ROOT / "Library" / "lib",
            USD_ROOT / "python" / "MaterialX",
        ]
    )


def _candidate_executable_paths() -> list[Path]:
    return _existing([USD_ROOT / "bin", USD_ROOT / "Library" / "bin"])


def _candidate_plugin_paths() -> list[Path]:
    explicit = [
        USD_ROOT / "plugin" / "usd",
        USD_ROOT / "plugin",
        USD_ROOT / "lib" / "usd",
        USD_ROOT / "lib64" / "usd",
        USD_ROOT / "Library" / "lib" / "usd",
    ]

    # Be robust to layout changes by finding plugInfo.json files.
    descriptor_parents = [p.parent for p in USD_ROOT.rglob("plugInfo.json")] if USD_ROOT.exists() else []
    candidates = _existing([*explicit, *descriptor_parents])

    # Drop any path already covered by a shallower candidate that holds a
    # plugInfo.json. USD's aggregate lib/usd/plugInfo.json pulls in every
    # */resources/ plugin via "Includes", so ALSO registering each nested
    # <plugin>/resources dir reloads the same plugin library a second time and
    # aborts the process with "multiple debug symbol definitions" (e.g.
    # USDMTLX_READER). Registering a covering ancestor that itself lacks a
    # plugInfo.json (e.g. plugin/ vs plugin/usd/) is not a cover, so keep the
    # deeper one in that case.
    def _has_descriptor(directory: Path) -> bool:
        return (directory / "plugInfo.json").is_file()

    kept: list[Path] = []
    for path in sorted(candidates, key=lambda p: len(p.parts)):
        covered = any(ancestor in path.parents and _has_descriptor(ancestor) for ancestor in kept)
        if not covered:
            kept.append(path)
    return kept


def _candidate_materialx_paths() -> list[Path]:
    candidates: list[Path] = []

    likely_roots = [
        USD_ROOT / "share" / "MaterialX" / "libraries",
        USD_ROOT / "libraries",
        USD_ROOT / "MaterialX" / "libraries",
        USD_ROOT / "lib" / "python" / "MaterialX" / "libraries",
        USD_ROOT / "python" / "MaterialX" / "libraries",
        USD_ROOT / "Library" / "share" / "MaterialX" / "libraries",
    ]
    candidates.extend(likely_roots)

    if USD_ROOT.exists():
        # Standard library files are often below a libraries/ directory.
        for stdlib_file in USD_ROOT.rglob("stdlib_defs.mtlx"):
            candidates.append(stdlib_file.parent)
            if stdlib_file.parent.parent.name.lower() in {"libraries", "materialx"}:
                candidates.append(stdlib_file.parent.parent)

        # Include parents of .mtlx files near a MaterialX libraries folder.
        for mtlx_file in USD_ROOT.rglob("*.mtlx"):
            parts = {part.lower() for part in mtlx_file.parts}
            if "libraries" in parts or "materialx" in parts:
                candidates.append(mtlx_file.parent)

    return _existing(candidates)


def get_bundle_info() -> BundleInfo:
    return BundleInfo(
        package_root=PACKAGE_ROOT,
        usd_root=USD_ROOT,
        python_paths=tuple(_candidate_python_paths()),
        library_paths=tuple(_candidate_library_paths()),
        executable_paths=tuple(_candidate_executable_paths()),
        plugin_paths=tuple(_candidate_plugin_paths()),
        materialx_paths=tuple(_candidate_materialx_paths()),
        platform=platform.platform(),
    )


def prepare(register_plugins: bool = True) -> BundleInfo:
    """Prepare the bundled USD runtime for the current Python process.

    This function is idempotent. It modifies process-level environment variables and
    sys.path so that the bundled `pxr` package and USD plugins can be discovered.
    """

    global _BOOTSTRAPPED

    info = get_bundle_info()

    for path in reversed(info.python_paths):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)

    _prepend_env_path("PATH", [*info.executable_paths, *info.library_paths])

    if sys.platform.startswith("linux"):
        _prepend_env_path("LD_LIBRARY_PATH", info.library_paths)
    elif sys.platform == "darwin":
        _prepend_env_path("DYLD_LIBRARY_PATH", info.library_paths)

    # USD plugin discovery.
    _prepend_env_path("PXR_PLUGINPATH_NAME", info.plugin_paths)

    # UsdMtlx / MaterialX discovery.
    _prepend_env_path("PXR_MTLX_STDLIB_SEARCH_PATHS", info.materialx_paths)
    _prepend_env_path("PXR_MTLX_PLUGIN_SEARCH_PATHS", info.materialx_paths)
    _prepend_env_path("MATERIALX_SEARCH_PATH", info.materialx_paths)

    # Windows Python 3.8+ requires explicit DLL directories for extension modules.
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        for path in info.library_paths:
            try:
                handle = os.add_dll_directory(str(path))
            except OSError:
                continue
            _ADDED_DLL_DIRS.append(handle)

    if register_plugins and info.plugin_paths:
        try:
            from pxr import Plug  # type: ignore
        except Exception:
            # pxr may not be importable until platform wheel repair is correct.
            pass
        else:
            registry = Plug.Registry()
            for path in info.plugin_paths:
                try:
                    registry.RegisterPlugins(str(path))
                except Exception:
                    # Keep going; some paths are parents and some are direct plugin dirs.
                    continue
                _REGISTERED_PLUGIN_PATHS.append(path)

    _BOOTSTRAPPED = True
    return info


def validate(verbose: bool = True) -> dict[str, object]:
    """Validate that pxr imports and likely usdMtlx descriptors are discoverable."""

    info = prepare(register_plugins=True)
    result: dict[str, object] = {
        "usd_root": str(info.usd_root),
        "python_paths": [str(p) for p in info.python_paths],
        "plugin_paths": [str(p) for p in info.plugin_paths],
        "materialx_paths": [str(p) for p in info.materialx_paths],
        "pxr_import": False,
        "usd_version": None,
        "usdmtlx_descriptors": [],
        "usdmtlx_module_import": False,
    }

    try:
        from pxr import Plug, Sdf, Usd  # type: ignore
    except Exception as exc:  # pragma: no cover - only used in built wheel envs
        result["error"] = f"pxr import failed: {exc!r}"
        if verbose:
            print(result["error"])
        return result

    result["pxr_import"] = True
    try:
        result["usd_version"] = ".".join(str(x) for x in Usd.GetVersion())
    except Exception:
        result["usd_version"] = "unknown"

    descriptors = []
    for plug_info in info.usd_root.rglob("plugInfo.json") if info.usd_root.exists() else []:
        text = ""
        try:
            text = plug_info.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass
        if "usdMtlx" in text or "UsdMtlx" in text or "mtlx" in text.lower():
            descriptors.append(str(plug_info))
    result["usdmtlx_descriptors"] = descriptors

    try:
        __import__("pxr.UsdMtlx")
        result["usdmtlx_module_import"] = True
    except Exception:
        # Some USD builds provide only plugins/libraries, not a Python pxr.UsdMtlx module.
        result["usdmtlx_module_import"] = False

    # Very small smoke test: can USD resolve the mtlx extension plugin type?
    try:
        result["mtlx_layer_type"] = str(Sdf.FileFormat.FindByExtension("mtlx"))
    except Exception as exc:
        result["mtlx_layer_type_error"] = repr(exc)

    if verbose:
        print("Bundle root:", info.usd_root)
        print("pxr import:", "OK" if result["pxr_import"] else "FAILED")
        print("USD version:", result["usd_version"])
        print("usdMtlx descriptors:", len(descriptors))
        print("pxr.UsdMtlx import:", "OK" if result["usdmtlx_module_import"] else "not available / not required")
        print("Sdf .mtlx file format:", result.get("mtlx_layer_type", result.get("mtlx_layer_type_error")))

    return result
