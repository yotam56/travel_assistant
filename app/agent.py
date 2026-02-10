from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from app.prompts.system_prompt import system_prompt

model = init_chat_model("google_genai:gemini-3-flash-preview")
checkpointer = InMemorySaver()

agent = create_react_agent(
    model=model,
    tools=[],
    prompt=system_prompt,
    checkpointer=checkpointer,
)
