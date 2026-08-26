from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def migrate_legacy_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table in ("campaigns", "model_providers", "agent_runs"):
            if table not in existing:
                continue
            columns = {column["name"] for column in inspector.get_columns(table)}
            if "tenant_id" not in columns:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER"))
        if "users" in existing:
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            if "is_platform_admin" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN is_platform_admin BOOLEAN DEFAULT FALSE"))


def assign_legacy_records(engine: Engine, tenant_id: int) -> None:
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in ("campaigns", "model_providers", "agent_runs"):
            if table not in inspector.get_table_names():
                continue
            columns = {column["name"] for column in inspector.get_columns(table)}
            if "tenant_id" in columns:
                connection.execute(text(f"UPDATE {table} SET tenant_id = :tenant_id WHERE tenant_id IS NULL"), {"tenant_id": tenant_id})


def enforce_postgres_tenant_constraints(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    statements = [
        "ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_campaign_id_fkey",
        "ALTER TABLE campaigns ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS campaigns_pkey",
        "ALTER TABLE campaigns ADD CONSTRAINT campaigns_pkey PRIMARY KEY (tenant_id, id)",
        "ALTER TABLE model_providers ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE model_providers DROP CONSTRAINT IF EXISTS model_providers_display_name_key",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_model_provider_tenant_name ON model_providers (tenant_id, display_name)",
        "CREATE INDEX IF NOT EXISTS ix_campaigns_tenant_id ON campaigns (tenant_id)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
