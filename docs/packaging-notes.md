# Packaging notes

## Do not build OpenUSD inside ordinary pip install

OpenUSD and MaterialX are large C++ projects. Building them during `pip install git+...`
makes installs slow and fragile. Prefer CI-built wheels.

## Wheel tags

You need separate wheels per platform, architecture, and CPython minor version. Examples:

```text
openusd_materialx-0.1.0-cp311-cp311-manylinux_2_28_x86_64.whl
openusd_materialx-0.1.0-cp311-cp311-macosx_14_0_arm64.whl
openusd_materialx-0.1.0-cp311-cp311-win_amd64.whl
materialx_python_standalone-0.1.0-cp311-cp311-manylinux_2_28_x86_64.whl
```

## OpenUSD build profiles

The OpenUSD builder supports:

```bash
python scripts/build_openusd_bundle.py --profile minimal
python scripts/build_openusd_bundle.py --profile default
python scripts/build_openusd_bundle.py --profile full
```

`full` enables the broad set of OpenUSD optional components available through
`build_usd.py`: Python, MaterialX, imaging, USD imaging, usdview, tools, examples,
tutorials, tests, Ptex, OpenImageIO, OpenColorIO, OpenVDB, Alembic, HDF5, Draco, Embree,
and oneTBB.

Some options are intentionally explicit because they need external SDKs:

```bash
python scripts/build_openusd_bundle.py --profile full --enable-vulkan
python scripts/build_openusd_bundle.py --profile full --enable-osl
python scripts/build_openusd_bundle.py --profile full --enable-prman
python scripts/build_openusd_bundle.py --profile full --enable-docs
```

## Latest MaterialX source

Both build paths default to:

```text
MATERIALX_REPO_URL=https://github.com/AcademySoftwareFoundation/MaterialX.git
MATERIALX_REF=main
```

Override with a release tag when you need reproducibility:

```bash
python scripts/build_openusd_bundle.py --materialx-ref v1.39.4
python scripts/build_materialx_python_bundle.py --ref v1.39.4
```

## MaterialX Slang shader generation

The scaffold explicitly passes `-DMATERIALX_BUILD_GEN_SLANG=ON` when building MaterialX
from current source. That option builds MaterialX's Slang shader generator backend.

The standalone MaterialX package can disable it with `--no-slang-gen`; the MaterialX SDK
used by the OpenUSD build can disable it with `--no-materialx-slang-gen`.

## Validation checklist

After installing each repaired wheel in a clean venv:

```bash
python -m materialx_python --validate
python -m openusd_materialx --validate
python examples/simple_usd_materialx_check.py
```

Also test a real MaterialX file from your pipeline:

```python
import openusd_materialx
from pxr import Sdf

openusd_materialx.prepare()
layer = Sdf.Layer.FindOrOpen("your_material.mtlx")
print(layer)
```
