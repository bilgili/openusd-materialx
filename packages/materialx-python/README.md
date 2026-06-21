# materialx-python-standalone

Standalone wheel scaffold for the ASWF MaterialX Python bindings, built from the
MaterialX GitHub source tree.

This package is intended to be built by CI, not compiled during a normal end-user
`pip install`. The build script clones MaterialX, configures CMake with Python bindings
enabled, installs MaterialX into this package, and then builds a binary wheel.

## Build

From the repository root:

```bash
python scripts/build_materialx_python_bundle.py --ref main --clean
python packages/materialx-python/scripts/validate_materialx_bundle.py
python -m build --wheel --outdir wheelhouse/raw/materialx packages/materialx-python
python scripts/repair_wheel.py wheelhouse/raw/materialx/*.whl --out-dir wheelhouse
```


## Slang generation

The MaterialX build enables the Slang shader generator by default using:

```text
-DMATERIALX_BUILD_GEN_SLANG=ON
```

Use `--no-slang-gen` only when you intentionally want to disable it.

## Use

```python
import MaterialX as mx
print(mx.getVersionString())
```

You may also inspect the bundle with:

```bash
python -m materialx_python --validate
```

## Notes

The top-level `MaterialX` package in this wheel is a small shim. It adds the bundled
MaterialX install tree to the runtime search paths and then executes the real MaterialX
Python package from the CMake install output.
