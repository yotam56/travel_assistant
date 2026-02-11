from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.tools.external.weather import get_weather_forecast
from app.tools.internal.placeholder import retrieve_from_db
from app.middleware import retry_model, retry_tool, hallucination_guardrail

model = init_chat_model("google_genai:gemini-3-flash-preview")
checkpointer = InMemorySaver()
tools = [get_weather_forecast, retrieve_from_db]

agent = create_agent(
    model=model,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
    middleware=[retry_model, retry_tool, hallucination_guardrail],
)
