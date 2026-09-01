from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

CURRENT_SCHEMA_VERSION = "20260831.1"


def record_schema_version(engine: Engine) -> None:
    """Record the application schema version for deployment health checks."""
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_versions (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO schema_versions(version) VALUES (:version) ON CONFLICT(version) DO NOTHING"), {"version": CURRENT_SCHEMA_VERSION})


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
    inspector = inspect(engine)
    campaign_primary_key = inspector.get_pk_constraint("campaigns")
    primary_key_columns = campaign_primary_key.get("constrained_columns") or []
    statements = [
        "ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_campaign_id_fkey",
        "ALTER TABLE campaigns ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE model_providers ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE model_providers DROP CONSTRAINT IF EXISTS model_providers_display_name_key",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_model_provider_tenant_name ON model_providers (tenant_id, display_name)",
        "CREATE INDEX IF NOT EXISTS ix_campaigns_tenant_id ON campaigns (tenant_id)",
    ]
    with engine.begin() as connection:
        if primary_key_columns != ["tenant_id", "id"]:
            primary_key_name = campaign_primary_key.get("name")
            if primary_key_name:
                quoted_name = connection.dialect.identifier_preparer.quote(primary_key_name)
                connection.execute(text(f"ALTER TABLE campaigns DROP CONSTRAINT {quoted_name}"))
            connection.execute(text("ALTER TABLE campaigns ADD CONSTRAINT campaigns_pkey PRIMARY KEY (tenant_id, id)"))
        for statement in statements:
            connection.execute(text(statement))
