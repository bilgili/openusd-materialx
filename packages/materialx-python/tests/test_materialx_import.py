from pathlib import Path

import pytest


def test_import_wrapper():
    import materialx_python

    info = materialx_python.prepare()
    assert info.package_root.exists()


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "src" / "materialx_python" / "_materialx").exists(),
    reason="MaterialX bundle has not been built yet",
)
def test_find_real_materialx_init_resolves():
    # Regression: the shim must locate the bundled real MaterialX/__init__.py.
    # Exercises find_real_materialx_init() directly so it fails even in the source
    # tree, where validate() otherwise shadows the shim by prepending the real
    # package to sys.path before `import MaterialX`.
    from materialx_python import bootstrap

    init = bootstrap.find_real_materialx_init()
    assert init is not None, "find_real_materialx_init() returned None despite a built bundle"
    assert init.exists()
    assert init.name == "__init__.py" and init.parent.name == "MaterialX"


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "src" / "materialx_python" / "_materialx").exists(),
    reason="MaterialX bundle has not been built yet",
)
def test_import_materialx_after_bundle():
    import MaterialX as mx

    assert hasattr(mx, "getVersionString")
