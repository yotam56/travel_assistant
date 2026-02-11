import logging
from datetime import date
from typing import Any

from langchain.agents.middleware.tool_selection import LLMToolSelectorMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse, ContextT, ResponseT
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool

from app.middleware.event_collector import emit_event

logger = logging.getLogger(__name__)


class ToolSelectorMiddleware(LLMToolSelectorMiddleware):
    """Extends LLMToolSelectorMiddleware with two robustness fixes:

    1. **Skip on retries** – When the last user message is a system-injected
       correction (e.g. from the hallucination guardrail), the selection model
       would see that corrective text instead of the real user query, leading
       to confused tool selections.  We detect these messages and pass through
       without filtering.

    2. **Graceful handling of invalid tool names** – If the selection model
       returns tool names that don't exist (structured-output hallucination),
       the base class raises ``ValueError``.  We catch that and fall back to
       keeping all tools available.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Store the raw template so we can inject today's date on each call.
        self._prompt_template = self.system_prompt

    def wrap_model_call(self, request, handler):
        # Inject today's date into the prompt template so the LLM can reason
        # about whether travel dates fall within the 7-day forecast window.
        self.system_prompt = self._prompt_template.format(today=date.today().isoformat())

        available_tool_names = [t.name for t in request.tools if not isinstance(t, dict)]
        logger.info(
            "Tool selector invoked — %d tool(s) available: %s",
            len(available_tool_names), available_tool_names,
        )

        # Gate: skip selection when processing a system-injected corrective
        # message (e.g. hallucination guardrail retry).  These start with
        # "[SYSTEM:" and would confuse the selection model.
        for msg in reversed(request.messages):
            if isinstance(msg, HumanMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if content.startswith("[SYSTEM:"):
                    logger.info(
                        "Tool selector skipped: last user message is a system-injected correction"
                    )
                    emit_event(
                        middleware="tool_selector",
                        status="skipped",
                        message="Skipped — processing hallucination guardrail retry",
                    )
                    return handler(request)
                logger.info("Tool selector evaluating user message: %.120s", content)
                break

        # Capture which tools the base class actually passes to the handler
        # by wrapping the handler to inspect the filtered request.
        selected_names_capture = []

        def _capturing_handler(filtered_request):
            selected_names_capture.extend(
                t.name for t in filtered_request.tools if not isinstance(t, dict)
            )
            return handler(filtered_request)

        try:
            result = super().wrap_model_call(request, _capturing_handler)
        except (ValueError, AssertionError) as exc:
            # Graceful fallback: if the selection model hallucinated invalid
            # tool names or returned an unexpected format, keep all tools.
            logger.warning(
                "Tool selector failed (%s: %s) — falling back to all tools: %s",
                type(exc).__name__, exc, available_tool_names,
            )
            emit_event(
                middleware="tool_selector",
                status="error",
                message="Tool selection failed — keeping all tools available",
                details={"error": str(exc)},
            )
            return handler(request)

        logger.info("Tool selector completed — selected tools: %s", selected_names_capture)
        emit_event(
            middleware="tool_selector",
            status="success",
            message=f"Tool selection completed",
            details={"selected_tools": selected_names_capture},
        )
        return result
