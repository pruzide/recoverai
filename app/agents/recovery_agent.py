import json
from functools import lru_cache
from typing import Optional, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.agents.llm import LLMError, call_recovery_llm
from app.agents.schemas import (
    AgentDecision,
    AgentDecisionOutput,
    AgentDecisionRequest,
)
from app.config import settings
from app.models.enums import RecoveryActionType


logger = structlog.get_logger()


class RecoveryAgentState(TypedDict, total=False):
    merchant_id: str
    recovery_case_id: str

    amount_minor: int
    currency: str

    failure_category: Optional[str]

    engine_candidate_action: str
    deterministic_final_action: str

    total_action_count: int
    reminder_count: int
    active_payment_link_count: int

    selected_action: Optional[str]
    decision_reason: Optional[str]
    decision_source: Optional[str]
    confidence: Optional[float]

    fallback_used: bool
    error: Optional[str]


def _fallback_state(
    state: RecoveryAgentState,
    reason: str,
    error: Optional[str] = None,
) -> dict:
    return {
        "selected_action": state.get("deterministic_final_action"),
        "decision_reason": reason,
        "decision_source": "deterministic_fallback",
        "confidence": None,
        "fallback_used": True,
        "error": error,
    }


def parse_llm_output(raw: str) -> AgentDecisionOutput:
    data = json.loads(raw)

    if isinstance(data, dict):
        reason = data.get("reason")
        if isinstance(reason, str) and len(reason) > 512:
            data["reason"] = reason[:512]

    return AgentDecisionOutput.model_validate(data)


def decide_node(state: RecoveryAgentState) -> dict:
    if not settings.llm_enabled:
        return _fallback_state(state, "llm_disabled")

    try:
        raw_output = call_recovery_llm(state)
        parsed = parse_llm_output(raw_output)

        return {
            "selected_action": parsed.action.value,
            "decision_reason": parsed.reason,
            "decision_source": "llm",
            "confidence": parsed.confidence,
            "fallback_used": False,
            "error": None,
        }

    except (LLMError, ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.warning(
            "agent_llm_failed",
            error=str(exc),
        )
        return _fallback_state(state, "llm_failed", str(exc))

    except Exception as exc:
        logger.exception("agent_llm_unexpected_failure")
        return _fallback_state(state, "llm_unexpected_failure", str(exc))


def validate_node(state: RecoveryAgentState) -> dict:
    selected_raw = state.get("selected_action")

    try:
        selected = RecoveryActionType(selected_raw)
    except ValueError:
        return _fallback_state(
            state,
            "invalid_agent_action",
            f"invalid action: {selected_raw}",
        )

    return {
        "selected_action": selected.value,
    }


@lru_cache
def get_recovery_agent_graph():
    graph = StateGraph(RecoveryAgentState)

    graph.add_node("decide", decide_node)
    graph.add_node("validate", validate_node)

    graph.add_edge(START, "decide")
    graph.add_edge("decide", "validate")
    graph.add_edge("validate", END)

    return graph.compile()


def run_recovery_agent(request: AgentDecisionRequest) -> AgentDecision:
    fallback = AgentDecision(
        selected_action=request.deterministic_final_action,
        reason="agent_unavailable",
        source="deterministic_fallback",
        confidence=None,
    )

    try:
        graph = get_recovery_agent_graph()

        state: RecoveryAgentState = {
            "merchant_id": request.merchant_id,
            "recovery_case_id": request.recovery_case_id,
            "amount_minor": request.amount_minor,
            "currency": request.currency,
            "failure_category": request.failure_category,
            "engine_candidate_action": request.engine_candidate_action.value,
            "deterministic_final_action": request.deterministic_final_action.value,
            "total_action_count": request.total_action_count,
            "reminder_count": request.reminder_count,
            "active_payment_link_count": request.active_payment_link_count,
        }

        result = graph.invoke(state)

        selected_raw = result.get("selected_action")
        reason = result.get("decision_reason") or "agent_decision"
        source = result.get("decision_source") or "deterministic_fallback"
        confidence = result.get("confidence")

        try:
            selected_action = RecoveryActionType(selected_raw)
        except ValueError:
            return fallback

        return AgentDecision(
            selected_action=selected_action,
            reason=reason,
            source=source,
            confidence=confidence,
        )

    except Exception as exc:
        logger.warning(
            "recovery_agent_graph_failed",
            error=str(exc),
        )
        return fallback