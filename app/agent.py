from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from app.prompts.system_prompt import system_prompt
from app.tools.external.weather import get_weather_forecast
from app.tools.internal.placeholder import retrieve_from_db

model = init_chat_model("google_genai:gemini-3-flash-preview")
checkpointer = InMemorySaver()

tools = [get_weather_forecast, retrieve_from_db]

agent = create_react_agent(
    model=model,
    tools=tools,
    prompt=system_prompt,
    checkpointer=checkpointer,
)
