import json
import time

from app.config import settings


class LLMError(Exception):
    pass


class LLMTimeoutError(LLMError):
    pass


def call_recovery_llm(state: dict) -> str:
    provider = settings.llm_provider

    if provider == "mock":
        return call_mock_llm(state)

    raise LLMError(f"unsupported LLM provider: {provider}")


def call_mock_llm(state: dict) -> str:
    mode = settings.llm_mock_mode

    if mode == "timeout":
        time.sleep(0.05)
        raise LLMTimeoutError("mock LLM timed out")

    if mode == "malformed":
        return "{this is not valid JSON"

    if mode == "illegal_action":
        return json.dumps(
            {
                "action": "REFUND_CUSTOMER",
                "reason": "This action does not exist in RecoverAI.",
                "confidence": 0.99,
            }
        )

    # normal mode
    action = state.get("engine_candidate_action") or "STOP"

    return json.dumps(
        {
            "action": action,
            "reason": "Mock LLM selected deterministic engine candidate.",
            "confidence": 0.82,
        }
    )