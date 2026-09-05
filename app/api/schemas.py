from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import (
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)


class MerchantSummary(BaseModel):
    id: UUID
    name: str


class MetricSummary(BaseModel):
    merchant_id: UUID
    total_cases: int
    recovered_cases: int
    stopped_cases: int
    escalated_cases: int
    total_amount_at_risk_minor: int
    recovered_amount_minor: int
    recovery_rate_percent: float
    total_actions: int
    avg_time_to_recovery_hours: float


class CaseSummary(BaseModel):
    id: UUID
    merchant_id: UUID
    status: RecoveryCaseStatus
    amount_minor: int
    currency: str
    failure_category: Optional[str]
    created_at: datetime
    updated_at: datetime
    next_action_at: Optional[datetime]


class PaginatedCases(BaseModel):
    items: List[CaseSummary]
    total_count: int
    limit: int
    offset: int


class AuditTimelineEntry(BaseModel):
    id: UUID
    event_type: str
    actor: str
    created_at: datetime
    payload: Dict[str, Any]


class ActionSummary(BaseModel):
    id: UUID
    action_type: RecoveryActionType
    status: RecoveryActionStatus
    attempt_number: int
    provider_reference: Optional[str]
    created_at: datetime
    executed_at: Optional[datetime]


class CaseDetail(BaseModel):
    case: CaseSummary
    actions: List[ActionSummary]
    audit_trail: List[AuditTimelineEntry]