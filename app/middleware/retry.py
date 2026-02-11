import logging
import random
import time

from langchain.agents.middleware import wrap_model_call, wrap_tool_call

from app.middleware.event_collector import emit_event

logger = logging.getLogger(__name__)

MAX_MODEL_RETRIES = 3
MODEL_INITIAL_DELAY = 1.0
MODEL_BACKOFF_FACTOR = 2.0

MAX_TOOL_RETRIES = 2
TOOL_INITIAL_DELAY = 1.5
TOOL_BACKOFF_FACTOR = 2.0


@wrap_model_call
def retry_model(request, handler):
    """Retry model calls on transient failures with exponential backoff + jitter."""
    logger.info("Model call started")
    for attempt in range(MAX_MODEL_RETRIES):
        try:
            result = handler(request)
            if attempt > 0:
                logger.info("Model call succeeded on attempt %d/%d", attempt + 1, MAX_MODEL_RETRIES)
                emit_event(
                    middleware="retry_model",
                    status="recovered",
                    message=f"Model call succeeded after {attempt + 1} attempts",
                    details={"attempts": attempt + 1},
                )
            else:
                logger.info("Model call succeeded on first attempt")
                emit_event(middleware="retry_model", status="success", message="Model call succeeded on first attempt")
            return result
        except Exception as e:
            if attempt == MAX_MODEL_RETRIES - 1:
                logger.error(
                    "Model call failed after %d attempts. Final error: %s: %s",
                    MAX_MODEL_RETRIES, type(e).__name__, e,
                )
                emit_event(
                    middleware="retry_model",
                    status="failed",
                    message=f"Model call failed after {MAX_MODEL_RETRIES} attempts",
                    details={"error": f"{type(e).__name__}: {e}", "attempts": MAX_MODEL_RETRIES},
                )
                raise
            delay = MODEL_INITIAL_DELAY * (MODEL_BACKOFF_FACTOR ** attempt)
            jitter = random.uniform(0, delay * 0.5)
            sleep_time = delay + jitter
            logger.warning(
                "Model call attempt %d/%d failed (%s: %s) — retrying in %.1fs",
                attempt + 1, MAX_MODEL_RETRIES, type(e).__name__, e, sleep_time,
            )
            emit_event(
                middleware="retry_model",
                status="retrying",
                message=f"Model call attempt {attempt + 1}/{MAX_MODEL_RETRIES} failed — retrying in {sleep_time:.1f}s",
                details={"error": f"{type(e).__name__}: {e}", "attempt": attempt + 1, "delay_s": round(sleep_time, 1)},
            )
            time.sleep(sleep_time)


@wrap_tool_call
def retry_tool(request, handler):
    """Retry tool calls on transient failures with exponential backoff + jitter."""
    tool_name = getattr(request, "name", None) or getattr(request, "tool_name", "unknown")
    logger.info("Tool call started: %s", tool_name)
    for attempt in range(MAX_TOOL_RETRIES):
        try:
            result = handler(request)
            if attempt > 0:
                logger.info("Tool call '%s' succeeded on attempt %d/%d", tool_name, attempt + 1, MAX_TOOL_RETRIES)
                emit_event(
                    middleware="retry_tool",
                    status="recovered",
                    message=f"Tool '{tool_name}' succeeded after {attempt + 1} attempts",
                    details={"tool": tool_name, "attempts": attempt + 1},
                )
            else:
                logger.info("Tool call '%s' succeeded on first attempt", tool_name)
                emit_event(
                    middleware="retry_tool",
                    status="success",
                    message=f"Tool '{tool_name}' succeeded on first attempt",
                    details={"tool": tool_name},
                )
            return result
        except Exception as e:
            if attempt == MAX_TOOL_RETRIES - 1:
                logger.error(
                    "Tool call '%s' failed after %d attempts. Final error: %s: %s",
                    tool_name, MAX_TOOL_RETRIES, type(e).__name__, e,
                )
                emit_event(
                    middleware="retry_tool",
                    status="failed",
                    message=f"Tool '{tool_name}' failed after {MAX_TOOL_RETRIES} attempts",
                    details={"tool": tool_name, "error": f"{type(e).__name__}: {e}", "attempts": MAX_TOOL_RETRIES},
                )
                raise
            delay = TOOL_INITIAL_DELAY * (TOOL_BACKOFF_FACTOR ** attempt)
            jitter = random.uniform(0, delay * 0.5)
            sleep_time = delay + jitter
            logger.warning(
                "Tool call '%s' attempt %d/%d failed (%s: %s) — retrying in %.1fs",
                tool_name, attempt + 1, MAX_TOOL_RETRIES, type(e).__name__, e, sleep_time,
            )
            emit_event(
                middleware="retry_tool",
                status="retrying",
                message=f"Tool '{tool_name}' attempt {attempt + 1}/{MAX_TOOL_RETRIES} failed — retrying in {sleep_time:.1f}s",
                details={"tool": tool_name, "error": f"{type(e).__name__}: {e}", "attempt": attempt + 1, "delay_s": round(sleep_time, 1)},
            )
            time.sleep(sleep_time)
