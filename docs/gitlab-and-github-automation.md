# CI automation plan

Both CI systems build the two wheels from **variable upstream versions** and stamp the
**wheel version from the git tag**. Wheels are exposed as **job artifacts** (no package
registry publishing is configured).

## Variables

| Variable | Meaning | Default |
| --- | --- | --- |
| `OPENUSD_REF` | OpenUSD tag/branch/sha | `v26.05` |
| `MATERIALX_REF` | MaterialX tag/branch/sha (`main` = latest source) | `main` |
| `OPENUSD_BUILD_PROFILE` | `full` \| `default` \| `minimal` | `full` |
| `BUILD_PKG` | `both` \| `openusd-materialx` \| `materialx-python` | `both` |
| `PACKAGE_VERSION` | wheel version; CI derives it from the tag | `0.0.0` when untagged |

## Wheel versioning

The wheel version is read from `PACKAGE_VERSION` by each package's `setup.py`. CI sets it
from the pushed git tag, stripping a leading `v`:

```text
git tag v1.2.3 && git push --tags   ->   openusd_materialx-1.2.3-...whl
                                         materialx_python_standalone-1.2.3-...whl
```

Untagged manual runs build `0.0.0`. For a one-off local build:

```bash
PACKAGE_VERSION=1.2.3 python -m build --wheel --outdir wheelhouse/raw/materialx packages/materialx-python
```

For reproducible builds, set `MATERIALX_REF` / `OPENUSD_REF` to a tag or commit SHA rather
than `main`.

## GitHub

1. Push this repo to GitHub.
2. To cut a release: push a tag, e.g. `git tag v1.2.3 && git push origin v1.2.3`. The
   **Build wheels** workflow runs automatically and stamps `1.2.3`.
3. To experiment without a tag: **Actions > Build wheels > Run workflow** and set the
   `package`, `openusd_ref`, `materialx_ref`, `openusd_profile`, and optional
   `package_version` inputs.
4. Download the per-job wheel artifacts (`wheels-<pkg>-<os>-py<ver>`).

Each matrix job builds the selected wheel(s) across ubuntu-22.04, macos-13, macos-14, and
windows-2022 for Python 3.10–3.12, smoke-tests the repaired wheel in a clean venv, then
uploads `wheelhouse/*.whl`.

## GitLab

1. Push this repo to GitLab.
2. Configure Linux, macOS, and Windows runners (Windows needs Visual Studio Build Tools).
3. Override variables if needed via project **CI/CD > Variables**, or per run in
   **Build > Pipelines > Run pipeline**:

   ```text
   OPENUSD_REF=v26.05
   MATERIALX_REF=main
   OPENUSD_BUILD_PROFILE=full
   BUILD_PKG=both
   ```

4. To cut a release, push a tag (`v1.2.3`). Pipelines run on **tags** and on **manual**
   ("Run pipeline") runs only — not on every push, because full OpenUSD builds are heavy.
5. Download wheel artifacts from the job pages.

Shared GitLab SaaS runners usually cover Linux only; macOS and Windows need configured
runners depending on your plan.

## Adding a package registry later

This pipeline stops at artifacts. To publish, add a step after the build:

- **GitLab PyPI registry:** `twine upload --repository-url
  "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/pypi" wheelhouse/*.whl` with
  `TWINE_USERNAME=gitlab-ci-token` / `TWINE_PASSWORD=$CI_JOB_TOKEN`.
- **GitHub Releases:** attach `wheelhouse/*.whl` with `softprops/action-gh-release` on tag
  pushes.
