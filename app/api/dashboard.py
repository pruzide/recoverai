from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import (
    ActionSummary,
    AuditTimelineEntry,
    CaseDetail,
    CaseSummary,
    MerchantSummary,
    MetricSummary,
    PaginatedCases,
)
from app.db import get_session_factory
from app.models.enums import RecoveryCaseStatus
from app.services.dashboard_service import (
    get_case_explainability,
    get_merchant_metrics,
    get_paginated_cases,
    list_merchants,
)


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def get_db_session():
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.get("/merchants", response_model=List[MerchantSummary])
def read_merchants(session: Session = Depends(get_db_session)):
    merchants = list_merchants(session)
    return [MerchantSummary(id=m.id, name=m.name) for m in merchants]


@router.get("/metrics/{merchant_id}", response_model=MetricSummary)
def read_metrics(merchant_id: UUID, session: Session = Depends(get_db_session)):
    metrics = get_merchant_metrics(session, merchant_id)
    return MetricSummary(merchant_id=merchant_id, **metrics)


@router.get("/cases", response_model=PaginatedCases)
def read_cases(
    merchant_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[RecoveryCaseStatus] = None,
    session: Session = Depends(get_db_session),
):
    cases, total_count = get_paginated_cases(
        session, merchant_id, limit, offset, status
    )

    items = [
        CaseSummary(
            id=c.id,
            merchant_id=c.merchant_id,
            status=c.status,
            amount_minor=c.amount_minor,
            currency=c.currency,
            failure_category=c.failure_category,
            created_at=c.created_at,
            updated_at=c.updated_at,
            next_action_at=c.next_action_at,
        )
        for c in cases
    ]

    return PaginatedCases(
        items=items,
        total_count=total_count,
        limit=limit,
        offset=offset,
    )


@router.get("/cases/{case_id}", response_model=CaseDetail)
def read_case_detail(
    case_id: UUID,
    merchant_id: UUID,
    session: Session = Depends(get_db_session),
):
    case_obj, actions, audits = get_case_explainability(
        session, case_id, merchant_id
    )

    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    case_summary = CaseSummary(
        id=case_obj.id,
        merchant_id=case_obj.merchant_id,
        status=case_obj.status,
        amount_minor=case_obj.amount_minor,
        currency=case_obj.currency,
        failure_category=case_obj.failure_category,
        created_at=case_obj.created_at,
        updated_at=case_obj.updated_at,
        next_action_at=case_obj.next_action_at,
    )

    action_summaries = [
        ActionSummary(
            id=a.id,
            action_type=a.action_type,
            status=a.status,
            attempt_number=a.attempt_number,
            provider_reference=a.provider_reference,
            created_at=a.created_at,
            executed_at=a.executed_at,
        )
        for a in actions
    ]

    audit_entries = [
        AuditTimelineEntry(
            id=au.id,
            event_type=au.event_type,
            actor=au.actor,
            created_at=au.created_at,
            payload=au.payload,
        )
        for au in audits
    ]

    return CaseDetail(
        case=case_summary,
        actions=action_summaries,
        audit_trail=audit_entries,
    )