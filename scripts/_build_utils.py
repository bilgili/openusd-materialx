from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(cwd) if cwd else None, env=env)


def clone_or_update(repo_url: str, ref: str, source_dir: Path, *, recursive: bool = True) -> None:
    """Clone or update a git checkout.

    `ref` may be a branch, tag, or commit SHA. We first try a shallow branch/tag clone and
    fall back to a fetch+checkout path for arbitrary SHAs.
    """

    if source_dir.exists() and (source_dir / ".git").exists():
        run(["git", "fetch", "--tags", "--depth", "1", "origin", ref], cwd=source_dir)
        run(["git", "checkout", ref], cwd=source_dir)
        if recursive:
            run(["git", "submodule", "update", "--init", "--recursive"], cwd=source_dir)
        return

    if source_dir.exists():
        raise RuntimeError(f"source dir exists but is not a git checkout: {source_dir}")

    cmd = ["git", "clone", "--depth", "1"]
    if recursive:
        cmd.append("--recursive")
    cmd.extend(["--branch", ref, repo_url, str(source_dir)])
    try:
        run(cmd)
    except subprocess.CalledProcessError:
        # A commit SHA cannot always be shallow-cloned with --branch.
        if source_dir.exists():
            shutil.rmtree(source_dir)
        run(["git", "clone", "--depth", "1", repo_url, str(source_dir)])
        run(["git", "fetch", "--tags", "--depth", "1", "origin", ref], cwd=source_dir)
        run(["git", "checkout", ref], cwd=source_dir)
        if recursive:
            run(["git", "submodule", "update", "--init", "--recursive"], cwd=source_dir)


def cmake_generator_args() -> list[str]:
    """Prefer Ninja when installed, otherwise let CMake choose the platform default."""
    if shutil.which("ninja") or shutil.which("ninja-build"):
        return ["-G", "Ninja"]
    return []


def copy_tree(src: Path, dst: Path, *, ignore: shutil.IgnorePattern | None = None) -> None:
    if not src.exists():
        raise RuntimeError(f"Source directory does not exist: {src}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)


def remove_paths(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


def prepend_env_path(env: dict[str, str], name: str, path: Path) -> None:
    existing = env.get(name, "")
    values = [str(path)]
    if existing:
        values.append(existing)
    env[name] = os.pathsep.join(values)
