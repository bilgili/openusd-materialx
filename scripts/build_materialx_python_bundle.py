#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from _build_utils import rmtree
from materialx_build import DEFAULT_MATERIALX_REF, DEFAULT_MATERIALX_REPO, build_materialx

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = REPO_ROOT / "packages" / "materialx-python"
DEFAULT_SOURCE = REPO_ROOT / "_materialx_src"
DEFAULT_BUILD = REPO_ROOT / "_materialx_build"
DEFAULT_INSTALL = REPO_ROOT / "_materialx_install"
DEFAULT_PACKAGE_BUNDLE = PKG_ROOT / "src" / "materialx_python" / "_materialx"


def copy_materialx_install_tree(install_dir: Path, package_bundle_dir: Path) -> None:
    if not install_dir.exists():
        raise RuntimeError(f"MaterialX install dir does not exist: {install_dir}")

    if package_bundle_dir.exists():
        rmtree(package_bundle_dir)

    ignore = shutil.ignore_patterns(
        "*.a",
        "*.la",
        "cmake",
        "pkgconfig",
        "__pycache__",
        "*.pyc",
        "*.pyo",
        ".DS_Store",
    )
    shutil.copytree(install_dir, package_bundle_dir, ignore=ignore)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build latest MaterialX from source and copy it into the standalone MaterialX Python wheel package"
    )
    parser.add_argument("--repo-url", default=os.environ.get("MATERIALX_REPO_URL", DEFAULT_MATERIALX_REPO))
    parser.add_argument(
        "--ref",
        default=os.environ.get("MATERIALX_REF", DEFAULT_MATERIALX_REF),
        help="MaterialX tag/branch/sha. Default is main, i.e. latest source.",
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--install-dir", type=Path, default=DEFAULT_INSTALL)
    parser.add_argument("--package-bundle-dir", type=Path, default=DEFAULT_PACKAGE_BUNDLE)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--skip-build", action="store_true", help="Only copy an existing install-dir into the package")
    parser.add_argument("--source-dir-is-checkout", action="store_true", help="Use --source-dir as-is and do not git fetch/checkout")

    # Optional MaterialX components. The Python wheel defaults to the library + Python
    # bindings + shader generators, while UI apps remain opt-in because they add GUI deps.
    parser.add_argument("--with-viewer", action="store_true", help="Build MaterialX Viewer executable too")
    parser.add_argument("--with-graph-editor", action="store_true", help="Build MaterialX Graph Editor executable too")
    parser.add_argument("--with-tests", action="store_true", help="Build MaterialX tests")
    parser.add_argument("--with-docs", action="store_true", help="Build MaterialX API docs, requires Doxygen")
    parser.add_argument("--with-oiio", action="store_true", help="Build OpenImageIO support, requires OIIO")
    parser.add_argument("--with-ocio", action="store_true", help="Build OpenColorIO support, requires OCIO")
    parser.add_argument("--no-osl-gen", action="store_true", help="Disable OSL shader generation")
    parser.add_argument("--no-mdl-gen", action="store_true", help="Disable MDL shader generation")
    parser.add_argument("--no-glsl-gen", action="store_true", help="Disable GLSL shader generation")
    parser.add_argument("--no-msl-gen", action="store_true", help="Disable MSL shader generation")
    parser.add_argument("--no-slang-gen", action="store_true", help="Disable Slang shader generation")
    parser.add_argument("--extra-cmake-arg", action="append", default=[], help="Extra raw argument passed to MaterialX CMake")
    args = parser.parse_args()

    if not args.skip_build:
        build_materialx(
            repo_url=args.repo_url,
            ref=args.ref,
            source_dir=args.source_dir,
            build_dir=args.build_dir,
            install_dir=args.install_dir,
            clean=args.clean,
            skip_checkout=args.source_dir_is_checkout,
            build_python=True,
            build_viewer=args.with_viewer,
            build_graph_editor=args.with_graph_editor,
            build_tests=args.with_tests,
            build_docs=args.with_docs,
            build_oiio=args.with_oiio,
            build_ocio=args.with_ocio,
            build_osl=not args.no_osl_gen,
            build_mdl=not args.no_mdl_gen,
            build_glsl=not args.no_glsl_gen,
            build_msl=not args.no_msl_gen,
            build_slang=not args.no_slang_gen,
            extra_cmake_arg=args.extra_cmake_arg,
        )

    copy_materialx_install_tree(args.install_dir, args.package_bundle_dir)
    print(f"Bundled MaterialX install copied to: {args.package_bundle_dir}")
    print("Next:")
    print("  python packages/materialx-python/scripts/validate_materialx_bundle.py")
    print("  mkdir -p wheelhouse")
    print("  python -m build --wheel --outdir wheelhouse packages/materialx-python")


if __name__ == "__main__":
    main()
