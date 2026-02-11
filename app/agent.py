from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from app.prompts.system_prompt import SYSTEM_PROMPT
from app.prompts.tool_selector_prompt import TOOL_SELECTOR_PROMPT
from app.tools.external.weather import get_weather_forecast
from app.middleware import retry_model, retry_tool, hallucination_guardrail, ToolSelectorMiddleware

model = init_chat_model("google_genai:gemini-3-flash-preview")
checkpointer = InMemorySaver()
tools = [get_weather_forecast]

tool_selector = ToolSelectorMiddleware(
    system_prompt=TOOL_SELECTOR_PROMPT,
)

agent = create_agent(
    model=model,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
    middleware=[tool_selector, retry_model, retry_tool, hallucination_guardrail],
)
