# Standalone MaterialX Python wheel

The standalone wheel package lives in `packages/materialx-python` and publishes as:

```text
materialx-python-standalone
```

It exposes the standard import name:

```python
import MaterialX as mx
```

The package uses a shim in `packages/materialx-python/src/MaterialX/__init__.py`. The shim
prepares the bundled install tree and then executes the real MaterialX Python package from:

```text
packages/materialx-python/src/materialx_python/_materialx/python/MaterialX
```

Build from latest source:

```bash
python scripts/build_materialx_python_bundle.py --ref main --clean
python packages/materialx-python/scripts/validate_materialx_bundle.py
python -m build --wheel --outdir wheelhouse/raw/materialx packages/materialx-python
python scripts/repair_wheel.py wheelhouse/raw/materialx/*.whl --out-dir wheelhouse
```

Useful optional build switches:

```bash
--with-viewer
--with-graph-editor
--with-oiio
--with-ocio
--with-docs
--with-tests
--no-slang-gen   # disable Slang shader generation; it is ON by default
```

For CI reproducibility, prefer pinning `MATERIALX_REF` to a tag or commit SHA after you
validate the current `main` branch.
