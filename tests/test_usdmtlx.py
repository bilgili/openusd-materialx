from pathlib import Path

import pytest


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "src" / "openusd_materialx" / "_usd").exists(),
    reason="OpenUSD bundle has not been built yet",
)
def test_usdmtlx_descriptor_after_bundle():
    import openusd_materialx

    result = openusd_materialx.validate(verbose=False)
    assert result.get("usdmtlx_descriptors") or result.get("usdmtlx_module_import")
