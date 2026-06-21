from __future__ import annotations

import os

from setuptools import setup
from wheel.bdist_wheel import bdist_wheel

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE_DIR = os.path.join(HERE, "src", "materialx_python", "_materialx")


class BinaryBdistWheel(bdist_wheel):
    """Mark this wheel as platform-specific because it bundles native libraries."""

    def finalize_options(self) -> None:
        super().finalize_options()
        self.root_is_pure = False

    def run(self) -> None:
        # Refuse to build a binary-less wheel. Without the bundled MaterialX tree the
        # wheel is a few KB of pure Python and the shim raises ImportError at runtime.
        # Set MATERIALX_PYTHON_ALLOW_EMPTY_WHEEL=1 to override.
        allow_empty = os.environ.get("MATERIALX_PYTHON_ALLOW_EMPTY_WHEEL", "") not in {"", "0", "false", "False"}
        has_bundle = os.path.isdir(BUNDLE_DIR) and any(os.scandir(BUNDLE_DIR))
        if not has_bundle and not allow_empty:
            raise SystemExit(
                "Refusing to build an empty materialx-python-standalone wheel: bundled "
                f"MaterialX tree not found (or empty) at {BUNDLE_DIR}.\n"
                "Run `python scripts/build_materialx_python_bundle.py ...` first. "
                "`python packages/materialx-python/scripts/validate_materialx_bundle.py` "
                "must pass before building the wheel.\n"
                "Override with MATERIALX_PYTHON_ALLOW_EMPTY_WHEEL=1 if you really want a "
                "pure-Python wheel."
            )
        super().run()


def _package_version() -> str:
    """Resolve the wheel version from the environment.

    CI sets PACKAGE_VERSION from the git tag (tag ``v1.2.3`` -> ``1.2.3``). Manual,
    dev, and local builds fall back to ``0.0.0`` so they never collide with a release.
    """
    version = os.environ.get("PACKAGE_VERSION", "").strip()
    if version[:1] in {"v", "V"}:
        version = version[1:]
    return version or "0.0.0"


setup(version=_package_version(), cmdclass={"bdist_wheel": BinaryBdistWheel})
