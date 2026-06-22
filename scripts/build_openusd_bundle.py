#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from _build_utils import clone_or_update, prepend_env_path, rmtree, run
from materialx_build import (
    DEFAULT_MATERIALX_REF,
    DEFAULT_MATERIALX_REPO,
    build_materialx,
    find_materialx_config_dir,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPENUSD_REPO = "https://github.com/PixarAnimationStudios/OpenUSD.git"
DEFAULT_OPENUSD_REF = "v26.05"

# build_usd.py has a stable user-facing flag layer; we still filter these against
# --help at runtime so this scaffold is resilient to OpenUSD release changes.
PROFILE_ARGS: dict[str, list[str]] = {
    "minimal": [
        "--python",
        "--materialx",
        "--no-imaging",
        "--no-usdview",
        "--no-examples",
        "--no-tutorials",
        "--no-tests",
    ],
    "default": [
        "--python",
        "--materialx",
        # --usd-imaging builds both imaging and USD imaging. In OpenUSD's build_usd.py
        # --imaging/--usd-imaging/--no-imaging are one mutually exclusive setting, so we
        # must pass only one (passing --imaging too errors: "not allowed with --imaging").
        "--usd-imaging",
        "--tools",
        "--no-usdview",
        "--no-examples",
        "--no-tutorials",
        "--no-tests",
    ],
    "full": [
        "--python",
        "--materialx",
        # See note in "default": --usd-imaging already implies --imaging; do not pass both.
        "--usd-imaging",
        "--usdview",
        "--tools",
        "--examples",
        "--tutorials",
        # No tests: building them links the boost.python `exec_` executable, which fails on
        # Linux under PXR_PY_UNDEFINED_DYNAMIC_LOOKUP (undefined Python symbols in an
        # executable), and they install malformed test plugInfo fixtures. Tests aren't part
        # of the distributable runtime.
        "--no-tests",
        "--ptex",
        "--openimageio",
        "--opencolorio",
        "--openvdb",
        "--alembic",
        "--draco",
        "--embree",
        "--onetbb",
    ],
}

FULL_USD_CMAKE_OPTIONS = [
    "-DPXR_ENABLE_PYTHON_SUPPORT=TRUE",
    # PXR_PY_UNDEFINED_DYNAMIC_LOOKUP is added (macOS only) in build_usd_cmake_options();
    # Linux links libpython by soname instead (portable, and lets the USD tools link).
    "-DPXR_ENABLE_MATERIALX_SUPPORT=TRUE",
    "-DPXR_ENABLE_GL_SUPPORT=TRUE",
    "-DPXR_BUILD_IMAGING=TRUE",
    "-DPXR_BUILD_USD_IMAGING=TRUE",
    "-DPXR_BUILD_USDVIEW=TRUE",
    "-DPXR_BUILD_USD_TOOLS=TRUE",
    "-DPXR_BUILD_EXAMPLES=TRUE",
    "-DPXR_BUILD_TUTORIALS=TRUE",
    "-DPXR_BUILD_TESTS=FALSE",  # see --no-tests note: tests break Linux link + ship bad plugInfo
    "-DPXR_ENABLE_PTEX_SUPPORT=TRUE",
    "-DPXR_BUILD_OPENIMAGEIO_PLUGIN=TRUE",
    "-DPXR_BUILD_OPENCOLORIO_PLUGIN=TRUE",
    "-DPXR_BUILD_EMBREE_PLUGIN=TRUE",
    "-DPXR_BUILD_ALEMBIC_PLUGIN=TRUE",
    # No HDF5: build_usd.py v26.05 dropped the --hdf5 flag (so it never builds the HDF5
    # dependency), and forcing PXR_ENABLE_HDF5_SUPPORT made the build fail with
    # "Could NOT find HDF5". The Alembic plugin still works via the Ogawa backend.
    "-DPXR_BUILD_DRACO_PLUGIN=TRUE",
]

DEFAULT_USD_CMAKE_OPTIONS = [
    "-DPXR_ENABLE_PYTHON_SUPPORT=TRUE",
    "-DPXR_ENABLE_MATERIALX_SUPPORT=TRUE",
    "-DPXR_BUILD_IMAGING=TRUE",
    "-DPXR_BUILD_USD_IMAGING=TRUE",
    "-DPXR_BUILD_USD_TOOLS=TRUE",
    "-DPXR_BUILD_USDVIEW=FALSE",
    "-DPXR_BUILD_EXAMPLES=FALSE",
    "-DPXR_BUILD_TUTORIALS=FALSE",
    "-DPXR_BUILD_TESTS=FALSE",
]

MINIMAL_USD_CMAKE_OPTIONS = [
    "-DPXR_ENABLE_PYTHON_SUPPORT=TRUE",
    "-DPXR_ENABLE_MATERIALX_SUPPORT=TRUE",
    "-DPXR_BUILD_IMAGING=FALSE",
    "-DPXR_BUILD_USD_IMAGING=FALSE",
    "-DPXR_BUILD_USDVIEW=FALSE",
    "-DPXR_BUILD_EXAMPLES=FALSE",
    "-DPXR_BUILD_TUTORIALS=FALSE",
    "-DPXR_BUILD_TESTS=FALSE",
]


def read_supported_build_usd_flags(build_script: Path) -> set[str]:
    try:
        text = subprocess.check_output([sys.executable, str(build_script), "--help"], text=True, stderr=subprocess.STDOUT)
    except Exception:
        return set()
    return set(re.findall(r"(?<!\w)--[A-Za-z0-9][A-Za-z0-9_-]*", text))


def filter_supported_flags(flags: list[str], supported: set[str], *, strict: bool) -> list[str]:
    if not supported:
        return flags
    kept: list[str] = []
    skipped: list[str] = []
    for flag in flags:
        if flag in supported:
            kept.append(flag)
        else:
            skipped.append(flag)
    if skipped:
        message = "OpenUSD build_usd.py does not advertise these flags; skipped: " + ", ".join(skipped)
        if strict:
            raise RuntimeError(message)
        print("WARNING:", message)
    return kept


def copy_install_tree(install_dir: Path, package_usd_dir: Path) -> None:
    if not install_dir.exists():
        raise RuntimeError(f"OpenUSD install dir does not exist: {install_dir}")

    if package_usd_dir.exists():
        rmtree(package_usd_dir)

    ignore = shutil.ignore_patterns(
        "*.a",
        "*.la",
        "cmake",
        "pkgconfig",
        "__pycache__",
        "*.pyc",
        "*.pyo",
        ".DS_Store",
        # build_usd.py leaves its intermediate build/ and dependency src/ trees inside
        # the install prefix. Bundling them doubles size AND ships a second copy of every
        # plugInfo.json/dylib (e.g. usdMtlx), which makes the runtime load the plugin
        # library twice and abort ("multiple debug symbol definitions"). Never bundle them.
        "build",
        "src",
        # PXR_BUILD_TESTS installs a tests/ tree containing deliberately-malformed
        # plugInfo.json fixtures (e.g. testSdfMetaDataPlugInfo with "bad_1"/"bad_10"
        # entries). The bootstrap rglobs every plugInfo.json, so bundling these makes
        # plugin registration / validate spew SdfSchema errors and fail. Tests are not
        # part of the distributable runtime — never bundle them.
        "tests",
        # libtbbmalloc_proxy is an optional malloc replacement USD never loads. It carries a
        # dangling @rpath/libtbbmalloc dependency with no usable rpath, which trips wheel
        # repair tools for no benefit.
        "libtbbmalloc_proxy*.dylib",
        "libtbbmalloc_proxy*.so*",
    )
    shutil.copytree(install_dir, package_usd_dir, ignore=ignore)
    make_bundle_self_contained(package_usd_dir, install_dir)


def make_bundle_self_contained(package_usd_dir: Path, install_dir: Path) -> None:
    """Strip the absolute build-prefix rpath baked into the bundled binaries.

    OpenUSD builds its shared libraries with two LC_RPATHs: an absolute one pointing at
    the build prefix (``<install_dir>/lib``) and a relative ``@loader_path`` one. While the
    build prefix still exists on disk, the absolute rpath wins and the process loads a
    *second* copy of libraries such as ``libusd_usdMtlx`` from the build prefix, aborting
    with "multiple debug symbol definitions". Removing the absolute rpath makes the bundle
    resolve everything through its own ``@loader_path`` rpaths, i.e. fully self-contained.
    Because this is exactly the relocation the wheel needs, the OpenUSD wheel does not run
    delocate/auditwheel afterwards (those relocate libraries in a way that breaks the deeply
    nested ``_usd/lib/python/pxr`` layout).
    """
    bad_rpaths = [str((install_dir / sub).resolve()) for sub in ("lib", "lib64")]
    binaries = [p for p in package_usd_dir.rglob("*") if p.suffix in {".dylib", ".so"} or ".so." in p.name]

    if sys.platform == "darwin":
        otool = shutil.which("otool")
        int_tool = shutil.which("install_name_tool")
        codesign = shutil.which("codesign")
        if not (otool and int_tool):
            print("WARNING: otool/install_name_tool not found; bundle may not be self-contained")
            return
        changed = 0
        for f in binaries:
            try:
                rpaths = subprocess.check_output([otool, "-l", str(f)], text=True, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                continue
            touched = False
            for bad in bad_rpaths:
                if bad in rpaths:
                    subprocess.run([int_tool, "-delete_rpath", bad, str(f)], stderr=subprocess.DEVNULL)
                    touched = True
            if touched and codesign:
                # install_name_tool invalidates the code signature; re-sign ad-hoc or the
                # binary is SIGKILLed on load on Apple Silicon.
                subprocess.run([codesign, "--force", "--sign", "-", str(f)], stderr=subprocess.DEVNULL)
                changed += 1
        print(f"Relocated {changed} bundled binaries to be self-contained (removed build-prefix rpath)")
    elif sys.platform.startswith("linux"):
        patchelf = shutil.which("patchelf")
        if not patchelf:
            print("WARNING: patchelf not found; bundle may keep absolute build-prefix RPATHs")
            return
        changed = 0
        for f in binaries:
            try:
                cur = subprocess.check_output([patchelf, "--print-rpath", str(f)], text=True, stderr=subprocess.DEVNULL).strip()
            except subprocess.CalledProcessError:
                continue
            if not cur:
                continue
            # Keep only $ORIGIN-relative RPATHs. Drop every absolute entry: the build prefix
            # (<install>/lib), but also the build interpreter's lib dir that OpenUSD bakes in
            # (e.g. /opt/hostedtoolcache/Python/3.x/x64/lib) — that path doesn't exist on a
            # user's machine and makes the wheel non-portable. Bundled libs resolve each other
            # via $ORIGIN; libpython resolves from the loaded interpreter via its DT_NEEDED soname.
            kept = [e for e in cur.split(":") if e and (e.startswith("$ORIGIN") or e.startswith("${ORIGIN}"))]
            if kept != cur.split(":"):
                subprocess.run([patchelf, "--set-rpath", ":".join(kept), str(f)], stderr=subprocess.DEVNULL)
                changed += 1
        print(f"Relocated {changed} bundled binaries to be self-contained (kept only $ORIGIN RPATHs)")


def build_usd_cmake_options(profile: str, materialx_dir: Path | None, args: argparse.Namespace) -> list[str]:
    if profile == "full":
        opts = list(FULL_USD_CMAKE_OPTIONS)
    elif profile == "default":
        opts = list(DEFAULT_USD_CMAKE_OPTIONS)
    else:
        opts = list(MINIMAL_USD_CMAKE_OPTIONS)

    if materialx_dir:
        opts.append(f"-DMaterialX_DIR={materialx_dir}")

    # macOS ONLY: link the pxr binaries with -undefined dynamic_lookup instead of the
    # python.org Python.framework (whose absolute path doesn't exist on a Homebrew/conda
    # host), so the wheel imports on any CPython. On Linux this flag is NOT used: it would
    # leave Python symbols undefined in the .so and then break linking the standalone USD
    # executables (sdfdump, usdcat, the boost.python exec_, ...). Linux instead links
    # libpython by its bare SONAME (libpython3.x.so.1.0), which is already portable — it
    # resolves from the loaded interpreter, exactly like PyPI usd-core. Windows: no-op.
    if sys.platform == "darwin":
        opts.append("-DPXR_PY_UNDEFINED_DYNAMIC_LOOKUP=ON")

    if args.enable_vulkan:
        opts.extend(["-DPXR_ENABLE_VULKAN_SUPPORT=TRUE"])
    if args.enable_metal:
        opts.extend(["-DPXR_ENABLE_METAL_SUPPORT=TRUE"])
    if args.enable_osl:
        opts.extend(["-DPXR_ENABLE_OSL_SUPPORT=TRUE"])
    if args.enable_prman:
        opts.extend(["-DPXR_BUILD_PRMAN_PLUGIN=TRUE"])
    if args.enable_docs:
        opts.extend(
            [
                "-DPXR_BUILD_DOCUMENTATION=TRUE",
                "-DPXR_BUILD_HTML_DOCUMENTATION=TRUE",
                "-DPXR_BUILD_PYTHON_DOCUMENTATION=TRUE",
            ]
        )
    opts.extend(args.extra_usd_cmake_arg)
    return opts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build OpenUSD, force it to use a separately built latest MaterialX SDK, "
            "and copy the install tree into the Python wheel package"
        )
    )
    parser.add_argument("--repo-url", default=os.environ.get("OPENUSD_REPO_URL", DEFAULT_OPENUSD_REPO))
    parser.add_argument("--ref", default=os.environ.get("OPENUSD_REF", DEFAULT_OPENUSD_REF), help="OpenUSD tag/branch/sha")
    parser.add_argument("--source-dir", type=Path, default=REPO_ROOT / "_openusd_src")
    parser.add_argument("--install-dir", type=Path, default=REPO_ROOT / "_openusd_install")
    parser.add_argument("--package-usd-dir", type=Path, default=REPO_ROOT / "src" / "openusd_materialx" / "_usd")
    parser.add_argument("--clean", action="store_true", help="Delete source/install/package bundle dirs before building")
    parser.add_argument("--profile", choices=sorted(PROFILE_ARGS), default=os.environ.get("OPENUSD_BUILD_PROFILE", "full"))
    parser.add_argument("--strict-profile-flags", action="store_true", help="Fail if a profile flag is not supported by this OpenUSD ref")
    parser.add_argument("--build-target", default=os.environ.get("OPENUSD_BUILD_TARGET", ""), help="Optional OpenUSD build target, e.g. arm64 on macOS")
    parser.add_argument("--extra-build-usd-arg", action="append", default=[], help="Extra raw argument passed to build_usd.py")
    parser.add_argument("--extra-usd-cmake-arg", action="append", default=[], help="Extra raw CMake option passed to the USD build")
    parser.add_argument("--skip-build", action="store_true", help="Only copy an existing install-dir into the package")

    parser.add_argument("--materialx-repo-url", default=os.environ.get("MATERIALX_REPO_URL", DEFAULT_MATERIALX_REPO))
    parser.add_argument(
        "--materialx-ref",
        default=os.environ.get("MATERIALX_REF", DEFAULT_MATERIALX_REF),
        help="MaterialX tag/branch/sha. Default is main, i.e. latest source.",
    )
    parser.add_argument("--materialx-source-dir", type=Path, default=REPO_ROOT / "_materialx_src")
    parser.add_argument("--materialx-build-dir", type=Path, default=REPO_ROOT / "_materialx_for_usd_build")
    parser.add_argument(
        "--materialx-dir",
        type=Path,
        default=None,
        help="Use an existing MaterialXConfig.cmake directory instead of building MaterialX first",
    )
    parser.add_argument("--skip-materialx-build", action="store_true", help="Do not build MaterialX; rely on --materialx-dir or CMAKE_PREFIX_PATH")
    parser.add_argument("--with-materialx-oiio", action="store_true", help="Build latest MaterialX with OIIO support before USD")
    parser.add_argument("--with-materialx-ocio", action="store_true", help="Build latest MaterialX with OCIO support before USD")
    parser.add_argument("--with-materialx-viewer", action="store_true", help="Build MaterialX Viewer in the shared MaterialX SDK")
    parser.add_argument("--with-materialx-graph-editor", action="store_true", help="Build MaterialX Graph Editor in the shared MaterialX SDK")
    parser.add_argument("--no-materialx-slang-gen", action="store_true", help="Disable MaterialX Slang shader generation in the shared MaterialX SDK")

    parser.add_argument("--enable-vulkan", action="store_true", help="Also enable experimental Vulkan support; requires VULKAN_SDK")
    parser.add_argument("--enable-metal", action="store_true", default=sys.platform == "darwin", help="Enable Metal support on macOS")
    parser.add_argument("--enable-osl", action="store_true", help="Enable USD OSL support; requires OSL SDK discoverable by CMake")
    parser.add_argument("--enable-prman", action="store_true", help="Enable RenderMan plugin; requires RenderMan installation")
    parser.add_argument("--enable-docs", action="store_true", help="Enable USD docs; requires Doxygen and GraphViz")
    args = parser.parse_args()

    if args.clean:
        for path in [args.install_dir, args.package_usd_dir, args.materialx_build_dir]:
            if path.exists():
                rmtree(path)
        if args.source_dir.exists() and args.ref != "none":
            rmtree(args.source_dir)
        if args.materialx_source_dir.exists() and not args.skip_materialx_build and args.materialx_dir is None:
            rmtree(args.materialx_source_dir)

    materialx_cmake_dir: Path | None = args.materialx_dir

    if not args.skip_build:
        if not args.skip_materialx_build and materialx_cmake_dir is None:
            # Install latest MaterialX into the same prefix that OpenUSD will use. This
            # both satisfies build_usd.py's dependency check and ensures the wheel bundles
            # the exact MaterialX libraries that usdMtlx links against.
            build_materialx(
                repo_url=args.materialx_repo_url,
                ref=args.materialx_ref,
                source_dir=args.materialx_source_dir,
                build_dir=args.materialx_build_dir,
                install_dir=args.install_dir,
                clean=False,
                skip_checkout=False,
                build_python=True,
                build_viewer=args.with_materialx_viewer,
                build_graph_editor=args.with_materialx_graph_editor,
                build_tests=False,
                build_docs=False,
                build_oiio=args.with_materialx_oiio,
                build_ocio=args.with_materialx_ocio,
                build_osl=True,
                build_mdl=True,
                build_glsl=True,
                build_msl=True,
                build_slang=not args.no_materialx_slang_gen,
            )
            materialx_cmake_dir = find_materialx_config_dir(args.install_dir)
            print(f"Using latest MaterialX for OpenUSD: {materialx_cmake_dir}")

        if args.ref != "none":
            clone_or_update(args.repo_url, args.ref, args.source_dir)
        build_script = args.source_dir / "build_scripts" / "build_usd.py"
        if not build_script.exists():
            raise RuntimeError(f"Could not find build_usd.py at {build_script}")

        supported_flags = read_supported_build_usd_flags(build_script)
        profile_args = filter_supported_flags(PROFILE_ARGS[args.profile], supported_flags, strict=args.strict_profile_flags)

        if args.enable_vulkan and "VULKAN_SDK" not in os.environ:
            raise RuntimeError("--enable-vulkan was requested, but VULKAN_SDK is not set")

        usd_cmake_options = build_usd_cmake_options(args.profile, materialx_cmake_dir, args)
        cmd = [sys.executable, str(build_script), *profile_args]
        if args.build_target:
            cmd.extend(["--build-target", args.build_target])
        if usd_cmake_options:
            # Use the --build-args=VALUE form (single argv token). build_usd.py's
            # --build-args has nargs="*", so the space form ("--build-args", "USD,...")
            # greedily swallows the trailing install_dir positional and fails with
            # "the following arguments are required: install_dir".
            cmd.append("--build-args=USD," + " ".join(shlex.quote(opt) for opt in usd_cmake_options))
        cmd.extend(args.extra_build_usd_arg)
        cmd.append(str(args.install_dir))

        env = os.environ.copy()
        env.setdefault("PYTHONNOUSERSITE", "1")
        if materialx_cmake_dir is not None:
            prepend_env_path(env, "CMAKE_PREFIX_PATH", args.install_dir)
        run(cmd, cwd=args.source_dir, env=env)

    copy_install_tree(args.install_dir, args.package_usd_dir)
    print(f"Bundled OpenUSD + MaterialX install copied to: {args.package_usd_dir}")
    print("Next:")
    print("  python scripts/validate_bundle.py")
    print("  mkdir -p wheelhouse")
    print("  python -m build --wheel --outdir wheelhouse")


if __name__ == "__main__":
    main()
