"""Build a local SQLite snapshot for the OWL export, using the app's own seed chain.

Run from services/platform-api:

    python scripts/seed_export_snapshot.py

The export script reads the resulting file in read-only mode, so docs/本体导出 stays
reproducible without starting the API server or touching the deployed database.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed a snapshot database for the ontology export.")
    parser.add_argument("--out", type=Path, default=API_ROOT / "ontology-export.db")
    args = parser.parse_args(argv)
    os.environ["DATABASE_URL"] = f"sqlite:///{args.out.as_posix()}"
    os.environ.setdefault("INITIAL_ADMIN_USERNAME", "admin")
    os.environ.setdefault("INITIAL_ADMIN_PASSWORD", "Admin@12345")
    os.environ.setdefault("TOKEN_SECRET", "export-snapshot-only-token-secret")
    os.environ.setdefault("ENCRYPTION_KEY", "wrxE4kMm60hSu103lUo7KQdZrF4alZpqaJO1Y0gHg5s=")
    import sys

    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))
    if args.out.exists():
        args.out.unlink()

    from sqlalchemy import func, select

    from app.database import Base, SessionLocal, engine
    from app.db_models import OntologyEntityRecord, OntologyRelationRecord, TenantRecord, UserRecord
    from app.ontology.bootstrap import seed_marketing_lifecycle
    from app.seed import seed_competition_workspace, seed_database, seed_tenant_data

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        headquarters_id = seed_database(session)
        seed_tenant_data(session, headquarters_id)
        user_id = session.scalar(select(UserRecord.id).where(UserRecord.username == os.environ["INITIAL_ADMIN_USERNAME"]))
        competition_id = seed_competition_workspace(session, user_id)
        for tenant_id in {headquarters_id, competition_id}:
            seed_marketing_lifecycle(session, tenant_id)
        summary = {
            "database": args.out.name,
            "tenants": [row for row in session.execute(select(TenantRecord.code, TenantRecord.name))],
            "ontology_entities": session.scalar(select(func.count()).select_from(OntologyEntityRecord)) or 0,
            "ontology_relations": session.scalar(select(func.count()).select_from(OntologyRelationRecord)) or 0,
        }
    print(json.dumps(summary, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
