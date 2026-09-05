from typing import Tuple
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, RecoveryAction, RecoveryCase
from app.models.enums import RecoveryCaseStatus


def get_merchant_metrics(session: Session, merchant_id: UUID) -> dict:
    stmt = select(
        func.count(RecoveryCase.id).label("total_cases"),
        func.sum(
            case(
                (RecoveryCase.status == RecoveryCaseStatus.RECOVERED.value, 1),
                else_=0,
            )
        ).label("recovered_cases"),
        func.sum(
            case(
                (RecoveryCase.status == RecoveryCaseStatus.STOPPED.value, 1),
                else_=0,
            )
        ).label("stopped_cases"),
        func.sum(
            case(
                (RecoveryCase.status == RecoveryCaseStatus.ESCALATED.value, 1),
                else_=0,
            )
        ).label("escalated_cases"),
        func.sum(RecoveryCase.amount_minor).label("total_amount_at_risk_minor"),
        func.sum(
            case(
                (
                    RecoveryCase.status == RecoveryCaseStatus.RECOVERED.value,
                    RecoveryCase.amount_minor,
                ),
                else_=0,
            )
        ).label("recovered_amount_minor"),
    ).where(RecoveryCase.merchant_id == merchant_id)

    result = session.execute(stmt).one()

    total_cases = result.total_cases or 0
    recovered_cases = result.recovered_cases or 0
    total_at_risk = result.total_amount_at_risk_minor or 0
    recovered_amount = result.recovered_amount_minor or 0

    recovery_rate = (recovered_cases / total_cases * 100.0) if total_cases > 0 else 0.0

    return {
        "total_cases": total_cases,
        "recovered_cases": recovered_cases,
        "stopped_cases": result.stopped_cases or 0,
        "escalated_cases": result.escalated_cases or 0,
        "total_amount_at_risk_minor": total_at_risk,
        "recovered_amount_minor": recovered_amount,
        "recovery_rate_percent": round(recovery_rate, 2),
    }


def get_paginated_cases(
    session: Session,
    merchant_id: UUID,
    limit: int,
    offset: int,
    status_filter: RecoveryCaseStatus | None = None,
) -> Tuple[list[RecoveryCase], int]:
    base_query = select(RecoveryCase).where(RecoveryCase.merchant_id == merchant_id)

    if status_filter:
        base_query = base_query.where(RecoveryCase.status == status_filter.value)

    count_stmt = select(func.count()).select_from(base_query.subquery())
    total_count = session.execute(count_stmt).scalar_one()

    data_stmt = (
        base_query.order_by(RecoveryCase.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    cases = session.execute(data_stmt).scalars().all()

    return cases, total_count


def get_case_explainability(
    session: Session,
    case_id: UUID,
    merchant_id: UUID,
) -> Tuple[RecoveryCase | None, list[RecoveryAction], list[AuditEvent]]:
    case_obj = session.execute(
        select(RecoveryCase).where(
            RecoveryCase.id == case_id,
            RecoveryCase.merchant_id == merchant_id,
        )
    ).scalar_one_or_none()

    if not case_obj:
        return None, [], []

    actions = session.execute(
        select(RecoveryAction)
        .where(RecoveryAction.recovery_case_id == case_id)
        .order_by(RecoveryAction.created_at.asc())
    ).scalars().all()

    audits = session.execute(
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "recovery_case",
            AuditEvent.entity_id == str(case_id),
        )
        .order_by(AuditEvent.created_at.asc())
    ).scalars().all()

    return case_obj, actions, audits