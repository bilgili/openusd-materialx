# openusd-materialx-wheel

A starter repository for building two pip-installable binary wheel packages:

1. `openusd-materialx` — OpenUSD bundled with `usdMtlx`, built against a separately
   built latest MaterialX SDK.
2. `materialx-python-standalone` — standalone ASWF MaterialX Python bindings as a wheel.

The intended production workflow is CI-built wheels for Linux, macOS, and Windows. The
repo intentionally avoids compiling OpenUSD or MaterialX during an ordinary end-user
`pip install`, because those are large C++ builds.

## Why this package exists

The official `usd-core` package is useful for core USD, but it does not ship all optional
plugins. If you need the USD MaterialX plugin, you usually need a custom OpenUSD build
with MaterialX enabled and the `usdMtlx` plugin discoverable at runtime.

OpenUSD's own build script has a pinned MaterialX dependency. This scaffold instead builds
MaterialX from `https://github.com/AcademySoftwareFoundation/MaterialX` first, installs it
into the same prefix used by OpenUSD, and passes `MaterialX_DIR` into the OpenUSD build.
That makes `usdMtlx` link against the MaterialX SDK you selected.

## Build profiles

`openusd-materialx` now defaults to the `full` profile:

```text
--python --materialx --imaging --usd-imaging --usdview --tools --examples --tutorials
--tests --ptex --openimageio --opencolorio --openvdb --alembic --hdf5 --draco --embree
--onetbb
```

It also forwards explicit USD CMake options for the matching components, such as
`PXR_ENABLE_MATERIALX_SUPPORT`, `PXR_BUILD_OPENIMAGEIO_PLUGIN`, `PXR_BUILD_OPENCOLORIO_PLUGIN`,
`PXR_BUILD_ALEMBIC_PLUGIN`, `PXR_BUILD_DRACO_PLUGIN`, and `PXR_BUILD_EMBREE_PLUGIN`.

Some switches remain opt-in because they require external SDKs that CI images usually do
not include:

```bash
--enable-vulkan   # requires VULKAN_SDK
--enable-osl      # requires OSL discoverable by CMake
--enable-prman    # requires RenderMan
--enable-docs     # requires Doxygen and GraphViz
```

For smaller wheels, use:

```bash
python scripts/build_openusd_bundle.py --profile minimal --clean
```

## Repository layout

```text
openusd-materialx-wheel/
  src/openusd_materialx/                 # OpenUSD runtime bootstrap package
  packages/materialx-python/             # standalone MaterialX wheel package
  scripts/
    build_openusd_bundle.py              # latest MaterialX + OpenUSD bundle builder
    build_materialx_python_bundle.py     # standalone MaterialX Python wheel bundle builder
    materialx_build.py                   # shared MaterialX CMake build helpers
    validate_bundle.py                   # OpenUSD/usdMtlx smoke test
    repair_wheel.py                      # auditwheel / delocate / delvewheel wrapper
  .github/workflows/build-wheels.yml
  .gitlab-ci.yml
```

## Local build: standalone MaterialX Python wheel

Wheels take their version from `PACKAGE_VERSION` (default `0.0.0` locally; CI sets it from
the git tag). Prefix with `PACKAGE_VERSION=1.2.3` on the `python -m build` line to stamp a
version.

```bash
python -m pip install -U pip build setuptools wheel
# Install the platform wheel-repair tool that the last step (repair_wheel.py) needs:
#   macOS:   python -m pip install delocate
#   Linux:   python -m pip install auditwheel   (also needs the system `patchelf`)
#   Windows: python -m pip install delvewheel
python -m pip install delocate
python scripts/build_materialx_python_bundle.py --ref main --clean
python packages/materialx-python/scripts/validate_materialx_bundle.py
python -m build --wheel --outdir wheelhouse/raw/materialx packages/materialx-python
python scripts/repair_wheel.py wheelhouse/raw/materialx/*.whl --out-dir wheelhouse
```

Install and test:

```bash
python -m pip install wheelhouse/materialx_python_standalone-*.whl
python - <<'PY'
import MaterialX as mx
print(mx.getVersionString())
PY
```

## Local build: OpenUSD + usdMtlx + latest MaterialX

```bash
python -m pip install -U pip build setuptools wheel PyOpenGL PySide6 jinja2
# (jinja2 lets build_usd.py build usdGenSchema/usdInitSchema; without it they are skipped.)
# CMake 4 removed OLD policy support (e.g. CMP0042) that OpenUSD v26.05's bundled
# dependency builds (Alembic, etc.) still rely on, so pin CMake < 4 for this build:
python -m pip install "cmake<4" ninja
python scripts/build_openusd_bundle.py --ref v26.05 --materialx-ref main --profile full --clean
python scripts/validate_bundle.py
python -m build --wheel --outdir wheelhouse
```

Note: unlike the standalone MaterialX wheel, the OpenUSD wheel is **not** run through
`repair_wheel.py`/delocate. `build_openusd_bundle.py` already makes the `_usd/` tree
self-contained (it strips the absolute build-prefix rpath that OpenUSD bakes in and re-signs
the binaries), and the tree resolves its own libraries via `@loader_path`. delocate/auditwheel
would relocate libraries in a way that breaks the deeply nested `_usd/lib/python/pxr` layout,
so the wheel ships as built. On macOS the bundle binaries are re-signed ad-hoc; on Linux the
build-prefix `RPATH` is removed with `patchelf` (install it: `apt-get install patchelf`).

The OpenUSD build is large and can fail partway. It only counts as done when
`build_openusd_bundle.py` finishes and populates `src/openusd_materialx/_usd/`, and
`validate_bundle.py` prints a USD version and exits 0. If the bundle is missing, the wheel
build stops with a clear "Refusing to build an empty wheel" error rather than producing a
binary-less wheel.

Install and test:

```bash
python -m pip install wheelhouse/openusd_materialx-*.whl
python -m openusd_materialx --validate
```

Then:

```python
import openusd_materialx
from pxr import Usd, Sdf, Plug

print(Usd.GetVersion())
print(Sdf.FileFormat.FindByExtension("mtlx"))
```


## MaterialX Slang generation

Slang shader generation is enabled by default for both MaterialX build paths. The shared
helper passes this CMake option to MaterialX:

```text
-DMATERIALX_BUILD_GEN_SLANG=ON
```

Disable it only when building against an older MaterialX branch or a CI image that cannot
build the Slang generator:

```bash
python scripts/build_materialx_python_bundle.py --no-slang-gen
python scripts/build_openusd_bundle.py --no-materialx-slang-gen
```

If you want to pass an installed Slang SDK location or any upstream-specific CMake option,
use repeated `--extra-cmake-arg` on the MaterialX standalone build, or
`--extra-usd-cmake-arg` / `--extra-build-usd-arg` for OpenUSD.

## Git install during development

`pip install git+...` works only after the repo already contains a bundled `_usd` or
`_materialx` tree, or after you publish wheels and install from a wheel URL. Building the
C++ projects during normal pip installation is intentionally not implemented.

Recommended internal install pattern:

```bash
pip install openusd-materialx --find-links https://your-wheel-host/simple
pip install materialx-python-standalone --find-links https://your-wheel-host/simple
```

## CI

GitHub Actions (`.github/workflows/build-wheels.yml`) and GitLab CI (`.gitlab-ci.yml`)
build both wheels on Ubuntu x86_64, macOS x86_64, macOS arm64, and Windows x64.

Versions are variable, so the same pipeline produces new packages without code changes:

| Variable / input | Meaning | Default |
| --- | --- | --- |
| `OPENUSD_REF` | OpenUSD tag/branch/sha | `v26.05` |
| `MATERIALX_REF` | MaterialX tag/branch/sha (`main` = latest) | `main` |
| `OPENUSD_BUILD_PROFILE` | `full` \| `default` \| `minimal` | `full` |
| `BUILD_PKG` | `both` \| `openusd-materialx` \| `materialx-python` | `both` |

The **wheel version comes from the git tag**: pushing `v1.2.3` builds
`openusd_materialx-1.2.3` and `materialx_python_standalone-1.2.3`. Untagged manual runs
build `0.0.0`. Wheels are uploaded as CI job artifacts (no registry publishing configured).
Pipelines run on tag pushes and manual runs only — not on every push, since full OpenUSD
builds are heavy. See [docs/gitlab-and-github-automation.md](docs/gitlab-and-github-automation.md)
for the full workflow.

You will still need platform runners with compilers, CMake, Ninja, and enough disk/time for
full OpenUSD builds. macOS/Windows GitLab jobs require configured native runners.

## Runtime bootstrap

Importing `openusd_materialx` does these things:

1. Adds bundled OpenUSD and MaterialX Python paths to `sys.path`.
2. Adds bundled DLL/shared-library directories where the platform allows it.
3. Prepends likely plugin locations to `PXR_PLUGINPATH_NAME`.
4. Sets likely MaterialX search paths such as `PXR_MTLX_STDLIB_SEARCH_PATHS` and
   `MATERIALX_SEARCH_PATH`.
5. Calls `Plug.Registry().RegisterPlugins(...)` for discovered `plugInfo.json` files.

The standalone MaterialX wheel exposes `import MaterialX as mx` through a small shim that
bootstraps the bundled CMake install tree and then executes the real MaterialX Python
package.

## Known hard parts

### Full profile builds are heavy

The `full` OpenUSD profile is intentionally ambitious. It can produce very large wheels and
may expose platform-specific dependency issues. Keep `--profile minimal` and `--profile default`
for debugging or lighter internal distributions.

### Shared library relocation

Bundling binaries in Python wheels requires platform-specific repair:

- Linux: `auditwheel repair`
- macOS: `delocate-wheel`
- Windows: `delvewheel repair`

`scripts/repair_wheel.py` wraps these tools, but you still need to test the repaired wheel
in a clean virtual environment.

### Licensing

OpenUSD and MaterialX have their own Apache-2.0 licenses, and full OpenUSD builds may bundle
additional third-party libraries. Before publishing wheels, include the full license texts
for everything you redistribute.
