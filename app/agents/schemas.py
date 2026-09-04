from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.enums import RecoveryActionType


class AgentDecisionRequest(BaseModel):
    merchant_id: str
    recovery_case_id: str

    amount_minor: int
    currency: str

    failure_category: Optional[str] = None

    engine_candidate_action: RecoveryActionType
    deterministic_final_action: RecoveryActionType

    total_action_count: int
    reminder_count: int
    active_payment_link_count: int


class AgentDecisionOutput(BaseModel):
    action: RecoveryActionType
    reason: str = Field(max_length=512)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class AgentDecision(BaseModel):
    selected_action: RecoveryActionType
    reason: str
    source: Literal["llm", "deterministic_fallback"] = "deterministic_fallback"
    confidence: Optional[float] = None