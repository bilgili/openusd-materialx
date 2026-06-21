from __future__ import annotations

import dataclasses
import os
import platform
import sys
from pathlib import Path
from typing import Iterable

PACKAGE_ROOT = Path(__file__).resolve().parent
BUNDLE_ROOT = PACKAGE_ROOT / "_materialx"
_ADDED_DLL_DIRS: list[object] = []


@dataclasses.dataclass(frozen=True)
class BundleInfo:
    package_root: Path
    bundle_root: Path
    python_paths: tuple[Path, ...]
    library_paths: tuple[Path, ...]
    executable_paths: tuple[Path, ...]
    library_data_paths: tuple[Path, ...]
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
    new_values = [str(p) for p in _existing(paths)]
    if not new_values:
        return
    old_values = [p for p in os.environ.get(name, "").split(os.pathsep) if p]
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*new_values, *old_values]:
        key = os.path.normcase(os.path.abspath(value))
        if key not in seen:
            merged.append(value)
            seen.add(key)
    os.environ[name] = os.pathsep.join(merged)


def _candidate_python_paths() -> list[Path]:
    candidates = [
        BUNDLE_ROOT / "python",
        BUNDLE_ROOT / "lib" / "python",
        BUNDLE_ROOT / "lib64" / "python",
        BUNDLE_ROOT / "Library" / "lib" / "python",
    ]
    for base in [BUNDLE_ROOT / "lib", BUNDLE_ROOT / "lib64", BUNDLE_ROOT / "Library" / "lib"]:
        if base.exists():
            candidates.extend(base.glob("python*/site-packages"))
            candidates.extend(base.glob("python*/dist-packages"))
    return _existing(candidates)


def _candidate_library_paths() -> list[Path]:
    return _existing(
        [
            BUNDLE_ROOT / "lib",
            BUNDLE_ROOT / "lib64",
            BUNDLE_ROOT / "bin",
            BUNDLE_ROOT / "Library" / "bin",
            BUNDLE_ROOT / "Library" / "lib",
            BUNDLE_ROOT / "python" / "MaterialX",
        ]
    )


def _candidate_executable_paths() -> list[Path]:
    return _existing([BUNDLE_ROOT / "bin", BUNDLE_ROOT / "Library" / "bin"])


def _candidate_library_data_paths() -> list[Path]:
    candidates = [
        BUNDLE_ROOT / "libraries",
        BUNDLE_ROOT / "share" / "MaterialX" / "libraries",
        BUNDLE_ROOT / "MaterialX" / "libraries",
        BUNDLE_ROOT / "python" / "MaterialX" / "libraries",
    ]
    if BUNDLE_ROOT.exists():
        for stdlib in BUNDLE_ROOT.rglob("stdlib_defs.mtlx"):
            candidates.append(stdlib.parent)
            if stdlib.parent.parent.name.lower() in {"libraries", "materialx"}:
                candidates.append(stdlib.parent.parent)
    return _existing(candidates)


def get_bundle_info() -> BundleInfo:
    return BundleInfo(
        package_root=PACKAGE_ROOT,
        bundle_root=BUNDLE_ROOT,
        python_paths=tuple(_candidate_python_paths()),
        library_paths=tuple(_candidate_library_paths()),
        executable_paths=tuple(_candidate_executable_paths()),
        library_data_paths=tuple(_candidate_library_data_paths()),
        platform=platform.platform(),
    )


def prepare() -> BundleInfo:
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

    _prepend_env_path("MATERIALX_SEARCH_PATH", info.library_data_paths)

    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        for path in info.library_paths:
            try:
                handle = os.add_dll_directory(str(path))
            except OSError:
                continue
            _ADDED_DLL_DIRS.append(handle)
    return info


def find_real_materialx_init() -> Path | None:
    info = prepare()

    # The only file we must avoid returning is the shim package's own __init__.py,
    # installed as a sibling top-level `MaterialX` package next to `materialx_python`.
    # Everything we want lives under the bundle (BUNDLE_ROOT). The previous guard
    # rejected any candidate under PACKAGE_ROOT.parent, but that directory (e.g.
    # site-packages) is also an ancestor of the bundled real package, so it rejected
    # the real __init__.py and the shim raised "Bundled MaterialX package not found".
    shim_dir = PACKAGE_ROOT.parent / "MaterialX"

    def _is_shim(candidate: Path) -> bool:
        try:
            return candidate.parent.resolve() == shim_dir.resolve()
        except OSError:
            return candidate.parent == shim_dir

    for base in info.python_paths:
        candidate = base / "MaterialX" / "__init__.py"
        if candidate.exists() and not _is_shim(candidate):
            return candidate
    if info.bundle_root.exists():
        for candidate in info.bundle_root.rglob("MaterialX/__init__.py"):
            if not _is_shim(candidate):
                return candidate
    return None


def validate(verbose: bool = True) -> dict[str, object]:
    info = prepare()
    result: dict[str, object] = {
        "bundle_root": str(info.bundle_root),
        "python_paths": [str(p) for p in info.python_paths],
        "library_paths": [str(p) for p in info.library_paths],
        "library_data_paths": [str(p) for p in info.library_data_paths],
        "materialx_import": False,
        "version": None,
    }
    try:
        import MaterialX as mx  # type: ignore
    except Exception as exc:
        result["error"] = f"MaterialX import failed: {exc!r}"
        if verbose:
            print(result["error"])
        return result

    result["materialx_import"] = True
    try:
        result["version"] = mx.getVersionString()
    except Exception:
        result["version"] = "unknown"

    if verbose:
        print("MaterialX bundle root:", info.bundle_root)
        print("MaterialX import:", "OK" if result["materialx_import"] else "FAILED")
        print("MaterialX version:", result["version"])
    return result
