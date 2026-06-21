from pathlib import Path

import pytest


def test_import_package():
    import openusd_materialx

    info = openusd_materialx.prepare(register_plugins=False)
    assert info.package_root.exists()


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "src" / "openusd_materialx" / "_usd").exists(),
    reason="OpenUSD bundle has not been built yet",
)
def test_pxr_import_after_bundle():
    import openusd_materialx

    result = openusd_materialx.validate(verbose=False)
    assert result["pxr_import"] is True
