# Contribution Guide

## Branches

- `main`: production-ready code. No direct pushes.
- `develop`: integration branch for daily development.
- `feature/<scope>-<name>`: feature work.
- `fix/<scope>-<name>`: bug fixes.
- `hotfix/<scope>-<name>`: emergency production fixes. Merge to both `main` and `develop`.

Create work branches from the latest `develop`. Open a pull request for every merge. Prefer squash merge after review and CI pass.

## Commit messages

Use Conventional Commits:

`<type>(<scope>): <summary>`

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `build`, `chore`.

Examples:

- `feat(campaign): add approval handoff`
- `fix(web): prevent repeated localization labels`
- `docs(architecture): update deployment topology`

Each commit should represent one complete change.

## Before opening a PR

- Run `git diff --check`.
- Run `node --check` for JavaScript under `apps/web-v32`.
- Run API tests under `services/platform-api`.
- Do not commit `.env`, credentials, tokens, database files, logs, or dependency directories.
- Update `docs` and `VERSION.md` when API, database, or deployment behavior changes.

## Ownership boundaries

- Frontend: `apps/web-v32` and `apps/web`.
- API, agent runtime, model configuration, and ontology: `services/platform-api`.
- Container and reverse proxy: `compose.yml`, Dockerfiles, and nginx configs.
- Architecture decisions: `docs/adr`.

Do not overwrite another contributor's uncommitted work. Keep changes within the agreed ownership boundary.
