from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.auth import TenantContext
from app.data_pipeline import DataProcessingAgent, PipelineCancelled
from app.database import SessionLocal
from app.db_models import DataPipelineJobRecord, TenantMembershipRecord
from app.main import _fail_pipeline_job


@pytest.fixture
def job_env():
    """Create a disposable pipeline job and yield (job_id, context)."""
    with SessionLocal() as session:
        membership = session.scalars(select(TenantMembershipRecord).limit(1)).one()
        context = TenantContext(
            user_id=membership.user_id,
            username="cancellation-probe",
            display_name="cancellation-probe",
            tenant_id=membership.tenant_id,
            tenant_code="probe",
            tenant_name="probe",
            role=membership.role,
        )
        record = DataPipelineJobRecord(
            id=f"DP-{uuid4().hex[:12].upper()}",
            tenant_id=membership.tenant_id,
            created_by=membership.user_id,
            file_name="cancel-probe.json",
            file_format="json",
            source_type="file",
            status="running",
            current_stage="queued",
        )
        session.add(record)
        session.commit()
        job_id = record.id
    yield job_id, context
    with SessionLocal() as cleanup:
        row = cleanup.get(DataPipelineJobRecord, job_id)
        if row is not None:
            cleanup.delete(row)
            cleanup.commit()


def cancel_through_api(job_id: str) -> None:
    """Flip the row on a separate session, like the cancel endpoint does."""
    with SessionLocal() as outside:
        target = outside.get(DataPipelineJobRecord, job_id)
        target.status = "cancelled"
        target.current_stage = "cancelled"
        outside.commit()


def test_worker_stops_when_the_job_is_cancelled(job_env):
    """Cancellation is only honoured if the worker re-reads the committed row."""
    job_id, context = job_env
    cancel_through_api(job_id)

    with SessionLocal() as session:
        agent = DataProcessingAgent(session, context, session.get(DataPipelineJobRecord, job_id))
        with pytest.raises(PipelineCancelled):
            agent._ensure_active()
        with pytest.raises(PipelineCancelled):
            agent._stage("normalizing", "Normalize objects", "running")

    with SessionLocal() as check:
        assert check.get(DataPipelineJobRecord, job_id).status == "cancelled"


def test_failure_handler_keeps_cancellation(job_env):
    job_id, context = job_env
    cancel_through_api(job_id)

    with SessionLocal() as session:
        _fail_pipeline_job(session, job_id, RuntimeError("boom"))

    with SessionLocal() as check:
        assert check.get(DataPipelineJobRecord, job_id).status == "cancelled"


def test_failure_handler_records_real_failures(job_env):
    job_id, _context = job_env

    with SessionLocal() as session:
        _fail_pipeline_job(session, job_id, RuntimeError("真实故障"))

    with SessionLocal() as check:
        record = check.get(DataPipelineJobRecord, job_id)
        assert record.status == "failed"
        assert "真实故障" in (record.error_message or "")
