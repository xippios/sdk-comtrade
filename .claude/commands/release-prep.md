Prepare the release of xippios-comtrade: $ARGUMENTS

Expected argument: the new version, e.g. `0.2.0`. Tagging and publishing are human
actions; this command only prepares the PR.

1. Work on a branch `chore/release-<version>`.
2. SemVer check: pre-1.0, a breaking change bumps the minor. An upstream API change that
   changed our public surface is a breaking change. Read `CHANGELOG.md` Unreleased and
   confirm the version matches what is in it; say so in the PR if it does not.
3. `pyproject.toml`: set `version`. The publish workflow refuses a tag that does not
   equal it.
4. `CHANGELOG.md`: move everything under Unreleased into a `## [<version>] - <today>`
   section, leave an empty Unreleased above it.
5. README: the status table reflects what this version covers; install snippets are
   current.
6. Run the full suite: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`.
   If live tests can run (`XIPPIOS_LIVE_TESTS=1`), run them too and report the result.
7. Open the PR with the definition-of-done checklist. Then stop and print the human
   steps: merge, `git tag v<version>` on `main`, push the tag, approve the `pypi`
   environment run in the Actions tab.
