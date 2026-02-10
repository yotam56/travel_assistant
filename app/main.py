import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Travel Assistant service started")
    yield
    logger.info("Travel Assistant service shutting down")


app = FastAPI(title="Travel Assistant", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info("%s %s", request.method, request.url.path)
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    logger.info("%s %s completed %d in %.2fms", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


class CompletionRequest(BaseModel):
    thread_id: str
    input: str


@app.post("/completions")
async def completions(req: CompletionRequest):
    from app.agent import agent

    logger.info("Invoking agent for thread_id=%s", req.thread_id)
    try:
        config = {"configurable": {"thread_id": req.thread_id}}
        result = agent.invoke(
            {"messages": [{"role": "user", "content": req.input}]},
            config=config,
        )
        last_message = result["messages"][-1]
    except Exception:
        logger.exception("Agent invocation failed for thread_id=%s", req.thread_id)
        return JSONResponse(
            status_code=500,
            content={"error": "Something went wrong. Please try again later."},
        )

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "gemini-3-flash-preview",
        "thread_id": req.thread_id,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": last_message.content,
                },
                "finish_reason": "stop",
            }
        ],
    }
