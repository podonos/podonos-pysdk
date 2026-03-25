---
name: release-pypi
version: 1.0.0
description: |
  Release the podonos Python SDK to PyPI.
  Trigger: "release", "publish to pypi", "pypi release", "ship sdk"
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - Grep
  - Glob
  - AskUserQuestion
---

# Release podonos SDK to PyPI

This skill automates the full release process for the podonos Python SDK. It handles
version bumping, testing, building, uploading to Test PyPI (always), user confirmation,
uploading to Production PyPI, verification, git tagging, and GitHub Release creation.

## Step 0: Parse Arguments

Parse `{{ARGUMENTS}}` to determine the release type:

| Input | Behavior |
|-------|----------|
| *(empty)* | Release the current version as-is (no bump) |
| `patch` | Bump patch: e.g., 0.35.0 -> 0.35.1 |
| `minor` | Bump minor: e.g., 0.35.0 -> 0.36.0 |
| `major` | Bump major: e.g., 0.35.0 -> 1.0.0 |
| `X.Y.Z` | Bump to explicit version (must be > current) |

Validate the input:
- If the argument is not empty and does not match `patch`, `minor`, `major`, or `^\d+\.\d+\.\d+$`, STOP:
  "Invalid argument: '{input}'. Usage: /release-pypi [patch|minor|major|X.Y.Z]"

Store the result as `TARGET_VERSION` (one of: `patch`, `minor`, `major`, an explicit
version string, or empty for no bump).

## Step 1: Pre-flight Checks

Run ALL of these checks. Stop on any failure unless noted otherwise.

### 1a. Clean working tree
```bash
git status --porcelain
```
If output is non-empty, STOP: "Working tree is not clean. Commit or stash changes first."

### 1b. Branch check
```bash
git branch --show-current
```
If not `main`, warn the user and ask via AskUserQuestion:
- A) Continue on this branch
- B) Abort — switch to main first

### 1c. Up to date with remote
```bash
git fetch origin main && git diff --quiet HEAD origin/main
```
If diverged, STOP: "Local branch is behind origin/main. Pull first."

### 1d. PyPI credentials
```bash
test -f ~/.pypirc && echo "OK" || echo "MISSING"
```
If MISSING, STOP: "~/.pypirc not found. Create it with your PyPI and Test PyPI API tokens.
See: https://packaging.python.org/en/latest/guides/distributing-packages-using-setuptools/#create-an-account"

### 1e. Unit tests (non-negotiable)
```bash
.venv/bin/coverage run --source=./podonos -m pytest && .venv/bin/coverage report
```
NOTE: `--source` is a coverage flag, NOT a pytest flag. It must come before `-m pytest`.
If tests fail, STOP. No skip flag, no exceptions, not even for hotfixes.

Parse the coverage percentage from the output. If coverage < 70%, warn:
"Coverage is {X}% (minimum: 70%)." Ask via AskUserQuestion:
- A) Continue anyway
- B) Abort — add more tests first

### 1f. Build tools

NOTE: Always use `.venv/bin/python` — the system `python` may not exist or lack required modules.

```bash
.venv/bin/python -m build --version && .venv/bin/python -m twine --version && .venv/bin/coverage --version
```
If any is missing, install them: `.venv/bin/python -m pip install build twine coverage`

NOTE: The venv may lack pip. If so, bootstrap it first:
```bash
.venv/bin/python -m ensurepip --upgrade
```

### 1g. Check if version already exists on PyPI
```bash
.venv/bin/python -m pip index versions podonos
```
If CURRENT_VERSION (or intended RELEASE_VERSION) already exists on PyPI and no bump was
requested, warn the user early: "v{VERSION} already exists on PyPI. You must bump the
version." Ask for patch/minor/major bump before proceeding.

### 1h. Integration tests (optional)
Ask via AskUserQuestion:
- A) Run integration tests
- B) Skip integration tests

**Do NOT use `run_integration_tests.sh`** — it has multiple unresolved issues:
- Requires `conda` which may not be installed (`brew install miniconda` to install)
- Even if conda is installed, TOS must be accepted first
- `conda activate` doesn't work in non-interactive scripts without `conda init`
- Script lacks `set -e` — silently swallows all errors and prints success regardless
- The script doesn't pass `--api_key` to `integration_test_all.py`

**Instead**, run the integration test directly. Pull the API key from 1Password:
```bash
API_KEY=$(op read "op://Engineering/DEV Podonos API Key/password")
.venv/bin/python tests/integration/integration_test_all.py --api_key="$API_KEY"
```
This must be run from the project root directory. If the `op` CLI is not installed or
not authenticated, ask the user for the API key manually.

If skipped, note "Integration tests: skipped" for the summary.

## Step 2: Version Verification (or Bump)

### Read current version
Extract versions using grep (never hardcode line numbers):
```bash
grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)".*/\1/'
grep '__version__' podonos/__init__.py | sed 's/.*"\(.*\)".*/\1/'
```
Verify both match. If they don't, STOP: "Version mismatch between pyproject.toml and __init__.py"

Store as `CURRENT_VERSION`.

### If TARGET_VERSION is provided (bump needed)

Calculate `RELEASE_VERSION` from `CURRENT_VERSION` and `TARGET_VERSION`:
- `patch`: increment the third number (0.35.0 -> 0.35.1)
- `minor`: increment the second number, reset third (0.35.0 -> 0.36.0)
- `major`: increment the first number, reset second and third (0.35.0 -> 1.0.0)
- Explicit `X.Y.Z`: validate format matches `^\d+\.\d+\.\d+$`, verify > CURRENT_VERSION

Update both files using the Edit tool:
- In `pyproject.toml`: replace `version = "{CURRENT_VERSION}"` with `version = "{RELEASE_VERSION}"`
- In `podonos/__init__.py`: replace `__version__ = "{CURRENT_VERSION}"` with `__version__ = "{RELEASE_VERSION}"`

### Auto-generate changelog
```bash
git log $(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)..HEAD --oneline
```
If the git log returns no commits, warn: "No commits found since last tag. Changelog will be empty."
Ask via AskUserQuestion:
- A) Proceed with empty changelog
- B) Abort — make some changes first

Rewrite the raw git log entries into clean, human-readable bullet points. Focus on
user-facing changes, group related commits, and remove noise (merge commits, CI fixes, etc.).

Prepend to `History.md` at the top of the file:
```
## {RELEASE_VERSION}

- {changelog entry 1}
- {changelog entry 2}
...

```

Store the changelog entries as `CHANGELOG_ENTRY` for use in the GitHub Release later.

### Commit locally (do NOT push yet)
```bash
git add pyproject.toml podonos/__init__.py History.md
git commit -m "Release v{RELEASE_VERSION}"
```
Do NOT push. Push happens in Step 8, only after PyPI upload succeeds.

### If no TARGET_VERSION (no bump)
Store `CURRENT_VERSION` as `RELEASE_VERSION`. No files to modify.
Read the latest section from `History.md` (everything under the first `## X.Y.Z` heading
until the next `##` heading) and store as `CHANGELOG_ENTRY`.

## Step 2.5: Local Install Sanity Check

Verify the package installs and imports correctly before building:
```bash
.venv/bin/python -m venv /tmp/podonos-pre-check && \
source /tmp/podonos-pre-check/bin/activate && \
pip install -e . && \
python -c "import podonos; print(podonos.__version__)" && \
deactivate
rm -rf /tmp/podonos-pre-check
```

NOTE: Use `pip install -e .` (not `pip install -r requirements.txt`) — the package should
install all its own dependencies automatically via `pyproject.toml [project.dependencies]`.

If import fails or version doesn't match `RELEASE_VERSION`, STOP:
"Local install check failed. Fix the issue before proceeding."

## Step 3: Build

```bash
rm -rf dist/ podonos.egg-info/
.venv/bin/python -m build
ls dist/
```

Verify that `dist/` contains both a `.tar.gz` and a `.whl` file.
If either is missing, STOP: "Build failed — check output above."

## Step 4: Upload to Test PyPI

```bash
.venv/bin/python -m twine upload --repository testpypi dist/*
```

Wait for propagation:
```bash
sleep 10
```

Verify installation from Test PyPI in a temp venv:
```bash
.venv/bin/python -m venv /tmp/podonos-release-test && \
source /tmp/podonos-release-test/bin/activate && \
pip install --no-cache-dir --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ podonos && \
python -c "import podonos; print(podonos.__version__)" && \
deactivate
rm -rf /tmp/podonos-release-test
```

NOTE: Use `--index-url` (not `-i`) for Test PyPI, plus `--extra-index-url` pointing to
production PyPI. This lets pip find the podonos package on Test PyPI while resolving its
dependencies (glog, soundfile, etc.) from production PyPI. Using `-i` alone will fail
because Test PyPI doesn't host all dependency packages.

If install fails due to missing dependencies on Test PyPI (common — Test PyPI doesn't
have all packages), warn but do NOT block. Note: "Test PyPI install had dependency issues
(expected — Test PyPI is incomplete). The package itself uploaded successfully."

If twine upload fails with "File already exists", warn:
"This version already exists on Test PyPI. This often happens when re-running a release.
Bump to a new version (e.g., /release-pypi patch) or delete the existing Test PyPI version
at https://test.pypi.org/manage/project/podonos/"

If twine upload fails for other reasons (auth/network), STOP with guidance.

## Step 5: User Confirmation Gate (MANDATORY)

**This step is non-negotiable.** Always ask before uploading to production PyPI.

Use AskUserQuestion to present a release summary:

```
Ready to release podonos v{RELEASE_VERSION} to production PyPI.

- Unit tests: PASSED (coverage: {X}%)
- Integration tests: {PASSED|SKIPPED}
- Local install check: PASSED
- Build: OK ({list .tar.gz and .whl filenames})
- Test PyPI upload: OK
- Test PyPI install verification: {OK|DEPS_MISSING (expected)}

Options:
A) Yes, release v{RELEASE_VERSION} to production PyPI
B) No, abort (artifacts remain in dist/)
```

If user chooses B, STOP: "Release aborted. Built artifacts are still in dist/ if you
want to inspect them. The version bump commit is local only (not pushed)."

If a version bump commit was made, offer to revert it:
- A) Revert the version bump commit (`git reset --soft HEAD~1`)
- B) Keep the commit for later

## Step 6: Upload to Production PyPI

```bash
.venv/bin/python -m twine upload dist/*
```

If this fails with an auth error, provide guidance:
"Upload failed. Check that ~/.pypirc has a valid [pypi] section with your API token.
Generate one at: https://pypi.org/manage/account/token/"

If this fails with "File already exists", warn:
"This version already exists on PyPI. You cannot re-upload the same version.
Bump to a new version and try again."

## Step 7: Post-release Verification

Wait for PyPI propagation (30 seconds — 15 is often not enough):
```bash
sleep 30
```

Verify installation from production PyPI in a temp venv:
```bash
.venv/bin/python -m venv /tmp/podonos-release-verify && \
source /tmp/podonos-release-verify/bin/activate && \
pip install --no-cache-dir podonos=={RELEASE_VERSION} && \
python -c "import podonos; print(podonos.__version__)" && \
deactivate
rm -rf /tmp/podonos-release-verify
```

NOTE: Pin the version with `podonos=={RELEASE_VERSION}` to ensure you're testing the
new release, not a cached older version.

**IMPORTANT**: Do NOT pre-install dependencies (e.g., `pip install -r requirements.txt`)
before installing from PyPI. The whole point of this check is to verify that
`pip install podonos` automatically resolves all dependencies declared in
`pyproject.toml [project.dependencies]`. If dependencies are missing from pyproject.toml,
this step should catch it.

Verify the installed version matches `RELEASE_VERSION`.
If it doesn't match, warn: "Installed version {X} doesn't match expected {RELEASE_VERSION}.
PyPI may still be propagating. Check manually: pip install podonos=={RELEASE_VERSION}"

## Step 8: Git Tag, GitHub Release, and Push

Only run this step after Step 7 succeeds.

### Create git tag
```bash
git tag -a "v{RELEASE_VERSION}" -m "Release v{RELEASE_VERSION}"
```

### Push to remote

**Branch protection**: The `main` branch has branch protection rules that prevent direct
pushes. Instead of `git push origin main`, create a release branch and PR:

```bash
git checkout -b release/v{RELEASE_VERSION}
git push origin release/v{RELEASE_VERSION} --follow-tags
```

Then create a PR:
```bash
gh pr create --title "Release v{RELEASE_VERSION}" \
  --body "Release v{RELEASE_VERSION} to PyPI" \
  --base main --head release/v{RELEASE_VERSION}
```

If direct push to main works (no branch protection), that's fine too. But be prepared
for it to fail and fall back to the PR approach.

Do NOT force push.

### Post-merge cleanup (if PR was used)
After the PR is merged, switch back to main and clean up:
```bash
git checkout main && git pull origin main && git branch -d release/v{RELEASE_VERSION}
```

### Create GitHub Release
```bash
gh release create "v{RELEASE_VERSION}" \
  --title "v{RELEASE_VERSION}" \
  --notes "{CHANGELOG_ENTRY}"
```

GitHub automatically marks this as the "Latest" release. The BE can query
`https://api.github.com/repos/podonos/podonos-pysdk/releases/latest` to get the
current SDK version programmatically.

If `gh` CLI is not available or not authenticated, warn but don't fail:
"GitHub Release not created (gh CLI unavailable). Create manually at:
https://github.com/podonos/podonos-pysdk/releases/new?tag=v{RELEASE_VERSION}"

## Step 9: Summary

Print the final release summary:

```
=== Release Complete: podonos v{RELEASE_VERSION} ===

PyPI:           https://pypi.org/project/podonos/{RELEASE_VERSION}/
Test PyPI:      https://test.pypi.org/project/podonos/{RELEASE_VERSION}/
GitHub Release: https://github.com/podonos/podonos-pysdk/releases/tag/v{RELEASE_VERSION}
Git Tag:        v{RELEASE_VERSION}

Install: pip install podonos=={RELEASE_VERSION}

Unit tests:        PASSED (coverage: {X}%)
Integration tests: {PASSED|SKIPPED}

Post-release checklist:
- [ ] Update @Get("version/sdk") in the BE API with the new version
{If major version bump:}
- [ ] **BREAKING CHANGE** — updating @Get("version/sdk") in the BE API is likely required
- [ ] Notify users of breaking changes
```
