# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A scaffold that produces **two pip-installable binary wheels** by bundling prebuilt native
C++ install trees. It does **not** compile C++ during an end-user `pip install` — that is a
deliberate non-goal. The C++ is built ahead of time (locally or in CI) and copied into the
Python package as a `_usd/` or `_materialx/` tree, then the wheel is repaired and published.

Two independent packages:

1. **`openusd-materialx`** (`src/openusd_materialx/`) — OpenUSD built with the `usdMtlx`
   plugin, linked against a *separately built latest MaterialX SDK* (not OpenUSD's pinned
   one). Bundle lives at `src/openusd_materialx/_usd/`.
2. **`materialx-python-standalone`** (`packages/materialx-python/`) — standalone ASWF
   MaterialX Python bindings. Bundle lives at
   `packages/materialx-python/src/materialx_python/_materialx/`.

The key architectural idea: build MaterialX first, install it into the **same prefix**
OpenUSD will use, and pass `-DMaterialX_DIR=...` so `usdMtlx` links the MaterialX you chose.

## Build commands

Standalone MaterialX wheel:

```bash
python scripts/build_materialx_python_bundle.py --ref main --clean
python packages/materialx-python/scripts/validate_materialx_bundle.py
python -m build --wheel --outdir wheelhouse/raw/materialx packages/materialx-python
python scripts/repair_wheel.py wheelhouse/raw/materialx/*.whl --out-dir wheelhouse
```

OpenUSD + usdMtlx + latest MaterialX wheel:

```bash
python scripts/build_openusd_bundle.py --ref v26.05 --materialx-ref main --profile full --clean
python scripts/validate_bundle.py
python -m build --wheel --outdir wheelhouse/raw/openusd
python scripts/repair_wheel.py wheelhouse/raw/openusd/*.whl --out-dir wheelhouse
```

Smaller OpenUSD wheel: `--profile minimal` or `--profile default` (default profile is `full`).

Validate an installed wheel:

```bash
python -m openusd_materialx --validate        # also: --json for machine output
python -c "import MaterialX as mx; print(mx.getVersionString())"
```

## Test commands

```bash
pytest tests                                          # openusd-materialx
pytest packages/materialx-python/tests                # standalone MaterialX
pytest tests/test_usdmtlx.py::test_usdmtlx_descriptor_after_bundle   # single test
```

Tests that need the native bundle are `@pytest.mark.skipif` on the existence of `_usd/` /
`_materialx/`, so they **silently skip until a bundle is built**. A green `pytest` run does
not mean the native path was exercised — check for skips.

## Architecture

### Two-layer build pipeline

`scripts/materialx_build.py` is the shared MaterialX CMake helper used by *both* package
builds — it owns the canonical MaterialX CMake option set (`MATERIALX_BUILD_*`, including
`-DMATERIALX_BUILD_GEN_SLANG=ON` by default) and the `MaterialXConfig.cmake` locator.

- `scripts/build_openusd_bundle.py` → builds MaterialX (into the OpenUSD prefix) via the
  shared helper, then drives OpenUSD's own `build_scripts/build_usd.py`, then copies the
  install tree into `_usd/`.
- `scripts/build_materialx_python_bundle.py` → builds MaterialX standalone via the shared
  helper, copies into `_materialx/`.
- `scripts/_build_utils.py` → git clone/update (shallow with SHA fallback), Ninja detection,
  env-path helpers, used everywhere.

The OpenUSD profile system (`PROFILE_ARGS` = `build_usd.py` flags, plus
`*_USD_CMAKE_OPTIONS` = raw `PXR_*` CMake options) is resilient to OpenUSD releases:
`read_supported_build_usd_flags()` parses `build_usd.py --help` and
`filter_supported_flags()` drops unsupported flags (warn, or fail with
`--strict-profile-flags`). When adding a profile flag, add it to *both* the `build_usd.py`
flag list and the matching `PXR_*` CMake option list.

macOS note: `--enable-metal` defaults **on** here (`sys.platform == "darwin"`). Vulkan/OSL/
PRMan/docs stay opt-in because they need external SDKs CI images lack.

### Runtime bootstrap (the hard, important part)

Each package ships a `bootstrap.py` that fixes up the process at import time so the bundled
native code is discoverable from an arbitrary install location. `src/openusd_materialx/
__init__.py` calls `prepare()` automatically on import (disable with
`OPENUSD_MATERIALX_AUTO_BOOTSTRAP=0`). `prepare()` is idempotent and:

1. Inserts bundled Python paths into `sys.path` (so `from pxr import ...` works).
2. Prepends library dirs to `PATH` / `LD_LIBRARY_PATH` / `DYLD_LIBRARY_PATH`, and calls
   `os.add_dll_directory` on Windows.
3. Sets `PXR_PLUGINPATH_NAME` and MaterialX search vars
   (`PXR_MTLX_STDLIB_SEARCH_PATHS`, `PXR_MTLX_PLUGIN_SEARCH_PATHS`, `MATERIALX_SEARCH_PATH`).
4. Calls `Plug.Registry().RegisterPlugins(...)` for discovered `plugInfo.json` dirs.

Path discovery is **layout-tolerant by design**: the `_candidate_*_paths()` functions list
known locations *and* `rglob()` for marker files (`plugInfo.json`, `stdlib_defs.mtlx`,
`*.mtlx`, `MaterialXConfig.cmake`) so it survives differences between Linux/macOS/Windows
install trees. Preserve this fallback-glob pattern when editing — do not hardcode a single
layout.

The standalone MaterialX package uses an additional **shim**: `MaterialX/__init__.py`
bootstraps, locates the real bundled `MaterialX/__init__.py`, rewrites `__file__`/`__path__`/
`__package__`, and `exec()`s the real module so `import MaterialX as mx` resolves the bundled
extension and resources.

### Wheel packaging

`setup.py` forces `root_is_pure = False` (platform wheel) because native libs are bundled.
Both `pyproject.toml` files declare `dynamic = ["version"]`; the version is injected by
each `setup.py` from the `PACKAGE_VERSION` env var (leading `v` stripped, default `0.0.0`).
CI sets `PACKAGE_VERSION` from the git tag. `package-data` globs ship the entire `_usd/` /
`_materialx/` tree.
`scripts/repair_wheel.py` dispatches per-platform: `auditwheel` (Linux) / `delocate-wheel`
(macOS) / `delvewheel` (Windows) to relocate shared libraries — used for the **standalone
MaterialX wheel only**. Repaired wheels still need a clean-venv install test.

The **OpenUSD wheel is NOT run through repair_wheel.py/delocate.** Instead
`build_openusd_bundle.py::make_bundle_self_contained()` relocates the bundle in place:
OpenUSD bakes an absolute build-prefix `LC_RPATH` (`<install>/lib`) ahead of the relative
`@loader_path` one, so while the build prefix exists the process loads a *second* copy of
libraries like `libusd_usdMtlx` and aborts with "multiple debug symbol definitions". The
builder strips that absolute rpath (and re-signs ad-hoc on macOS / `patchelf` on Linux) so
the tree resolves through `@loader_path`. delocate/auditwheel are *avoided* here because
they relocate libraries into a sibling `.dylibs/` dir and miscompute the `@loader_path/..`
depth for the deeply nested `_usd/lib/python/pxr` layout, breaking `import pxr`. `copy_install_tree`
also excludes `build/`, `src/` (build_usd.py intermediates — bundling them ships duplicate
plugInfo/dylibs) and `libtbbmalloc_proxy*` (optional, dangling rpath).

## CI

`.github/workflows/build-wheels.yml` (matrix: ubuntu-22.04, macos-13, macos-14, windows-2022
× py3.10/3.11/3.12) and `.gitlab-ci.yml`. Both build **both** wheels per job (gated by
`BUILD_PKG` = `both`/`openusd-materialx`/`materialx-python`) from variable
`OPENUSD_REF` / `MATERIALX_REF` / `OPENUSD_BUILD_PROFILE`, each: bundle builder →
`validate_*` → `python -m build --wheel` → `repair_wheel.py` → smoke-test in clean venv →
upload `wheelhouse/*.whl` artifacts (no registry publish). Pipelines trigger on tag pushes
(`v*`) and manual runs only — not every push — and the tag drives `PACKAGE_VERSION`. macOS
arm64 (`macos-14`) passes `--build-target arm64`. GitLab macOS/Windows jobs need configured
native runners. These are heavy full C++ builds — real compilers, CMake, Ninja, time.

## Gotchas

- `pip install git+...` does **not** build the C++; it only works once a `_usd/`/`_materialx/`
  tree is already committed or you install from a published wheel.
- The `full` OpenUSD profile produces very large wheels and is the most likely to hit
  platform-specific dependency failures; drop to `minimal`/`default` when debugging.
- This repo is not a git checkout in the current working tree; the global "work in worktrees"
  convention does not apply until it is initialized as one.
