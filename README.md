# China Eastern Intelligent Marketing Platform

Production-oriented system for airline marketing operators, product operators,
approvers, and effect analysts.

The current release provides tenant-isolated marketing operations, governed
ontology imports, dynamic graph exploration, configurable model providers, and
platform-level tenant and user administration.

## Structure

```text
apps/web                 React + TypeScript operations console
services/platform-api    FastAPI business, agent, and ontology services
docs                     Architecture and domain decisions
```

## Reference designs

- The agent runtime borrows plugin registration, event logs, governed tool
  execution, and replaceable loops from DeepSeek Harness.
- The ontology service borrows entity resolution, relationship construction,
  constraints, provenance, and decision records from Semantica.
- Neither reference repository is a runtime dependency.

## Local development

```powershell
cd services/platform-api
python -m uvicorn app.main:app --reload --port 8800
```

```powershell
cd apps/web
pnpm install
pnpm dev --host 127.0.0.1 --port 8780
```

## Production build

The public deployment is hosted below the `/ceair-marketing/` path. Build the
frontend with matching base paths:

```powershell
$env:VITE_BASE_PATH='/ceair-marketing/'
$env:VITE_API_BASE='/ceair-marketing'
npm run build
```

Production containers are managed with `compose.yml`; PostgreSQL and the API
remain private, while the web container is exposed through the existing
reverse proxy.

## Git workflow

The system root is a Git repository. Keep runtime secrets in `.env` only; commit `.env.example` and source changes. Use small commits by change type, for example `fix(web): prevent repeated localization labels`, and run the API tests plus frontend syntax/build checks before pushing.

## Production CI/CD

A push to `main` triggers `.github/workflows/deploy-production.yml`. The workflow runs frontend syntax checks and API tests, uploads an immutable release package to Tencent Cloud over SSH, preserves the server `.env`, rebuilds Docker Compose services, checks `/health`, and updates `/opt/ceair-marketing/current` only after the new release is healthy.

Configure the `production` GitHub environment with `DEPLOY_HOST`, `DEPLOY_PORT`, `DEPLOY_USER`, and `DEPLOY_SSH_KEY`. See `docs/deployment-ci-cd.md` for server prerequisites and rollback steps.
