import logging
from typing import Any, Annotated

from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain.agents.middleware.types import AgentState
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from app.middleware.event_collector import emit_event
from app.prompts.grounding_check_prompt import GROUNDING_CHECK_PROMPT

logger = logging.getLogger(__name__)

MAX_HALLUCINATION_RETRIES = 1


def _extract_text(content) -> str:
    """Extract plain text from a content field that may be a string or a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return str(content)


class HallucinationGuardrailState(AgentState):
    """Extended state to track hallucination retry count."""
    hallucination_retries: Annotated[int, 0]


class HallucinationGuardrailMiddleware(AgentMiddleware):
    """Post-model middleware that verifies grounding of final responses.

    Only activates on final text responses (no tool calls). When the response
    fails grounding verification, it injects a corrective instruction and
    re-routes to the model for re-generation.
    """

    state_schema = HallucinationGuardrailState
    tools = []

    def __init__(self, verification_model=None):
        super().__init__()
        self._verification_model = verification_model

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: HallucinationGuardrailState, runtime: Runtime) -> dict[str, Any] | None:
        messages = state["messages"]
        last_message = messages[-1]

        # Gate 1: Only verify final text responses (no tool calls)
        if not isinstance(last_message, AIMessage):
            logger.debug("Hallucination guardrail skipped: last message is not AIMessage (type=%s)", type(last_message).__name__)
            return None
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            tool_names = [tc["name"] for tc in last_message.tool_calls]
            logger.debug("Hallucination guardrail skipped: model is calling tools %s", tool_names)
            return None

        response_text = _extract_text(last_message.content)
        if not response_text or not response_text.strip():
            logger.debug("Hallucination guardrail skipped: empty response")
            return None

        # Gate 2: Check retry budget
        retries_so_far = state.get("hallucination_retries", 0)
        if retries_so_far >= MAX_HALLUCINATION_RETRIES:
            logger.warning(
                "Hallucination retry budget exhausted (%d/%d). Accepting response as-is.",
                retries_so_far, MAX_HALLUCINATION_RETRIES,
            )
            return None

        logger.info(
            "Hallucination guardrail running grounding check (attempt %d/%d, response length=%d chars)",
            retries_so_far + 1, MAX_HALLUCINATION_RETRIES + 1, len(response_text),
        )

        # Gather context for grounding check
        tool_observations = self._extract_tool_observations(messages)
        conversation_summary = self._summarize_conversation(messages)
        logger.debug(
            "Grounding check context — tool_observations=%d chars, conversation_summary=%d chars",
            len(tool_observations), len(conversation_summary),
        )

        check_prompt = GROUNDING_CHECK_PROMPT.format(
            conversation_summary=conversation_summary,
            tool_observations=tool_observations if tool_observations else "(No tools were called)",
            response_to_check=response_text,
        )

        # Run grounding check
        try:
            verification_model = self._verification_model or init_chat_model(
                "google_genai:gemini-3-flash-preview"
            )
            logger.debug("Invoking verification model for grounding check")
            result = verification_model.invoke([HumanMessage(content=check_prompt)])
            verdict = _extract_text(result.content).strip()
            logger.info("Grounding check raw verdict: %r", verdict)
        except Exception:
            logger.exception("Grounding check model invocation failed — accepting response as-is")
            emit_event(
                middleware="hallucination_guardrail",
                status="error",
                message="Grounding check model invocation failed — accepting response as-is",
            )
            return None

        # Parse verdict
        if verdict.startswith("PASS"):
            logger.info("Grounding check PASSED — response is well-grounded")
            emit_event(
                middleware="hallucination_guardrail",
                status="passed",
                message="Grounding check PASSED — response is well-grounded",
                details={"verdict": verdict},
            )
            return None

        if verdict.startswith("FAIL"):
            failure_reason = verdict[len("FAIL:"):].strip() if ":" in verdict else "ungrounded content detected"
            logger.warning(
                "Grounding check FAILED (reason: %s) — injecting corrective instructions and re-routing to model",
                failure_reason,
            )
            emit_event(
                middleware="hallucination_guardrail",
                status="failed",
                message=f"Grounding check FAILED — re-routing to model for correction",
                details={"verdict": verdict, "reason": failure_reason, "retry": retries_so_far + 1},
            )

            corrective_msg = HumanMessage(content=(
                f"[SYSTEM: Your previous response did not pass a factual grounding check. "
                f"Issue: {failure_reason}. "
                f"Please regenerate your response. Follow these rules strictly: "
                f"(1) Only cite weather data that was returned by the weather tool. "
                f"(2) Do not invent specific prices, hours, or real-time details. "
                f"(3) If a tool returned an error, acknowledge you could not retrieve that data. "
                f"(4) Hedge or qualify any specific claims you are not certain about.]"
            ))

            logger.info("Re-routing to model node for corrected response (retry %d/%d)", retries_so_far + 1, MAX_HALLUCINATION_RETRIES)
            return {
                "messages": [corrective_msg],
                "hallucination_retries": retries_so_far + 1,
                "jump_to": "model",
            }

        logger.warning("Unexpected grounding check verdict format: %r — accepting response as-is", verdict)
        emit_event(
            middleware="hallucination_guardrail",
            status="error",
            message=f"Unexpected grounding check verdict format — accepting response as-is",
            details={"verdict": verdict},
        )
        return None

    @staticmethod
    def _extract_tool_observations(messages) -> str:
        """Extract all ToolMessage contents from the conversation."""
        observations = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                tool_name = getattr(msg, "name", "unknown_tool")
                observations.append(f"[{tool_name}]: {_extract_text(msg.content)}")
        return "\n".join(observations)

    @staticmethod
    def _summarize_conversation(messages) -> str:
        """Build a brief summary of user requests for context."""
        parts = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                content = _extract_text(msg.content)
                if content.startswith("[SYSTEM:"):
                    continue
                parts.append(f"User: {content}")
            elif isinstance(msg, AIMessage):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tool_names = [tc["name"] for tc in msg.tool_calls]
                    parts.append(f"Assistant: [called tools: {', '.join(tool_names)}]")
                else:
                    text = _extract_text(msg.content)
                    snippet = text[:100] + "..." if len(text) > 100 else text
                    parts.append(f"Assistant: {snippet}")
        return "\n".join(parts[-10:])


hallucination_guardrail = HallucinationGuardrailMiddleware()
