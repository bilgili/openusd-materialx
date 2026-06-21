from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

try:
    from _build_utils import cmake_generator_args, clone_or_update, run
except ImportError:  # pragma: no cover
    from scripts._build_utils import cmake_generator_args, clone_or_update, run

DEFAULT_MATERIALX_REPO = "https://github.com/AcademySoftwareFoundation/MaterialX.git"
DEFAULT_MATERIALX_REF = "main"


def materialx_cmake_options(
    install_dir: Path,
    *,
    build_python: bool = True,
    build_viewer: bool = False,
    build_graph_editor: bool = False,
    build_tests: bool = False,
    build_docs: bool = False,
    build_oiio: bool = False,
    build_ocio: bool = False,
    build_osl: bool = True,
    build_mdl: bool = True,
    build_glsl: bool = True,
    build_msl: bool = True,
    build_slang: bool = True,
    extra_cmake_arg: list[str] | None = None,
) -> list[str]:
    """Return CMake options for a broad MaterialX build.

    Unknown options are tolerated by CMake as warnings on older/newer MaterialX trees,
    which makes this useful across MaterialX releases.
    """

    on = "ON"
    off = "OFF"
    opts = [
        f"-DCMAKE_INSTALL_PREFIX={install_dir}",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DMATERIALX_BUILD_SHARED_LIBS=ON",
        f"-DMATERIALX_BUILD_PYTHON={on if build_python else off}",
        f"-DMATERIALX_INSTALL_PYTHON={on if build_python else off}",
        f"-DMATERIALX_PYTHON_EXECUTABLE={sys.executable}",
        f"-DMATERIALX_BUILD_VIEWER={on if build_viewer else off}",
        f"-DMATERIALX_BUILD_GRAPH_EDITOR={on if build_graph_editor else off}",
        f"-DMATERIALX_BUILD_TESTS={on if build_tests else off}",
        f"-DMATERIALX_BUILD_DOCS={on if build_docs else off}",
        f"-DMATERIALX_BUILD_OIIO={on if build_oiio else off}",
        f"-DMATERIALX_BUILD_OCIO={on if build_ocio else off}",
        f"-DMATERIALX_BUILD_GEN_OSL={on if build_osl else off}",
        f"-DMATERIALX_BUILD_GEN_MDL={on if build_mdl else off}",
        f"-DMATERIALX_BUILD_GEN_GLSL={on if build_glsl else off}",
        f"-DMATERIALX_BUILD_GEN_MSL={on if build_msl else off}",
        f"-DMATERIALX_BUILD_GEN_SLANG={on if build_slang else off}",
    ]
    if extra_cmake_arg:
        opts.extend(extra_cmake_arg)
    return opts


def build_materialx(
    *,
    repo_url: str,
    ref: str,
    source_dir: Path,
    build_dir: Path,
    install_dir: Path,
    clean: bool = False,
    skip_checkout: bool = False,
    build_python: bool = True,
    build_viewer: bool = False,
    build_graph_editor: bool = False,
    build_tests: bool = False,
    build_docs: bool = False,
    build_oiio: bool = False,
    build_ocio: bool = False,
    build_osl: bool = True,
    build_mdl: bool = True,
    build_glsl: bool = True,
    build_msl: bool = True,
    build_slang: bool = True,
    extra_cmake_arg: list[str] | None = None,
) -> None:
    if clean:
        for path in [build_dir, install_dir]:
            if path.exists():
                shutil.rmtree(path)
        if source_dir.exists() and not skip_checkout:
            shutil.rmtree(source_dir)

    if not skip_checkout:
        clone_or_update(repo_url, ref, source_dir, recursive=True)

    if not (source_dir / "CMakeLists.txt").exists():
        raise RuntimeError(f"MaterialX source does not look valid: {source_dir}")

    build_dir.mkdir(parents=True, exist_ok=True)
    install_dir.mkdir(parents=True, exist_ok=True)

    configure_cmd = [
        "cmake",
        "-S",
        str(source_dir),
        "-B",
        str(build_dir),
        *cmake_generator_args(),
        *materialx_cmake_options(
            install_dir,
            build_python=build_python,
            build_viewer=build_viewer,
            build_graph_editor=build_graph_editor,
            build_tests=build_tests,
            build_docs=build_docs,
            build_oiio=build_oiio,
            build_ocio=build_ocio,
            build_osl=build_osl,
            build_mdl=build_mdl,
            build_glsl=build_glsl,
            build_msl=build_msl,
            build_slang=build_slang,
            extra_cmake_arg=extra_cmake_arg,
        ),
    ]
    run(configure_cmd)
    run(["cmake", "--build", str(build_dir), "--config", "Release", "--target", "install", "-j", str(os.cpu_count() or 2)])


def find_materialx_config_dir(install_dir: Path) -> Path:
    candidates = list(install_dir.rglob("MaterialXConfig.cmake"))
    if not candidates:
        raise RuntimeError(
            f"Could not find MaterialXConfig.cmake under {install_dir}. "
            "Check that MaterialX installed correctly."
        )
    # Prefer the canonical CMake package directory.
    candidates.sort(key=lambda p: ("cmake" not in str(p).lower(), len(str(p))))
    return candidates[0].parent
