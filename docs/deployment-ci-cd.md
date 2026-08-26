# Production CI/CD

## Flow

A push to `main` runs JavaScript checks and API tests first. Only after the checks pass does GitHub Actions package the repository, upload it to Tencent Cloud over SSH, create an immutable release directory, preserve the server `.env`, rebuild the Docker Compose services, run the web health check, and move `/opt/ceair-marketing/current` to the new release.

The workflow keeps the previous five release directories for rollback. The database volume is managed by Docker Compose and is not deleted during deployment.

## GitHub Actions secrets

Create a GitHub environment named `production`, then add these secrets:

- `DEPLOY_HOST`: `124.220.225.29`
- `DEPLOY_PORT`: `22`
- `DEPLOY_USER`: deployment user, preferably a dedicated non-root user
- `DEPLOY_SSH_KEY`: private OpenSSH key whose public key is installed on the server

Do not put the server password in GitHub Actions, workflow files, or the repository.

## Server prerequisites

The deployment user must be able to:

- write under `/opt/ceair-marketing`
- run `sudo docker compose` without an interactive password prompt
- access the Docker daemon
- reach the existing `current_default` Docker network

The first production setup must create `/opt/ceair-marketing/.env` with values based on `.env.example`, including the production database password, token secret, encryption key, admin password, and basic-auth password.

## Rollback

To roll back, stop the pipeline and point the symlink to a previous release, then restart Compose:

```bash
cd /opt/ceair-marketing
sudo ln -sfn releases/<previous-sha> current
cd current
sudo docker compose up -d --remove-orphans
curl -fsS http://127.0.0.1:8088/health
```

A rollback must be recorded as an issue or deployment note.
