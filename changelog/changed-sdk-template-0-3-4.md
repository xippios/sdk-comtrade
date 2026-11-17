- Adopts sdk-template v0.3.4, from v0.3.1, with conventions 1.27 and no new core minor: the
  floor stays `xippios-core~=0.3.0`. The README lists the package's documents under
  `## Documents`, and `CLAUDE.md` holds the rules that `.claude/family.md` carried, which
  leaves with `/adopt-release`. Changelog entries are fragments under `changelog/`, the
  package's own decisions go into `docs/adr/` with the index `scripts/adr_index.py` writes,
  and a pull request runs the organization's checks from `organization.yml`, where
  `gates.yml` was, on its opening, a push, a reopening and an edit.
  (https://github.com/xippios/sdk-template/releases/tag/v0.3.4,
  https://github.com/xippios/sdk-comtrade/issues/18)
